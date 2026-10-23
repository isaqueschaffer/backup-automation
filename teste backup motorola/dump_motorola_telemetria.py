# -*- coding: utf-8 -*-
"""Salva e analisa as respostas XML de telemetria do NVR Motorola (NVMS-9000):
Uso de CPU, Uso de RAM, Status e interfaces de rede, Capacidade e status dos discos.

Uso: py dump_motorola_telemetria.py <ip> <usuario> <senha>
Grava um arquivo por comando/envelope em respostas_telemetria_<ip>/ e exibe
no final um relatorio consolidado no formato do dashboard do sistema.
"""
import base64
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
import urllib3
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuração de encoding UTF-8 no console do Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass


def autenticar_nvms9000(session, ip, usuario, senha):
    """
    Realiza o login no NVR Motorola (protocolo NVMS-9000 / TVT):
    1. Tenta o fluxo moderno: reqLogin (obtém nonce e token) -> doLogin (SHA-512)
    2. Fallback: doLogin direto com Base64
    """
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
            root_req = ET.fromstring(r_req.content)
            nonce_el = root_req.find(".//nonce")
            token_el = root_req.find(".//token")
            nonce = nonce_el.text.strip() if nonce_el is not None and nonce_el.text else None
            token = token_el.text.strip() if token_el is not None and token_el.text else None

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
                    root_login = ET.fromstring(r_login.content)
                    sid_el = root_login.find(".//sessionId")
                    session_id = sid_el.text.strip() if sid_el is not None and sid_el.text else ""
                    session.cookies.set("auInfo_N9K", pwd_b64)
                    if session_id:
                        session.cookies.set("sessionId", session_id.strip("{}"))
                    session.tvt_token = token
                    return True
    except Exception as e:
        print(f"[-] Tentativa com reqLogin falhou: {e}")

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
            root_b64 = ET.fromstring(r_login_b64.content)
            sid_el = root_b64.find(".//sessionId")
            session_id = sid_el.text.strip() if sid_el is not None and sid_el.text else ""
            session.cookies.set("auInfo_N9K", pwd_b64)
            if session_id:
                session.cookies.set("sessionId", session_id.strip("{}"))
            session.tvt_token = ""
            return True
    except Exception as e:
        print(f"[-] Login Base64 falhou: {e}")

    return False


