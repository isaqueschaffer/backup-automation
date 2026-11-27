import logging
import math
import ssl
import threading
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import urlsplit

TIMEOUT_SERVER = 120

# ── Conexão com o servidor da Trilan (AGT-02, auditoria de 25/11/2026) ─────────────────────────────────────
# Todas as chamadas à API do servidor (conf["server_url"]) passam por _requisitar: uma Session única, os cabeçalhos
# de autenticação montados num lugar só e o certificado VALIDADO. Os equipamentos da LAN (NVR, câmeras, OLT...) têm
# certificado autoassinado e continuam com verify=False nos módulos deles: isto aqui vale só para o servidor.
#
# Fallback: um agente em campo pode estar com https:// para um endereço cujo certificado não valida (IP, domínio
# interno). Exigir a validação de uma vez cortaria o contato dele com o servidor e com a OTA, sem conserto remoto.
# Por isso, na primeira falha de VERIFICAÇÃO do certificado, o processo avisa no log (uma vez) e segue sem validar
# até reiniciar, como nas versões anteriores. Os avisos chegam ao painel (log remoto) e mostram quais máquinas
# precisam de ajuste antes de a validação passar a ser obrigatória. Outros erros de TLS (conexão caída no meio do
# handshake etc.) não ligam o modo inseguro: são passageiros e desligar a validação não os resolve.
log = logging.getLogger("trilan.api")

_sessao: requests.Session | None = None
_trava = threading.Lock()
_tls_inseguro = False          # True depois da 1ª falha de certificado: o processo segue sem validar
_avisos_dados: set[str] = set()


def _obter_sessao() -> requests.Session:
    global _sessao
    with _trava:
        if _sessao is None:
            _sessao = requests.Session()
        return _sessao


def _cabecalhos(conf: dict, extra: dict | None = None) -> dict:
    headers = {"X-Client-ID": conf["client_id"], "X-API-Key": conf["api_key"]}
    if extra:
        headers.update(extra)
    return headers


def _url(conf: dict, caminho: str) -> str:
    return f"{str(conf['server_url']).rstrip('/')}{caminho}"


def _avisar_uma_vez(chave: str, mensagem: str) -> None:
    with _trava:
        if chave in _avisos_dados:
            return
        _avisos_dados.add(chave)
    # O aviso pode nascer dentro do envio de logs (send_logs), onde o log remoto descarta tudo para não entrar em
    # laço. Enfileirar não faz HTTP, então liberamos só esta linha para ela chegar ao painel.
    try:
        from src.application import log_remoto
        ctx = log_remoto._contexto_thread
    except Exception:
        ctx = None
    anterior = getattr(ctx, "enviando_logs", False) if ctx is not None else False
    try:
        if ctx is not None:
            ctx.enviando_logs = False
        log.warning(mensagem, extra={"enviar_servidor": True})
    finally:
        if ctx is not None:
            ctx.enviando_logs = anterior


def _falha_de_certificado(exc: BaseException) -> bool:
    """True quando o SSLError é a verificação do certificado (autoassinado, CA desconhecida, vencido, nome/IP que
    não bate). Percorre a cadeia de exceções (requests -> urllib3 -> ssl)."""
    vistos = set()
    pendentes = [exc]
    while pendentes:
        e = pendentes.pop()
        if e is None or id(e) in vistos:
            continue
        vistos.add(id(e))
        if isinstance(e, ssl.SSLCertVerificationError) or type(e).__name__ == "CertificateError":
            return True
        texto = str(e).lower()
        if "certificate verify failed" in texto or "hostname mismatch" in texto or "doesn't match" in texto:
            return True
        pendentes.extend([getattr(e, "__cause__", None), getattr(e, "__context__", None),
                          getattr(e, "reason", None)])
        pendentes.extend(a for a in getattr(e, "args", ()) if isinstance(a, BaseException))
    return False


