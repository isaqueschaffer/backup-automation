import requests
import xml.etree.ElementTree as ET
from requests.auth import HTTPDigestAuth
from datetime import datetime, timedelta
import re
import uuid
import logging
import base64

TIMEOUT = 20
DIAS_VERIFICAR = 15
NS_URI = "http://www.hikvision.com/ver20/XMLSchema"
NS = {"hik": NS_URI}

def fazer_get(url, usuario, senha):
    return requests.get(
        url,
        auth=HTTPDigestAuth(usuario, senha),
        timeout=TIMEOUT,
        verify=False
    )

def detectar_namespace(root):
    match = re.match(r"\{(.*?)\}", root.tag)
    return match.group(1) if match else None

def texto(elemento, caminho, namespace):
    if elemento is None:
        return ""
    el = elemento.find(caminho, {"hik": namespace}) if namespace else elemento.find(caminho)
    if el is not None and el.text:
        return el.text.strip()
    return ""

def limpar_xml(content_bytes):
    texto_str = content_bytes.decode('utf-8', errors='replace')
    resultado = []
    for ch in texto_str:
        cp = ord(ch)
        if (cp == 0x9 or cp == 0xA or cp == 0xD or
            (0x20 <= cp <= 0xD7FF) or
            (0xE000 <= cp <= 0xFFFD) or
            (0x10000 <= cp <= 0x10FFFF)):
            resultado.append(ch)
    return ''.join(resultado)

def parse_xml_seguro(content_bytes):
    try:
        return ET.fromstring(content_bytes)
    except ET.ParseError:
        conteudo_limpo = limpar_xml(content_bytes)
        return ET.fromstring(conteudo_limpo)

def buscar_cameras_nvr(nvr_ip, usuario, senha):
    url_config = f"http://{nvr_ip}/ISAPI/ContentMgmt/InputProxy/channels"
    url_status = f"http://{nvr_ip}/ISAPI/ContentMgmt/InputProxy/channels/status"
    try:
        resp_config = fazer_get(url_config, usuario, senha)
        if resp_config.status_code != 200:
            return None

        root = parse_xml_seguro(resp_config.content)
        ns = detectar_namespace(root)
        cameras = {}
        elementos = root.findall("hik:InputProxyChannel", {"hik": ns}) if ns else root.findall("InputProxyChannel")

        if not elementos:
            return None

        for canal in elementos:
            if ns:
                canal_id = texto(canal, "hik:id", ns)
                nome = texto(canal, "hik:name", ns)
                source = canal.find("hik:sourceInputPortDescriptor", {"hik": ns})
            else:
                canal_id = texto(canal, "id", None)
                nome = texto(canal, "name", None)
                source = canal.find("sourceInputPortDescriptor")

            ip = ""
            if source is not None:
                ip = texto(source, "hik:ipAddress", ns) if ns else texto(source, "ipAddress", None)

            cameras[canal_id] = {"nome": nome, "ip": ip, "online": None}

        if not cameras:
            return None

        try:
            resp_status = fazer_get(url_status, usuario, senha)
            if resp_status.status_code == 200:
                root_status = parse_xml_seguro(resp_status.content)
                ns_status = detectar_namespace(root_status)
                status_els = root_status.findall("hik:InputProxyChannelStatus", {"hik": ns_status}) if ns_status else root_status.findall("InputProxyChannelStatus")

                for st in status_els:
                    cid = texto(st, "hik:id", ns_status) if ns_status else texto(st, "id", None)
                    online = texto(st, "hik:online", ns_status) if ns_status else texto(st, "online", None)
                    if cid in cameras:
                        cameras[cid]["online"] = online.lower() == "true"
        except Exception:
            pass

        return cameras
    except Exception:
        return None

