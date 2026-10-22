import asyncio
import base64
import hashlib
import json
import logging
import sys
import xml.etree.ElementTree as ET
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuração de encoding UTF-8 no console do Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")


def texto_seguro(elemento, tag_path: str, default: str = "") -> str:
    """Extrai texto seguro de tag XML sem erro caso não exista."""
    if elemento is None:
        return default
    alvo = elemento.find(tag_path)
    if alvo is not None and alvo.text:
        return alvo.text.strip()
    return default


def extrair_content_xml(xml_texto: str) -> str:
    """Extrai a seção <content> de um XML para evitar poluição visual de <types>."""
    try:
        root = ET.fromstring(xml_texto)
        content = root.find("content")
        if content is not None:
            return ET.tostring(content, encoding="utf-8").decode("utf-8")
    except Exception:
        pass
    return xml_texto


def autenticar_nvms9000(session: requests.Session, ip: str, usuario: str, senha: str):
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
            nonce = texto_seguro(root_req, ".//nonce")
            token = texto_seguro(root_req, ".//token")

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
                    session_id = texto_seguro(root_login, ".//sessionId")
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
            session_id = texto_seguro(root_b64, ".//sessionId")
            session.cookies.set("auInfo_N9K", pwd_b64)
            if session_id:
                session.cookies.set("sessionId", session_id.strip("{}"))
            session.tvt_token = ""
            return True
    except Exception as e:
        print(f"[-] Login Base64 falhou: {e}")

    return False


def testar_endpoints_motorola(session: requests.Session, ip: str, disk_ids: list = None):
    """
    Testa os principais endpoints de telemetria da arquitetura TVT / NVMS-9000 do NVR Motorola.
    """
    xml_header = '<?xml version="1.0" encoding="utf-8" ?>'
    token_val = getattr(session, "tvt_token", "")
    token_tag = f"<token>{token_val}</token>" if token_val else ""

    disk_ids = disk_ids or []
    cond_disk = f"<condition><diskId>{disk_ids[0]}</diskId></condition>" if disk_ids else ""
    cond_item = f"<condition><item id=\"{disk_ids[0]}\"/></condition>" if disk_ids else ""

    # Variações de envelopes XML suportados pelo NVMS-9000
    corpos_teste = [
        ("padrao", f"{xml_header}<request version=\"1.0\" systemType=\"NVMS-9000\" clientType=\"WEB\">{token_tag}</request>"),
        ("com_condition", f"{xml_header}<request version=\"1.0\" systemType=\"NVMS-9000\" clientType=\"WEB\">{token_tag}<condition/></request>"),
        ("com_content", f"{xml_header}<request version=\"1.0\" systemType=\"NVMS-9000\" clientType=\"WEB\">{token_tag}<content/></request>")
    ]
    if cond_disk:
        corpos_teste.append(("com_disk_id", f"{xml_header}<request version=\"1.0\" systemType=\"NVMS-9000\" clientType=\"WEB\">{token_tag}{cond_disk}</request>"))
        corpos_teste.append(("com_item_id", f"{xml_header}<request version=\"1.0\" systemType=\"NVMS-9000\" clientType=\"WEB\">{token_tag}{cond_item}</request>"))

    # Lista consolidada com foco em discos, capacidade e hardware
    endpoints_candidatos = [
        # Armazenamento e Discos
        "queryDiskStatus",
        "queryDiskDetailInfo",
        "queryDiskSmartInfo",
        "queryDiskProperty",
        "queryDiskState",
        "queryDiskInfo",
        "queryDiskList",
        "queryStorageDevice",
        "queryStorageStatus",
        "queryStorageInfo",
        "queryStorageCapacity",
        "queryDiskCapacity",
        "queryPartitionInfo",
        "queryRecordDisk",
        "queryDiskGroup",
        "queryHddInfo",
        "queryHddDetailInfo",
        "queryHddStatus",
        # Sistema e Hardware
        "queryBasicCfg",
        "queryDeviceInfo",
        "queryDevInfo",
        "queryDevStatus",
        "queryDeviceStatus",
        "querySystemStatus",
        "querySysStatus",
        "queryWorkStatus",
        "queryCpuStatus",
        "queryMemoryStatus",
        # Rede e Canais
        "queryNetCfg",
        "queryNetStatus",
        "queryChlStatus",
        "queryOnlineChlList"
    ]

    print("\n[*] Sondando endpoints de telemetria no NVR Motorola (NVMS-9000)...")
    respostas = {}

    for ep in endpoints_candidatos:
        url = f"http://{ip}/{ep}"
        sucesso_ep = False

        for nome_envelope, payload in corpos_teste:
            try:
                r = session.post(
                    url,
                    data=payload.encode("utf-8"),
                    headers={"Content-Type": "application/xml", "Accept": "application/xml, text/xml, */*"},
                    timeout=5,
                    verify=False
                )

                if r.status_code == 200:
                    texto_res = r.text.strip()
                    if "success" in texto_res or "<content" in texto_res or "<disk" in texto_res or "<item" in texto_res:
                        print(f"  [+] SUCESSO HTTP 200 em /{ep} (envelope: {nome_envelope})!")
                        respostas[ep] = texto_res
                        sucesso_ep = True
                        break
                    elif "<response" in texto_res or "<status>" in texto_res:
                        resumo = texto_res[:100].replace("\n", " ")
                        print(f"  [~] /{ep} ({nome_envelope}): HTTP 200 mas resposta: {resumo}")
                elif r.status_code != 404:
                    print(f"  [?] /{ep}: HTTP {r.status_code}")
            except Exception as e:
                print(f"  [!] /{ep} erro: {e}")
                break

            if sucesso_ep:
                break

    return respostas


