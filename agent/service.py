"""
Trilan NVR Backup Agent — Windows Service
Runs agent.py on a schedule and listens for manual trigger events.

Install:  python service.py install
Start:    python service.py start
Stop:     python service.py stop
Remove:   python service.py remove
"""
import os
import queue
import sys
import threading
import time
import traceback
import logging
from datetime import datetime, timedelta
from pathlib import Path

import win32event
import win32service
import win32serviceutil
import servicemanager
import win32security

# Imports explicitos para o PyInstaller não perder dependências em imports dinâmicos
import src.camera.rtsp_client
import src.application.api_client

DIRETORIO = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
EVENTO_BACKUP_MANUAL = r"Global\TrilanAgentNVR_RunNow"
# O dashboard estima o "Próximo contato" como last_seen + este intervalo (AGENT_PING_INTERVAL_MS)
PING_INTERVAL_S = 15

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
        # Manual-reset: a thread de ping e o loop principal esperam no mesmo evento de parada
        self.hWaitStop = win32event.CreateEvent(None, 1, 0, None)
        self.hPingResp = win32event.CreateEvent(None, 0, 0, None)
        self.ping_responses = queue.Queue()
        self.last_backup_finished_at = 0.0

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
        # Tenta carregar a versão do updater se possível
        try:
            from src.application.updater import get_current_version
            v = get_current_version()
        except Exception:
            v = "Desconhecida"

        log("=" * 60)
        log(f"TRILAN AGENT NVR INICIADO (Versão: {v})")
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

        from src.core.config import load_conf, ConfigError, parse_config_extra
        from src.application.api_client import fetch_server_config

        log(f"Lendo configuracoes de: {DIRETORIO / 'agent.conf'}")
        try:
            conf = load_conf()
        except ConfigError as e:
            log(str(e), is_error=True)
            return

        log(f"Servidor configurado: {conf['server_url']}")
        log(f"Client ID: {conf['client_id']}")

        config_loaded = True
        log(f"Testando comunicacao com o servidor: {conf['server_url']}/api/v1/agent/config ...")
        try:
            server_cfg = fetch_server_config(conf)
            hora = int(server_cfg.get("backup_hour", 2))
            minuto = int(server_cfg.get("backup_minute", 0))
            log("COMUNICACAO BEM SUCEDIDA! Configuracoes do servidor recebidas.")
            
            # Start Webhook for Digifort/Defense if needed
            for eq in server_cfg.get("equipamentos", []):
                tipo = (eq.get("tipo") or "").upper()
                if tipo == "DIGIFORT":
                    # config_extra é anulável no banco; uma exceção aqui marcaria config_loaded=False e causaria restart em loop
                    cfg_ext = parse_config_extra(eq)
                    caminho_csv = cfg_ext.get("caminho_csv", "")
                    caminho_log = cfg_ext.get("caminho_log_csv", "")
                    
                    try:
                        from src.application.webhook_digifort import start_webhook
                        start_webhook(caminho_csv, caminho_log)
                        log("Agente Webhook Digifort integrado e iniciado com sucesso.")
                    except Exception as e:
                        log(f"Falha ao iniciar Agente Webhook Digifort: {e}", is_error=True)
                
                elif tipo == "DEFENSE":
                    try:
                        from src.application.webhook_defense import start_webhook_defense
                        start_webhook_defense()
                        log("Agente Webhook Defense IA iniciado com sucesso na porta 8181.")
                    except Exception as e:
                        log(f"Falha ao iniciar Agente Webhook Defense IA: {e}", is_error=True)
        except Exception as e:
            log(f"FALHA na comunicacao com o servidor: {e}", is_error=True)
            log("Usando horario padrao 02:00 para o proximo backup.")
            hora, minuto = 2, 0
            config_loaded = False

        headers = {"X-Client-ID": conf["client_id"], "X-API-Key": conf["api_key"]}
        self._run_loop(hora, minuto, conf["server_url"], headers, conf, config_loaded)

    def _restart_service(self):
        import subprocess
        subprocess.Popen(
            ["cmd", "/c", "ping 127.0.0.1 -n 4 >nul && sc start TrilanAgentNVR"],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
        )
        self.stop_requested = True
        win32event.SetEvent(self.hWaitStop)

    @staticmethod
    def _resumo_ping(ping_resp) -> str:
        """Resumo do ping seguro para log (rtsp_task contem usuario/senha da camera)."""
        if not isinstance(ping_resp, dict):
            return "<resposta invalida>"
        resumo = {k: v for k, v in ping_resp.items() if k != "rtsp_task"}
        task = ping_resp.get("rtsp_task")
        if task:
            t = task if isinstance(task, dict) else {}
            resumo["rtsp_task"] = {k: t.get(k) for k in ("equipamento_id", "ip", "canal", "modo")}
        return str(resumo)

    def _ping_loop(self, conf: dict):
        """Pinga em cadência fixa (início a início), independente de backups em andamento no loop principal."""
        from src.application.api_client import ping_server

        last_successful_ping = time.monotonic()
        proximo_ping = time.monotonic()
        while not self.stop_requested:
            proximo_ping += PING_INTERVAL_S
            try:
                ping_resp = ping_server(conf)
                if ping_resp:
                    log(f"Ping recebido pelo servidor. Instrucoes: {self._resumo_ping(ping_resp)}")
                    if time.monotonic() - last_successful_ping > 300:
                        log("Servidor voltou a responder apos periodo de desconexao!")
                    last_successful_ping = time.monotonic()
                    self.ping_responses.put(ping_resp)
                    win32event.SetEvent(self.hPingResp)
                else:
                    log("Ping enviado, mas resposta vazia.")
            except Exception as e:
                log(f"Falha ao enviar ping para o servidor (tentara novamente em {PING_INTERVAL_S}s): {e}", is_error=True)

            espera = proximo_ping - time.monotonic()
            if espera < 0:
                # Ping demorou mais que o intervalo (timeout de rede): realinha a partir de agora
                proximo_ping = time.monotonic()
                espera = 0
            if win32event.WaitForSingleObject(self.hWaitStop, int(espera * 1000)) == win32event.WAIT_OBJECT_0:
                return

    def _disparar_rtsp(self, ping_resp: dict, conf: dict):
        """Dispara em thread o teste RTSP pedido pelo dashboard, se houver."""
        task = ping_resp.get("rtsp_task")
        if not task:
            return
        log("Teste RTSP solicitado pelo dashboard! Iniciando teste local...")
        from src.camera.rtsp_client import executar_tarefa_rtsp
        from src.application.api_client import send_rtsp_result

        def run_and_send_rtsp(task=task):
            try:
                result = executar_tarefa_rtsp(task)
                send_rtsp_result(conf, result)
                log(f"Teste RTSP concluído e enviado: sucesso={result['success']}")
            except Exception as e:
                log(f"Falha no teste RTSP: {e}", is_error=True)

        threading.Thread(target=run_and_send_rtsp, daemon=True).start()

    def _process_ping_responses(self, agent_mod, conf: dict, config_loaded: bool) -> bool:
        """Executa as instruções recebidas nos pings. Retorna True se o serviço deve encerrar."""
        from src.application.updater import check_and_apply_update

        while True:
            try:
                ping_resp = self.ping_responses.get_nowait()
            except queue.Empty:
                return False

            # Se ligou sem internet/servidor, reinicia agora para baixar a config correta
            if not config_loaded:
                log("Servidor voltou a responder! Reiniciando servico para buscar configuracoes e horario corretos...")
                self._restart_service()
                return True

            self._disparar_rtsp(ping_resp, conf)

            if ping_resp.get("restart"):
                log("Reinicio solicitado pelo dashboard. Agendando reinicio do servico...")
                self._restart_service()
                return True

            if ping_resp.get("backup"):
                log("Geracao de backup manual solicitada pelo dashboard!")
                self._executar_backup(agent_mod, "manual_dashboard")
                # Drena quaisquer pings repetidos com comando de backup que acumularam na fila durante a execução
                backup_drained = 0
                while not self.ping_responses.empty():
                    try:
                        discarded = self.ping_responses.get_nowait()
                        self._disparar_rtsp(discarded, conf)
                        if discarded.get("restart"):
                            self._restart_service()
                            return True
                        if discarded.get("backup"):
                            backup_drained += 1
                    except queue.Empty:
                        break
                if backup_drained > 0:
                    log(f"Descartadas {backup_drained} instrucoes repetidas de backup acumuladas durante a execucao.")

            try:
                atualizou = check_and_apply_update(conf)
            except Exception:
                log(f"[OTA] Erro inesperado na verificacao de atualizacao:\n{traceback.format_exc()}", is_error=True)
                atualizou = False
            if atualizou:
                log("[OTA] Nova versao baixada e aplicada. Aguardando reinicio do servico...")
                self.stop_requested = True
                win32event.SetEvent(self.hWaitStop)
                return True

    def _run_loop(self, hora: int, minuto: int, server_url: str, headers: dict, conf: dict, config_loaded: bool = True):
        import agent as agent_mod

        threading.Thread(target=self._ping_loop, args=(conf,), daemon=True).start()

        while not self.stop_requested:
            agora = datetime.now()
            proximo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
            if proximo <= agora:
                proximo += timedelta(days=1)
            log(f"Proximo backup: {proximo.strftime('%d/%m/%Y %H:%M')}")

            while not self.stop_requested:
                segundos = (proximo - datetime.now()).total_seconds()
                if segundos <= 0:
                    self._executar_backup(agent_mod, "scheduled")
                    break

                # Reduzido de 60s para 5s para que o Agente consiga capturar os pings e comandos RTSP a tempo
                espera_ms = int(min(segundos, 5) * 1000)
                resultado = win32event.WaitForMultipleObjects(
                    [self.hWaitStop, self.hBackupManual, self.hPingResp], False, espera_ms
                )
                if resultado == win32event.WAIT_OBJECT_0:
                    return
                elif resultado == win32event.WAIT_OBJECT_0 + 1:
                    self._executar_backup(agent_mod, "manual")
                elif resultado == win32event.WAIT_OBJECT_0 + 2:
                    if self._process_ping_responses(agent_mod, conf, config_loaded):
                        return

    def _executar_backup(self, agent_mod, trigger: str):
        if self.stop_requested:
            return
        agora = time.monotonic()
        if agora - getattr(self, "last_backup_finished_at", 0.0) < 60:
            log(f"IGNORANDO BACKUP DUPLICADO ({trigger}) — Ultimo backup finalizou ha menos de 60 segundos.")
            return

        log(f"INICIANDO BACKUP — {trigger.upper()}")
        try:
            agent_mod.run_backup(trigger)
            self.last_backup_finished_at = time.monotonic()
            log("BACKUP FINALIZADO.")
        except Exception:
            self.last_backup_finished_at = time.monotonic()
            log(f"ERRO NO BACKUP:\n{traceback.format_exc()}", is_error=True)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(TrilanAgentService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(TrilanAgentService)

