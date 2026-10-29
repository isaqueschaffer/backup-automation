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

# Espera crescente por equipamento sem resposta (senha errada ou fora do ar): tentar login a cada 5 min mantém
# a conta (Intelbras/Dahua) ou o IP (Hikvision) bloqueado no NVR. A espera dobra a cada falha seguida
# (5 -> 10 -> 20 -> 40 -> 60 min, no máximo 60) e zera na primeira leitura com sucesso.
ESPERA_INICIAL_MIN = 5
ESPERA_MAXIMA_MIN = 60
# (nome, ip) -> {"falhas": falhas seguidas, "pular": ciclos que ainda faltam pular}. Só a thread de presença usa.
_espera_por_equipamento: Dict[tuple, Dict[str, int]] = {}


def _deve_pular(chave: tuple) -> bool:
    """True se o equipamento ainda está em espera (e consome um ciclo dela)."""
    estado = _espera_por_equipamento.get(chave)
    if estado and estado["pular"] > 0:
        estado["pular"] -= 1
        return True
    return False


def _registrar_falha(chave: tuple, nome: str) -> None:
    estado = _espera_por_equipamento.setdefault(chave, {"falhas": 0, "pular": 0})
    estado["falhas"] += 1
    espera_min = min(ESPERA_INICIAL_MIN * 2 ** (estado["falhas"] - 1), ESPERA_MAXIMA_MIN)
    # Em ciclos inteiros de presença: a espera de 5 min pula o próximo ciclo (sem tentar por 5 min)
    estado["pular"] = max(1, (espera_min * 60) // INTERVALO_PRESENCA_S)
    logging.warning(
        f"Presença de câmeras: {nome} sem resposta ({estado['falhas']} falha(s) seguida(s)). "
        f"Nova tentativa em {espera_min} min."
    )


def _registrar_sucesso(chave: tuple) -> None:
    _espera_por_equipamento.pop(chave, None)


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
                chave = (nome_eq or "", (eq.get("ip") or "").strip())
                lista_cams = []

                if tipo_eq == "NVR":
                    if _deve_pular(chave):
                        continue
                    cfg = parse_config_extra(eq)
                    cameras, tipo, _ = buscar_cameras(
                        eq["ip"], eq["username"], eq["password"], cfg.get("marca")
                    )
                    if not cameras:
                        _registrar_falha(chave, nome_eq)
                        continue
                    _registrar_sucesso(chave)

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
                    # Estado pela API do Defense IA (sem gravações e sem RTSP), com os mesmos nomes do backup.
                    # Sem senha da API não há o que consultar; API sem resposta não envia nada.
                    if not eq.get("password") or _deve_pular(chave):
                        continue
                    from src.vms.defense import coletar_presenca_defense
                    leituras = coletar_presenca_defense(eq)
                    if leituras is None:
                        _registrar_falha(chave, nome_eq)
                        continue
                    _registrar_sucesso(chave)
                    lista_cams = leituras

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
