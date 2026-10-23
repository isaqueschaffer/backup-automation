import base64
import hashlib
import logging
import re
import xml.etree.ElementTree as ET
import requests
import urllib3

from src.utils.xml_parser import parse_xml_seguro, texto

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Status de HDD do NVMS-9000 traduzidos para o StatusBadge do dashboard
_STATUS_HDD = {
    "ok": "OK",
    "normal": "OK",
    "recording": "OK",
    "idle": "OK",
    "readwrite": "OK",
    "error": "ERRO",
    "abnormal": "ERRO",
    "damage": "ERRO",
    "lost": "ERRO",
    "uninitialized": "NAO_INICIALIZADO",
    "no_format": "NAO_FORMATADO",
    "notformatted": "NAO_FORMATADO",
    "sleep": "REPOUSO",
    "hibernate": "REPOUSO",
    "standby": "REPOUSO",
    "offline": "OFFLINE",
}


def _normalizar_status_disco(st_raw: str) -> str:
    if not st_raw:
        return "DESCONHECIDO"
    chave = st_raw.strip().lower()
    return _STATUS_HDD.get(chave, st_raw.strip().upper())


def _parse_size_gb(el, *tag_names):
    """Extrai capacidade/tamanho em GB considerando unit='MB'/'GB'/'KB'/'Byte' ou heurística."""
    for tag in tag_names:
        alvo = el.find(f".//{tag}") if el is not None else None
        if alvo is not None and alvo.text and alvo.text.strip():
            texto_raw = alvo.text.strip()
            try:
                texto_limpo = re.sub(r"[^\d.]", "", texto_raw)
                val = float(texto_limpo)
                unit = (alvo.get("unit") or "").upper().strip()

                if unit == "GB":
                    return round(val, 1)
                elif unit == "TB":
                    return round(val * 1024, 1)
                elif unit == "KB":
                    return round(val / (1024 * 1024), 1)
                elif unit in ("B", "BYTE", "BYTES"):
                    return round(val / (1024 ** 3), 1)
                elif unit == "MB":
                    return round(val / 1024, 1)

                if val > 10_000_000_000:
                    return round(val / (1024 ** 3), 1)
                elif val > 10_000_000:
                    return round(val / (1024 * 1024), 1)
                elif val > 100:
                    return round(val / 1024, 1)
                else:
                    return round(val, 1)
            except (ValueError, TypeError):
                continue
    return None


def _parse_percent(el, *tag_names):
    """Extrai percentual inteiro 0-100 de uma tag."""
    for tag in tag_names:
        alvo = el.find(f".//{tag}") if el is not None else None
        if alvo is not None and alvo.text and alvo.text.strip():
            texto_raw = alvo.text.strip().replace("%", "").strip()
            try:
                val = float(texto_raw)
                if 0 <= val <= 1:
                    val *= 100
                if 0 <= val <= 100:
                    return int(round(val))
            except (ValueError, TypeError):
                continue
    return None


