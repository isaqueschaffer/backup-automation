import logging
import re
import time

from src.nvr.motorola.cameras import abrir_sessao_motorola
from src.utils.xml_parser import parse_xml_seguro, texto

TIMEOUT_S = 15
PAUSA_S = 0.5
MAX_DISCOS = 16


def _numero(txt):
    """Converte texto para inteiro ou retorna None."""
    if not txt or not str(txt).strip():
        return None
    try:
        return int(float(str(txt).strip()))
    except (ValueError, TypeError):
        return None


def _post(session, nvr_ip, endpoint, corpo=""):
    """Envia requisicao XML NVMS-9000 e retorna a raiz parseada ou None."""
    token_val = getattr(session, "tvt_token", "") or ""
    token_xml = f"<token>{token_val}</token>" if token_val else ""
    xml_data = (
        '<?xml version="1.0" encoding="utf-8" ?>'
        f'<request version="1.0" systemType="NVMS-9000" clientType="WEB">{token_xml}{corpo}</request>'
    )
    url = f"http://{nvr_ip}/{endpoint}"
    try:
        resp = session.post(
            url,
            data=xml_data.encode("utf-8"),
            headers={"Content-Type": "application/xml"},
            timeout=TIMEOUT_S,
            verify=False,
        )
        if resp.status_code != 200:
            return None
        raiz = parse_xml_seguro(resp.content)
        status = texto(raiz, ".//status", None)
        if status != "success" and not raiz.findall(".//content"):
            return None
        return raiz
    except Exception as e:
        logging.debug(f"Falha na consulta {endpoint} em {nvr_ip}: {e}")
        return None
    finally:
        time.sleep(PAUSA_S)