def buscar_cameras_dvr(nvr_ip, usuario, senha):
    url = f"http://{nvr_ip}/ISAPI/System/Video/inputs/channels"
    try:
        resp = fazer_get(url, usuario, senha)
        if resp.status_code != 200:
            return None

        root = parse_xml_seguro(resp.content)
        ns = detectar_namespace(root)
        cameras = {}
        elementos = root.findall("hik:VideoInputChannel", {"hik": ns}) if ns else root.findall("VideoInputChannel")

        if not elementos:
            return None

        for canal in elementos:
            if ns:
                canal_id = texto(canal, "hik:id", ns)
                nome = texto(canal, "hik:name", ns)
                res_desc = texto(canal, "hik:resDesc", ns)
            else:
                canal_id = texto(canal, "id", None)
                nome = texto(canal, "name", None)
                res_desc = texto(canal, "resDesc", None)

            online = res_desc.upper() != "NO VIDEO" if res_desc else True
            cameras[canal_id] = {"nome": nome, "ip": nvr_ip, "online": online}

        return cameras
    except Exception:
        return None

def buscar_cameras(nvr_ip, usuario, senha):
    cameras = buscar_cameras_nvr(nvr_ip, usuario, senha)
    if cameras: return cameras, "NVR", None
    cameras = buscar_cameras_dvr(nvr_ip, usuario, senha)
    if cameras: return cameras, "DVR", None
    
    cameras, sessao = buscar_cameras_motorola(nvr_ip, usuario, senha)
    if cameras: return cameras, "MOTOROLA", sessao
    
    return {}, "DESCONHECIDO", None

def buscar_cameras_motorola(nvr_ip, usuario, senha):
    session = requests.Session()
    pwd_b64 = base64.b64encode(senha.encode('utf-8')).decode('utf-8')
    xml_header = '<?xml version="1.0" encoding="utf-8" ?>'
    
    try:
        # Tenta o fluxo novo de login (reqLogin -> doLogin com hash SHA-512)
        xml_req = f'{xml_header}<request version="1.0" systemType="NVMS-9000" clientType="WEB"/>'
        r_req = session.post(f"http://{nvr_ip}/reqLogin", data=xml_req.encode('utf-8'), headers={"Content-Type": "application/xml"}, timeout=10, verify=False)
        
        login_efetuado = False
        r = None
        
        if r_req.status_code == 200 and "success" in r_req.text:
            root_req = parse_xml_seguro(r_req.content)
            nonce = texto(root_req, ".//nonce", None)
            token = texto(root_req, ".//token", None)
            
            if nonce and token:
                import hashlib
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
                return None, None
            session.cookies.set('auInfo_N9K', pwd_b64)
            session.cookies.set('sessionId', session_id.strip('{}'))
            
            # Save token for later requests
            token_val = token if 'token' in locals() and token else ""
            session.tvt_token = token_val
            token_xml = f"<token>{token_val}</token>" if token_val else ""
            
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

