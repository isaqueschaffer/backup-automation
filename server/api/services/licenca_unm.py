"""Licenca da UNM2000: dias restantes ate a data de validade informada no cadastro do equipamento.

O servidor da UNM2000 nao informa a validade por nenhum caminho de leitura (o template Zabbix tambem pedia a data como
macro), entao ela e digitada no equipamento (`licenca_fim`, opcionalmente `licenca_inicio`).
"""
import re
from datetime import date
from typing import Any, Optional


def parse_data(texto: Any) -> Optional[date]:
    """'2026-12-31', '31/12/2026' ou '20261231' -> date; None se nao for uma data valida."""
    t = str(texto or "").strip()
    for padrao, ordem in ((r"^(\d{4})-(\d{2})-(\d{2})$", "ymd"), (r"^(\d{2})/(\d{2})/(\d{4})$", "dmy"), (r"^(\d{4})(\d{2})(\d{2})$", "ymd")):
        m = re.match(padrao, t)
        if m:
            a, b, c = (int(x) for x in m.groups())
            try:
                return date(a, b, c) if ordem == "ymd" else date(c, b, a)
            except ValueError:
                return None
    return None


def licenca_da_config(config: Any, hoje: Optional[date] = None) -> Optional[dict]:
    """{'inicio', 'fim', 'dias_restantes'} (negativo = vencida) ou None quando `licenca_fim` nao foi informada."""
    if not isinstance(config, dict):
        return None
    fim = parse_data(config.get("licenca_fim"))
    if not fim:
        return None
    inicio = parse_data(config.get("licenca_inicio"))
    return {
        "inicio": inicio.isoformat() if inicio else None,
        "fim": fim.isoformat(),
        "dias_restantes": (fim - (hoje or date.today())).days,
    }
