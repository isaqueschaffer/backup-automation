import json
import sys
import configparser
from pathlib import Path

DIR_AGENT = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent.parent
CONF_FILE = DIR_AGENT / "agent.conf"

class ConfigError(Exception):
    """agent.conf ausente ou mal formatado."""


def parse_config_extra(equipamento: dict) -> dict:
    """Retorna o config_extra do equipamento como dict (aceita None, dict ou string JSON)."""
    cfg = (equipamento or {}).get("config_extra") or {}
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except Exception:
            return {}
    return cfg if isinstance(cfg, dict) else {}


def load_conf() -> dict:
    if not CONF_FILE.exists():
        raise ConfigError(f"ERRO: {CONF_FILE} nao encontrado. Copie agent.conf.example e configure.")
    
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
        raise ConfigError(f"ERRO FATAL: Arquivo agent.conf mal formatado ou faltando informacoes. Detalhe: {e}") from e
