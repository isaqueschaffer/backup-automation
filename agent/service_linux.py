"""Agente Linux (container ARMv7 no Mikrotik RouterOS), com as mesmas rotinas do serviço do Windows (1.1.58):
captura da Galeria (ao vivo, referência e noite), presença das câmeras, OLTs, antenas, alarmes do Defense (status e
armar/desarmar), teste de conexão, vigia de backup travado, log no painel e OTA.

O Mikrotik é PONTE/TÚNEL até o servidor: trabalha em memória e não grava nada. O backup (UNM2000 e Digifort por
pasta de rede) é lido por SMB e enviado ao servidor em fluxo (src/backup/tunel.py), sem arquivo no roteador;
NVR, PABX e demais tipos que gravam em disco ficam com os agentes Windows. Também não roda os webhooks
Defense/Digifort (gravam CSV) e a imagem da noite sai só quando pedida na Galeria. TRILAN_ENABLE_BACKUPS=false
desliga o backup. O launcher_linux.py (na imagem) religa o processo quando ele sai.
"""
import logging
import os
import signal
import site
import sys
import threading
import time
from datetime import datetime
from pathlib import Path


def _pasta_bibliotecas_ota() -> None:
    """Bibliotecas Python puras que a OTA instalou (pip --user em PYTHONUSERBASE, padrão /app/data/pyuser): entram
    no sys.path também em imagens antigas, que não definem PYTHONUSERBASE."""
    base = os.environ.setdefault("PYTHONUSERBASE", "/app/data/pyuser")
    pasta = Path(base) / "lib" / f"python{sys.version_info[0]}.{sys.version_info[1]}" / "site-packages"
    if pasta.is_dir() and str(pasta) not in sys.path:
        site.addsitedir(str(pasta))


_pasta_bibliotecas_ota()

from src.core.config import load_conf
from src.application.api_client import fetch_server_config, ping_server
from src.application import estado, log_remoto, updater_linux

LOG = logging.getLogger("trilan.linux")
STOP = threading.Event()
BACKUP_LOCK = threading.Lock()
# O roteador tem pouca RAM: capturas RTSP (sob demanda e da noite) rodam uma de cada vez
RTSP_LOCK = threading.Lock()
# OTA (>= 1.1.52): 1ª verificação 2 min após subir, depois a cada 1 h (o servidor também limita a 1 oferta/h)
OTA_PRIMEIRA_S = 120
OTA_INTERVALO_S = 3600
# Versão nova que não consegue pingar nesse prazo encerra com erro; o launcher conta a falha e desfaz após 3
PRAZO_CONFIRMACAO_S = 600
SAIDA_SEM_PING = 3
ULTIMO_PING_OK = [0.0]
PING_INTERVALO_S = 15
# Backup que passa disso (equipamento que não responde) prende o loop: o processo sai e o launcher o religa
LIMITE_BACKUP_S = 6 * 3600
# O servidor só entrega o alarme_task (leva a senha do DEFENSE) a quem declara saber executá-lo
RECURSOS_EXTRA = ("comando_alarme",)

def enabled(name):
    return os.getenv(name, "false").lower() in ("true", "1", "yes")

def backups_ligados():
    """Backup em túnel vem LIGADO; TRILAN_ENABLE_BACKUPS=false desliga."""
    return os.getenv("TRILAN_ENABLE_BACKUPS", "true").lower() not in ("false", "0", "no")

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
    if not backups_ligados():
        LOG.warning("Backup desativado neste agente (TRILAN_ENABLE_BACKUPS=false); pedido ignorado")
        return
    if not BACKUP_LOCK.acquire(blocking=False):
        LOG.warning("Backup already running")
        return
    estado.backup_inicio = time.monotonic()
    estado.backup_em_andamento = True
    try:
        from src.backup.tunel import executar_backup_tunel   # nunca o backup_job: ele grava em disco
        executar_backup_tunel(trigger)
    except Exception:
        LOG.exception("Backup execution failed")
    finally:
        estado.backup_em_andamento = False
        BACKUP_LOCK.release()

def reinicio_forcado(conf, motivo):
    """O loop principal está preso num backup e não sai sozinho: encerra o processo (o launcher sobe de novo)."""
    LOG.error("Reiniciando o agente a forca: %s", motivo, extra={"enviar_servidor": True})
    enviar_logs_restantes(conf)
    logging.shutdown()
    os._exit(1)

