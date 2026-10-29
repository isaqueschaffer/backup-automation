import logging
import re
import requests
from requests.auth import HTTPDigestAuth

TIMEOUT_S = 6

# Estados do getCameraState (Dahua) -> online; outro valor (ex.: "Connecting") = desconhecido
_ESTADOS_CONEXAO = {"connected": True, "disconnected": False}


def _estado_cameras(nvr_ip, auth):
    """Estado de conexao de cada canal pela CGI Dahua getCameraState: {canal (base 1): True/False/None}.
    Linhas da resposta: states[N].channel=<canal base 0> e states[N].connectionState=Connected|Disconnected|...
    Sem resposta ou erro: {} (o chamador deixa online=None, desconhecido).
    NAO validado em equipamento real: por isso tudo aqui e defensivo."""
    try:
        r = requests.get(
            f"http://{nvr_ip}/cgi-bin/LogicDeviceManager.cgi?action=getCameraState&uniqueChannels[0]=-1",
            auth=auth,
            timeout=TIMEOUT_S,
            verify=False
        )
        if r.status_code != 200:
            logging.debug(f"getCameraState sem resposta no Intelbras {nvr_ip} (HTTP {r.status_code})")
            return {}
        por_item = {}
        for line in r.text.splitlines():
            m = re.match(r"states\[(\d+)\]\.(channel|connectionState)=(.*)", line.strip())
            if m:
                por_item.setdefault(m.group(1), {})[m.group(2)] = m.group(3).strip()
        estados = {}
        for item in por_item.values():
            try:
                canal = int(item.get("channel", "")) + 1
            except ValueError:
                continue
            estados[canal] = _ESTADOS_CONEXAO.get((item.get("connectionState") or "").lower())
        return estados
    except Exception as e:
        logging.debug(f"Falha ao consultar getCameraState no Intelbras {nvr_ip}: {e}")
        return {}


def buscar_cameras(nvr_ip, usuario, senha):
    """
    Descobre câmeras em NVR/DVR Intelbras (arquitetura Dahua CGI).
    Consulta RemoteDevice (câmeras IP) e ChannelTitle (títulos de canais) e o estado de conexão (getCameraState).
    Retorna dicionário {canal_id: {"nome": str, "ip": str, "online": bool | None}}: online None = estado desconhecido.
    Retorna None quando nenhuma das duas consultas respondeu HTTP 200 (NVR inacessível ou senha errada)
    e {} quando o NVR respondeu mas não há câmeras.
    """
    auth = HTTPDigestAuth(usuario, senha)
    cameras = {}
    respondeu = False

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
            respondeu = True
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
            respondeu = True
            for line in r_dev.text.splitlines():
                m = re.match(r"table\.RemoteDevice\.uuid:System_CONFIG_NETCAMERA_INFO_(\d+)\.([^=]+)=(.*)", line.strip())
                if m:
                    idx = int(m.group(1)) + 1
                    campo, valor = m.group(2).strip(), m.group(3).strip()
                    remote_cams.setdefault(idx, {})[campo] = valor
    except Exception as e:
        logging.debug(f"Falha ao consultar RemoteDevice no Intelbras {nvr_ip}: {e}")

    if not respondeu:
        return None

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
                "online": None
            }

    # Estado real de conexão das câmeras IP (canal ausente na resposta fica None)
    if cameras:
        estados = _estado_cameras(nvr_ip, auth)
        for ch_idx, cam in cameras.items():
            cam["online"] = estados.get(ch_idx)

    # Se for DVR analógico e não tiver remote_cams habilitadas, usa ChannelTitle (estado desconhecido)
    if not cameras and titles:
        for ch_idx, nome in titles.items():
            if nome and not nome.lower().startswith("canal"):
                cameras[ch_idx] = {
                    "nome": nome,
                    "ip": nvr_ip,
                    "online": None
                }

    return cameras
