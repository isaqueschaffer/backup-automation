import hashlib
import json
import logging
import time

import requests

from src.core.config import parse_config_extra

PORTA_PADRAO = 52302
TIMEOUT_HTTP_S = 30
TIMEOUT_OCIOSA_S = 120
TIMEOUT_EXPORTACAO_S = 600
INTERVALO_S = 3


class UnmApiError(Exception):
    """Erro retornado pela API do UNM2000."""


def _chamar(url: str, operador: str, sessionid: str, parametros: dict = None) -> dict:
    corpo = {
        "header": {
            "operator": operador,
            "sessionid": str(sessionid),
        }
    }
    if parametros is not None:
        corpo["parameters"] = parametros

    resp = requests.post(
        url,
        data=json.dumps(corpo),
        headers={"Content-Type": "application/json"},
        timeout=TIMEOUT_HTTP_S,
    )
    resp.raise_for_status()
    dados = resp.json()
    params = dados.get("parameters") or {}
    errorcode = params.get("errorcode")
    if errorcode is not None and errorcode != 0 and errorcode != "" and errorcode != "0":
        msg = params.get("errormsg") or params.get("errordetail") or f"código de erro {errorcode}"
        raise UnmApiError(f"{operador}: {msg}")
    return dados


def _login(url: str, usuario: str, senha: str) -> str:
    pwd_hash = hashlib.md5(senha.encode("utf-8")).hexdigest().lower()
    resp = _chamar(
        url,
        "Logon",
        "0",
        {"username": usuario, "password": pwd_hash, "langtype": 1},
    )
    sid = (resp.get("header") or {}).get("sessionid")
    if not sid:
        raise UnmApiError("login sem sessão")
    return str(sid)


def _listar_zips(url: str, sid: str) -> set:
    resp = _chamar(url, "GetStoreFileInfo", sid, {"storeflag": 1})
    params = resp.get("parameters") or {}
    filelist = params.get("filelist") or []
    return {
        item["filename"]
        for item in filelist
        if isinstance(item, dict) and item.get("filename")
    }


def _status(url: str, sid: str) -> dict:
    resp = _chamar(url, "GetExportEMSCfgStatus", sid, {"type": 0})
    params = resp.get("parameters") or {}
    taskstatus = params.get("taskstatus")
    return taskstatus if isinstance(taskstatus, dict) else {}


def exportar_configuracao_unm2000(equipamento: dict):
    """Pede ao UNM2000 uma exportação completa da configuração e espera o zip novo aparecer.
    Retorna True se gerou, None se a exportação não está configurada para este equipamento,
    False se falhou. Nunca levanta exceção."""
    try:
        cfg = parse_config_extra(equipamento)
        exp_manual = cfg.get("exportar_no_manual")
        habilitado = exp_manual is True or (isinstance(exp_manual, str) and exp_manual.strip().lower() == "true")
        if not habilitado:
            logging.info("  [UNM2000] Exportação manual não habilitada no painel: usando o zip existente.")
            return None

        usuario = (equipamento.get("username") or "").strip()
        senha = equipamento.get("password") or ""
        if not usuario or not senha:
            logging.error("  [UNM2000] Exportação habilitada, mas usuário/senha da API não cadastrados.")
            return False

        host = str(cfg.get("host_api") or "").strip() or "127.0.0.1"
        porta = PORTA_PADRAO
        porta_cfg = cfg.get("porta_api")
        if porta_cfg is not None:
            try:
                p = int(porta_cfg)
                if 1 <= p <= 65535:
                    porta = p
            except (ValueError, TypeError):
                pass
        url = f"http://{host}:{porta}/unmcmcgi"

        sid = _login(url, usuario, senha)
        antes = _listar_zips(url, sid)

        inicio_ociosa = time.monotonic()
        while True:
            st = _status(url, sid)
            if st.get("step") == 0:
                break
            if time.monotonic() - inicio_ociosa >= TIMEOUT_OCIOSA_S:
                logging.error("  [UNM2000] Outra exportação em andamento no UNM2000; tempo limite esgotado.")
                return False
            time.sleep(INTERVALO_S)

        _chamar(url, "ExportEMSCfg", sid, {"type": 0, "filedesc": "Backup manual Trilan"})
        logging.info("  [UNM2000] Exportação solicitada ao UNM2000.")

        inicio_exp = time.monotonic()
        while time.monotonic() - inicio_exp < TIMEOUT_EXPORTACAO_S:
            time.sleep(INTERVALO_S)
            st = _status(url, sid)
            errmsg = st.get("errmsg")
            if errmsg:
                logging.error(f"  [UNM2000] Erro na exportação do UNM2000: {errmsg}")
                return False

            novos = _listar_zips(url, sid) - antes
            try:
                pct = int(st.get("percentage", 0))
            except (ValueError, TypeError):
                pct = 0
            if novos and st.get("step") == 0 and pct >= 100:
                nomes = ", ".join(sorted(novos))
                logging.info(f"  [UNM2000] Nova exportação gerada com sucesso: {nomes}")
                time.sleep(2)
                return True

        logging.error("  [UNM2000] Tempo esgotado aguardando a exportação do UNM2000.")
        return False
    except Exception as e:
        logging.error(f"  [UNM2000] Falha na exportação: {e}")
        return False
