"""Coleta periodica do status das OLTs (ONUs e sinal optico) das UNM2000 cadastradas com OLTs para monitorar."""
import logging
from typing import Any, Dict, List

from src.core.config import parse_config_extra

INTERVALO_OLT_S = 300


def _eh_unm2000(eq: dict, cfg: dict) -> bool:
    if (eq.get("tipo") or "").upper() != "OLT":
        return False
    fabricante = (eq.get("fabricante") or cfg.get("fabricante_olt") or cfg.get("fabricante") or "unm2000").lower()
    return "unm" in fabricante


def coletar_status_olts(equipamentos: list, coletar=None, buscar_nomes=None) -> List[Dict[str, Any]]:
    """[{'nome': equipamento, 'olts': [{'nome', 'ip', ...status ou 'erro'}]}] das UNM2000 ativas com OLTs
    (`olts`, um IP por linha) e acesso Telnet (`telnet_usuario`, `telnet_senha`, `telnet_enable`)
    configurados. `coletar(ip, usuario, senha, enable, porta)` e injetavel para teste."""
    from src.olt.unm_nomes import aplicar_nomes, consultar_nomes
    from src.olt.unm_telnet import PORTA_PADRAO, coletar_olt, parse_hosts
    coletar = coletar or coletar_olt
    resultado = []
    for eq in equipamentos or []:
        try:
            if not eq.get("active", True):
                continue
            cfg = parse_config_extra(eq)
            if not _eh_unm2000(eq, cfg):
                continue
            hosts = parse_hosts(cfg.get("olts"))
            usuario = (cfg.get("telnet_usuario") or "").strip()
            if not hosts or not usuario:
                continue
            senha = cfg.get("telnet_senha") or ""
            enable = cfg.get("telnet_enable") or senha
            try:
                porta = int(cfg.get("telnet_porta") or PORTA_PADRAO)
            except (TypeError, ValueError):
                porta = PORTA_PADRAO
            olts = [{"nome": h["nome"], **coletar(h["ip"], usuario, senha, enable, porta)} for h in hosts]
            nomes, erros_nomes = consultar_nomes(cfg, buscar_nomes)
            if nomes or erros_nomes:
                for olt in olts:
                    if olt.get("erro"):
                        continue
                    com, sem = aplicar_nomes(olt.get("onus"), nomes)
                    olt["nomes"] = {"com_nome": com, "sem_nome": sem, **({"erro": " | ".join(erros_nomes)} if erros_nomes else {})}
            resultado.append({"nome": eq.get("name"), "olts": olts})
        except Exception as e:
            logging.warning(f"Erro ao coletar o status das OLTs de {eq.get('name')}: {e}", exc_info=True)
    return resultado
