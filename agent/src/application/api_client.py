import logging
import requests
from pathlib import Path
from datetime import datetime

TIMEOUT_SERVER = 120

def fetch_server_config(conf: dict) -> dict:
    headers = {"X-Client-ID": conf["client_id"], "X-API-Key": conf["api_key"]}
    url = f"{conf['server_url']}/api/v1/agent/config"
    r = requests.get(
        url,
        headers=headers,
        timeout=30,
        verify=False,
    )
    r.raise_for_status()
    try:
        return r.json()
    except ValueError as e:
        logging.error(f"Resposta do servidor nao é um JSON valido. Verifique a URL do servidor e a porta.")
        logging.error(f"URL acessada: {url}")
        logging.error(f"Status Code: {r.status_code}")
        logging.error(f"Conteudo recebido: {r.text[:200]}")
        raise RuntimeError("Servidor retornou uma resposta invalida (provavelmente HTML em vez de JSON).") from e

def post_report(conf: dict, started_at: datetime, finished_at: datetime,
                resultados: list, trigger: str) -> str | None:
    headers = {"X-Client-ID": conf["client_id"], "X-API-Key": conf["api_key"]}
    payload = {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "status": (
            "OK" if all(r["status"] == "OK" for r in resultados) else
            "ERROR" if all(r["status"] == "ERRO" for r in resultados) else "PARTIAL"
        ),
        # campo nvr_results mantido por compatibilidade com o servidor; inclui tipo do equipamento
        "nvr_results": [
            {
                "nome": r["nome"],
                "tipo": r.get("tipo") or "NVR",
                "status": r["status"],
                "cameras": r.get("cameras") or [],
            }
            for r in resultados
        ],
        "trigger": trigger,
    }
    try:
        r = requests.post(
            f"{conf['server_url']}/api/v1/agent/backup/report",
            json=payload, headers=headers, timeout=30, verify=False,
        )
        r.raise_for_status()
        try:
            resp_data = r.json()
            backup_id = resp_data["backup_id"]
        except ValueError:
            logging.error(f"  Resposta nao-JSON ao enviar relatorio. Conteudo: {r.text[:200]}")
            return None
            
        logging.info(f"  Relatorio enviado. backup_id={backup_id}")
        return backup_id
    except Exception as e:
        logging.error(f"  Erro ao enviar relatorio: {e}")
        return None

def upload_zip(conf: dict, backup_id: str, zip_path: Path, device_type: str = "NVR") -> bool:
    headers = {"X-Client-ID": conf["client_id"], "X-API-Key": conf["api_key"]}
    try:
        with open(zip_path, "rb") as f:
            r = requests.post(
                f"{conf['server_url']}/api/v1/agent/backup/upload/{backup_id}",
                params={"device_type": device_type},
                headers=headers,
                files={"file": (zip_path.name, f, "application/zip")},
                timeout=TIMEOUT_SERVER,
                verify=False,
            )
        r.raise_for_status()
        try:
            resp_json = r.json()
        except ValueError:
            resp_json = r.text[:100]
        logging.info(f"  ZIP ({device_type}) enviado ao servidor. Resposta: {resp_json}")
        return True
    except Exception as e:
        logging.error(f"  Erro ao enviar ZIP ({device_type}): {e}")
        return False
