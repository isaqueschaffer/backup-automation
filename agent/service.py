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


# Janela após a troca do TrilanAgentTray.exe em que o serviço ainda a reabre ao iniciar.
# Só reabre se o arquivo foi trocado agora (atualização), para não reabrir uma bandeja que o usuário fechou.
JANELA_REABRIR_BANDEJA_S = 15 * 60


def reabrir_bandeja_atualizada():
    """A atualização OTA fecha a bandeja para trocar o arquivo e não a abre de novo.

    O serviço roda como SYSTEM na sessão 0 e não consegue mostrar janelas; por isso a bandeja é
    iniciada como o usuário de cada sessão logada (console ou RDP) que ainda não a tem aberta.
    """
    tray = DIRETORIO / "TrilanAgentTray.exe"
    try:
        if not tray.exists() or time.time() - tray.stat().st_mtime > JANELA_REABRIR_BANDEJA_S:
            return
        import win32process
        import win32profile
        import win32ts

        servidor = win32ts.WTS_CURRENT_SERVER_HANDLE
        com_bandeja = {
            sessao for (sessao, _pid, nome, _sid) in win32ts.WTSEnumerateProcesses(servidor, 1, 0)
            if (nome or "").lower() == "trilanagenttray.exe"
        }
        for info in win32ts.WTSEnumerateSessions(servidor, 1, 0):
            sessao = info["SessionId"]
            if sessao == 0 or sessao in com_bandeja:
                continue
            if info["State"] not in (win32ts.WTSActive, win32ts.WTSDisconnected):
                continue
            token = None
            try:
                token = win32ts.WTSQueryUserToken(sessao)  # requer SYSTEM (privilégio SE_TCB)
                ambiente = win32profile.CreateEnvironmentBlock(token, False)
                si = win32process.STARTUPINFO()
                si.lpDesktop = "winsta0\\default"
                win32process.CreateProcessAsUser(
                    token, str(tray), None, None, None, False,
                    win32process.CREATE_UNICODE_ENVIRONMENT | win32process.NORMAL_PRIORITY_CLASS,
                    ambiente, str(DIRETORIO), si,
                )
                log(f"Bandeja reaberta apos atualizacao na sessao {sessao}.")
            except Exception as e:
                log(f"Nao foi possivel reabrir a bandeja na sessao {sessao}: {e}", is_error=True)
            finally:
                if token is not None:
                    token.Close()
    except Exception as e:
        log(f"Falha ao verificar a bandeja apos atualizacao: {e}", is_error=True)


# Script que religa o serviço depois do "Reiniciar" do painel. Roda fora do processo do serviço.
# Espera o processo antigo sair de verdade (o executável leva alguns segundos para encerrar),
# tenta iniciar até 5 vezes, confere se subiu e registra tudo em reinicio.log.
SCRIPT_REINICIO = r"""
$svc = 'TrilanAgentNVR'
$log = '__LOG__'
function L($m) { Add-Content -Path $log -Encoding UTF8 -Value ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m) }
$antigo = __PID__
L "Reinicio pedido pelo painel. Aguardando o processo $antigo encerrar..."
$t = 0
while ($t -lt 90 -and (Get-Process -Id $antigo -ErrorAction SilentlyContinue)) { Start-Sleep -Seconds 1; $t++ }
L "Processo antigo encerrado apos ${t}s."
for ($i = 1; $i -le 5; $i++) {
    Start-Sleep -Seconds 3
    $st = (Get-Service -Name $svc -ErrorAction SilentlyContinue).Status
    if ($st -eq 'Running') { L "Servico em execucao (tentativa $i)."; exit 0 }
    try { Start-Service -Name $svc -ErrorAction Stop; L "Start-Service enviado (tentativa $i)." }
    catch { L "Falha ao iniciar (tentativa $i): $($_.Exception.Message)" }
}
$st = (Get-Service -Name $svc -ErrorAction SilentlyContinue).Status
if ($st -eq 'Running') { L 'Servico em execucao.' } else { L "ERRO: servico nao voltou (status: $st). A recuperacao do Windows ainda pode reinicia-lo." }
"""


def garantir_recuperacao_windows():
    """Configura a recuperação do serviço no Windows (reinicia 5/10/30 s após parar com erro).

    É refeita a cada início porque máquinas instaladas por instaladores antigos não a têm.
    O reinício pelo painel depende dela como segunda garantia (ver _restart_service).
    """
    import subprocess
    try:
        r = subprocess.run(
            ["sc.exe", "failure", "TrilanAgentNVR", "reset=", "86400",
             "actions=", "restart/5000/restart/10000/restart/30000"],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=20,
        )
        if r.returncode != 0:
            log(f"Nao foi possivel configurar a recuperacao do servico: {(r.stdout or r.stderr).strip()[:200]}", is_error=True)
    except Exception as e:
        log(f"Nao foi possivel configurar a recuperacao do servico: {e}", is_error=True)

class TrilanAgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = "TrilanAgentNVR"
    _svc_display_name_ = "Trilan — Agente Backup NVR"
    _svc_description_ = "Executa backups automaticos de NVRs e envia os arquivos ao servidor Trilan."
    _svc_start_type_ = win32service.SERVICE_AUTO_START

    def __init__(self, args):
        super().__init__(args)
        self.stop_requested = False
        # Manual-reset: a thread de ping e o loop principal esperam no mesmo evento de parada
        self.hWaitStop = win32event.CreateEvent(None, 1, 0, None)
        self.hPingResp = win32event.CreateEvent(None, 0, 0, None)
        self.ping_responses = queue.Queue()
        self.last_backup_finished_at = 0.0
        self.schedule_hour = 2
        self.schedule_minute = 0
        self.config_loaded = False
        self.schedule_updated = False
        # Reinício pedido pelo painel: o processo termina com erro para a recuperação do Windows religar
        self.reiniciar_pelo_windows = False

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
        # Em thread: nunca atrasa nem derruba a inicialização do serviço
        threading.Thread(target=reabrir_bandeja_atualizada, daemon=True).start()
        threading.Thread(target=garantir_recuperacao_windows, daemon=True).start()
        try:
            self._load_schedule_and_run()
        except Exception:
            log(f"ERRO FATAL:\n{traceback.format_exc()}", is_error=True)
        log("TRILAN AGENT NVR ENCERRADO")
        log("=" * 60)
        if self.reiniciar_pelo_windows:
            # Termina sem avisar "parado" ao Windows: ele trata como falha e a recuperação configurada
            # (garantir_recuperacao_windows) religa o serviço em 5 s. É a segunda garantia, caso o
            # script de reinício (SCRIPT_REINICIO) não consiga.
            logging.shutdown()
            os._exit(1)

    def _init_webhooks(self, server_cfg: dict):
        """Inicializa integrações locais de webhook (Digifort / Defense) de forma segura."""
        from src.core.config import parse_config_extra
        for eq in server_cfg.get("equipamentos", []):
            tipo = (eq.get("tipo") or "").upper()
            if tipo == "DIGIFORT":
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

    def _load_schedule_and_run(self):
        """Load schedule from server config and run the event loop."""
        if str(DIRETORIO) not in sys.path:
            sys.path.insert(0, str(DIRETORIO))

        from src.core.config import load_conf, ConfigError
        from src.application.api_client import fetch_server_config

        log(f"Lendo configuracoes de: {DIRETORIO / 'agent.conf'}")
        try:
            conf = load_conf()
        except ConfigError as e:
            log(str(e), is_error=True)
            return

        log(f"Servidor configurado: {conf['server_url']}")
        log(f"Client ID: {conf['client_id']}")

        log(f"Testando comunicacao com o servidor: {conf['server_url']}/api/v1/agent/config ...")
        try:
            server_cfg = fetch_server_config(conf)
            self.schedule_hour = int(server_cfg.get("backup_hour", 2))
            self.schedule_minute = int(server_cfg.get("backup_minute", 0))
            self.config_loaded = True
            log("COMUNICACAO BEM SUCEDIDA! Configuracoes do servidor recebidas.")
            self._init_webhooks(server_cfg)
        except Exception as e:
            log(f"FALHA na comunicacao com o servidor: {e}", is_error=True)
            log("Usando horario padrao 02:00 para o proximo backup (sincronizara automaticamente quando a conexao voltar).")
            self.schedule_hour, self.schedule_minute = 2, 0
            self.config_loaded = False

        headers = {"X-Client-ID": conf["client_id"], "X-API-Key": conf["api_key"]}
        self._run_loop(conf["server_url"], headers, conf)

    def _restart_service(self):
        """Reinício pedido pelo painel, por dois caminhos independentes:
        1) SCRIPT_REINICIO (fora deste processo) espera o processo do serviço sair e o inicia de novo;
        2) o processo termina com erro e a recuperação do Windows o religa em 5 s.
        """
        import subprocess
        pid_servico = os.getpid()
        try:
            # No executável de arquivo único quem o Windows acompanha é o processo pai (o bootloader)
            import psutil
            pai = psutil.Process(pid_servico).parent()
            if pai is not None and pai.name().lower() == "trilanagentservice.exe":
                pid_servico = pai.pid
        except Exception:
            pass
        script = (SCRIPT_REINICIO.replace("__LOG__", str(PASTA_LOG / "reinicio.log"))
                  .replace("__PID__", str(pid_servico)))
        try:
            # Console oculto + entradas/saídas nulas. NÃO usar DETACHED_PROCESS: sem console o PowerShell
            # fecha na hora sem executar o script (era por isso que o serviço não voltava no reinício).
            subprocess.Popen(
                ["powershell.exe", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-Command", script],
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            log(f"Falha ao iniciar o script de reinicio (a recuperacao do Windows vai religar): {e}", is_error=True)
        self.reiniciar_pelo_windows = True
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

    def _process_ping_responses(self, agent_mod, conf: dict) -> bool:
        """Executa as instruções recebidas nos pings. Retorna True se o serviço deve encerrar."""
        from src.application.updater import check_and_apply_update

        while True:
            try:
                ping_resp = self.ping_responses.get_nowait()
            except queue.Empty:
                return False

            # Se ligou sem internet/servidor, busca a configuração em memória sem derrubar o serviço
            if not self.config_loaded:
                log("Servidor voltou a responder! Sincronizando configuracoes em execucao...")
                try:
                    from src.application.api_client import fetch_server_config
                    server_cfg = fetch_server_config(conf)
                    nova_hora = int(server_cfg.get("backup_hour", 2))
                    novo_minuto = int(server_cfg.get("backup_minute", 0))
                    self._init_webhooks(server_cfg)
                    self.config_loaded = True
                    if (nova_hora, novo_minuto) != (self.schedule_hour, self.schedule_minute):
                        self.schedule_hour = nova_hora
                        self.schedule_minute = novo_minuto
                        self.schedule_updated = True
                        log(f"Horario de backup atualizado com sucesso: {self.schedule_hour:02d}:{self.schedule_minute:02d}")
                    else:
                        log("Configuracoes e agendamento sincronizados com sucesso.")
                except Exception as e:
                    log(f"Falha ao sincronizar configuracoes apos reconexao: {e}", is_error=True)

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

    def _run_loop(self, server_url: str, headers: dict, conf: dict):
        import agent as agent_mod

        threading.Thread(target=self._ping_loop, args=(conf,), daemon=True).start()

        while not self.stop_requested:
            agora = datetime.now()
            proximo = agora.replace(hour=self.schedule_hour, minute=self.schedule_minute, second=0, microsecond=0)
            if proximo <= agora:
                proximo += timedelta(days=1)
            log(f"Proximo backup: {proximo.strftime('%d/%m/%Y %H:%M')}")

            while not self.stop_requested:
                # Se as configurações foram atualizadas dinamicamente, recalcula o próximo backup
                if self.schedule_updated:
                    self.schedule_updated = False
                    break

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
                    if self._process_ping_responses(agent_mod, conf):
                        return

    def _executar_backup(self, agent_mod, trigger: str):
        if self.stop_requested:
            return
        agora = time.monotonic()
        if agora - getattr(self, "last_backup_finished_at", 0.0) < 60:
            log(f"IGNORANDO BACKUP DUPLICADO ({trigger}) — Ultimo backup finalizou ha menos de 60 segundos.")
            return

        from src.application import estado
        log(f"INICIANDO BACKUP — {trigger.upper()}")
        estado.backup_em_andamento = True
        try:
            agent_mod.run_backup(trigger)
            self.last_backup_finished_at = time.monotonic()
            log("BACKUP FINALIZADO.")
        except Exception:
            self.last_backup_finished_at = time.monotonic()
            log(f"ERRO NO BACKUP:\n{traceback.format_exc()}", is_error=True)
        finally:
            estado.backup_em_andamento = False


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(TrilanAgentService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        # Se for instalação e não especificou --startup, define como auto por padrão (opções devem vir antes do comando)
        if len(sys.argv) > 1 and sys.argv[1].lower() == "install" and not any(a.startswith("--startup") for a in sys.argv):
            sys.argv.insert(1, "--startup=auto")  # pywin32 (getopt) só lê opções antes da ação
        win32serviceutil.HandleCommandLine(TrilanAgentService)
        # Após install ou update, garante inicialização automática e recuperação de falhas no Windows
        if len(sys.argv) > 1 and sys.argv[1].lower() in ("install", "update"):
            import subprocess
            try:
                subprocess.run(["sc.exe", "config", "TrilanAgentNVR", "start=", "auto"], capture_output=True)
                subprocess.run(
                    ["sc.exe", "failure", "TrilanAgentNVR", "reset=", "86400", "actions=", "restart/5000/restart/10000/restart/30000"],
                    capture_output=True
                )
            except Exception:
                pass