def _ativar_tls_inseguro(url: str, exc: BaseException) -> None:
    global _tls_inseguro
    with _trava:
        _tls_inseguro = True
    host = urlsplit(url).netloc or url
    _avisar_uma_vez(
        "tls-inseguro",
        f"[TLS] O certificado do servidor {host} não pôde ser validado ({type(exc).__name__}). O agente vai "
        f"continuar SEM validar o certificado até reiniciar (modo inseguro, como nas versões anteriores). "
        f"Ajuste a URL do servidor no agent.conf para https://server.suportetrilan.com.br (ou instale um "
        f"certificado válido): uma versão futura vai exigir a validação e esta máquina perderá o contato.",
    )


def _requisitar(conf: dict, metodo: str, caminho: str, *, headers_extra: dict | None = None,
                ao_repetir=None, **kwargs) -> requests.Response:
    """Chamada à API do servidor. `ao_repetir` (opcional) prepara o corpo para a 2ª tentativa (ex.: f.seek(0))."""
    url = _url(conf, caminho)
    headers = _cabecalhos(conf, headers_extra)
    sessao = _obter_sessao()
    if url.lower().startswith("http://"):
        _avisar_uma_vez(
            "http",
            f"[TLS] A URL do servidor ({urlsplit(url).netloc}) usa http://, sem criptografia: a API Key e os "
            f"backups trafegam abertos na rede. Troque para https://server.suportetrilan.com.br no agent.conf.",
        )
        return sessao.request(metodo, url, headers=headers, **kwargs)
    if _tls_inseguro:
        return sessao.request(metodo, url, headers=headers, verify=False, **kwargs)
    try:
        return sessao.request(metodo, url, headers=headers, verify=True, **kwargs)
    except requests.exceptions.SSLError as e:
        if not _falha_de_certificado(e):
            raise
        # A verificação falha no handshake, antes de o corpo sair: um iterador (upload em fluxo) ainda está intacto.
        _ativar_tls_inseguro(url, e)
        if ao_repetir is not None:
            ao_repetir()
        return sessao.request(metodo, url, headers=headers, verify=False, **kwargs)


def _post(conf: dict, caminho: str, **kwargs) -> requests.Response:
    return _requisitar(conf, "POST", caminho, **kwargs)


# ── Novas tentativas no fim do backup (26/11/2026) ─────────────────────────────────────────────────────────────
# Na Horizontes, uma queda de DNS de menos de 1 minuto bem no fim do backup fez o relatório falhar e o agente
# descartou a rodada inteira (6 equipamentos OK). O relatório e o ZIP agora são tentados de novo, mas SÓ quando o
# pedido com certeza não chegou ao servidor: DNS, conexão recusada, tempo de conexão esgotado, ou 502/503 do proxy
# (Dokploy/Traefik com o backend fora). Um tempo de leitura esgotado ou uma conexão que caiu no meio não entram:
# o servidor pode ter gravado o relatório, e repetir criaria um backup duplicado e avançaria a fila do Cliente duas
# vezes.
ESPERAS_NOVA_TENTATIVA_S = (30, 60, 120, 240)  # ~7,5 min no total, além das 5 tentativas
_STATUS_SEM_PROCESSAR = (502, 503)


def _nao_chegou_ao_servidor(exc: BaseException) -> bool:
    """True quando o erro é anterior ao envio do pedido (nada foi processado no servidor). Percorre a cadeia de
    exceções (requests -> urllib3 MaxRetryError -> NewConnectionError/NameResolutionError)."""
    from urllib3.exceptions import ConnectTimeoutError, NewConnectionError

    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return True
    if not isinstance(exc, requests.exceptions.ConnectionError) or isinstance(exc, requests.exceptions.SSLError):
        return False
    vistos = set()
    pendentes = [exc]
    while pendentes:
        e = pendentes.pop()
        if e is None or id(e) in vistos:
            continue
        vistos.add(id(e))
        # NameResolutionError (urllib3 2.x) é subclasse de NewConnectionError
        if isinstance(e, (NewConnectionError, ConnectTimeoutError)):
            return True
        pendentes.extend([getattr(e, "__cause__", None), getattr(e, "__context__", None),
                          getattr(e, "reason", None)])
        pendentes.extend(a for a in getattr(e, "args", ()) if isinstance(a, BaseException))
    texto = str(exc)
    return any(t in texto for t in ("NameResolutionError", "NewConnectionError", "getaddrinfo failed",
                                    "Failed to resolve"))


