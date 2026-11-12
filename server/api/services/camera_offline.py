"""
Serviço para cálculo e persistência do tempo em que câmeras permanecem offline.
Funções puras sem I/O e sem acesso a banco de dados.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


def formatar_offline_ha(segundos: int, aprox: bool = False) -> str:
    """Formata o tempo em que a câmera está offline para exibição legível (ex.: 'há 3h', 'há 5 dias')."""
    s = max(0, int(segundos))
    if s < 60:
        texto = "há menos de 1 min"
    elif s < 3600:
        texto = f"há {s // 60} min"
    elif s < 86400:
        texto = f"há {s // 3600}h"
    else:
        d = s // 86400
        texto = "há 1 dia" if d == 1 else f"há {d} dias"

    if aprox and texto.startswith("há "):
        texto = "há mais de " + texto[3:]

    return texto


def _canal_chave(valor: Any) -> Any:
    """Normaliza o identificador de canal para int ou string."""
    if valor is None:
        return None
    try:
        return int(valor)
    except (ValueError, TypeError):
        pass
    try:
        # Trata GUID Motorola "{0000000N-0000-...}"
        limpo = str(valor).strip("{}")
        primeira_parte = limpo.split("-")[0]
        return int(primeira_parte, 16)
    except (ValueError, TypeError, IndexError, AttributeError):
        pass
    return str(valor)


def _chave(st: dict, por_nome: bool) -> Any:
    """Gera chave de pareamento para uma câmera (nome em minúsculas ou canal normalizado)."""
    if not isinstance(st, dict):
        return None
    if por_nome:
        nome = (st.get("nome") or "").strip().lower()
        return nome if nome else None
    return _canal_chave(st.get("canal"))


def _comunicacao(st: dict) -> Optional[str]:
    """Extrai o status de comunicação da câmera ('ONLINE', 'OFFLINE' ou None)."""
    if not isinstance(st, dict):
        return None
    com = st.get("status_comunicacao")
    if com is not None:
        return str(com)
    online = st.get("online")
    if online is True:
        return "ONLINE"
    if online is False:
        return "OFFLINE"
    return None


def aplicar_presenca(
    anterior: Optional[List[Any]],
    novo: Optional[List[Any]],
    agora: datetime,
    por_nome: bool = False,
) -> List[Any]:
    """Preserva e atualiza o histórico de quando a câmera ficou offline no relatório de backup."""
    if novo is None:
        return []

    mapa_antigos: Dict[Any, dict] = {}
    for item in (anterior or []):
        if isinstance(item, dict):
            k = _chave(item, por_nome)
            if k is not None:
                mapa_antigos[k] = item

    saida: List[Any] = []
    for st in novo:
        if not isinstance(st, dict):
            saida.append(st)
            continue

        copia = dict(st)
        com = _comunicacao(copia)
        k = _chave(copia, por_nome)
        ant = mapa_antigos.get(k) if k is not None else None

        if com == "ONLINE":
            copia.pop("offline_desde", None)
            copia.pop("offline_desde_aprox", None)
        elif com == "OFFLINE":
            ant_offline_desde = ant.get("offline_desde") if ant else None
            if ant and isinstance(ant_offline_desde, str) and ant_offline_desde.strip():
                copia["offline_desde"] = ant_offline_desde
                if ant.get("offline_desde_aprox"):
                    copia["offline_desde_aprox"] = True
                else:
                    copia.pop("offline_desde_aprox", None)
            elif ant is not None and _comunicacao(ant) == "OFFLINE":
                # Já estava offline antes desta funcionalidade
                copia["offline_desde"] = (agora - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
                copia["offline_desde_aprox"] = True
            else:
                # Câmera nova ou que estava ONLINE/desconhecida
                copia["offline_desde"] = agora.strftime("%Y-%m-%dT%H:%M:%S")
                copia.pop("offline_desde_aprox", None)
        else:
            # Estado incerto (None, "ERRO_COMUNICACAO", "DESCONHECIDO"...): não zera contagem
            ant_offline_desde = ant.get("offline_desde") if ant else None
            if ant and isinstance(ant_offline_desde, str) and ant_offline_desde.strip():
                copia["offline_desde"] = ant_offline_desde
                if ant.get("offline_desde_aprox"):
                    copia["offline_desde_aprox"] = True
                else:
                    copia.pop("offline_desde_aprox", None)

        saida.append(copia)

    return saida


def atualizar_presenca(
    anterior: Optional[List[Any]],
    leituras: Optional[List[Any]],
    agora: datetime,
    por_nome: bool = False,
) -> Tuple[List[Any], int]:
    """Atualiza a presença online/offline das câmeras a partir das leituras periódicas do agente."""
    mapa_leituras: Dict[Any, dict] = {}
    for l in (leituras or []):
        if isinstance(l, dict) and isinstance(l.get("online"), bool):
            k = _chave(l, por_nome)
            if k is not None:
                mapa_leituras[k] = l

    nova_lista: List[Any] = []
    qtd_atualizadas = 0

    for item in (anterior or []):
        if not isinstance(item, dict):
            nova_lista.append(item)
            continue

        entrada = dict(item)
        k = _chave(entrada, por_nome)
        if k is not None and k in mapa_leituras:
            leitura = mapa_leituras[k]
            is_online = leitura["online"]
            entrada["status_comunicacao"] = "ONLINE" if is_online else "OFFLINE"
            entrada["online"] = is_online

            if is_online:
                entrada.pop("offline_desde", None)
                entrada.pop("offline_desde_aprox", None)
            else:
                ant_offline_desde = item.get("offline_desde")
                if isinstance(ant_offline_desde, str) and ant_offline_desde.strip():
                    entrada["offline_desde"] = ant_offline_desde
                    if item.get("offline_desde_aprox"):
                        entrada["offline_desde_aprox"] = True
                    else:
                        entrada.pop("offline_desde_aprox", None)
                elif _comunicacao(item) == "OFFLINE":
                    # Já estava offline antes, mas sem offline_desde
                    entrada["offline_desde"] = (agora - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
                    entrada["offline_desde_aprox"] = True
                else:
                    # Estava online ou desconhecido
                    entrada["offline_desde"] = agora.strftime("%Y-%m-%dT%H:%M:%S")
                    entrada.pop("offline_desde_aprox", None)

            qtd_atualizadas += 1

        nova_lista.append(entrada)

    return nova_lista, qtd_atualizadas


def segundos_offline(st: dict, agora: datetime) -> Tuple[Optional[int], bool]:
    """Calcula quantos segundos a câmera está offline e se a contagem é aproximada."""
    if not isinstance(st, dict):
        return None, False

    offline_desde = st.get("offline_desde")
    if not offline_desde or not isinstance(offline_desde, str):
        return None, False

    try:
        dt = datetime.strptime(offline_desde, "%Y-%m-%dT%H:%M:%S")
    except (ValueError, TypeError):
        return None, False

    if _comunicacao(st) != "ONLINE":
        seg = max(0, int((agora - dt).total_seconds()))
        aprox = bool(st.get("offline_desde_aprox"))
        return seg, aprox

    return None, False
