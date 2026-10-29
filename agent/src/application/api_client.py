import logging
import math
import requests
from pathlib import Path
from datetime import datetime

TIMEOUT_SERVER = 120

def fetch_server_config(conf: dict) -> dict:
    headers = {"X-Client-ID": conf["client_id"], "X-API-Key": conf["api_key"]}
    url = f"{conf['server_url']}/api/v1/agent/config"
    r = requests.get(
        url,
        headers=headers,
        timeout=30,
        verify=False,
    )
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

def ping_server(conf: dict) -> dict:
    """Envia um ping para o servidor para manter o status online. Usa long-polling."""
    headers = {"X-Client-ID": conf["client_id"], "X-API-Key": conf["api_key"]}
    try:
        telemetry = _json_safe(_get_telemetry())
    except Exception as e:
        logging.error(f"Telemetria ignorada neste ping: {e}")
        telemetry = None
    payload = {"telemetry": telemetry}
    r = requests.post(
        f"{conf['server_url']}/api/v1/agent/ping",
        headers=headers, timeout=40, verify=False, json=payload
    )
    r.raise_for_status()
    return r.json()

def send_rtsp_result(conf: dict, result: dict) -> bool:
    headers = {"X-Client-ID": conf["client_id"], "X-API-Key": conf["api_key"]}
    try:
        r = requests.post(
            f"{conf['server_url']}/api/v1/agent/rtsp-result",
            json=result, headers=headers, timeout=60, verify=False,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"Erro ao enviar resultado RTSP: {e}")
        return False

def upload_night_image(conf: dict, payload: dict) -> bool:
    headers = {"X-Client-ID": conf["client_id"], "X-API-Key": conf["api_key"]}
    try:
        r = requests.post(
            f"{conf['server_url']}/api/v1/agent/nvr-cameras/night-image",
            json=payload, headers=headers, timeout=60, verify=False,
        )
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
    headers = {"X-Client-ID": conf["client_id"], "X-API-Key": conf["api_key"]}
    try:
        r = requests.post(
            f"{conf['server_url']}/api/v1/agent/cameras/status",
            json={"equipamentos": equipamentos},
            headers=headers,
            timeout=60,
            verify=False,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"Erro ao enviar presenca de cameras: {e}")
        return False


# Mesmo conjunto de _OK_STATUSES (server/api/services/backup_runs.py): NVR Motorola sai SEM_ARQUIVOS
# (sem backup de configuração) e não deve deixar o backup geral como PARTIAL
_STATUS_OK = {"OK", "SEM_ARQUIVOS"}


def post_report(conf: dict, started_at: datetime, finished_at: datetime,
                resultados: list, trigger: str) -> str | None:
    headers = {"X-Client-ID": conf["client_id"], "X-API-Key": conf["api_key"]}
    payload = {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "status": (
            "OK" if all(r["status"] in _STATUS_OK for r in resultados) else
            "ERROR" if all(r["status"] == "ERRO" for r in resultados) else "PARTIAL"
        ),
        # campo nvr_results mantido por compatibilidade com o servidor; inclui tipo do equipamento
        "nvr_results": [
            {
                "nome": r["nome"],
                "tipo": r.get("tipo") or "NVR",
                "status": r["status"],
                # None = o equipamento não informou câmeras (ex.: inacessível): o servidor mantém a lista anterior
                "cameras": r.get("cameras"),
                "telemetria": r.get("telemetria"),
            }
            for r in resultados
        ],
        "trigger": trigger,
    }
    try:
        r = requests.post(
            f"{conf['server_url']}/api/v1/agent/backup/report",
            json=payload, headers=headers, timeout=30, verify=False,
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
    headers = {"X-Client-ID": conf["client_id"], "X-API-Key": conf["api_key"]}
    try:
        with open(zip_path, "rb") as f:
            r = requests.post(
                f"{conf['server_url']}/api/v1/agent/backup/upload/{backup_id}",
                params={"device_type": device_type},
                headers=headers,
                files={"file": (zip_path.name, f, "application/zip")},
                timeout=TIMEOUT_SERVER,
                verify=False,
            )
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


def send_logs(conf: dict, logs: list) -> bool:
    """Envia lote de logs do agente para a API do servidor."""
    headers = {"X-Client-ID": conf["client_id"], "X-API-Key": conf["api_key"]}
    try:
        r = requests.post(
            f"{conf['server_url']}/api/v1/agent/logs",
            json={"logs": logs},
            headers=headers,
            timeout=30,
            verify=False,
        )
        r.raise_for_status()
        return True
    except Exception:
        # Crucial: NUNCA chamar logging.error aqui para evitar laço de log infinito
        return False
