"""
Captura automática da imagem da noite das câmeras de equipamentos DIGIFORT/DEFENSE.
Essas câmeras são diretas (sem playback de NVR): a imagem é um quadro ao vivo por RTSP, então só é "da noite"
se for tirada no escuro. A rotina roda só na janela noturna (19h30 às 4h), uma vez por noite e por câmera, e
repete as que falharam. Não depende de a câmera gravar por movimento: o stream ao vivo existe sempre.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, time as hora, timedelta
from typing import Dict, Optional

TIPOS_VMS = ("DIGIFORT", "DEFENSE")
INICIO_NOITE = hora(19, 30)
FIM_NOITE = hora(4, 0)
INTERVALO_CICLO_S = 600
REPETIR_FALHA_S = 30 * 60

_noite_atual: Optional[date] = None
_capturadas: set = set()
_ultima_tentativa: Dict[tuple, float] = {}


def na_janela_noite(agora: datetime) -> bool:
    return agora.time() >= INICIO_NOITE or agora.time() < FIM_NOITE


def _id_da_noite(agora: datetime) -> date:
    """A noite é identificada pelo dia em que começou (de madrugada, o dia anterior)."""
    return agora.date() if agora.time() >= INICIO_NOITE else agora.date() - timedelta(days=1)


def capturar_noite_vms(equipamentos: list, conf: dict, agora: Optional[datetime] = None) -> int:
    """Captura as câmeras (com IP na Galeria) que ainda não têm imagem desta noite. Retorna quantas deram certo."""
    global _noite_atual
    from src.camera.rtsp_client import capturar_imagens_noite_vms

    agora = agora or datetime.now()
    if not na_janela_noite(agora):
        return 0
    if _noite_atual != _id_da_noite(agora):
        _noite_atual = _id_da_noite(agora)
        _capturadas.clear()
        _ultima_tentativa.clear()

    ok = 0
    for eq in equipamentos:
        if (eq.get("tipo") or "").upper() not in TIPOS_VMS or not eq.get("active", True):
            continue
        nome_eq = eq.get("name", "")
        pendentes = []
        for cam in eq.get("cameras_config") or []:
            chave = (nome_eq, cam.get("canal") or cam.get("nome"))
            if not (cam.get("ip") or "").strip() or chave in _capturadas:
                continue
            if time.monotonic() - _ultima_tentativa.get(chave, -REPETIR_FALHA_S) < REPETIR_FALHA_S:
                continue
            pendentes.append((chave, {**cam}))  # cópia: a captura anota `imagem_noite` no item
        if not pendentes:
            continue

        logging.info(f"  [NOITE] {nome_eq}: capturando {len(pendentes)} câmera(s) pela rede (ao vivo, RTSP).")
        capturar_imagens_noite_vms(nome_eq, [c for _, c in pendentes], conf)
        for chave, cam in pendentes:
            _ultima_tentativa[chave] = time.monotonic()
            status = (cam.get("imagem_noite") or {}).get("status")
            if status == "OK":
                _capturadas.add(chave)
                ok += 1
            else:
                logging.info(f"  [NOITE] {nome_eq} / {cam.get('nome')}: {(cam.get('imagem_noite') or {}).get('motivo')}")
    return ok