def buscar_datas_gravacao_motorola(nvr_ip, session, canal_id):
    """
    Consulta as datas que possuem gravações em um canal de um NVR Motorola.

    Retorna:
        (datas, True)  -> consulta realizada com sucesso
        ([], False)    -> falha na consulta
    """

    import time
    import requests

    xml_header = '<?xml version="1.0" encoding="utf-8" ?>'

    token_val = getattr(session, 'tvt_token', '')
    token_xml = f"<token>{token_val}</token>" if token_val else ""

    xml_req = (
        f'{xml_header}'
        f'<request version="1.0" '
        f'systemType="NVMS-9000" '
        f'clientType="WEB">'
        f'{token_xml}'
        f'<condition>'
        f'<chlId>{canal_id}</chlId>'
        f'</condition>'
        f'</request>'
    )

    url = f"http://{nvr_ip}/queryDatesExistRec"

    # Número máximo de tentativas
    max_tentativas = 3

    # Timeout:
    # 10s para conectar
    # 60s aguardando resposta do NVR
    timeout = (10, 60)

    for tentativa in range(1, max_tentativas + 1):

        inicio = time.monotonic()

        try:
            logging.info(
                f"[Motorola {nvr_ip}] "
                f"Buscando datas de gravação - "
                f"canal={canal_id} "
                f"tentativa={tentativa}/{max_tentativas}"
            )

            response = session.post(
                url,
                data=xml_req.encode("utf-8"),
                headers={
                    "Content-Type": "application/xml",
                    "Accept": "application/xml, text/xml, */*",
                },
                timeout=timeout,
                verify=False
            )

            tempo_resposta = time.monotonic() - inicio

            logging.info(
                f"[Motorola {nvr_ip}] "
                f"Resposta recebida em {tempo_resposta:.2f}s "
                f"HTTP={response.status_code} "
                f"canal={canal_id}"
            )

            # ---------------------------------------------------------
            # HTTP diferente de 200
            # ---------------------------------------------------------

            if response.status_code != 200:

                logging.warning(
                    f"[Motorola {nvr_ip}] "
                    f"queryDatesExistRec retornou HTTP "
                    f"{response.status_code} "
                    f"canal={canal_id}"
                )

                # Erros HTTP podem ser temporários
                if tentativa < max_tentativas:
                    time.sleep(2 * tentativa)
                    continue

                return [], False

            # ---------------------------------------------------------
            # Resposta vazia
            # ---------------------------------------------------------

            if not response.content:

                logging.warning(
                    f"[Motorola {nvr_ip}] "
                    f"Resposta vazia em queryDatesExistRec "
                    f"canal={canal_id}"
                )

                if tentativa < max_tentativas:
                    time.sleep(2 * tentativa)
                    continue

                return [], False

            # ---------------------------------------------------------
            # Validação básica da resposta
            # ---------------------------------------------------------

            response_text = response.text.strip()

            if "success" not in response_text.lower():

                logging.warning(
                    f"[Motorola {nvr_ip}] "
                    f"NVR não retornou sucesso em queryDatesExistRec "
                    f"canal={canal_id} "
                    f"resposta={response_text[:300]}"
                )

                return [], False

            # ---------------------------------------------------------
            # Parse XML
            # ---------------------------------------------------------

            try:
                root = parse_xml_seguro(response.content)

            except Exception as xml_error:

                logging.error(
                    f"[Motorola {nvr_ip}] "
                    f"Erro ao interpretar XML "
                    f"canal={canal_id}: {xml_error}"
                )

                return [], False

            # ---------------------------------------------------------
            # Extrair datas
            # ---------------------------------------------------------

            datas = []

            for item in root.findall(".//item"):

                if not item.text:
                    continue

                valor = item.text.strip()

                try:
                    dt = datetime.strptime(
                        valor,
                        "%Y-%m-%d"
                    )

                    datas.append(dt)

                except ValueError:

                    logging.warning(
                        f"[Motorola {nvr_ip}] "
                        f"Data inválida recebida: "
                        f"'{valor}' "
                        f"canal={canal_id}"
                    )

            # ---------------------------------------------------------
            # Remover duplicadas e ordenar
            # ---------------------------------------------------------

            datas = sorted(set(datas))

            logging.info(
                f"[Motorola {nvr_ip}] "
                f"Consulta concluída com sucesso - "
                f"canal={canal_id} "
                f"datas_encontradas={len(datas)} "
                f"tempo={tempo_resposta:.2f}s"
            )

            return datas, True

        # =============================================================
        # TIMEOUT DE CONEXÃO
        # =============================================================

        except requests.exceptions.ConnectTimeout:

            tempo = time.monotonic() - inicio

            logging.warning(
                f"[Motorola {nvr_ip}] "
                f"Timeout de conexão após {tempo:.2f}s "
                f"canal={canal_id} "
                f"tentativa={tentativa}/{max_tentativas}"
            )

        # =============================================================
        # TIMEOUT AGUARDANDO RESPOSTA
        # =============================================================

        except requests.exceptions.ReadTimeout:

            tempo = time.monotonic() - inicio

            logging.warning(
                f"[Motorola {nvr_ip}] "
                f"Timeout aguardando resposta do NVR "
                f"após {tempo:.2f}s "
                f"canal={canal_id} "
                f"tentativa={tentativa}/{max_tentativas}"
            )

        # =============================================================
        # ERRO DE CONEXÃO
        # =============================================================

        except requests.exceptions.ConnectionError as e:

            logging.warning(
                f"[Motorola {nvr_ip}] "
                f"Erro de conexão "
                f"canal={canal_id}: {e}"
            )

        # =============================================================
        # OUTROS ERROS HTTP
        # =============================================================

        except requests.exceptions.RequestException as e:

            logging.error(
                f"[Motorola {nvr_ip}] "
                f"Erro HTTP em queryDatesExistRec "
                f"canal={canal_id}: {e}"
            )

            return [], False

        # =============================================================
        # ERRO INESPERADO
        # =============================================================

        except Exception as e:

            logging.exception(
                f"[Motorola {nvr_ip}] "
                f"Erro inesperado ao buscar datas "
                f"canal={canal_id}: {e}"
            )

            return [], False

        # -------------------------------------------------------------
        # Retry
        # -------------------------------------------------------------

        if tentativa < max_tentativas:

            espera = 2 ** tentativa

            logging.info(
                f"[Motorola {nvr_ip}] "
                f"Aguardando {espera}s antes de tentar novamente..."
            )

            time.sleep(espera)

    # Todas as tentativas falharam

    logging.error(
        f"[Motorola {nvr_ip}] "
        f"Falha definitiva ao buscar datas de gravação "
        f"canal={canal_id} "
        f"após {max_tentativas} tentativas"
    )

    return [], False