def autenticar_nvms9000(session: requests.Session, ip: str, usuario: str, senha: str) -> bool:
    """Realiza o login no NVR Motorola (protocolo NVMS-9000 / TVT)."""
    xml_header = '<?xml version="1.0" encoding="utf-8" ?>'
    pwd_b64 = base64.b64encode(senha.encode("utf-8")).decode("utf-8")

    # 1. Tentativa com reqLogin (SHA-512 + nonce)
    xml_req = f'{xml_header}<request version="1.0" systemType="NVMS-9000" clientType="WEB"/>'
    try:
        r_req = session.post(
            f"http://{ip}/reqLogin",
            data=xml_req.encode("utf-8"),
            headers={"Content-Type": "application/xml"},
            timeout=8,
            verify=False
        )

        if r_req.status_code == 200 and "success" in r_req.text:
            root_req = parse_xml_seguro(r_req.content)
            nonce = texto(root_req, ".//nonce", None)
            token = texto(root_req, ".//token", None)

            if nonce and token:
                pwd_md5 = hashlib.md5(senha.encode("utf-8")).hexdigest().upper()
                hash_final = hashlib.sha512((pwd_md5 + "#" + nonce).encode("utf-8")).hexdigest()

                xml_login = (
                    f'{xml_header}<request version="1.0" systemType="NVMS-9000" clientType="WEB">'
                    f'<token>{token}</token>'
                    f'<content><userName><![CDATA[{usuario}]]></userName>'
                    f'<password><![CDATA[{hash_final}]]></password></content></request>'
                )

                r_login = session.post(
                    f"http://{ip}/doLogin",
                    data=xml_login.encode("utf-8"),
                    headers={"Content-Type": "application/xml"},
                    timeout=8,
                    verify=False
                )

                if r_login.status_code == 200 and "success" in r_login.text:
                    root_login = parse_xml_seguro(r_login.content)
                    session_id = texto(root_login, ".//sessionId", None)
                    session.cookies.set("auInfo_N9K", pwd_b64)
                    if session_id:
                        session.cookies.set("sessionId", session_id.strip("{}"))
                    session.tvt_token = token
                    return True
    except Exception:
        pass

    # 2. Fallback com login direto em Base64
    try:
        xml_login_b64 = (
            f'{xml_header}<request version="1.0" systemType="NVMS-9000" clientType="WEB">'
            f'<content><userName><![CDATA[{usuario}]]></userName>'
            f'<password><![CDATA[{pwd_b64}]]></password></content></request>'
        )
        r_login_b64 = session.post(
            f"http://{ip}/doLogin",
            data=xml_login_b64.encode("utf-8"),
            headers={"Content-Type": "application/xml"},
            timeout=8,
            verify=False
        )
        if r_login_b64.status_code == 200 and "success" in r_login_b64.text:
            root_b64 = parse_xml_seguro(r_login_b64.content)
            session_id = texto(root_b64, ".//sessionId", None)
            session.cookies.set("auInfo_N9K", pwd_b64)
            if session_id:
                session.cookies.set("sessionId", session_id.strip("{}"))
            session.tvt_token = ""
            return True
    except Exception:
        pass

    return False


