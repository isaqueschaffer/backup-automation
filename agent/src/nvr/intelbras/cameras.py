import logging
import re
import requests
from requests.auth import HTTPDigestAuth

TIMEOUT_S = 6


def buscar_cameras(nvr_ip, usuario, senha):
    """
    Descobre câmeras em NVR/DVR Intelbras (arquitetura Dahua CGI).
    Consulta RemoteDevice (câmeras IP) e ChannelTitle (títulos de canais).
    Retorna dicionário {canal_id: {"nome": str, "ip": str, "online": bool}}.
    """
    auth = HTTPDigestAuth(usuario, senha)
    cameras = {}

    # 1. Obter nomes dos canais (ChannelTitle)
    titles = {}
    try:
        r_title = requests.get(
            f"http://{nvr_ip}/cgi-bin/configManager.cgi?action=getConfig&name=ChannelTitle",
            auth=auth,
            timeout=TIMEOUT_S,
            verify=False
        )
        if r_title.status_code == 200:
            for line in r_title.text.splitlines():
                m = re.match(r"table\.ChannelTitle\[(\d+)\]\.Name=(.*)", line.strip())
                if m:
                    ch_idx = int(m.group(1)) + 1
                    titles[ch_idx] = m.group(2).strip()
    except Exception as e:
        logging.debug(f"Falha ao consultar ChannelTitle no Intelbras {nvr_ip}: {e}")

    # 2. Obter dispositivos remotos / câmeras IP (RemoteDevice)
    remote_cams = {}
    try:
        r_dev = requests.get(
            f"http://{nvr_ip}/cgi-bin/configManager.cgi?action=getConfig&name=RemoteDevice",
            auth=auth,
            timeout=TIMEOUT_S,
            verify=False
        )
        if r_dev.status_code == 200:
            for line in r_dev.text.splitlines():
                m = re.match(r"table\.RemoteDevice\.uuid:System_CONFIG_NETCAMERA_INFO_(\d+)\.([^=]+)=(.*)", line.strip())
                if m:
                    idx = int(m.group(1)) + 1
                    campo, valor = m.group(2).strip(), m.group(3).strip()
                    remote_cams.setdefault(idx, {})[campo] = valor
    except Exception as e:
        logging.debug(f"Falha ao consultar RemoteDevice no Intelbras {nvr_ip}: {e}")

    # 3. Montar lista de câmeras ativas
    for ch_idx, dev in remote_cams.items():
        habilitado = dev.get("Enable") == "true"
        ip_cam = dev.get("Address", "").strip()
        if ip_cam in ("192.168.0.0", "0.0.0.0", "ff:ff:ff:ff:ff:ff"):
            ip_cam = ""

        if habilitado and ip_cam:
            nome = (
                dev.get("VideoInputs[0].Name")
                or dev.get("Name")
                or titles.get(ch_idx)
                or f"Canal {ch_idx}"
            )
            cameras[ch_idx] = {
                "nome": nome,
                "ip": ip_cam,
                "online": True
            }

    # Se for DVR analógico e não tiver remote_cams habilitadas, usa ChannelTitle
    if not cameras and titles:
        for ch_idx, nome in titles.items():
            if nome and not nome.lower().startswith("canal"):
                cameras[ch_idx] = {
                    "nome": nome,
                    "ip": nvr_ip,
                    "online": True
                }

    return cameras
