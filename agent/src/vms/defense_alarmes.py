"""Alarmes das centrais Intelbras cadastradas no Defense IA, por uma API HTTP simples e separada da API nativa
BRMS usada em `defense.py` (porta configuravel, padrao 3001, `/api/alarm-centrals`), autenticada com HTTP Basic
Auth e as mesmas credenciais do equipamento DEFENSE."""
import logging

import requests
from requests.auth import HTTPBasicAuth

from src.core.config import parse_config_extra

TIMEOUT_S = 10
PORTA_PADRAO = 3001


def _texto(valor):
    texto = str(valor).strip() if valor is not None else ""
    return texto or None


def parse_alarmes(dados: list) -> list:
    """[{'nome','status','particoes': [{'nome','armada'}]}] da resposta de `/api/alarm-centrals`. `status' e o
    status de comunicacao bruto da central (a API nao documenta os valores); `armada' vem de
    `partitions[].armed' (0/1), convertido para bool."""
    saida = []
    for central in dados or []:
        if not isinstance(central, dict):
            continue
        particoes = [
            {"nome": _texto(p.get("name")) or f"Partição {p.get('index', '?')}", "armada": bool(p.get("armed"))}
            for p in (central.get("partitions") or []) if isinstance(p, dict)
        ]
        saida.append({
            "nome": _texto(central.get("name")) or "Central sem nome",
            "status": central.get("status"),
            "particoes": particoes,
        })
    return saida


def consultar_alarmes_defense(ip: str, username: str, password: str, porta: int = PORTA_PADRAO) -> list:
    """Centrais de alarme (`/api/alarm-centrals`) de um Defense IA. Levanta `requests.RequestException` ou
    `ValueError` (resposta nao-JSON ou com formato inesperado) em falha; quem coleta por equipamento decide o
    que fazer com o erro."""
    resposta = requests.get(
        f"http://{ip}:{porta}/api/alarm-centrals",
        auth=HTTPBasicAuth(username, password),
        timeout=TIMEOUT_S,
    )
    resposta.raise_for_status()
    dados = resposta.json()
    if not isinstance(dados, list):
        raise ValueError("resposta da API de alarmes nao e uma lista")
    return parse_alarmes(dados)


def coletar_alarmes_equipamento(equipamento: dict, consultar=None) -> dict:
    """{'ip','alarmes'} ou {'ip','erro'} das centrais de alarme de um equipamento DEFENSE. Nunca levanta erro.
    `consultar(ip, usuario, senha, porta)` e injetavel para teste."""
    consultar = consultar or consultar_alarmes_defense
    config_extra = parse_config_extra(equipamento)
    ip = equipamento.get("ip") or config_extra.get("ip")
    username = equipamento.get("username") or "system"
    password = equipamento.get("password") or ""
    try:
        porta = int(config_extra.get("porta_alarme") or PORTA_PADRAO)
    except (TypeError, ValueError):
        porta = PORTA_PADRAO

    if not ip or not password:
        return {"ip": ip, "erro": "IP ou senha nao informados"}

    try:
        return {"ip": ip, "alarmes": consultar(ip, username, password, porta)}
    except Exception as e:
        logging.warning(f"  [DEFENSE] Falha ao consultar alarmes em {ip}:{porta}: {e}")
        return {"ip": ip, "erro": str(e) or e.__class__.__name__}