def coletar_telemetria_motorola(nvr_ip: str, usuario: str, senha: str, session: requests.Session = None):
    """
    Coleta dados de telemetria de NVRs Motorola (protocolo NVMS-9000 / TVT):
    - Uso de CPU (%)
    - Uso de RAM (%, Total GB, Usado GB)
    - Status e capacidade dos discos (HDD)
    - Interfaces e status de rede (LAN)
    """
    if session is None:
        session = requests.Session()
        sucesso = autenticar_nvms9000(session, nvr_ip, usuario, senha)
        if not sucesso:
            logging.warning(f"  [Motorola {nvr_ip}] Falha na autenticacao para telemetria.")
            return None

    header = '<?xml version="1.0" encoding="utf-8" ?>'
    token = getattr(session, "tvt_token", "")
    token_tag = f"<token>{token}</token>" if token else ""

    def corpo(extra=""):
        return f'{header}<request version="1.0" systemType="NVMS-9000" clientType="WEB">{token_tag}{extra}</request>'

    def post(ep, extra=""):
        payload = corpo(extra)
        try:
            r = session.post(
                f"http://{nvr_ip}/{ep}",
                data=payload.encode("utf-8"),
                headers={"Content-Type": "application/xml", "Accept": "application/xml, text/xml, */*"},
                timeout=6,
                verify=False
            )
            if r.status_code == 200 and ("success" in r.text.lower() or "<content" in r.text.lower()):
                return parse_xml_seguro(r.content)
        except Exception:
            pass
        return None

    telemetria = {
        "cpu_percent": None,
        "ram_percent": None,
        "ram_total_gb": None,
        "ram_used_gb": None,
        "disks": [],
        "networks": []
    }
    teve_sucesso = False

    # =========================================================================
    # 1. DISCOS (queryDiskStatus + queryDiskDetailInfo / queryStorageCapacity)
    # =========================================================================
    discos_map = {}
    disk_ids = []

    # queryDiskStatus: Lista todos os discos instalados e status inicial
    root_ds = post("queryDiskStatus")
    if root_ds is not None:
        teve_sucesso = True
        for item in root_ds.findall(".//item"):
            d_id = item.get("id") or str(len(discos_map) + 1)
            st_text = item.text.strip() if item.text else ""
            st_child = item.find("status")
            if st_child is not None and st_child.text:
                st_text = st_child.text.strip()
            if d_id not in disk_ids:
                disk_ids.append(d_id)
            d = discos_map.setdefault(d_id, {"id": d_id})
            if st_text:
                d["status"] = _normalizar_status_disco(st_text)

    # Detalhes de Capacidade dos discos
    req_disk = (
        "<requireField>"
        "<name/><model/><sn/><totalCapacity/><remainCapacity/><freeCapacity/><freeSpace/>"
        "<totalSpace/><capacity/><status/><property/>"
        "</requireField>"
    )

    detalhe_endpoints = ["queryDiskDetailInfo", "queryDiskInfo", "queryStorageCapacity", "queryStorageStatus"]
    for ep in detalhe_endpoints:
        # Tenta consulta padrao ou requireField
        root_det = post(ep, req_disk) or post(ep)
        if root_det is not None:
            teve_sucesso = True
            itens = root_det.findall(".//item")
            if not itens:
                content = root_det.find(".//content")
                if content is not None:
                    itens = [content]

            for item in itens:
                d_id = item.get("id") or item.findtext("diskId") or item.findtext("id")
                if not d_id and disk_ids:
                    d_id = disk_ids[0]
                elif not d_id:
                    d_id = "1"

                d = discos_map.setdefault(d_id, {"id": d_id})
                nome = item.findtext("name") or item.findtext("devName") or item.findtext("model")
                if nome and not d.get("device"):
                    d["device"] = nome

                st = item.findtext("status") or item.findtext("property") or item.findtext("state")
                if st and not d.get("status"):
                    d["status"] = _normalizar_status_disco(st)

                tot = _parse_size_gb(item, "totalCapacity", "totalSpace", "capacity", "size")
                free = _parse_size_gb(item, "remainCapacity", "freeCapacity", "freeSpace", "free")
                if tot and not d.get("total_gb"):
                    d["total_gb"] = tot
                if free is not None and d.get("free_gb") is None:
                    d["free_gb"] = free

        # Se ja encontrou capacidade para todos os discos, pode parar
        if discos_map and all(d.get("total_gb") for d in discos_map.values()):
            break

    # Se ainda faltar capacidade por disco, tenta buscar individualmente por diskId
    for d_id in disk_ids:
        d = discos_map.get(d_id, {})
        if not d.get("total_gb"):
            cond = f"<condition><diskId>{d_id}</diskId></condition>{req_disk}"
            root_ind = post("queryDiskDetailInfo", cond)
            if root_ind is not None:
                teve_sucesso = True
                tot = _parse_size_gb(root_ind, "totalCapacity", "totalSpace", "capacity", "size")
                free = _parse_size_gb(root_ind, "remainCapacity", "freeCapacity", "freeSpace", "free")
                if tot:
                    d["total_gb"] = tot
                if free is not None:
                    d["free_gb"] = free

    for idx, (d_id, d) in enumerate(discos_map.items(), start=1):
        total_gb = d.get("total_gb")
        free_gb = d.get("free_gb")
        pct = None
        if total_gb and free_gb is not None and total_gb > 0:
            pct = round(((total_gb - free_gb) / total_gb) * 100, 1)

        telemetria["disks"].append({
            "device": d.get("device") or f"HDD{idx}",
            "status": d.get("status") or "OK",
            "percent": pct,
            "total_gb": total_gb,
            "free_gb": free_gb
        })

    # =========================================================================
    # 2. CPU E MEMÓRIA RAM
    # =========================================================================
    req_cpu_ram = (
        "<requireField>"
        "<cpu/><cpuUsage/><cpuUtilization/><cpuRate/>"
        "<memory/><memUsage/><memoryUsage/><memTotal/><memFree/><totalMemory/><freeMemory/>"
        "</requireField>"
    )

    for ep in ("queryCpuStatus", "queryMemoryStatus", "queryDevStatus", "querySystemStatus", "queryWorkStatus"):
        root_sys = post(ep, req_cpu_ram) or post(ep)
        if root_sys is not None:
            teve_sucesso = True
            if telemetria["cpu_percent"] is None:
                cpu = _parse_percent(root_sys, "cpuUsage", "cpuUtilization", "cpuRate", "cpuPercent", "cpu")
                if cpu is not None:
                    telemetria["cpu_percent"] = cpu

            if telemetria["ram_percent"] is None:
                ram_pct = _parse_percent(root_sys, "memUsage", "memoryUsage", "memUtilization", "ramPercent", "memoryPercent")
                if ram_pct is not None:
                    telemetria["ram_percent"] = ram_pct

            if telemetria["ram_total_gb"] is None:
                tot_ram = _parse_size_gb(root_sys, "memTotal", "totalMemory", "memoryTotal")
                if tot_ram:
                    telemetria["ram_total_gb"] = tot_ram

            if telemetria["ram_used_gb"] is None:
                used_ram = _parse_size_gb(root_sys, "memUsed", "usedMemory", "memoryUsed")
                if used_ram:
                    telemetria["ram_used_gb"] = used_ram

    if telemetria["ram_total_gb"] and telemetria["ram_percent"] and not telemetria["ram_used_gb"]:
        telemetria["ram_used_gb"] = round(telemetria["ram_total_gb"] * (telemetria["ram_percent"] / 100), 1)
    elif telemetria["ram_total_gb"] and telemetria["ram_used_gb"] and not telemetria["ram_percent"]:
        telemetria["ram_percent"] = int(round((telemetria["ram_used_gb"] / telemetria["ram_total_gb"]) * 100))

    # =========================================================================
    # 3. REDE (queryNetCfg / queryNetStatus / queryNICInfo)
    # =========================================================================
    nics_map = {}
    req_net = (
        "<requireField>"
        "<nic/><ip/><mask/><gateway/><mac/><dns/><speed/><dhcp/><mtu/>"
        "<linkStatus/><status/><recvRate/><sendRate/><rx/><tx/><bandwidth/>"
        "</requireField>"
    )

    for ep in ("queryNetCfg", "queryNetStatus", "queryNICInfo", "queryEthStatus"):
        root_net = post(ep, req_net) or post(ep)
        if root_net is not None:
            teve_sucesso = True
            itens = root_net.findall(".//item")
            if not itens:
                content = root_net.find(".//content")
                if content is not None:
                    itens = [content]

            for item in itens:
                nic_id = item.get("id") or item.findtext("id") or "1"
                n = nics_map.setdefault(nic_id, {"id": nic_id})

                name = item.findtext("name") or item.findtext("nicName")
                if name:
                    n["name"] = name
                ip_val = item.findtext("ip") or item.findtext("ipAddress")
                if ip_val:
                    n["ip"] = ip_val
                mac_val = item.findtext("mac") or item.findtext("macAddress")
                if mac_val:
                    n["mac"] = mac_val

                speed_raw = item.findtext("speed") or item.findtext("workMode")
                if speed_raw:
                    num = re.sub(r"[^\d]", "", speed_raw)
                    if num and int(num) > 0:
                        n["speed_mbps"] = int(num)

                link = item.findtext("linkStatus") or item.findtext("status")
                if link:
                    lk = link.strip().lower()
                    n["status"] = "UP" if lk in ("up", "connected", "linked", "1", "true") else "DOWN"

                rx = _parse_size_gb(item, "recvRate", "rx", "inBandwidth")
                tx = _parse_size_gb(item, "sendRate", "tx", "outBandwidth")
                if rx is not None:
                    n["recv_mbps"] = round(rx * 8, 1)
                if tx is not None:
                    n["sent_mbps"] = round(tx * 8, 1)

    for idx, (nid, n) in enumerate(nics_map.items(), start=1):
        telemetria["networks"].append({
            "name": n.get("name") or f"LAN{idx}",
            "ip": n.get("ip"),
            "mac": n.get("mac"),
            "status": n.get("status") or "UP",
            "speed_mbps": n.get("speed_mbps"),
            "recv_mbps": n.get("recv_mbps"),
            "sent_mbps": n.get("sent_mbps")
        })

    if not telemetria["networks"]:
        telemetria["networks"].append({
            "name": "LAN",
            "ip": nvr_ip,
            "mac": None,
            "status": "UP",
            "speed_mbps": 1000,
            "recv_mbps": None,
            "sent_mbps": None
        })

    return telemetria if teve_sucesso else None
