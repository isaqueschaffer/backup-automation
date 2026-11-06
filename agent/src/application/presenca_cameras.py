"""
Módulo para coleta periódica do status de presença das câmeras (online/offline).
Executado em intervalos curtos (ex.: 5 min) independentemente do backup diário.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.core.config import parse_config_extra
from src.nvr.factory import buscar_cameras, _canal_numerico_motorola
from src.application import log_remoto

INTERVALO_PRESENCA_S = 300


def coletar_presenca(equipamentos: list) -> List[Dict[str, Any]]:
    """
    Coleta o estado atual de presença (online/offline) das câmeras para os equipamentos suportados.
    Retorna uma lista de equipamentos com suas respectivas leituras de câmeras.
    Equipamentos inativos, inacessíveis ou sem leitura não são incluídos no retorno.
    """
    resultado = []
    for eq in equipamentos:
        with log_remoto.equipamento_atual(eq.get("name", "")):
            try:
                if not eq.get("active", True):
                    continue

                tipo_eq = (eq.get("tipo") or "NVR").upper()
                nome_eq = eq.get("name")
                lista_cams = []

                if tipo_eq == "NVR":
                    cfg = parse_config_extra(eq)
                    cameras, tipo, _ = buscar_cameras(
                        eq["ip"], eq["username"], eq["password"], cfg.get("marca")
                    )
                    if not cameras:
                        continue

                    for canal_id, cam in cameras.items():
                        online = cam.get("online")
                        if online in (True, False):
                            canal = _canal_numerico_motorola(canal_id) if tipo == "MOTOROLA" else canal_id
                            lista_cams.append({
                                "canal": canal,
                                "nome": cam.get("nome"),
                                "online": bool(online),
                            })

                elif tipo_eq == "DIGIFORT":
                    import src.application.webhook_digifort as wh_digifort
                    st_cameras = dict(wh_digifort._ultimo_status_cameras)
                    if not st_cameras:
                        continue
                    for nome, status in st_cameras.items():
                        lista_cams.append({
                            "canal": None,
                            "nome": nome,
                            "online": status == "OK",
                        })

                elif tipo_eq == "DEFENSE":
                    from src.application.webhook_defense import get_status_cameras_defense
                    cfg = parse_config_extra(eq)
                    st_cameras = get_status_cameras_defense(cfg.get("pasta_origem", ""))
                    if not st_cameras:
                        continue
                    for nome, evento in st_cameras.items():
                        lista_cams.append({
                            "canal": None,
                            "nome": nome,
                            "online": (evento == "OK"),
                        })

                else:
                    continue

                if lista_cams:
                    resultado.append({
                        "nome": nome_eq,
                        "cameras": lista_cams,
                    })

            except Exception as e:
                logging.warning(f"Erro ao coletar presença de {eq.get('name')}: {e}", exc_info=True)

    return resultado
