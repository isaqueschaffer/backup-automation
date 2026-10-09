import sys
import configparser
from pathlib import Path

DIR_AGENT = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent.parent
CONF_FILE = DIR_AGENT / "agent.conf"

def load_conf() -> dict:
    if not CONF_FILE.exists():
        sys.exit(f"ERRO: {CONF_FILE} nao encontrado. Copie agent.conf.example e configure.")
    
    cfg = configparser.ConfigParser()
    try:
        cfg.read(CONF_FILE, encoding="utf-8-sig")
        url = cfg["server"]["url"].rstrip("/")
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"http://{url}"

        return {
            "server_url": url,
            "client_id": cfg["auth"]["client_id"],
            "api_key": cfg["auth"]["api_key"],
        }
    except (configparser.Error, KeyError) as e:
        sys.exit(f"ERRO FATAL: Arquivo agent.conf mal formatado ou faltando informacoes. Detalhe: {e}")
