import logging
from pathlib import Path
from typing import Optional

from src.backup.downloader import LimiteMemoriaExcedido
import requests
from requests.auth import HTTPDigestAuth

TIMEOUT_BACKUP_S = 30


def baixar_configuracao_intelbras_memoria(nvr_ip: str, usuario: str, senha: str, limite: Optional[int] = None) -> Optional[bytes]:
    """Mesma exportação, mas devolve os bytes sem gravar em disco (túnel do Mikrotik). None se falhou."""
    auth = HTTPDigestAuth(usuario, senha)
    url = f"http://{nvr_ip}/cgi-bin/configManager.cgi?action=getConfig&name=All"
    try:
        r = requests.get(url, auth=auth, timeout=TIMEOUT_BACKUP_S, verify=False)
        if r.status_code == 200 and len(r.content) > 1000:
            if limite is not None and len(r.content) > limite:
                raise LimiteMemoriaExcedido(f"a config do NVR passou de {limite // (1024 * 1024)} MB")
            logging.info(f"  Config NVR Intelbras em memoria ({len(r.content):,} bytes).")
            return r.content
        logging.warning(f"  Falha no download da config Intelbras: HTTP {r.status_code}, tamanho: {len(r.content)} bytes.")
        return None
    except LimiteMemoriaExcedido:
        raise
    except Exception as e:
        logging.warning(f"  Erro ao baixar config do NVR Intelbras {nvr_ip}: {e}")
        return None


def baixar_configuracao_intelbras(nvr_ip: str, usuario: str, senha: str, destino: Path) -> bool:
    """
    Exporta a configuração completa do NVR/DVR Intelbras via Dahua CGI (getConfig&name=All).
    Grava o arquivo no caminho de destino e retorna True se bem-sucedido.
    """
    dados = baixar_configuracao_intelbras_memoria(nvr_ip, usuario, senha)
    if dados is None:
        return False
    destino.write_bytes(dados)
    logging.info(f"  Backup NVR Intelbras OK ({len(dados):,} bytes -> {destino.name}).")
    return True
