import logging

from src.utils.xml_parser import parse_xml_seguro, detectar_namespace, texto
from src.utils.http import fazer_get

# Status de HDD do ISAPI (HDDStatusType) traduzidos para o StatusBadge do dashboard
_STATUS_HDD = {
    "ok": "OK",
    "normal": "OK",
    "error": "ERRO",
    "abnormal": "ERRO",
    "uninitialized": "NAO_INICIALIZADO",
    "notformatted": "NAO_FORMATADO",
    "sleep": "REPOUSO",
    "hibernate": "REPOUSO",
    "offline": "OFFLINE",
}


def _numero(texto_bruto):
    """Limpa quebras de linha e converte decimais com seguranca (ex.: '\\n71.5' -> 71)."""
    if not texto_bruto or not texto_bruto.strip():
        return None
    try:
        return int(float(texto_bruto.strip()))
    except ValueError:
        return None


def _calcular_ram(mem_uso_raw, mem_disp_raw=None):
    """Retorna (ram_percent, ram_total_gb, ram_used_gb)."""
    if not mem_uso_raw or not mem_uso_raw.strip():
        return None, None, None
    try:
        uso_mb = float(mem_uso_raw.strip())
        if mem_disp_raw and mem_disp_raw.strip():
            disp_mb = float(mem_disp_raw.strip())
            total_mb = uso_mb + disp_mb
            if total_mb > 0:
                pct = int(round((uso_mb / total_mb) * 100))
                total_gb = round(total_mb / 1024, 1)
                used_gb = round(uso_mb / 1024, 1)
                return pct, total_gb, used_gb
        if 0 <= uso_mb <= 100:
            return int(round(uso_mb)), None, None
        return None, None, None
    except ValueError:
        return None, None, None


def _status_hdd(status_bruto):
    chave = (status_bruto or "").strip().lower()
    return _STATUS_HDD.get(chave, (status_bruto or "DESCONHECIDO").upper())


def coletar_telemetria_hikvision(nvr_ip, usuario, senha):
    """Coleta CPU, RAM e discos de um NVR/DVR Hikvision via ISAPI.
    Retorna None se nenhuma das duas chamadas responder (equipamento provavelmente
    nao-Hikvision ou inacessivel nesse momento)."""
    telemetria = {}
    teve_sucesso = False

    try:
        resp = fazer_get(f"http://{nvr_ip}/ISAPI/System/status", usuario, senha, timeout=10)
        if resp.status_code == 200:
            root = parse_xml_seguro(resp.content)
            ns = detectar_namespace(root)
            cpu = texto(root, ".//hik:cpuUtilization" if ns else ".//cpuUtilization", ns)
            mem_uso = texto(root, ".//hik:memoryUsage" if ns else ".//memoryUsage", ns)
            mem_disp = texto(root, ".//hik:memoryAvailable" if ns else ".//memoryAvailable", ns)
            ram_pct, ram_total, ram_used = _calcular_ram(mem_uso, mem_disp)
            telemetria["cpu_percent"] = _numero(cpu)
            telemetria["ram_percent"] = ram_pct
            telemetria["ram_total_gb"] = ram_total
            telemetria["ram_used_gb"] = ram_used
            teve_sucesso = True
    except Exception:
        logging.warning(f"  Falha ao ler status (CPU/RAM) do NVR {nvr_ip}.", exc_info=True)

    try:
        resp = fazer_get(f"http://{nvr_ip}/ISAPI/ContentMgmt/Storage/hdd", usuario, senha, timeout=10)
        if resp.status_code == 200:
            root = parse_xml_seguro(resp.content)
            ns = detectar_namespace(root)
            elementos = root.findall("hik:hdd", {"hik": ns}) if ns else root.findall("hdd")

            discos = []
            for hdd in elementos:
                hdd_id = texto(hdd, "hik:id", ns) if ns else texto(hdd, "id", None)
                capacidade_mb = _numero(texto(hdd, "hik:capacity", ns) if ns else texto(hdd, "capacity", None))
                livre_mb = _numero(texto(hdd, "hik:freeSpace", ns) if ns else texto(hdd, "freeSpace", None))
                status_bruto = texto(hdd, "hik:status", ns) if ns else texto(hdd, "status", None)

                total_gb = round(capacidade_mb / 1024, 1) if capacidade_mb else None
                free_gb = round(livre_mb / 1024, 1) if livre_mb is not None else None
                percent = None
                if capacidade_mb and livre_mb is not None:
                    percent = round((capacidade_mb - livre_mb) / capacidade_mb * 100, 1)

                discos.append({
                    "device": f"HDD{hdd_id}" if hdd_id else "HDD",
                    "status": _status_hdd(status_bruto),
                    "percent": percent,
                    "total_gb": total_gb,
                    "free_gb": free_gb,
                })

            telemetria["disks"] = discos
            teve_sucesso = True
    except Exception:
        logging.warning(f"  Falha ao ler discos do NVR {nvr_ip}.", exc_info=True)

    return telemetria if teve_sucesso else None