def tem_gravacao_no_dia(nvr_ip, usuario, senha, canal_id, data):
    try:
        canal_numero = int(canal_id)
    except ValueError:
        return None

    track_id = (canal_numero * 100) + 1
    inicio_dia = data.replace(hour=0, minute=0, second=0, microsecond=0)
    fim_dia = inicio_dia + timedelta(days=1) - timedelta(seconds=1)
    search_id = "{" + str(uuid.uuid4()) + "}"
    url_search = f"http://{nvr_ip}/ISAPI/ContentMgmt/search"

    xml_busca = f"""<?xml version="1.0" encoding="UTF-8"?>
<CMSearchDescription>
    <searchID>{search_id}</searchID>
    <trackIDList><trackID>{track_id}</trackID></trackIDList>
    <timeSpanList>
        <timeSpan>
            <startTime>{inicio_dia.strftime("%Y-%m-%dT%H:%M:%SZ")}</startTime>
            <endTime>{fim_dia.strftime("%Y-%m-%dT%H:%M:%SZ")}</endTime>
        </timeSpan>
    </timeSpanList>
    <maxResults>1</maxResults>
    <searchResultPostion>0</searchResultPostion>
    <metadataList><metadataDescriptor>//recordType.meta.std-cgi.com</metadataDescriptor></metadataList>
</CMSearchDescription>"""

    try:
        response = requests.post(
            url_search,
            data=xml_busca.encode("utf-8"),
            auth=HTTPDigestAuth(usuario, senha),
            headers={"Content-Type": "application/xml", "Accept": "application/xml"},
            timeout=TIMEOUT,
            verify=False
        )
    except requests.exceptions.RequestException:
        return None

    if response.status_code != 200:
        return None

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError:
        return None

    ns = detectar_namespace(root)
    ns_map = {"hik": ns} if ns else {}

    path_num = ".//hik:numOfMatches" if ns else ".//numOfMatches"
    num_matches_el = root.find(path_num, ns_map) if ns_map else root.find(path_num)
    
    if num_matches_el is not None and num_matches_el.text:
        try:
            return int(num_matches_el.text.strip()) > 0
        except ValueError:
            pass

    path_item = ".//hik:searchMatchItem" if ns else ".//searchMatchItem"
    itens = root.findall(path_item, ns_map) if ns_map else root.findall(path_item)
    return len(itens) > 0

def gerar_mapa_dias(dias_com_gravacao):
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    datas_set = set(d.strftime("%Y-%m-%d") for d in dias_com_gravacao)
    mapa = ""
    for i in range(DIAS_VERIFICAR - 1, -1, -1):
        data = hoje - timedelta(days=i)
        if data.strftime("%Y-%m-%d") in datas_set:
            mapa += "█"
        else:
            mapa += "░"
    return mapa

