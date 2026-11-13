"""Experimental Linux runner for the Trilan agent (RouterOS ARMv7 pilot).

Existing Windows service and API are unchanged. Backups are disabled by default.
"""
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime

from src.core.config import load_conf
from src.application.api_client import fetch_server_config, ping_server
from src.application import updater_linux

LOG = logging.getLogger("trilan.linux")
STOP = threading.Event()
BACKUP_LOCK = threading.Lock()
# OTA (>= 1.1.52): 1ª verificação 2 min após subir, depois a cada 1 h (o servidor também limita a 1 oferta/h)
OTA_PRIMEIRA_S = 120
OTA_INTERVALO_S = 3600
# Versão nova que não consegue pingar nesse prazo encerra com erro; o launcher conta a falha e desfaz após 3
PRAZO_CONFIRMACAO_S = 600
SAIDA_SEM_PING = 3
ULTIMO_PING_OK = [0.0]

def enabled(name):
    return os.getenv(name, "false").lower() in ("true", "1", "yes")

def schedule(conf):
    try:
        cfg = fetch_server_config(conf)
        hour, minute = int(cfg.get("backup_hour", 2)), int(cfg.get("backup_minute", 0))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError("invalid backup time")
        return hour, minute
    except Exception as exc:
        LOG.warning("Config not available, fallback to 02:00: %s", exc)
        return 2, 0

def run_backup(trigger):
    if not enabled("TRILAN_ENABLE_BACKUPS"):
        LOG.warning("Backup disabled; ignoring command")
        return
    if not BACKUP_LOCK.acquire(blocking=False):
        LOG.warning("Backup already running")
        return
    try:
        from src.application.backup_job import run_backup as execute
        execute(trigger)
    except Exception:
        LOG.exception("Backup execution failed")
    finally:
        BACKUP_LOCK.release()

def run_connection_test(conf, task):
    """Teste de conexão pedido pelo painel (mesma rotina do agente Windows)."""
    try:
        from src.application.api_client import send_conexao_progresso
        from src.application.teste_conexao import executar_teste_conexao
        result = executar_teste_conexao(task, conf, lambda state: send_conexao_progresso(conf, state))
        LOG.info("Connection test for %s: ok=%s", task.get("name"), result["ok"])
    except Exception:
        LOG.exception("Connection test failed")

def heartbeat(conf, pending):
    while not STOP.is_set():
        started = time.monotonic()
        try:
            response = ping_server(conf)
            if isinstance(response, dict):
                ULTIMO_PING_OK[0] = time.monotonic()
                updater_linux.confirmar()
                if response.get("restart"):
                    LOG.warning("Restart requested; process stopping (launcher_linux.py starts it again)")
                    STOP.set()
                    return
                if response.get("backup"):
                    pending.set()
                if response.get("rtsp_task"):
                    LOG.warning("RTSP tasks not yet implemented for ARMv7 pilot")
                if isinstance(response.get("conexao_task"), dict):
                    threading.Thread(target=run_connection_test, args=(conf, response["conexao_task"]), daemon=True).start()
        except Exception as exc:
            LOG.warning("Heartbeat failed: %s", exc)
        STOP.wait(max(0, 15 - (time.monotonic() - started)))

def main():
    logging.basicConfig(level=os.getenv("TRILAN_LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    signal.signal(signal.SIGINT, lambda *_: STOP.set())
    conf = load_conf()
    if not conf["server_url"].startswith("https://") and not enabled("TRILAN_ALLOW_INSECURE_HTTP"):
        raise RuntimeError("HTTPS required (HTTP override for isolated testing only)")
    LOG.info("Experimental ARMv7 agent starting; backups=%s", enabled("TRILAN_ENABLE_BACKUPS"))
    hour, minute = schedule(conf)
    pending = threading.Event()
    threading.Thread(target=heartbeat, args=(conf, pending), daemon=True).start()
    started_at = time.monotonic()
    sync_at = started_at + 3600
    ota_at = started_at + OTA_PRIMEIRA_S
    last_scheduled_date = None
    last_backup_end = 0.0
    exit_code = 0
    while not STOP.is_set():
        now = datetime.now()
        if time.monotonic() >= sync_at:
            hour, minute = schedule(conf)
            sync_at = time.monotonic() + 3600
        if (updater_linux.aguardando_confirmacao() and ULTIMO_PING_OK[0] == 0.0
                and time.monotonic() - started_at > PRAZO_CONFIRMACAO_S):
            LOG.error("[OTA] New version did not reach the server in %ss; exiting so the launcher can roll back",
                      PRAZO_CONFIRMACAO_S)
            exit_code = SAIDA_SEM_PING
            break
        if time.monotonic() >= ota_at and not BACKUP_LOCK.locked():
            ota_at = time.monotonic() + OTA_INTERVALO_S
            if updater_linux.verificar_e_instalar(conf):
                break
        scheduled = enabled("TRILAN_ENABLE_BACKUPS") and (
            (now.hour, now.minute) == (hour, minute) and last_scheduled_date != now.date()
        )
        manual = pending.is_set()
        if manual:
            pending.clear()
        if scheduled or manual:
            if scheduled:
                last_scheduled_date = now.date()
            if time.monotonic() - last_backup_end >= 60:
                run_backup("scheduled" if scheduled else "manual_dashboard")
                last_backup_end = time.monotonic()
            else:
                LOG.info("Duplicate backup command ignored (60s cooldown)")
        STOP.wait(2)
    STOP.set()
    LOG.info("Agent stopped")
    return exit_code

if __name__ == "__main__":
    sys.exit(main())