def _com_novas_tentativas_servidor(fazer, descricao: str, esperas=None) -> requests.Response:
    """Roda `fazer()` (uma chamada ao servidor que devolve a Response) e repete após cada espera de
    `ESPERAS_NOVA_TENTATIVA_S` enquanto o pedido não chegou ao servidor. Esgotadas as tentativas, levanta o último
    erro ou devolve a última resposta (502/503), para quem chamou tratar como antes."""
    import time

    esperas = ESPERAS_NOVA_TENTATIVA_S if esperas is None else esperas
    for tentativa in range(len(esperas) + 1):
        ultima = tentativa == len(esperas)
        try:
            r = fazer()
        except Exception as e:
            if ultima or not _nao_chegou_ao_servidor(e):
                raise
            motivo = f"{type(e).__name__}: servidor inacessível"
        else:
            if ultima or r.status_code not in _STATUS_SEM_PROCESSAR:
                return r
            motivo = f"HTTP {r.status_code}"
        espera = esperas[tentativa]
        logging.warning(f"  {descricao}: {motivo}. Nova tentativa em {espera}s "
                        f"({tentativa + 2}/{len(esperas) + 1}).")
        time.sleep(espera)
    raise AssertionError("inalcançável")


def _get(conf: dict, caminho: str, **kwargs) -> requests.Response:
    return _requisitar(conf, "GET", caminho, **kwargs)


def fetch_server_config(conf: dict) -> dict:
    url = _url(conf, "/api/v1/agent/config")
    r = _get(conf, "/api/v1/agent/config", timeout=30)
    r.raise_for_status()
    try:
        return r.json()
    except ValueError as e:
        logging.error(f"Resposta do servidor nao é um JSON valido. Verifique a URL do servidor e a porta.")
        logging.error(f"URL acessada: {url}")
        logging.error(f"Status Code: {r.status_code}")
        logging.error(f"Conteudo recebido: {r.text[:200]}")
        raise RuntimeError("Servidor retornou uma resposta invalida (provavelmente HTML em vez de JSON).") from e