from concurrent.futures import ThreadPoolExecutor, as_completed

def verificar_gravacao_nvr(nvr_ip, usuario, senha):
    logging.info(f"  Verificando gravação para {nvr_ip}...")
    try:
        cameras, tipo, sessao = buscar_cameras(nvr_ip, usuario, senha)
        if not cameras:
            logging.info(f"  Nenhuma câmera encontrada para verificação de gravação.")
            return [], tipo

        hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        resultados = []
        
        if tipo == "MOTOROLA":
            # Motorola: Processamento mais rápido via endpoint agrupado por datas
            for canal_id, camera in cameras.items():
                datas_gravadas, query_sucesso = buscar_datas_gravacao_motorola(nvr_ip, sessao, canal_id)
                # Filtra apenas os dias que estão no range de verificação (0 a 14 dias atrás = 15 dias)
                dias_com_gravacao = []
                for dt in datas_gravadas:
                    if (hoje - timedelta(days=DIAS_VERIFICAR - 1)) <= dt <= hoje:
                        dias_com_gravacao.append(dt)
                        
                # ── Normalização do Status de Comunicação ──
                if camera["online"] is True:
                    status_comunicacao = "ONLINE"
                elif camera["online"] is False:
                    status_comunicacao = "OFFLINE"
                else:
                    status_comunicacao = "ERRO_COMUNICACAO"

                # ── Normalização do Status de Gravação ──
                if query_sucesso:
                    status_gravacao = "COM_GRAVACAO" if hoje in dias_com_gravacao else "SEM_GRAVACAO"
                else:
                    status_gravacao = "NAO_VERIFICADO"
                        
                resultados.append({
                    "canal": canal_id,
                    "nome": camera["nome"],
                    "ip": camera["ip"],
                    "online": camera["online"],  # Mantido para retrocompatibilidade
                    "status_comunicacao": status_comunicacao,
                    "status_gravacao": status_gravacao,
                    "total_dias": len(dias_com_gravacao),
                    "mapa": gerar_mapa_dias(dias_com_gravacao)
                })
            return resultados, tipo

        # Demais Marcas (Hikvision)
        with ThreadPoolExecutor(max_workers=10) as executor:
            for canal_id, camera in cameras.items():
                nome = camera["nome"]
                ip = camera["ip"]
                online = camera["online"]

                future_to_day = {
                    executor.submit(tem_gravacao_no_dia, nvr_ip, usuario, senha, canal_id, hoje - timedelta(days=i)): (hoje - timedelta(days=i))
                    for i in range(DIAS_VERIFICAR)
                }

                dias_com_gravacao = []
                teve_erro_hoje = False
                
                for future in as_completed(future_to_day):
                    data_ref = future_to_day[future]
                    try:
                        res = future.result()
                        if res is True:
                            dias_com_gravacao.append(data_ref)
                        elif res is None:
                            if data_ref == hoje:
                                teve_erro_hoje = True # Pode ter dado falha na API ou credenciais hoje
                    except Exception:
                        if data_ref == hoje:
                            teve_erro_hoje = True

                if online is None:
                    online = len(dias_com_gravacao) > 0

                # ── Normalização do Status de Comunicação ──
                status_comunicacao = "ONLINE" if online else "OFFLINE"

                # ── Normalização do Status de Gravação ──
                if teve_erro_hoje:
                    status_gravacao = "NAO_VERIFICADO"
                else:
                    status_gravacao = "COM_GRAVACAO" if hoje in dias_com_gravacao else "SEM_GRAVACAO"

                resultados.append({
                    "canal": canal_id,
                    "nome": nome,
                    "ip": ip,
                    "online": online,  # Retrocompatibilidade
                    "status_comunicacao": status_comunicacao,
                    "status_gravacao": status_gravacao,
                    "total_dias": len(dias_com_gravacao),
                    "mapa": gerar_mapa_dias(dias_com_gravacao)
                })

        return resultados, tipo
    except Exception as e:
        logging.error(f"  Erro ao verificar gravação no NVR {nvr_ip}: {e}")
        return [], "DESCONHECIDO"

