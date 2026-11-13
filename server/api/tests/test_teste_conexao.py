"""Estado em memória do "Testar conexão" (services/teste_conexao.py): entrega, progresso, prazos e isolamento."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import teste_conexao as tc  # noqa: E402


def _novo(maquina="m1", eq="e1"):
    tc._tarefas.clear()
    return tc.criar(maquina, eq, {"tipo": "NVR", "name": "N", "password": "x"})


def test_fluxo_completo():
    est = _novo()
    assert est["concluido"] is False and est["etapas"][0]["estado"] == "andamento"
    assert tc.proxima_para("outra") is None
    task = tc.proxima_para("m1")
    assert task["task_id"] == est["task_id"] and task["equipamento_id"] == "e1"
    assert tc.proxima_para("m1") is None  # entregue uma vez só

    prog = {"task_id": est["task_id"], "etapas": [{"id": "rede", "rotulo": "IP", "estado": "andamento"}]}
    assert tc.registrar_progresso("m1", prog) is None
    assert tc.estado("m1", est["task_id"])["etapas"][0]["estado"] == "ok"

    prog.update(concluido=True, ok=True, mensagem="OK", etapas=[{"id": "rede", "rotulo": "IP", "estado": "ok"}])
    assert tc.registrar_progresso("outra", prog) is None  # outra máquina não mexe
    final = tc.registrar_progresso("m1", prog)
    assert final["ok"] is True and final["concluido"] is True
    assert tc.registrar_progresso("m1", prog) is None  # já encerrado
    assert tc.estado("outra", est["task_id"]) is None


def test_repetido_devolve_o_mesmo():
    est = _novo()
    assert tc.criar("m1", "e1", {})["task_id"] == est["task_id"]


def test_prazo_de_entrega_e_de_resposta():
    est = _novo()
    tc._tarefas[est["task_id"]]["criado_em"] -= tc.ESPERA_ENTREGA_S + 1
    e = tc.estado("m1", est["task_id"])
    assert e["concluido"] and e["ok"] is False and "offline" in e["mensagem"]

    est = _novo()
    tc.proxima_para("m1")
    tc._tarefas[est["task_id"]]["enviado_em"] -= tc.ESPERA_RESPOSTA_S + 1
    e = tc.estado("m1", est["task_id"])
    assert e["concluido"] and "não respondeu" in e["mensagem"]


def test_agente_antigo_recusa_sem_entregar():
    est = _novo()
    tc.recusar_pendentes("m1")
    e = tc.estado("m1", est["task_id"])
    assert e["concluido"] and tc.VERSAO_MINIMA in e["mensagem"]
    assert tc.proxima_para("m1") is None