# Mapeamento de status de disco NVMS-9000 para os padroes do dashboard
_STATUS_HDD = {
    "ok": "OK",
    "normal": "OK",
    "read/write": "OK",
    "read_write": "OK",
    "readwrite": "OK",
    "read": "OK",
    "recording": "OK",
    "idle": "OK",
    "bad": "ERRO",
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


def _normalizar_status_disco(st_raw):
    if not st_raw:
        return "DESCONHECIDO"
    chave = st_raw.strip().lower()
    return _STATUS_HDD.get(chave, st_raw.strip().upper())


def _converter_valor_para_gb(val, unit=""):
    unit = (unit or "").upper().strip()
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

    # Heuristica de ordem de grandeza sem unidade expressa
    if val > 10_000_000_000:     # Bytes (ex: 4_000_787_030_016)
        return round(val / (1024 ** 3), 1)
    elif val > 10_000_000:       # KB
        return round(val / (1024 * 1024), 1)
    elif val > 100:              # MB (ex: 3815447 MB ~ 3.7 TB)
        return round(val / 1024, 1)
    else:                        # GB direto
        return round(val, 1)


def _parse_size_gb(el, *tag_names):
    """
    Busca qualquer uma das tags informadas dentro de 'el' e converte para GB.
    """
    if el is None:
        return None
    for tag in tag_names:
        for alvo in el.findall(f".//{tag}"):
            if alvo is not None and alvo.text and alvo.text.strip():
                texto_raw = alvo.text.strip()
                try:
                    texto_limpo = re.sub(r"[^\d.]", "", texto_raw)
                    if not texto_limpo:
                        continue
                    val = float(texto_limpo)
                    unit = alvo.get("unit") or ""
                    return _converter_valor_para_gb(val, unit)
                except (ValueError, TypeError):
                    continue
    return None


def _escanear_capacidade_heuristica(el):
    """
    Varre recursivamente todos os elementos filhos procurando números e termos
    como total, capacity, size, free, remain. Retorna (total_gb, free_gb).
    """
    if el is None:
        return None, None
    tot_gb, free_gb = None, None

    for filho in el.iter():
        tag_nome = filho.tag.lower()
        if not filho.text or not filho.text.strip():
            continue
        texto_limpo = re.sub(r"[^\d.]", "", filho.text.strip())
        if not texto_limpo:
            continue
        try:
            val = float(texto_limpo)
            if val <= 0:
                continue
            unit = filho.get("unit") or ""
            gb = _converter_valor_para_gb(val, unit)

            # Heurística para Total
            if tot_gb is None and any(t in tag_nome for t in ("total", "capacity", "allspace", "maxsize", "totalsize", "totalspace", "totalcap")):
                if not any(neg in tag_nome for neg in ("free", "remain", "used", "sub", "time", "date")):
                    tot_gb = gb

            # Heurística para Livre / Disponível
            if free_gb is None and any(t in tag_nome for t in ("remain", "free", "rest", "avail")):
                if not any(neg in tag_nome for neg in ("sub", "time", "date")):
                    free_gb = gb
        except Exception:
            continue

    return tot_gb, free_gb


def _parse_percent(el, *tag_names):
    """Extrai percentual inteiro 0-100 de uma tag."""
    if el is None:
        return None
    for tag in tag_names:
        alvo = el.find(f".//{tag}")
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


# Lista exaustiva de endpoints candidatos de telemetria no NVMS-9000
ENDPOINTS_DISCOS = [
    "queryDiskStatus",
    "queryDiskDetailInfo",
    "queryDiskSmartInfo",
    # Candidatos a lista e capacidade de armazenamento TVT / NVMS-9000
    "queryDiskList",
    "queryDiskCfg",
    "queryDisks",
    "queryDisk",
    "queryDiskSummary",
    "queryDiskTable",
    "queryStorageList",
    "queryStorageCfg",
    "queryStorage",
    "queryHddList",
    "queryHddCfg",
    "queryHdd",
    "queryHardDiskInfo",
    "queryHardDiskList",
    "queryHardDiskStatus",
    "queryRecStorage",
    "queryRecordStorage",
    "queryRecordDiskList",
    "queryRecDiskList",
    "queryRecDiskInfo",
    "queryRecordCapacity",
    "queryRecCapacity",
    "queryStorageDevList",
    "queryStorageVolume",
    "queryVolumeInfo",
    "queryVolumeList",
    "queryVolumeStatus",
    "queryPartitionList",
    "queryDiskPartition",
    "queryDiskUsage",
    "queryStorageUsage",
    "queryDiskSpace",
    "queryStorageSpace",
    "queryDevStorage",
    "queryDeviceStorage",
    "queryDevDisk",
    "queryDeviceDisk",
    "queryDiskManager",
    "queryStorageManager",
    "queryHddManager",
]

ENDPOINTS_SISTEMA_CPU_RAM = [
    "queryCpuStatus",
    "queryMemoryStatus",
    "queryMemStatus",
    "queryDevStatus",
    "queryDeviceStatus",
    "querySystemStatus",
    "querySysStatus",
    "queryWorkStatus",
    "queryResourceStatus",
    "queryHardwareStatus",
    "queryPerformance",
    "querySystemPerformance",
    "queryBasicCfg",
    "queryDevInfo",
    "queryDeviceInfo",
]

ENDPOINTS_REDE = [
    "queryNetCfg",
    "queryNetStatus",
    "queryNetWorkStatus",
    "queryNetworkStatus",
    "queryNICInfo",
    "queryNICStatus",
    "queryEthStatus",
    "queryNetFlow",
    "queryNetBandwidth",
    "queryBandwidth",
    "queryEthernetCfg",
]


def main():
    if len(sys.argv) < 2:
        print("Uso: py dump_motorola_telemetria.py <ip> <usuario> <senha>")
        print("  Ou: py dump_motorola_telemetria.py <caminho_pasta_respostas_xml>")
        return

    respostas_xml = {}
    ip = "NVR"
    pasta = None

    # Modo 1: Analise Offline de pasta existente com XMLs
    caminho_arg = Path(sys.argv[1])
    modo_offline = caminho_arg.is_dir() or sys.argv[1].endswith(".xml")
    disk_ids = []

    if modo_offline:
        pasta = caminho_arg if caminho_arg.is_dir() else caminho_arg.parent
        print(f"[*] Modo offline: Analisando arquivos XML da pasta '{pasta.resolve()}'...")
        for arq in pasta.glob("*.xml"):
            respostas_xml[arq.stem] = arq.read_bytes()
        print(f"    {len(respostas_xml)} arquivo(s) XML carregado(s).")

        # Procura disk_ids nos XMLs carregados
        for chave, xml_bytes in respostas_xml.items():
            if any(term in chave for term in ("DiskStatus", "DiskDetail", "DiskSmart")):
                try:
                    root_ds = ET.fromstring(xml_bytes)
                    for item in root_ds.findall(".//item"):
                        d_id = item.get("id")
                        if d_id and d_id not in disk_ids and not d_id.isdigit():
                            disk_ids.append(d_id)
                    content_el = root_ds.find(".//content")
                    if content_el is not None:
                        c_id = content_el.findtext("id")
                        if c_id and c_id not in disk_ids:
                            disk_ids.append(c_id)
                except Exception:
                    pass
        print(f"    Discos identificados nos arquivos: {len(disk_ids)} (IDs: {disk_ids})")
    else:
        if len(sys.argv) < 4:
            print("Uso: py dump_motorola_telemetria.py <ip> <usuario> <senha>")
            return
        ip, usuario, senha = sys.argv[1:4]

        session = requests.Session()
        print(f"[*] Conectando ao NVR Motorola {ip}...")
        if not autenticar_nvms9000(session, ip, usuario, senha):
            print(f"[-] Falha na autenticacao NVMS-9000 com o NVR {ip}.")
            return

        print(f"[+] Autenticado com sucesso em {ip}!")

        header = '<?xml version="1.0" encoding="utf-8" ?>'
        token = getattr(session, "tvt_token", "")
        token_tag = f"<token>{token}</token>" if token else ""

        def corpo(extra=""):
            return f'{header}<request version="1.0" systemType="NVMS-9000" clientType="WEB">{token_tag}{extra}</request>'

        def post(ep, payload):
            return session.post(
                f"http://{ip}/{ep}",
                data=payload.encode("utf-8"),
                headers={"Content-Type": "application/xml", "Accept": "application/xml, text/xml, */*"},
                timeout=8,
                verify=False
            )

        pasta = Path(f"respostas_telemetria_{ip.replace(':', '_')}")
        pasta.mkdir(exist_ok=True)

        def salvar(ep, nome, payload):
            try:
                r = post(ep, payload)
            except Exception as e:
                print(f"  [!] {ep} ({nome}): {e}")
                return None
            if r.status_code == 404:
                print(f"  [ ] {ep} ({nome}): 404")
                return None
            sucesso = "<status>success</status>" in r.text.lower() or "<content" in r.text.lower()
            marca = "+" if sucesso else "~"
            arquivo = pasta / f"{ep}__{nome}.xml"
            arquivo.write_bytes(r.content)
            print(f"  [{marca}] {ep} ({nome}): HTTP {r.status_code}, {len(r.content)} bytes -> {arquivo.name}")
            if r.status_code == 200:
                respostas_xml[f"{ep}__{nome}"] = r.content
            return r

        # 1. DISCOS: Descobrir IDs com queryDiskStatus
        print("\n[*] 1. Sondando armazenamento e discos...")
        r_ds = salvar("queryDiskStatus", "padrao", corpo())
        if r_ds and r_ds.status_code == 200:
            try:
                root_ds = ET.fromstring(r_ds.content)
                for item in root_ds.findall(".//item"):
                    d_id = item.get("id")
                    if d_id and d_id not in disk_ids:
                        disk_ids.append(d_id)
            except Exception:
                pass

        print(f"    Discos identificados preliminarmente: {len(disk_ids)} (IDs: {disk_ids})")

        # Envelopes de requireField para discos
        req_disk = (
            "<requireField>"
            "<name/><model/><sn/><totalCapacity/><remainCapacity/><freeCapacity/><freeSpace/>"
            "<totalSpace/><capacity/><status/><property/><diskType/><busType/>"
            "</requireField>"
        )

        for ep in ENDPOINTS_DISCOS:
            if ep == "queryDiskStatus" and "queryDiskStatus__padrao" in respostas_xml:
                continue
            salvar(ep, "padrao", corpo())
            salvar(ep, "requireField", corpo(req_disk))

            # Testa por ID de disco caso disponivel
            for d in disk_ids:
                cond_d = f"<condition><diskId>{d}</diskId></condition>"
                cond_item = f'<condition><item id="{d}"/></condition>'
                salvar(ep, f"disk_{d[:8]}_diskId", corpo(cond_d))
                salvar(ep, f"disk_{d[:8]}_itemId", corpo(cond_item))
                salvar(ep, f"disk_{d[:8]}_require", corpo(f"{cond_d}{req_disk}"))

        # 2. SISTEMA / CPU / RAM
        print("\n[*] 2. Sondando CPU, Memoria e Sistema...")
        req_cpu_ram = (
            "<requireField>"
            "<cpu/><cpuUsage/><cpuUtilization/><cpuRate/>"
            "<memory/><memUsage/><memoryUsage/><memTotal/><memFree/><totalMemory/><freeMemory/>"
            "<temperature/><disk/><network/>"
            "</requireField>"
        )
        for ep in ENDPOINTS_SISTEMA_CPU_RAM:
            salvar(ep, "padrao", corpo())
            salvar(ep, "requireField", corpo(req_cpu_ram))

        # 3. REDE
        print("\n[*] 3. Sondando interfaces e status de rede...")
        req_net = (
            "<requireField>"
            "<nic/><ip/><mask/><gateway/><mac/><dns/><speed/><dhcp/><mtu/>"
            "<linkStatus/><status/><recvRate/><sendRate/><rx/><tx/><bandwidth/>"
            "</requireField>"
        )
        for ep in ENDPOINTS_REDE:
            salvar(ep, "padrao", corpo())
            salvar(ep, "requireField", corpo(req_net))
            salvar(ep, "cond_item0", corpo('<condition><item id="0"/></condition>'))
            salvar(ep, "cond_nic1", corpo('<condition><nic id="1"/></condition>'))

    # =========================================================================
    # EXIBIR CONTEÚDO BRUTO DOS ENDPOINTS POSITIVOS
    # =========================================================================
    print("\n" + "=" * 65)
    print(" 📄 CONTEÚDO XML DOS ENDPOINTS DE DISCO E REDE")
    print("=" * 65)
    for ep_chave in sorted(respostas_xml.keys()):
        if any(k in ep_chave for k in ("DiskDetailInfo", "NetStatus", "NetCfg")):
            print(f"\n--- {ep_chave}.xml ({len(respostas_xml[ep_chave])} bytes) ---")
            try:
                txt = respostas_xml[ep_chave].decode("utf-8", errors="replace")
                print(txt[:1200])
                if len(txt) > 1200:
                    print(f"  ... ({len(txt) - 1200} bytes adicionais no arquivo)")
            except Exception as e:
                print(f"  Erro ao ler: {e}")

    # =========================================================================
    # PROCESSAMENTO E CONSOLIDAÇÃO DA TELEMETRIA
    # =========================================================================
    print("\n" + "=" * 65)
    print(" 📊 PROCESSAMENTO DOS DADOS COLETADOS")
    print("=" * 65)

    telemetria = {
        "cpu_percent": None,
        "ram_percent": None,
        "ram_total_gb": None,
        "ram_used_gb": None,
        "disks": [],
        "networks": []
    }

    # --- Extrair CPU e RAM ---
    for chave, xml_bytes in respostas_xml.items():
        try:
            root = ET.fromstring(xml_bytes)
        except Exception:
            continue

        # CPU
        if telemetria["cpu_percent"] is None:
            cpu = _parse_percent(root, "cpuUsage", "cpuUtilization", "cpuRate", "cpuPercent", "cpu")
            if cpu is not None:
                telemetria["cpu_percent"] = cpu

        # RAM %
        if telemetria["ram_percent"] is None:
            ram_pct = _parse_percent(root, "memUsage", "memoryUsage", "memUtilization", "ramPercent", "memoryPercent")
            if ram_pct is not None:
                telemetria["ram_percent"] = ram_pct

        # RAM Totais
        if telemetria["ram_total_gb"] is None:
            total_gb = _parse_size_gb(root, "memTotal", "totalMemory", "memoryTotal")
            if total_gb:
                telemetria["ram_total_gb"] = total_gb

        if telemetria["ram_used_gb"] is None:
            used_gb = _parse_size_gb(root, "memUsed", "usedMemory", "memoryUsed")
            if used_gb:
                telemetria["ram_used_gb"] = used_gb

    # Cálculo complementar de RAM caso tenhamos total e percentual
    if telemetria["ram_total_gb"] and telemetria["ram_percent"] and not telemetria["ram_used_gb"]:
        telemetria["ram_used_gb"] = round(telemetria["ram_total_gb"] * (telemetria["ram_percent"] / 100), 1)
    elif telemetria["ram_total_gb"] and telemetria["ram_used_gb"] and not telemetria["ram_percent"]:
        telemetria["ram_percent"] = int(round((telemetria["ram_used_gb"] / telemetria["ram_total_gb"]) * 100))

    # --- Extrair Discos ---
    discos_map = {}

    # 1. Lê status basico de queryDiskStatus
    for chave, xml_bytes in respostas_xml.items():
        if "queryDiskStatus" in chave:
            try:
                root = ET.fromstring(xml_bytes)
                for item in root.findall(".//item"):
                    d_id = item.get("id") or str(len(discos_map) + 1)
                    st_text = item.text.strip() if item.text else ""
                    st_child = item.find("status")
                    if st_child is not None and st_child.text:
                        st_text = st_child.text.strip()
                    d = discos_map.setdefault(d_id, {"id": d_id})
                    if st_text:
                        d["status"] = _normalizar_status_disco(st_text)
            except Exception:
                pass

    # 2. Informações S.M.A.R.T (Temperatura, Dias Ligado, Saúde)
    for chave, xml_bytes in respostas_xml.items():
        if "DiskSmartInfo" in chave:
            try:
                root = ET.fromstring(xml_bytes)
                content = root.find(".//content")
                if content is not None:
                    d_id = content.findtext("id")
                    if not d_id and disk_ids:
                        d_id = disk_ids[0]
                    elif not d_id:
                        d_id = list(discos_map.keys())[0] if discos_map else "1"

                    d = discos_map.setdefault(d_id, {"id": d_id})

                    temp_txt = content.findtext("temperature")
                    if temp_txt:
                        temp_num = re.sub(r"[^\d]", "", temp_txt)
                        if temp_num:
                            d["temperature_c"] = int(temp_num)

                    days_txt = content.findtext("powerOnDays")
                    if days_txt:
                        days_num = re.sub(r"[^\d]", "", days_txt)
                        if days_num:
                            d["power_on_days"] = int(days_num)

                    smart_st = content.findtext("diskStatus")
                    if smart_st and not d.get("status"):
                        d["status"] = _normalizar_status_disco(smart_st)
            except Exception:
                pass

    # 3. Complementa com queryDiskDetailInfo e outros endpoints de armazenamento
    for chave, xml_bytes in respostas_xml.items():
        if any(term in chave for term in ("DiskDetailInfo", "DiskInfo", "StorageCapacity", "DiskCapacity", "StorageStatus")):
            try:
                root = ET.fromstring(xml_bytes)
                itens = root.findall(".//disk") or root.findall(".//content")
                if not itens:
                    # Evita pegar smartItems como discos
                    itens = [it for it in root.findall(".//item") if not it.find("rawValue") and not it.get("id", "").isdigit()]

                for item in itens:
                    d_id = item.get("id") or item.findtext("diskId") or item.findtext("id")
                    if not d_id and disk_ids:
                        d_id = disk_ids[0]
                    elif not d_id:
                        d_id = list(discos_map.keys())[0] if discos_map else "1"

                    d = discos_map.setdefault(d_id, {"id": d_id})

                    # Nome / Dispositivo
                    nome = item.findtext("name") or item.findtext("devName") or item.findtext("model")
                    fonte = item.findtext("source")
                    if nome and not d.get("device"):
                        d["device"] = nome
                    elif fonte and not d.get("device"):
                        d["device"] = f"Disco ({fonte.capitalize()})"

                    # Status
                    st = item.findtext("status") or item.findtext("property") or item.findtext("rwProperty") or item.findtext("state")
                    if st and not d.get("status"):
                        d["status"] = _normalizar_status_disco(st)

                    # Capacidades nominais
                    tot = _parse_size_gb(item,
                        "totalCapacity", "totalSpace", "capacity", "size", "totalSize",
                        "total", "maxSize", "allSpace", "totalBlock", "diskCapacity", "totalCap")
                    free = _parse_size_gb(item,
                        "remainCapacity", "freeCapacity", "freeSpace", "free", "freeSize",
                        "remainSize", "remain", "remainSpace", "restSpace", "freeBlock", "remainCap")

                    if not tot or free is None:
                        h_tot, h_free = _escanear_capacidade_heuristica(item)
                        tot = tot or h_tot
                        free = free if free is not None else h_free

                    if tot and not d.get("total_gb"):
                        d["total_gb"] = tot
                    if free is not None and d.get("free_gb") is None:
                        d["free_gb"] = free
            except Exception:
                pass

    for idx, (d_id, d) in enumerate(discos_map.items(), start=1):
        total_gb = d.get("total_gb")
        free_gb = d.get("free_gb")
        pct = None
        if total_gb and free_gb is not None and total_gb > 0:
            pct = round(((total_gb - free_gb) / total_gb) * 100, 1)

        telemetria["disks"].append({
            "device": d.get("device") or f"Disco {idx}",
            "status": d.get("status") or "OK",
            "percent": pct,
            "total_gb": total_gb,
            "free_gb": free_gb,
            "temperature_c": d.get("temperature_c"),
            "power_on_days": d.get("power_on_days"),
        })

    # --- Extrair Rede e Largura de Banda ---
    # Largura de banda global TVT/NVMS-9000 (cameras recebidas vs clientes visualizando)
    bw_recv_mbps = None
    bw_sent_mbps = None
    for chave, xml_bytes in respostas_xml.items():
        if "NetStatus" in chave:
            try:
                root = ET.fromstring(xml_bytes)
                bw = root.find(".//bandwidth")
                if bw is not None:
                    tot_bw = bw.findtext("totalBandwidth")
                    rem_bw = bw.findtext("remainBandwidth")
                    send_tot_bw = bw.findtext("sendTotalBandwidth")
                    send_rem_bw = bw.findtext("sendRemainBandwidth")
                    if tot_bw and rem_bw:
                        try:
                            bw_recv_mbps = round(float(tot_bw) - float(rem_bw), 1)
                        except Exception:
                            pass
                    if send_tot_bw and send_rem_bw:
                        try:
                            bw_sent_mbps = round(float(send_tot_bw) - float(send_rem_bw), 1)
                        except Exception:
                            pass
            except Exception:
                pass

    nics_map = {}
    for chave, xml_bytes in respostas_xml.items():
        if any(term in chave for term in ("NetCfg", "NetStatus", "NICInfo", "EthStatus")):
            try:
                root = ET.fromstring(xml_bytes)
                itens = root.findall(".//item")
                if not itens:
                    content = root.find(".//content")
                    if content is not None:
                        itens = [content]

                for item in itens:
                    nic_id = item.get("id") or item.findtext("id") or "1"
                    n = nics_map.setdefault(nic_id, {"id": nic_id})

                    name = item.findtext("name") or item.findtext("nicName") or item.get("id")
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

                    link = item.findtext("linkStatus") or item.findtext("status") or item.findtext("nicStatus")
                    is_online = item.findtext("isOnline")
                    if is_online and is_online.strip().lower() in ("true", "1"):
                        n["status"] = "UP"
                    elif link:
                        lk = link.strip().lower()
                        n["status"] = "UP" if lk in ("up", "online", "connected", "linked", "1", "true") else "DOWN"

                    rx = _parse_size_gb(item, "recvRate", "rx", "inBandwidth")
                    tx = _parse_size_gb(item, "sendRate", "tx", "outBandwidth")
                    if rx is not None:
                        n["recv_mbps"] = round(rx * 8, 1)
                    if tx is not None:
                        n["sent_mbps"] = round(tx * 8, 1)
            except Exception:
                pass

    for idx, (nid, n) in enumerate(nics_map.items(), start=1):
        # Se nao tinha rx/tx individual por item, aplica a largura de banda global capturada da interface
        r_mbps = n.get("recv_mbps") if n.get("recv_mbps") is not None else bw_recv_mbps
        s_mbps = n.get("sent_mbps") if n.get("sent_mbps") is not None else bw_sent_mbps

        telemetria["networks"].append({
            "name": n.get("name") or f"LAN{idx}",
            "ip": n.get("ip"),
            "mac": n.get("mac"),
            "status": n.get("status") or "UP",
            "speed_mbps": n.get("speed_mbps") or 1000,
            "recv_mbps": r_mbps,
            "sent_mbps": s_mbps
        })

    if not telemetria["networks"]:
        telemetria["networks"].append({
            "name": "LAN",
            "ip": ip,
            "mac": None,
            "status": "UP",
            "speed_mbps": 1000,
            "recv_mbps": bw_recv_mbps,
            "sent_mbps": bw_sent_mbps
        })

    # Exibição dos Resultados Formatados
    print(f"\n🧠 CPU:")
    print(f"   Uso: {telemetria['cpu_percent']}%" if telemetria['cpu_percent'] is not None else "   Uso: — (não exposto via XML)")

    print(f"\n💾 Memória RAM:")
    if telemetria['ram_percent'] is not None:
        total_str = f" de {telemetria['ram_total_gb']} GB" if telemetria['ram_total_gb'] else ""
        used_str = f" ({telemetria['ram_used_gb']} GB em uso)" if telemetria['ram_used_gb'] else ""
        print(f"   Uso: {telemetria['ram_percent']}%{total_str}{used_str}")
    else:
        print("   Uso: — (não exposto via XML)")

    print(f"\n🌐 Rede ({len(telemetria['networks'])} interface(s)):")
    for net in telemetria["networks"]:
        vel = f" | {net['speed_mbps']} Mbps" if net.get("speed_mbps") else ""
        ip_str = f" | IP: {net['ip']}" if net.get("ip") else ""
        mac_str = f" | MAC: {net['mac']}" if net.get("mac") else ""
        rx_tx = ""
        if net.get("recv_mbps") is not None or net.get("sent_mbps") is not None:
            rx = f"Rx: {net['recv_mbps']} Mbps (câmeras)" if net.get("recv_mbps") is not None else ""
            tx = f"Tx: {net['sent_mbps']} Mbps (visualização)" if net.get("sent_mbps") is not None else ""
            sep = " · " if rx and tx else ""
            rx_tx = f" | {rx}{sep}{tx}"
        print(f"   • {net['name']} [{net['status']}]{vel}{ip_str}{mac_str}{rx_tx}")

    print(f"\n💽 Discos ({len(telemetria['disks'])} unidade(s)):")
    if telemetria["disks"]:
        for d in telemetria["disks"]:
            uso_str = f" | {d['percent']}% usado" if d.get("percent") is not None else ""
            cap_str = ""
            if d.get("total_gb"):
                livre = f"{d['free_gb']} GB livres de " if d.get("free_gb") is not None else ""
                cap_str = f" | {livre}{d['total_gb']} GB"
            temp_str = f" | {d['temperature_c']}°C" if d.get("temperature_c") is not None else ""
            idade_str = f" | {d['power_on_days']} dias ligado" if d.get("power_on_days") is not None else ""
            print(f"   • {d['device']} [{d['status']}]{uso_str}{cap_str}{temp_str}{idade_str}")
    else:
        print("   Nenhum disco detectado ou resposta vazia.")

    print("\n" + "=" * 65)
    print(" 📋 JSON RETORNADO PARA O DASHBOARD:")
    print(json.dumps(telemetria, indent=2, ensure_ascii=False))
    print("=" * 65)
    print(f"\n[*] Respostas XML brutas gravadas na pasta: {pasta.resolve()}")


if __name__ == "__main__":
    main()
