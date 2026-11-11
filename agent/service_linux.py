"""Experimental Linux runner for the Trilan agent (RouterOS ARMv7 pilot).

Existing Windows service and API are unchanged. Backups are disabled by default.
"""
import logging
import os
import signal
import threading
import time
from datetime import datetime

from src.core.config import load_conf
from src.application.api_client import fetch_server_config, ping_server

LOG = logging.getLogger("trilan.linux")
STOP = threading.Event()
BACKUP_LOCK = threading.Lock()

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

def heartbeat(conf, pending):
    while not STOP.is_set():
        started = time.monotonic()
        try:
            response = ping_server(conf)
            if isinstance(response, dict):
                if response.get("restart"):
                    LOG.warning("Restart requested; process stopping (external restart policy required)")
                    STOP.set()
                    return
                if response.get("backup"):
                    pending.set()
                if response.get("rtsp_task"):
                    LOG.warning("RTSP tasks not yet implemented for ARMv7 pilot")
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
    sync_at = time.monotonic() + 3600
    last_scheduled_date = None
    last_backup_end = 0.0
    while not STOP.is_set():
        now = datetime.now()
        if time.monotonic() >= sync_at:
            hour, minute = schedule(conf)
            sync_at = time.monotonic() + 3600
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
    LOG.info("Agent stopped")

if __name__ == "__main__":
    main()
