"""Estado em memória do "Testar conexão" de equipamentos (painel -> servidor -> agente -> servidor -> painel).

Fluxo: o painel cria o teste (`criar`); o ping do agente leva o pedido (`proxima_para`); o agente (>= 1.1.44)
manda o estado inteiro a cada etapa (`registrar_progresso`); o painel consulta (`estado`) a cada segundo.

LIMITAÇÃO (a mesma do `pending_rtsp_tasks` em routers/agent.py): vive na memória do processo, então pede
1 worker uvicorn. Com vários workers o ping e a consulta poderiam cair em processos diferentes.
"""
import threading
import time
import uuid
from typing import Optional

ESPERA_ENTREGA_S = 45     # o agente não buscou o pedido: máquina offline ou sem comunicação
ESPERA_RESPOSTA_S = 25    # entregue e sem nenhuma resposta (agente reiniciando ou thread do teste travada)
LIMITE_TESTE_S = 300      # teste que não termina (a leitura das ONUs de várias OLTs pode levar alguns minutos)
GUARDA_S = 600            # quanto tempo o resultado fica disponível para o painel consultar

VERSAO_MINIMA = "1.1.44"

_lock = threading.Lock()
_tarefas: dict = {}


def _etapa_agente(estado: str, detalhe: Optional[str] = None) -> dict:
    rotulo = "Agente da máquina recebeu o pedido" if estado == "ok" else "Aguardando o agente da máquina"
    return {"id": "agente", "rotulo": rotulo, "estado": estado, "detalhe": detalhe}


def _limpar(agora: float) -> None:
    for task_id in [t for t, e in _tarefas.items() if agora - e["criado_em"] > GUARDA_S]:
        _tarefas.pop(task_id, None)


def _concluir_erro(entry: dict, mensagem: str, agora: float) -> None:
    """Encerra por tempo: a etapa em andamento (ou a do agente) vira erro."""
    marcada = False
    for etapa in entry["etapas"]:
        if etapa["estado"] == "andamento":
            etapa["estado"] = "erro"
            etapa["detalhe"] = etapa.get("detalhe") or "Tempo esgotado"
            marcada = True
    if not marcada and entry["etapas"]:
        entry["etapas"][0]["estado"] = "erro"
    entry.update(concluido=True, ok=False, mensagem=mensagem, terminado_em=agora)


def _aplicar_prazos(entry: dict, agora: float) -> None:
    if entry["concluido"]:
        return
    if entry["enviado_em"] is None:
        if agora - entry["criado_em"] > ESPERA_ENTREGA_S:
            _concluir_erro(entry, f"O agente não buscou o pedido em {ESPERA_ENTREGA_S} s: a máquina está offline "
                                  "ou sem comunicação com o servidor.", agora)
    elif not entry["respondeu"]:
        if agora - entry["enviado_em"] > ESPERA_RESPOSTA_S:
            _concluir_erro(entry, "O agente recebeu o pedido, mas não respondeu (pode estar reiniciando). "
                                  "Tente de novo em instantes.", agora)
    elif agora - entry["criado_em"] > LIMITE_TESTE_S:
        _concluir_erro(entry, f"O teste passou de {LIMITE_TESTE_S // 60} minutos sem terminar.", agora)


def _publico(entry: dict, agora: float) -> dict:
    fim = entry.get("terminado_em") or agora
    return {
        "task_id": entry["task_id"],
        "equipamento_id": entry["equipamento_id"],
        "etapas": [dict(e) for e in entry["etapas"]],
        "concluido": entry["concluido"],
        "ok": entry["ok"],
        "mensagem": entry["mensagem"],
        "segundos": int(fim - entry["criado_em"]),
    }


def criar(machine_id: str, equipamento_id: str, task: dict) -> dict:
    """Novo teste (ou o que já está em andamento para o mesmo equipamento). `task` é o equipamento como o agente
    o recebe em /agent/config (com a senha aberta): só sai daqui pelo ping do próprio agente."""
    agora = time.monotonic()
    with _lock:
        _limpar(agora)
        for entry in _tarefas.values():
            _aplicar_prazos(entry, agora)
            if entry["equipamento_id"] == equipamento_id and not entry["concluido"]:
                return _publico(entry, agora)
        task_id = uuid.uuid4().hex
        _tarefas[task_id] = {
            "task_id": task_id,
            "machine_id": machine_id,
            "equipamento_id": equipamento_id,
            "task": {**task, "task_id": task_id, "equipamento_id": equipamento_id},
            "criado_em": agora,
            "enviado_em": None,
            "respondeu": False,
            "etapas": [_etapa_agente("andamento")],
            "concluido": False,
            "ok": None,
            "mensagem": None,
        }
        return _publico(_tarefas[task_id], agora)


def falha_imediata(equipamento_id: str, mensagem: str) -> dict:
    """Resposta de um teste que nem começa (ex.: máquina offline), sem guardar estado."""
    return {
        "task_id": None, "equipamento_id": equipamento_id, "etapas": [_etapa_agente("erro", mensagem)],
        "concluido": True, "ok": False, "mensagem": mensagem, "segundos": 0,
    }


def proxima_para(machine_id: str) -> Optional[dict]:
    """Pedido ainda não entregue para esta máquina (marca como entregue)."""
    agora = time.monotonic()
    with _lock:
        for entry in _tarefas.values():
            _aplicar_prazos(entry, agora)
            if entry["machine_id"] == machine_id and entry["enviado_em"] is None and not entry["concluido"]:
                entry["enviado_em"] = agora
                return entry["task"]
    return None


MSG_VERSAO = (f"O agente desta máquina é anterior à {VERSAO_MINIMA} e ainda não sabe testar a conexão. "
              "A atualização chega sozinha em até 1 h depois que a versão for liberada no painel.")


def recusar_pendentes(machine_id: str) -> None:
    """Agente sem suporte (não declarou "teste_conexao" no ping): encerra os pedidos dele sem entregar."""
    agora = time.monotonic()
    with _lock:
        for entry in _tarefas.values():
            if entry["machine_id"] == machine_id and entry["enviado_em"] is None and not entry["concluido"]:
                _concluir_erro(entry, MSG_VERSAO, agora)


def registrar_progresso(machine_id: str, progresso: dict) -> Optional[dict]:
    """Aplica o estado enviado pelo agente. Devolve o estado público quando o teste acabou de terminar (para gravar
    no equipamento); None nos demais casos (em andamento, desconhecido, de outra máquina ou já encerrado)."""
    agora = time.monotonic()
    with _lock:
        entry = _tarefas.get(progresso.get("task_id") or "")
        if entry is None or entry["machine_id"] != machine_id or entry["concluido"]:
            return None
        entry["respondeu"] = True
        etapas = [e for e in (progresso.get("etapas") or []) if e.get("id") != "agente"]
        entry["etapas"] = [_etapa_agente("ok")] + etapas
        entry["mensagem"] = progresso.get("mensagem")
        if progresso.get("concluido"):
            entry.update(concluido=True, ok=bool(progresso.get("ok")), terminado_em=agora)
            return _publico(entry, agora)
    return None


def estado(machine_id: str, task_id: str) -> Optional[dict]:
    agora = time.monotonic()
    with _lock:
        entry = _tarefas.get(task_id)
        if entry is None or entry["machine_id"] != machine_id:
            return None
        _aplicar_prazos(entry, agora)
        return _publico(entry, agora)