def _get_telemetry() -> dict:
    telemetry = {}
    try:
        import psutil
        
        # Leitura inicial de rede (por placa)
        net_start = psutil.net_io_counters(pernic=True)
        
        # Medição de CPU (espera 1 segundo)
        telemetry["cpu_percent"] = psutil.cpu_percent(interval=1)
        
        # Leitura final de rede após 1 segundo
        net_end = psutil.net_io_counters(pernic=True)
        stats = psutil.net_if_stats()
        
        networks = []
        for nic, start_io in net_start.items():
            if not stats.get(nic) or not stats[nic].isup:
                continue
            if "Loopback" in nic or "Pseudo" in nic:
                continue
            end_io = net_end.get(nic)
            if not end_io: continue
            
            bytes_sent_sec = end_io.bytes_sent - start_io.bytes_sent
            bytes_recv_sec = end_io.bytes_recv - start_io.bytes_recv
            
            networks.append({
                "name": nic,
                "mbps_sent": round((bytes_sent_sec * 8) / 1_000_000, 2),
                "mbps_recv": round((bytes_recv_sec * 8) / 1_000_000, 2)
            })
        
        telemetry["networks"] = networks
        
        mem = psutil.virtual_memory()
        telemetry["ram_percent"] = mem.percent
        telemetry["ram_total_gb"] = round(mem.total / (1024 ** 3), 2)
        telemetry["ram_used_gb"] = round(mem.used / (1024 ** 3), 2)
        
        # Coleta de todos os discos / partições montadas
        disks = []
        try:
            partitions = psutil.disk_partitions(all=False)
        except Exception as e:
            logging.error(f"Erro ao listar particoes de disco: {e}")
            partitions = []

        seen_mountpoints = set()
        for p in partitions:
            norm_mount = (p.mountpoint or "").strip().upper()
            if not norm_mount or norm_mount in seen_mountpoints:
                continue
            if 'cdrom' in p.opts or not p.fstype:
                continue
            try:
                usage = psutil.disk_usage(p.mountpoint)
                seen_mountpoints.add(norm_mount)
                
                device_name = p.device.rstrip('\\') if p.device else p.mountpoint.rstrip('\\')
                if not device_name:
                    device_name = p.mountpoint
                
                disks.append({
                    "device": device_name,
                    "mountpoint": p.mountpoint,
                    "fstype": p.fstype,
                    "percent": usage.percent,
                    "total_gb": round(usage.total / (1024 ** 3), 2),
                    "used_gb": round(usage.used / (1024 ** 3), 2),
                    "free_gb": round(usage.free / (1024 ** 3), 2)
                })
            except Exception:
                continue

        # Mantém compatibilidade com versões anteriores da UI/API
        if disks:
            c_disk = next((d for d in disks if d["mountpoint"].upper().startswith("C:")), disks[0])
            telemetry["disk_percent"] = c_disk["percent"]
            telemetry["disk_total_gb"] = c_disk["total_gb"]
            telemetry["disk_free_gb"] = c_disk["free_gb"]
        else:
            try:
                disk = psutil.disk_usage('C:\\')
                telemetry["disk_percent"] = disk.percent
                telemetry["disk_total_gb"] = round(disk.total / (1024 ** 3), 2)
                telemetry["disk_free_gb"] = round(disk.free / (1024 ** 3), 2)
                disks.append({
                    "device": "C:",
                    "mountpoint": "C:\\",
                    "fstype": "NTFS",
                    "percent": disk.percent,
                    "total_gb": round(disk.total / (1024 ** 3), 2),
                    "used_gb": round(disk.used / (1024 ** 3), 2),
                    "free_gb": round(disk.free / (1024 ** 3), 2)
                })
            except Exception:
                pass

        telemetry["disks"] = disks
    except Exception as e:
        logging.error(f"Erro ao coletar psutil: {e}")
        
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            gpu = gpus[0]
            telemetry["gpu_percent"] = round(gpu.load * 100, 1)
            telemetry["gpu_memory_total"] = gpu.memoryTotal
            telemetry["gpu_memory_used"] = gpu.memoryUsed
            telemetry["gpu_name"] = gpu.name
    except Exception as e:
        pass # Ignora se nao tiver GPUtil ou GPU
        
    # O servidor não fecha a rodada do Cliente enquanto a máquina ainda está fazendo o backup
    from src.application import estado
    telemetry["backup_em_andamento"] = estado.backup_em_andamento
    # Há quanto tempo: o servidor deixa de esperar um backup que passou do razoável (travado) para reiniciar
    telemetry["backup_ha_min"] = estado.backup_ha_min()
    return telemetry

def _json_safe(obj):
    # GPUtil devolve NaN para campos "[N/A]" do nvidia-smi; NaN quebra o JSON e derrubaria o ping inteiro
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj

