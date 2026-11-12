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


def _coletar_smart_disco(nvr_ip, usuario, senha, hdd_id):
    """Le idade (dias ligado) e temperatura de um disco pelo SMART do ISAPI.
    Retorna (power_on_days, temperature_c); (None, None) se o NVR nao expuser o endpoint."""
    try:
        resp = fazer_get(
            f"http://{nvr_ip}/ISAPI/ContentMgmt/Storage/hdd/{hdd_id}/SMARTTest/status",
            usuario,
            senha,
            timeout=5,
        )
        if resp.status_code != 200:
            return None, None
        root = parse_xml_seguro(resp.content)
        ns = detectar_namespace(root)
        dias_raw = texto(root, ".//hik:powerOnDay" if ns else ".//powerOnDay", ns)
        temp_raw = texto(root, ".//hik:temprature" if ns else ".//temprature", ns)
        dias = _numero(dias_raw)
        temp = _numero(temp_raw)
        power_on_days = dias if dias is not None and dias >= 0 else None
        temperature_c = temp if temp is not None and -20 <= temp <= 120 else None
        return power_on_days, temperature_c
    except Exception:
        logging.debug(f"Falha ao ler SMART do disco {hdd_id} no NVR {nvr_ip}.", exc_info=True)
        return None, None


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
            uptime = texto(root, ".//hik:deviceUpTime" if ns else ".//deviceUpTime", ns)
            mem_uso = texto(root, ".//hik:memoryUsage" if ns else ".//memoryUsage", ns)
            mem_disp = texto(root, ".//hik:memoryAvailable" if ns else ".//memoryAvailable", ns)
            ram_pct, ram_total, ram_used = _calcular_ram(mem_uso, mem_disp)
            uptime_seg = _numero(uptime)
            telemetria["cpu_percent"] = _numero(cpu)
            telemetria["uptime_seconds"] = uptime_seg if uptime_seg is not None and uptime_seg >= 0 else None
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
            for hdd in elementos[:32]:
                hdd_id = texto(hdd, "hik:id", ns) if ns else texto(hdd, "id", None)
                capacidade_mb = _numero(texto(hdd, "hik:capacity", ns) if ns else texto(hdd, "capacity", None))
                livre_mb = _numero(texto(hdd, "hik:freeSpace", ns) if ns else texto(hdd, "freeSpace", None))
                status_bruto = texto(hdd, "hik:status", ns) if ns else texto(hdd, "status", None)

                total_gb = round(capacidade_mb / 1024, 1) if capacidade_mb else None
                free_gb = None
                percent = None
                if livre_mb and livre_mb > 0:
                    free_gb = round(livre_mb / 1024, 1)
                    if capacidade_mb:
                        percent = round((capacidade_mb - livre_mb) / capacidade_mb * 100, 1)

                power_on_days, temperature_c = (
                    _coletar_smart_disco(nvr_ip, usuario, senha, hdd_id)
                    if hdd_id
                    else (None, None)
                )

                discos.append({
                    "device": f"HDD{hdd_id}" if hdd_id else "HDD",
                    "status": _status_hdd(status_bruto),
                    "percent": percent,
                    "total_gb": total_gb,
                    "free_gb": free_gb,
                    "power_on_days": power_on_days,
                    "temperature_c": temperature_c,
                })

            telemetria["disks"] = discos
            teve_sucesso = True
    except Exception:
        logging.warning(f"  Falha ao ler discos do NVR {nvr_ip}.", exc_info=True)

    # 3. Rede (Interfaces e Estatísticas de Banda)
    try:
        in_kbps = None
        out_kbps = None
        try:
            resp_st = fazer_get(f"http://{nvr_ip}/ISAPI/System/Network/statistics", usuario, senha, timeout=5)
            if resp_st.status_code == 200:
                try:
                    data_st = resp_st.json()
                    in_kbps = data_st.get("inputBandwidth")
                    out_kbps = data_st.get("outputBandwidth")
                except Exception:
                    root_st = parse_xml_seguro(resp_st.content)
                    ns_st = detectar_namespace(root_st)
                    in_kbps = _numero(texto(root_st, ".//hik:inputBandwidth" if ns_st else ".//inputBandwidth", ns_st))
                    out_kbps = _numero(texto(root_st, ".//hik:outputBandwidth" if ns_st else ".//outputBandwidth", ns_st))
        except Exception:
            pass

        recv_mbps = round(in_kbps / 1000, 1) if (in_kbps is not None and in_kbps >= 0) else None
        sent_mbps = round(out_kbps / 1000, 1) if (out_kbps is not None and out_kbps >= 0) else None

        networks = []
        try:
            resp_if = fazer_get(f"http://{nvr_ip}/ISAPI/System/Network/interfaces", usuario, senha, timeout=5)
            if resp_if.status_code == 200:
                root_if = parse_xml_seguro(resp_if.content)
                ns_if = detectar_namespace(root_if)
                elementos_if = root_if.findall("hik:NetworkInterface", {"hik": ns_if}) if ns_if else root_if.findall("NetworkInterface")

                for idx, nic in enumerate(elementos_if):
                    nic_id = texto(nic, "hik:id", ns_if) if ns_if else texto(nic, "id", None)
                    ip_addr = texto(nic, ".//hik:ipAddress", ns_if) if ns_if else texto(nic, ".//ipAddress", None)
                    mac_addr = texto(nic, ".//hik:MACAddress", ns_if) if ns_if else texto(nic, ".//MACAddress", None)
                    speed_str = texto(nic, ".//hik:speed", ns_if) if ns_if else texto(nic, ".//speed", None)
                    speed_num = _numero(speed_str)
                    speed_mbps = speed_num if (speed_num and speed_num > 0) else (1000 if speed_str == "0" else None)

                    networks.append({
                        "name": f"LAN{nic_id}" if nic_id else (f"LAN{idx + 1}" if len(elementos_if) > 1 else "LAN"),
                        "ip": ip_addr,
                        "mac": mac_addr,
                        "status": "UP",
                        "speed_mbps": speed_mbps,
                        "recv_mbps": recv_mbps if idx == 0 else None,
                        "sent_mbps": sent_mbps if idx == 0 else None,
                    })
        except Exception:
            pass

        if not networks and (recv_mbps is not None or sent_mbps is not None):
            networks.append({
                "name": "LAN",
                "status": "UP",
                "recv_mbps": recv_mbps,
                "sent_mbps": sent_mbps,
            })

        if networks:
            telemetria["networks"] = networks
            teve_sucesso = True
    except Exception:
        logging.warning(f"  Falha ao ler dados de rede do NVR {nvr_ip}.", exc_info=True)

    return telemetria if teve_sucesso else None