def vigia_backup_loop(conf):
    """Backup travado prendia o agente por dias (sem reinício pelo painel, sem OTA e sem o backup seguinte)."""
    while not STOP.wait(60):
        minutos = estado.backup_ha_min()
        if minutos is not None and minutos * 60 >= LIMITE_BACKUP_S:
            reinicio_forcado(conf, f"backup em andamento ha {minutos} min (limite {LIMITE_BACKUP_S // 3600} h)")

def run_alarm_command(conf, task):
    """Armar/desarmar central de alarme pedido pelo painel (mesma rotina do agente Windows)."""
    try:
        from src.application.status_alarmes_defense import atender_comando_alarme
        LOG.info("Comando de alarme pedido pelo painel: %s central %s (%s)", task.get("acao"), task.get("central_id"),
                 task.get("equipamento"))
        sucesso = atender_comando_alarme(task, conf)
        (LOG.info if sucesso else LOG.error)("Comando de alarme %s concluido: sucesso=%s", task.get("acao"), sucesso)
    except Exception:
        LOG.exception("Falha no comando de alarme")

def _equipamentos(conf):
    cfg = fetch_server_config(conf)
    return cfg.get("equipamentos") or cfg.get("nvrs") or []

def ciclo_loop(conf, nome, espera_inicial, intervalo, coletar, enviar, pula_em_backup=False):
    """Coleta periódica (presença, OLTs, antenas, alarmes) com o mesmo intervalo do agente Windows."""
    if STOP.wait(espera_inicial):
        return
    while not STOP.is_set():
        try:
            if pula_em_backup and estado.backup_em_andamento:
                LOG.info("%s ignorado: backup em andamento.", nome)
            else:
                lista = coletar(_equipamentos(conf))
                if lista:
                    enviar(conf, lista)
        except Exception as exc:
            LOG.error("Falha no ciclo de %s: %s", nome, exc)
        STOP.wait(intervalo)

def iniciar_coletas(conf):
    from src.application import api_client as api
    from src.application.presenca_cameras import INTERVALO_PRESENCA_S, coletar_presenca
    from src.application.status_alarmes_defense import INTERVALO_ALARMES_S, coletar_status_alarmes
    from src.application.status_antena import INTERVALO_ANTENA_S, coletar_status_antenas
    from src.application.status_olt import INTERVALO_OLT_S, coletar_status_olts
    coletas = (
        ("presença de câmeras", 90, INTERVALO_PRESENCA_S, coletar_presenca, api.send_presenca_cameras, True),
        ("status das OLTs", 150, INTERVALO_OLT_S, coletar_status_olts, api.send_status_olts, False),
        ("status das antenas", 90, INTERVALO_ANTENA_S, coletar_status_antenas, api.send_status_antenas, False),
        ("alarmes do DEFENSE", 150, INTERVALO_ALARMES_S, coletar_status_alarmes, api.send_status_alarmes, False),
    )
    for args in coletas:
        threading.Thread(target=ciclo_loop, args=(conf, *args), daemon=True).start()

def run_connection_test(conf, task):
    """Teste de conexão pedido pelo painel (mesma rotina do agente Windows)."""
    try:
        from src.application.api_client import send_conexao_progresso
        from src.application.teste_conexao import executar_teste_conexao
        result = executar_teste_conexao(task, conf, lambda state: send_conexao_progresso(conf, state))
        LOG.info("Connection test for %s: ok=%s", task.get("name"), result["ok"])
    except Exception:
        LOG.exception("Connection test failed")

def run_rtsp_task(conf, task):
    """Teste/captura RTSP pedido pelo painel (mesma rotina do agente Windows), sempre sequencial."""
    try:
        from src.camera.rtsp_client import executar_tarefa_rtsp
        from src.application.api_client import send_rtsp_result
        with RTSP_LOCK:
            result = executar_tarefa_rtsp(task)
        send_rtsp_result(conf, result)
        LOG.info("RTSP task done and sent: success=%s", result.get("success"))
    except Exception:
        LOG.exception("RTSP task failed")