def coletar_telemetria_motorola(nvr_ip, usuario, senha):
    """Coleta capacidade, idade, temperatura e saude dos HDs e status de rede de um NVR/DVR Motorola (NVMS-9000).
    Retorna {"disks": [...], "networks": [...]} ou None se o login ou as consultas falharem."""
    try:
        session = abrir_sessao_motorola(nvr_ip, usuario, senha)
        if session is None:
            return None

        # ---------------------------------------------------------------------
        # 1. DISCOS (queryStorageDevInfo + queryDiskStatus + queryDiskSmartInfo)
        # ---------------------------------------------------------------------
        discos_info = []
        raiz = _post(session, nvr_ip, "queryStorageDevInfo")
        if raiz is not None:
            itens = raiz.findall(".//diskList/item")
            for item in itens:
                disk_id = item.get("id")
                if not disk_id:
                    continue
                slot = texto(item, "slotIndex", None)
                size_mb = _numero(texto(item, "size", None))
                discos_info.append({"id": disk_id, "slot": slot, "size_mb": size_mb})
                if len(discos_info) >= MAX_DISCOS:
                    break

        estados = {}
        raiz_st = _post(session, nvr_ip, "queryDiskStatus")
        if raiz_st is not None:
            for item in raiz_st.findall(".//content/item"):
                item_id = item.get("id")
                if not item_id:
                    continue
                valor = (item.text or "").strip()
                if not valor:
                    valor = texto(item, "diskStatus", None)
                estados[item_id] = valor

        # Fallback para firmwares onde queryStorageDevInfo nao retorna diskList
        if not discos_info and estados:
            for idx, item_id in enumerate(estados.keys(), start=1):
                discos_info.append({"id": item_id, "slot": str(idx), "size_mb": None})

        discos = []
        for info in discos_info:
            disk_id = info["id"]
            slot = info["slot"]
            size_mb = info["size_mb"]

            corpo_sm = f"<condition><diskId>{disk_id}</diskId></condition>"
            raiz_sm = _post(session, nvr_ip, "queryDiskSmartInfo", corpo_sm)

            power_on_days = None
            temperature_c = None
            saude = None

            if raiz_sm is not None:
                content = raiz_sm.find(".//content")
                if content is not None:
                    dias = _numero(texto(content, ".//powerOnDays", None))
                    temp = _numero(texto(content, ".//temperature", None))
                    saude_txt = texto(content, ".//diskStatus", None)
                    saude = saude_txt if saude_txt else None
                    if dias is not None and dias >= 0:
                        power_on_days = dias
                    if temp is not None and -20 <= temp <= 120:
                        temperature_c = temp

            estado = estados.get(disk_id, "")
            if estado == "bad" or saude == "bad":
                status = "ERRO"
            elif saude == "lowHealth":
                status = "SAUDE_BAIXA"
            elif estado == "read":
                status = "SOMENTE_LEITURA"
            elif estado == "read/write" or saude == "good":
                status = "OK"
            else:
                status = "DESCONHECIDO"

            device = f"HDD{slot}" if slot else "HDD"
            total_gb = round(size_mb / 1024, 1) if size_mb and size_mb > 0 else None

            discos.append({
                "device": device,
                "status": status,
                "percent": None,
                "total_gb": total_gb,
                "free_gb": None,
                "power_on_days": power_on_days,
                "temperature_c": temperature_c,
            })

        # ---------------------------------------------------------------------
        # 2. REDE (queryNetStatus / queryNetCfg / bandwidth)
        # ---------------------------------------------------------------------
        networks = []
        bw_recv_mbps = None
        bw_sent_mbps = None

        raiz_net = _post(session, nvr_ip, "queryNetStatus")
        if raiz_net is not None:
            bw = raiz_net.find(".//bandwidth")
            if bw is not None:
                tot_bw = _numero(texto(bw, ".//totalBandwidth", None))
                rem_bw = _numero(texto(bw, ".//remainBandwidth", None))
                send_tot_bw = _numero(texto(bw, ".//sendTotalBandwidth", None))
                send_rem_bw = _numero(texto(bw, ".//sendRemainBandwidth", None))
                if tot_bw is not None and rem_bw is not None:
                    bw_recv_mbps = round(float(tot_bw - rem_bw), 1)
                if send_tot_bw is not None and send_rem_bw is not None:
                    bw_sent_mbps = round(float(send_tot_bw - send_rem_bw), 1)

            for item in raiz_net.findall(".//nic/item"):
                nic_id = item.get("id") or texto(item, "id", "eth0")
                nic_status = texto(item, "nicStatus", "") or ""
                ip_val = texto(item, "ip", None)
                mac_val = texto(item, "mac", None)
                status = "UP" if nic_status.lower() in ("online", "up", "connected") else "DOWN"

                networks.append({
                    "name": nic_id,
                    "ip": ip_val,
                    "mac": mac_val,
                    "status": status,
                    "speed_mbps": 1000,
                    "recv_mbps": bw_recv_mbps,
                    "sent_mbps": bw_sent_mbps,
                })

        # Se queryNetStatus nao retornou itens de placa, tenta queryNetCfg
        if not networks:
            raiz_cfg = _post(session, nvr_ip, "queryNetCfg")
            if raiz_cfg is not None:
                for item in raiz_cfg.findall(".//nicConfigs/item"):
                    nic_id = item.get("id") or "eth0"
                    ip_val = texto(item, "ip", None)
                    mac_val = texto(item, "mac", None)
                    is_online = texto(item, "isOnline", "")
                    status = "UP" if is_online.lower() in ("true", "1") else "DOWN"

                    networks.append({
                        "name": nic_id,
                        "ip": ip_val,
                        "mac": mac_val,
                        "status": status,
                        "speed_mbps": 1000,
                        "recv_mbps": bw_recv_mbps,
                        "sent_mbps": bw_sent_mbps,
                    })

        # Fallback de placa caso nao tenha retornado lista detalhada
        if not networks:
            networks.append({
                "name": "LAN",
                "ip": nvr_ip,
                "mac": None,
                "status": "UP",
                "speed_mbps": 1000,
                "recv_mbps": bw_recv_mbps,
                "sent_mbps": bw_sent_mbps,
            })

        if not discos and not networks:
            return None

        return {
            "disks": discos,
            "networks": networks,
        }
    except Exception as e:
        logging.warning(f"Falha ao coletar telemetria do NVR Motorola {nvr_ip}: {e}")
        return None
