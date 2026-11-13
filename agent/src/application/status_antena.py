"""Coleta periódica do status das antenas pelo MikroTik cadastrado no equipamento ANTENA.

O equipamento guarda o acesso SSH ao MikroTik (`ip`, `username`, `password`, `config_extra.porta_ssh`), a lista de
antenas (`config_extra.antenas`: nome + MAC) e os prefixos de fabricante para a busca automática
(`config_extra.prefixos_mac`). O agente lê o MikroTik, cruza os MACs (tolerância de 32), pinga o IP de cada antena e envia
o resultado ao servidor (`/agent/antenas/status`)."""
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from src.core.config import parse_config_extra
from src.mikrotik.antenas import (
    ErroMikrotik, PORTA_SSH_PADRAO, avaliar_antena, consolidar_dispositivos, descobrir_antenas, ler_mikrotik, pingar,
    prefixos_validos,
)

INTERVALO_ANTENA_S = 180
MAX_PINGS_PARALELOS = 8


def _eh_antena_ativa(eq: dict) -> bool:
    return bool(eq.get("active", True)) and (eq.get("tipo") or "").upper() == "ANTENA"


def porta_ssh(cfg: dict) -> int:
    try:
        return int(cfg.get("porta_ssh") or PORTA_SSH_PADRAO)
    except (TypeError, ValueError):
        return PORTA_SSH_PADRAO


def coletar_antena(eq: dict, ler: Optional[Callable] = None, ping: Optional[Callable] = None) -> Dict[str, Any]:
    """Status de um equipamento ANTENA: {'nome', 'mikrotik', 'antenas', 'descobertas'} ou, se o MikroTik não respondeu,
    {'nome', 'erro', 'antenas': [], 'descobertas': []} (o servidor mantém o último estado das antenas)."""
    ler = ler or ler_mikrotik
    ping = ping or pingar
    cfg = parse_config_extra(eq)
    ip, usuario, senha = (eq.get("ip") or "").strip(), eq.get("username") or "", eq.get("password") or ""
    if not ip or not usuario or not senha:
        return {"nome": eq.get("name"), "erro": "IP, usuário ou senha do MikroTik não informados", "antenas": [], "descobertas": []}
    try:
        leitura = ler(ip, usuario, senha, porta_ssh(cfg))
    except ErroMikrotik as e:
        return {"nome": eq.get("name"), "erro": str(e).replace(senha, "***") if len(senha) >= 3 else str(e),
                "antenas": [], "descobertas": []}
    disp = consolidar_dispositivos(leitura)
    cadastradas = [a for a in (cfg.get("antenas") or []) if isinstance(a, dict)]
    with ThreadPoolExecutor(max_workers=MAX_PINGS_PARALELOS) as pool:
        antenas = list(pool.map(lambda a: avaliar_antena(a, disp, ping), cadastradas))
    descobertas = descobrir_antenas(disp, cadastradas, prefixos_validos(cfg.get("prefixos_mac")))
    return {
        "nome": eq.get("name"),
        "mikrotik": {"identidade": leitura.get("identity") or "", "ip": ip, "dispositivos": len(disp)},
        "antenas": antenas,
        "descobertas": descobertas,
    }


def coletar_status_antenas(equipamentos: list, ler: Optional[Callable] = None, ping: Optional[Callable] = None) -> List[Dict[str, Any]]:
    """Lista para `/agent/antenas/status`, um item por equipamento ANTENA ativo. `ler` e `ping` são injetáveis (teste)."""
    resultado = []
    for eq in equipamentos or []:
        try:
            if _eh_antena_ativa(eq):
                resultado.append(coletar_antena(eq, ler, ping))
        except Exception as e:
            logging.warning(f"Erro ao coletar o status das antenas de {eq.get('name')}: {e.__class__.__name__}", exc_info=False)
    return resultado
