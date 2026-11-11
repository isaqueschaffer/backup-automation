"""Coleta periodica dos alarmes das centrais Intelbras cadastradas nos equipamentos DEFENSE (Intelbras Defense
IA), pela API HTTP de alarmes (porta configuravel em `config_extra.porta_alarme`, padrao 3001)."""
import logging
from typing import Any, Dict, List

INTERVALO_ALARMES_S = 300


def coletar_status_alarmes(equipamentos: list, coletar=None) -> List[Dict[str, Any]]:
    """[{'nome': equipamento, 'ip', 'alarmes': [...] ou 'erro': ...}] dos equipamentos DEFENSE ativos com IP e
    senha cadastrados. `coletar(equipamento)` e injetavel para teste."""
    from src.vms.defense_alarmes import coletar_alarmes_equipamento
    coletar = coletar or coletar_alarmes_equipamento
    resultado = []
    for eq in equipamentos or []:
        try:
            if not eq.get("active", True) or (eq.get("tipo") or "").upper() != "DEFENSE":
                continue
            resultado.append({"nome": eq.get("name"), **coletar(eq)})
        except Exception as e:
            logging.warning(f"Erro ao coletar os alarmes de {eq.get('name')}: {e}", exc_info=True)
    return resultado