def ping_server(conf: dict, recursos_extra: tuple = ()) -> dict:
    """Envia um ping para o servidor para manter o status online. Usa long-polling."""
    try:
        telemetry = _json_safe(_get_telemetry())
    except Exception as e:
        logging.error(f"Telemetria ignorada neste ping: {e}")
        telemetry = None
    # "recursos": o servidor só entrega o "Testar conexão" a quem declara saber executá-lo (agente >= 1.1.44)
    # "versao": o servidor guarda e o painel mostra em Configuração da Máquina (agente >= 1.1.49)
    from src.application.updater import CURRENT_VERSION
    # `recursos_extra`: o que só o serviço do Windows executa (ex.: "comando_alarme", >= 1.1.50); o do Linux não manda
    payload = {"telemetry": telemetry, "recursos": ["teste_conexao", *recursos_extra], "versao": CURRENT_VERSION}
    r = _post(conf, "/api/v1/agent/ping", timeout=40, json=payload)
    r.raise_for_status()
    return r.json()

def send_rtsp_result(conf: dict, result: dict) -> bool:
    try:
        r = _post(conf, "/api/v1/agent/rtsp-result", json=result, timeout=60)
        r.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"Erro ao enviar resultado RTSP: {e}")
        return False

def send_conexao_progresso(conf: dict, estado: dict) -> bool:
    """Andamento do "Testar conexão" (estado inteiro a cada etapa)."""
    try:
        r = _post(conf, "/api/v1/agent/conexao-progresso", json=estado, timeout=20)
        r.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"Erro ao enviar o progresso do teste de conexao: {e}")
        return False

def upload_night_image(conf: dict, payload: dict) -> bool:
    try:
        r = _post(conf, "/api/v1/agent/nvr-cameras/night-image", json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        if data.get("status") == "error":
            logging.error(f"Erro na API (night image): {data.get('message')}")
            return False
        return True
    except Exception as e:
        logging.error(f"Erro ao enviar night image: {e}")
        return False

def send_presenca_cameras(conf: dict, equipamentos: list) -> bool:
    try:
        r = _post(conf, "/api/v1/agent/cameras/status", json={"equipamentos": equipamentos}, timeout=60)
        r.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"Erro ao enviar presenca de cameras: {e}")
        return False


def send_status_olts(conf: dict, equipamentos: list) -> bool:
    try:
        r = _post(conf, "/api/v1/agent/olt/status", json={"equipamentos": equipamentos}, timeout=60)
        r.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"Erro ao enviar status das OLTs: {e}")
        return False


def send_status_antenas(conf: dict, equipamentos: list) -> bool:
    try:
        r = _post(conf, "/api/v1/agent/antenas/status", json={"equipamentos": equipamentos}, timeout=60)
        r.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"Erro ao enviar status das antenas: {e}")
        return False


def send_status_alarmes(conf: dict, equipamentos: list) -> bool:
    try:
        r = _post(conf, "/api/v1/agent/defense/alarmes/status", json={"equipamentos": equipamentos}, timeout=60)
        r.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"Erro ao enviar status dos alarmes: {e}")
        return False


def send_resultado_comando_alarme(conf: dict, sucesso: bool, mensagem: str) -> bool:
    try:
        r = _post(conf, "/api/v1/agent/defense/alarmes/comando-resultado", json={"sucesso": bool(sucesso), "mensagem": str(mensagem or "")[:500]}, timeout=30)
        r.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"Erro ao enviar resultado do comando de alarme: {e}")
        return False


def post_report(conf: dict, started_at: datetime, finished_at: datetime,
                resultados: list, trigger: str) -> str | None:
    payload = {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "status": (
            "OK" if all(r["status"] == "OK" for r in resultados) else
            "ERROR" if all(r["status"] == "ERRO" for r in resultados) else "PARTIAL"
        ),
        # campo nvr_results mantido por compatibilidade com o servidor; inclui tipo do equipamento
        "nvr_results": [
            {
                "nome": r["nome"],
                "tipo": r.get("tipo") or "NVR",
                "status": r["status"],
                "cameras": r.get("cameras") or [],
                "telemetria": r.get("telemetria"),
                # Por que não ficou OK (1.1.69): o painel mostra; servidor antigo ignora o campo
                **({"motivo": str(r["motivo"])[:500]} if r.get("motivo") else {}),
            }
            for r in resultados
        ],
        "trigger": trigger,
    }
    try:
        r = _com_novas_tentativas_servidor(
            lambda: _post(conf, "/api/v1/agent/backup/report", json=payload, timeout=30),
            "Envio do relatorio",
        )
        r.raise_for_status()
        try:
            resp_data = r.json()
            backup_id = resp_data["backup_id"]
        except ValueError:
            logging.error(f"  Resposta nao-JSON ao enviar relatorio. Conteudo: {r.text[:200]}")
            return None
            
        logging.info(f"  Relatorio enviado. backup_id={backup_id}")
        return backup_id
    except Exception as e:
        logging.error(f"  Erro ao enviar relatorio: {e}")
        return None