def coletar_telemetria_motorola(ip: str, usuario: str = "admin", senha: str = "agerip@123"):
    """
    Função principal de coleta de telemetria de NVR Motorola.
    """
    print(f"[*] Conectando ao NVR Motorola {ip} como '{usuario}'...")
    session = requests.Session()

    sucesso = autenticar_nvms9000(session, ip, usuario, senha)
    if not sucesso:
        print(f"[-] Falha na autenticacao NVMS-9000 com o NVR {ip}.")
        print("    Verifique se o IP, usuario e senha estao corretos.")
        return None

    print("[+] Autenticacao realizada com sucesso no NVR Motorola!")

    # 1. Primeira chamada direta para queryDiskStatus para pegar os IDs dos discos
    disk_ids = []
    xml_header = '<?xml version="1.0" encoding="utf-8" ?>'
    token_val = getattr(session, "tvt_token", "")
    token_tag = f"<token>{token_val}</token>" if token_val else ""
    xml_corpo = f"{xml_header}<request version=\"1.0\" systemType=\"NVMS-9000\" clientType=\"WEB\">{token_tag}</request>"

    try:
        r_ds = session.post(
            f"http://{ip}/queryDiskStatus",
            data=xml_corpo.encode("utf-8"),
            headers={"Content-Type": "application/xml"},
            timeout=5,
            verify=False
        )
        if r_ds.status_code == 200 and "success" in r_ds.text:
            root_ds = ET.fromstring(r_ds.content)
            for item in root_ds.findall(".//item"):
                d_id = item.get("id")
                if d_id:
                    disk_ids.append(d_id)
            print(f"[+] Discos identificados no hardware: {len(disk_ids)} (IDs: {disk_ids})")
    except Exception as e:
        print(f"[-] Erro ao ler queryDiskStatus: {e}")

    # 2. Sondagem de Endpoints HTTP com suporte aos IDs dos discos
    respostas = testar_endpoints_motorola(session, ip, disk_ids)

    # 3. Exibição detalhada de cada seção
    print("\n" + "=" * 65)
    print(" 📡 RESULTADOS DETALHADOS DO NVR MOTOROLA")
    print("=" * 65)

    # Informações do Sistema (queryBasicCfg)
    if "queryBasicCfg" in respostas:
        print("\n--- ⚙️ INFORMAÇÕES DO SISTEMA (queryBasicCfg) ---")
        try:
            root_b = ET.fromstring(respostas["queryBasicCfg"])
            content = root_b.find("content")
            if content is not None:
                for child in content:
                    # Exibe tags principais
                    if child.text and child.text.strip():
                        print(f"  • {child.tag}: {child.text.strip()}")
                    elif len(child) > 0:
                        subitens = [f"{sub.tag}={sub.text.strip()}" for sub in child if sub.text and sub.text.strip()]
                        if subitens:
                            print(f"  • {child.tag}: {', '.join(subitens)}")
            else:
                print(respostas["queryBasicCfg"][:500])
        except Exception:
            print(respostas["queryBasicCfg"][:500])

    # Status dos Discos (queryDiskStatus)
    if "queryDiskStatus" in respostas:
        print("\n--- 💾 STATUS DOS DISCOS (queryDiskStatus) ---")
        try:
            root_d = ET.fromstring(respostas["queryDiskStatus"])
            for idx, item in enumerate(root_d.findall(".//item"), start=1):
                d_id = item.get("id", "Desconhecido")
                st = item.text or "Desconhecido"
                print(f"  • Disco #{idx} [ID: {d_id}]: Status={st}")
        except Exception:
            print(respostas["queryDiskStatus"][:500])

    # Outros endpoints respondidos (como queryDiskDetailInfo, etc)
    for ep, xml_txt in respostas.items():
        if ep not in ("queryBasicCfg", "queryDiskStatus", "queryChlStatus", "queryOnlineChlList"):
            print(f"\n--- Resposta detalhada de /{ep} ---")
            print(xml_txt[:800])
            if len(xml_txt) > 800:
                print("  ... (dados continuam)")

    print("\n" + "=" * 65)
    return respostas


if __name__ == "__main__":
    ip_teste = sys.argv[1] if len(sys.argv) > 1 else "192.168.5.5"
    user_teste = sys.argv[2] if len(sys.argv) > 2 else "admin"
    pass_teste = sys.argv[3] if len(sys.argv) > 3 else "agerip@123"

    coletar_telemetria_motorola(ip_teste, user_teste, pass_teste)
