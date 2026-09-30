"""
Trilan NVR Backup Agent — Windows Service
Runs agent.py on a schedule and listens for manual trigger events.

Install:  python service.py install
Start:    python service.py start
Stop:     python service.py stop
Remove:   python service.py remove
"""
import os
import sys
import traceback
import logging
from datetime import datetime, timedelta
from pathlib import Path

import win32event
import win32service
import win32serviceutil
import servicemanager
import win32security

DIRETORIO = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
EVENTO_BACKUP_MANUAL = r"Global\TrilanAgentNVR_RunNow"

# Usa ProgramData para logs — gravavel sem privilegios de admin
PASTA_LOG = Path(os.environ.get("ProgramData", "C:\\ProgramData")) / "Trilan NVR Backup Agent" / "logs"
PASTA_LOG.mkdir(parents=True, exist_ok=True)
ARQUIVO_LOG = PASTA_LOG / "servico.log"

logging.basicConfig(
    filename=str(ARQUIVO_LOG),
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def log(msg, is_error=False):
    if is_error:
        logging.error(msg)
    else:
        logging.info(msg)
    try:
        if is_error:
            servicemanager.LogErrorMsg(str(msg))
        else:
            servicemanager.LogInfoMsg(str(msg))
    except Exception:
        pass


class TrilanAgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = "TrilanAgentNVR"
    _svc_display_name_ = "Trilan — Agente Backup NVR"
    _svc_description_ = "Executa backups automaticos de NVRs e envia os arquivos ao servidor Trilan."

    def __init__(self, args):
        super().__init__(args)
        self.stop_requested = False
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)

        sec_desc = win32security.SECURITY_DESCRIPTOR()
        sec_desc.SetSecurityDescriptorDacl(1, None, 0)
        sec_attr = win32security.SECURITY_ATTRIBUTES()
        sec_attr.SECURITY_DESCRIPTOR = sec_desc
        self.hBackupManual = win32event.CreateEvent(sec_attr, 0, 0, EVENTO_BACKUP_MANUAL)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        log("Parada solicitada.")
        self.stop_requested = True
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        log("=" * 60)
        log("TRILAN AGENT NVR INICIADO")
        log(f"Diretorio: {DIRETORIO}")
        try:
            self._load_schedule_and_run()
        except Exception:
            log(f"ERRO FATAL:\n{traceback.format_exc()}", is_error=True)
        log("TRILAN AGENT NVR ENCERRADO")
        log("=" * 60)

    def _load_schedule_and_run(self):
        """Load schedule from server config and run the event loop."""
        if str(DIRETORIO) not in sys.path:
            sys.path.insert(0, str(DIRETORIO))

        import configparser
        import requests

        conf_file = DIRETORIO / "agent.conf"
        log(f"Lendo configuracoes de: {conf_file}")
        if not conf_file.exists():
            log(f"ERRO FATAL: Arquivo de configuracao {conf_file} nao encontrado!", is_error=True)
            return

        cfg = configparser.ConfigParser()
        cfg.read(conf_file, encoding="utf-8-sig")
        server_url = cfg["server"]["url"].rstrip("/")
        client_id = cfg["auth"]["client_id"]
        api_key = cfg["auth"]["api_key"]

        log(f"Servidor configurado: {server_url}")
        log(f"Client ID: {client_id}")

        headers = {"X-Client-ID": client_id, "X-API-Key": api_key}
        log(f"Testando comunicacao com o servidor: {server_url}/api/v1/agent/config ...")
        config_loaded = True
        try:
            r = requests.get(f"{server_url}/api/v1/agent/config", headers=headers,
                             timeout=30, verify=False)
            r.raise_for_status()
            server_cfg = r.json()
            hora = int(server_cfg.get("backup_hour", 2))
            minuto = int(server_cfg.get("backup_minute", 0))
            log("COMUNICACAO BEM SUCEDIDA! Configuracoes do servidor recebidas.")
        except Exception as e:
            log(f"FALHA na comunicacao com o servidor: {e}", is_error=True)
            log("Usando horario padrao 02:00 para o proximo backup.")
            hora, minuto = 2, 0
            config_loaded = False

        self._run_loop(hora, minuto, server_url, headers, config_loaded)

    def _restart_service(self):
        import subprocess
        subprocess.Popen(
            ["cmd", "/c", "ping 127.0.0.1 -n 4 >nul && sc start TrilanAgentNVR"],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
        )
        self.stop_requested = True
        win32event.SetEvent(self.hWaitStop)

    def _run_loop(self, hora: int, minuto: int, server_url: str, headers: dict, config_loaded: bool = True):
        import agent as agent_mod
        import requests
        import time

        last_ping_time = 0
        last_successful_ping = time.time()

        while not self.stop_requested:
            agora = datetime.now()
            proximo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
            if proximo <= agora:
                proximo += timedelta(days=1)
            log(f"Proximo backup: {proximo.strftime('%d/%m/%Y %H:%M')}")

            while not self.stop_requested:
                agora = datetime.now()
                
                # Envia ping a cada 5 minutos (300s) se online, ou a cada 10 minutos (600s) se offline
                intervalo_ping = 300 if (time.time() - last_successful_ping < 300) else 600
                
                if time.time() - last_ping_time >= intervalo_ping:
                    try:
                        ping_resp = requests.post(
                            f"{server_url}/api/v1/agent/ping",
                            headers=headers, timeout=10, verify=False,
                        )
                        ping_resp.raise_for_status()
                        
                        if time.time() - last_successful_ping > 300 and config_loaded:
                            log("Servidor voltou a responder apos periodo de desconexao!")

                        last_ping_time = time.time()
                        last_successful_ping = time.time()
                        
                        # Se ligou sem internet/servidor, reinicia agora para baixar a config correta
                        if not config_loaded:
                            log("Servidor voltou a responder! Reiniciando servico para buscar configuracoes e horario corretos...")
                            self._restart_service()
                            return
                        
                        # Verifica se o servidor solicitou reinicio
                        if ping_resp.ok and ping_resp.json().get("restart"):
                            log("Reinicio solicitado pelo dashboard. Agendando reinicio do servico...")
                            self._restart_service()
                            return
                    except Exception as e:
                        log(f"Falha na conexao com o servidor (tentando novamente em 10 minutos): {e}", is_error=True)
                        last_ping_time = time.time()
                
                segundos = (proximo - agora).total_seconds()
                if segundos <= 0:
                    self._executar_backup(agent_mod, "scheduled")
                    break

                espera_ms = int(min(segundos, 60) * 1000)
                resultado = win32event.WaitForMultipleObjects(
                    [self.hWaitStop, self.hBackupManual], False, espera_ms
                )
                if resultado == win32event.WAIT_OBJECT_0:
                    return
                elif resultado == win32event.WAIT_OBJECT_0 + 1:
                    self._executar_backup(agent_mod, "manual")

    def _executar_backup(self, agent_mod, trigger: str):
        if self.stop_requested:
            return
        log(f"INICIANDO BACKUP — {trigger.upper()}")
        try:
            agent_mod.run_backup(trigger)
            log("BACKUP FINALIZADO.")
        except Exception:
            log(f"ERRO NO BACKUP:\n{traceback.format_exc()}", is_error=True)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(TrilanAgentService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(TrilanAgentService)