def upload_zip(conf: dict, backup_id: str, zip_path: Path, device_type: str = "NVR") -> bool:
    def _enviar():
        with open(zip_path, "rb") as f:
            # O requests lê o arquivo ao montar o corpo: se a 1ª tentativa cair no fallback de TLS, volta ao início
            return _post(
                conf, f"/api/v1/agent/backup/upload/{backup_id}",
                params={"device_type": device_type},
                files={"file": (zip_path.name, f, "application/zip")},
                timeout=TIMEOUT_SERVER,
                ao_repetir=lambda: f.seek(0),
            )

    try:
        # Cada nova tentativa reabre o arquivo (o corpo é lido do início)
        r = _com_novas_tentativas_servidor(_enviar, f"Envio do ZIP ({device_type})")
        r.raise_for_status()
        try:
            resp_json = r.json()
        except ValueError:
            resp_json = r.text[:100]
        logging.info(f"  ZIP ({device_type}) enviado ao servidor. Resposta: {resp_json}")
        return True
    except Exception as e:
        logging.error(f"  Erro ao enviar ZIP ({device_type}): {e}")
        return False


def upload_zip_stream(conf: dict, backup_id: str, nome_zip: str, pedacos, device_type: str = "MIXED") -> bool:
    """Envio em túnel (agente do Mikrotik): `pedacos` é um iterador de bytes (o ZIP sendo montado) e o corpo vai em
    pedaços (Transfer-Encoding: chunked), sem arquivo no disco. Se o iterador falhar no meio, a conexão cai e o
    servidor descarta o que recebeu."""
    try:
        r = _requisitar(
            conf, "PUT", f"/api/v1/agent/backup/upload-stream/{backup_id}",
            headers_extra={"Content-Type": "application/zip"},
            params={"device_type": device_type, "nome": nome_zip},
            data=pedacos,
            timeout=TIMEOUT_SERVER,
        )
        r.raise_for_status()
        try:
            resp_json = r.json()
        except ValueError:
            resp_json = r.text[:100]
        logging.info(f"  ZIP ({device_type}) enviado ao servidor em fluxo. Resposta: {resp_json}")
        return True
    except Exception as e:
        logging.error(f"  Erro ao enviar ZIP em fluxo ({device_type}): {e}")
        return False


def corrigir_resultado(conf: dict, backup_id: str, nome: str, status: str) -> bool:
    """Corrige no servidor o status de um equipamento do relatório (o do túnel sai antes do envio, provisório)."""
    try:
        r = _post(conf, f"/api/v1/agent/backup/{backup_id}/resultado", json={"nome": nome, "status": status},
                  timeout=30)
        r.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"  Erro ao corrigir o resultado de {nome}: {e}")
        return False


def send_logs(conf: dict, logs: list) -> bool:
    """Envia lote de logs do agente para a API do servidor."""
    try:
        r = _post(conf, "/api/v1/agent/logs", json={"logs": logs}, timeout=30)
        r.raise_for_status()
        return True
    except Exception:
        # Crucial: NUNCA chamar logging.error aqui para evitar laço de log infinito (o aviso único de TLS de
        # _requisitar só enfileira a linha, sem HTTP)
        return False