def noite_loop(conf):
    """Imagem da noite das câmeras DIGIFORT/DEFENSE (19h30-4h), igual ao agente Windows, uma câmera por vez."""
    from src.application.captura_noite_vms import INTERVALO_CICLO_S, capturar_noite_vms, na_janela_noite
    if STOP.wait(120):
        return
    while not STOP.is_set():
        try:
            if na_janela_noite(datetime.now()) and not BACKUP_LOCK.locked():
                equipamentos = _equipamentos(conf)
                with RTSP_LOCK:
                    capturar_noite_vms(equipamentos, conf)
        except Exception:
            LOG.exception("Night image cycle failed")
        STOP.wait(INTERVALO_CICLO_S)

def heartbeat(conf, pending):
    while not STOP.is_set():
        started = time.monotonic()
        try:
            response = ping_server(conf, recursos_extra=RECURSOS_EXTRA)
            if isinstance(response, dict):
                ULTIMO_PING_OK[0] = time.monotonic()
                updater_linux.confirmar()
                if isinstance(response.get("alarme_task"), dict):
                    threading.Thread(target=run_alarm_command, args=(conf, response["alarme_task"]), daemon=True).start()
                if response.get("restart"):
                    if estado.backup_em_andamento:
                        # O servidor só manda reiniciar com backup em andamento quando ele passou do razoável
                        reinicio_forcado(conf, "reinicio pedido pelo painel com backup travado")
                    LOG.warning("Restart requested; process stopping (launcher_linux.py starts it again)")
                    STOP.set()
                    return
                if response.get("backup"):
                    pending.set()
                if isinstance(response.get("rtsp_task"), dict):
                    threading.Thread(target=run_rtsp_task, args=(conf, response["rtsp_task"]), daemon=True).start()
                if isinstance(response.get("conexao_task"), dict):
                    threading.Thread(target=run_connection_test, args=(conf, response["conexao_task"]), daemon=True).start()
        except Exception as exc:
            LOG.warning("Heartbeat failed: %s", exc)
        STOP.wait(max(0, PING_INTERVALO_S - (time.monotonic() - started)))

def logs_loop(conf):
    """Envia ao servidor, a cada 20 s, o log do agente (1.1.56; antes o agente do Mikrotik não mandava log):
    mesma rotina do agente Windows (log_remoto), visível nos Eventos do Agente do painel."""
    while not STOP.is_set():
        try:
            while not STOP.is_set() and log_remoto.enviar_pendentes(conf) >= log_remoto.MAX_POR_ENVIO:
                pass
        except Exception:
            pass
        STOP.wait(log_remoto.INTERVALO_ENVIO_S)

def enviar_logs_restantes(conf):
    """Última tentativa de envio ao parar (reinício, OTA), para não perder as últimas linhas."""
    try:
        log_remoto.enviar_pendentes(conf)
    except Exception:
        pass

def main():
    logging.basicConfig(level=os.getenv("TRILAN_LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    signal.signal(signal.SIGINT, lambda *_: STOP.set())
    conf = load_conf()
    log_remoto.instalar(conf)
    threading.Thread(target=logs_loop, args=(conf,), daemon=True).start()
    if not conf["server_url"].startswith("https://") and not enabled("TRILAN_ALLOW_INSECURE_HTTP"):
        raise RuntimeError("HTTPS required (HTTP override for isolated testing only)")
    LOG.info("Agente Linux iniciando; backups=%s fuso=%s", backups_ligados(),
             time.strftime("%Z %z"))
    hour, minute = schedule(conf)
    pending = threading.Event()
    threading.Thread(target=heartbeat, args=(conf, pending), daemon=True).start()
    # O Mikrotik é ponte leve: a imagem da noite só sai quando pedida na Galeria. O ciclo automático da madrugada
    # (decodifica um frame de cada câmera a cada 10 min) liga só com TRILAN_NOITE_AUTOMATICA=true.
    if enabled("TRILAN_NOITE_AUTOMATICA"):
        threading.Thread(target=noite_loop, args=(conf,), daemon=True).start()
    threading.Thread(target=vigia_backup_loop, args=(conf,), daemon=True).start()
    iniciar_coletas(conf)
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
        scheduled = backups_ligados() and (
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
    enviar_logs_restantes(conf)
    return exit_code

if __name__ == "__main__":
    sys.exit(main())
