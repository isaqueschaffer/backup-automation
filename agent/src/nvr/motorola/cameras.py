import requests
import base64
import hashlib
import logging
from src.utils.xml_parser import parse_xml_seguro, texto
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def abrir_sessao_motorola(nvr_ip, usuario, senha):
    """Faz login NVMS-9000 (reqLogin/SHA-512 com fallback Base64). Retorna a sessao autenticada
    (com tvt_token) ou None se o login falhar."""
    session = requests.Session()
    pwd_b64 = base64.b64encode(senha.encode('utf-8')).decode('utf-8')
    xml_header = '<?xml version="1.0" encoding="utf-8" ?>'
    token = ""

    try:
        # Tenta o fluxo novo de login (reqLogin -> doLogin com hash SHA-512)
        xml_req = f'{xml_header}<request version="1.0" systemType="NVMS-9000" clientType="WEB"/>'
        r_req = session.post(f"http://{nvr_ip}/reqLogin", data=xml_req.encode('utf-8'), headers={"Content-Type": "application/xml"}, timeout=10, verify=False)

        login_efetuado = False
        r = None

        if r_req.status_code == 200 and "success" in r_req.text:
            root_req = parse_xml_seguro(r_req.content)
            nonce = texto(root_req, ".//nonce", None)
            token = texto(root_req, ".//token", None) or ""

            if nonce and token:
                pwd_md5 = hashlib.md5(senha.encode('utf-8')).hexdigest().upper()
                hash_final = hashlib.sha512((pwd_md5 + "#" + nonce).encode('utf-8')).hexdigest()

                xml_login = f'{xml_header}<request version="1.0" systemType="NVMS-9000" clientType="WEB"><token>{token}</token><content><userName><![CDATA[{usuario}]]></userName><password><![CDATA[{hash_final}]]></password></content></request>'

                r = session.post(f"http://{nvr_ip}/doLogin", data=xml_login.encode('utf-8'), headers={"Content-Type": "application/xml"}, timeout=10, verify=False)
                if r.status_code == 200 and "success" in r.text:
                    login_efetuado = True

        # Se falhou ou não suporta reqLogin, tenta o login antigo (Base64)
        if not login_efetuado:
            xml_login = f'{xml_header}<request version="1.0" systemType="NVMS-9000" clientType="WEB"><content><userName><![CDATA[{usuario}]]></userName><password><![CDATA[{pwd_b64}]]></password></content></request>'
            r = session.post(f"http://{nvr_ip}/doLogin", data=xml_login.encode('utf-8'), headers={"Content-Type": "application/xml"}, timeout=10, verify=False)
            if r.status_code == 200 and "success" in r.text:
                login_efetuado = True

        if login_efetuado and r is not None:
            root = parse_xml_seguro(r.content)
            session_id = texto(root, ".//sessionId", None)
            if not session_id:
                return None
            session.cookies.set('auInfo_N9K', pwd_b64)
            session.cookies.set('sessionId', session_id.strip('{}'))

            # Save token for later requests
            token_val = token
            session.tvt_token = token_val
            return session
    except Exception as e:
        logging.error(f"Erro no login/descoberta motorola {nvr_ip}: {e}")
        return None
    return None

def buscar_cameras(nvr_ip, usuario, senha):
    session = abrir_sessao_motorola(nvr_ip, usuario, senha)
    if not session:
        return None, None

    xml_header = '<?xml version="1.0" encoding="utf-8" ?>'
    token_val = session.tvt_token
    token_xml = f"<token>{token_val}</token>" if token_val else ""

    try:
        cameras = {}
        xml_chls = f'{xml_header}<request version="1.0" systemType="NVMS-9000" clientType="WEB">{token_xml}</request>'

        # ESTRATÉGIA DE DESCOBERTA (FALLBACKS)
        # Tentativa 1: queryChlStatus (Geralmente retorna TODOS os canais suportados no NVR)
        r2 = session.post(f"http://{nvr_ip}/queryChlStatus", data=xml_chls.encode('utf-8'), headers={"Content-Type": "application/xml"}, timeout=10, verify=False)
        if r2.status_code == 200 and "success" in r2.text:
            root2 = parse_xml_seguro(r2.content)
            for item in root2.findall(".//item"):
                chl = item.find("chl")
                if chl is not None:
                    cid = chl.get("id", "")
                    nome = chl.text or f"Canal {cid}"
                    cameras[cid] = {"nome": nome, "ip": nvr_ip, "online": None}

        # Tentativa 2 (Fallback): queryChlsExistRec (Se queryChlStatus não existir/falhar)
        if not cameras:
            r2b = session.post(f"http://{nvr_ip}/queryChlsExistRec", data=xml_chls.encode('utf-8'), headers={"Content-Type": "application/xml"}, timeout=10, verify=False)
            if r2b.status_code == 200 and "success" in r2b.text:
                root2b = parse_xml_seguro(r2b.content)
                for item in root2b.findall(".//item"):
                    cid = item.get("id", "")
                    nome = item.text or f"Canal {cid}"
                    cameras[cid] = {"nome": nome, "ip": nvr_ip, "online": None}

        if not cameras:
            logging.error(f"  [{nvr_ip}] Nenhuma câmera encontrada pelas estratégias de descoberta.")
            return None, None

        # Buscando status real de rede (online/offline)
        r3 = session.post(f"http://{nvr_ip}/queryOnlineChlList", data=xml_chls.encode('utf-8'), headers={"Content-Type": "application/xml"}, timeout=10, verify=False)
        if r3.status_code == 200:
            root3 = parse_xml_seguro(r3.content)
            online_cids = {item.get("id", "") for item in root3.findall(".//item")}
            for cid in cameras:
                cameras[cid]["online"] = cid in online_cids
        else:
            logging.warning(f"  [{nvr_ip}] Falha ao buscar status online das câmeras via queryOnlineChlList.")

        return cameras, session
    except Exception as e:
        logging.error(f"Erro no login/descoberta motorola {nvr_ip}: {e}")
        pass
    return None, None
