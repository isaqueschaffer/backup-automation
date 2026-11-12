"""Coleta periodica do status das OLTs (ONUs, e sinal optico quando disponivel) cadastradas para monitorar
(UNM2000 por Telnet, VSOL por HTTP, Huawei por SSH)."""
import logging
from typing import Any, Dict, List

from src.core.config import parse_config_extra

INTERVALO_OLT_S = 300


def _fabricante_olt(eq: dict, cfg: dict) -> str:
    """Fabricante da OLT (mesma logica do backup, `processar_olt`): campo explicito ou, na falta
    dele, 'unm2000' quando houver `olts` configurado (compatibilidade com cadastros antigos)."""
    fabricante = (eq.get("fabricante") or cfg.get("fabricante_olt") or cfg.get("fabricante") or "").lower().strip()
    if not fabricante and cfg.get("olts"):
        fabricante = "unm2000"
    return fabricante


def _eh_olt_ativa(eq: dict) -> bool:
    return bool(eq.get("active", True)) and (eq.get("tipo") or "").upper() == "OLT"


def coletar_status_olts(
    equipamentos: list, coletar=None, buscar_nomes=None, coletar_vsol=None, coletar_huawei=None,
) -> List[Dict[str, Any]]:
    """[{'nome': equipamento, 'olts': [{'nome', 'ip', ...status ou 'erro'}]}] das OLTs ativas:
    - UNM2000 (fabricante com 'unm'): uma ou mais OLTs por Telnet (`olts`, um IP por linha; usuario/senha/enable
      em `telnet_usuario`/`telnet_senha`/`telnet_enable`). `coletar(ip, usuario, senha, enable, porta)` e
      injetavel para teste.
    - VSOL (fabricante 'vsol'): a propria OLT do equipamento (IP/usuario/senha do cadastro), por HTTP.
      `coletar_vsol(equipamento)` e injetavel para teste.
    - Huawei (fabricante 'huawei'): a propria OLT do equipamento (IP/usuario/senha do cadastro), por SSH.
      `coletar_huawei(ip, usuario, senha, porta)` e injetavel para teste.
    """
    from src.olt.unm_nomes import aplicar_nomes, consultar_nomes
    from src.olt.unm_telnet import PORTA_PADRAO, coletar_olt, parse_hosts
    coletar = coletar or coletar_olt
    resultado = []
    for eq in equipamentos or []:
        try:
            if not _eh_olt_ativa(eq):
                continue
            cfg = parse_config_extra(eq)
            fabricante = _fabricante_olt(eq, cfg)
            if "vsol" in fabricante:
                from src.olt.vsol_status import coletar_vsol as _coletar_vsol
                vsol_fn = coletar_vsol or _coletar_vsol
                resultado.append({"nome": eq.get("name"), "olts": [{"nome": eq.get("name"), **vsol_fn(eq)}]})
                continue
            if "huawei" in fabricante:
                from src.olt.huawei_status import PORTA_PADRAO as PORTA_SSH_PADRAO, coletar_huawei as _coletar_huawei
                huawei_fn = coletar_huawei or _coletar_huawei
                ip = eq.get("ip")
                usuario = eq.get("username") or ""
                senha = eq.get("password") or ""
                try:
                    porta = int(cfg.get("porta_ssh") or PORTA_SSH_PADRAO)
                except (TypeError, ValueError):
                    porta = PORTA_SSH_PADRAO
                status = (
                    {"ip": ip, "erro": "IP, usuario ou senha nao informados"}
                    if not ip or not usuario or not senha else huawei_fn(ip, usuario, senha, porta)
                )
                resultado.append({"nome": eq.get("name"), "olts": [{"nome": eq.get("name"), "fabricante": "HUAWEI", **status}]})
                continue
            if "unm" not in fabricante:
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
