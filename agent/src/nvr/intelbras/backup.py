import logging
from pathlib import Path
import requests
from requests.auth import HTTPDigestAuth

TIMEOUT_BACKUP_S = 30


def baixar_configuracao_intelbras(nvr_ip: str, usuario: str, senha: str, destino: Path) -> bool:
    """
    Exporta a configuração completa do NVR/DVR Intelbras via Dahua CGI (getConfig&name=All).
    Grava o arquivo no caminho de destino e retorna True se bem-sucedido.
    """
    auth = HTTPDigestAuth(usuario, senha)
    url = f"http://{nvr_ip}/cgi-bin/configManager.cgi?action=getConfig&name=All"
    try:
        r = requests.get(url, auth=auth, timeout=TIMEOUT_BACKUP_S, verify=False)
        if r.status_code == 200 and len(r.content) > 1000:
            destino.write_bytes(r.content)
            logging.info(f"  Backup NVR Intelbras OK ({len(r.content):,} bytes -> {destino.name}).")
            return True
        else:
            logging.warning(f"  Falha no download da config Intelbras: HTTP {r.status_code}, tamanho: {len(r.content)} bytes.")
            return False
    except Exception as e:
        logging.warning(f"  Erro ao baixar config do NVR Intelbras {nvr_ip}: {e}")
        return False
