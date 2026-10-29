import hashlib
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import requests
import urllib3

# Desativa alertas de certificados SSL autoassinados ao consultar equipamentos locais
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from src.core.config import parse_config_extra


def calcular_assinatura_defense(username: str, password: str, realm: str, random_key: str) -> str:
    """
    Calcula a assinatura MD5 em 4 etapas conforme especificação nativa do BRMS / Dahua DSS / Intelbras Defense IA.
    """
    temp1 = hashlib.md5(password.encode('utf-8')).hexdigest()
    temp2 = hashlib.md5((username + temp1).encode('utf-8')).hexdigest()
    temp3 = hashlib.md5(temp2.encode('utf-8')).hexdigest()
    temp4 = hashlib.md5(f"{username}:{realm}:{temp3}".encode('utf-8')).hexdigest()
    return hashlib.md5(f"{temp4}:{random_key}".encode('utf-8')).hexdigest()


def extrair_cameras_defense_tree(devices: list) -> list:
    """
    Varre a árvore de dispositivos do Defense IA (BRMS):
    devices -> units (onde unit.get('encoder') ou str(unit.get('unitType')) == '1') -> channels.
    Extrai: canal sequencial (1..N), nome (amigável baseado no nome do dispositivo ou canal),
    codigo (channelCode), ip (deviceIp), modelo (deviceModelStr ou model), online (status == '1'),
    status_comunicacao ('ONLINE'/'OFFLINE'), dev_name, canal_nome_original.
    """
    if not isinstance(devices, list):
        return []

    cameras = []
    canal_idx = 1

    for dev in devices:
        if not isinstance(dev, dict):
            continue

        dev_name = (dev.get("name") or dev.get("deviceName") or "").strip()
        dev_ip = dev.get("deviceIp") or dev.get("ip") or "N/A"
        dev_model = dev.get("deviceModelStr") or dev.get("model") or ""
        units = dev.get("units")

        if not isinstance(units, list):
            units = []

        # Fallback defensivo caso channels venha no nível raiz do dispositivo
        if not units and "channels" in dev and isinstance(dev.get("channels"), list):
            units = [{"channels": dev.get("channels"), "unitType": "1"}]

        # Coleta os canais de encoders válidos deste dispositivo
        channels_validos = []
        for unit in units:
            if not isinstance(unit, dict):
                continue

            is_encoder = bool(unit.get("encoder")) or str(unit.get("unitType", "")) == "1"
            if not is_encoder:
                continue

            channels = unit.get("channels")
            if not isinstance(channels, list):
                continue

            for ch in channels:
                if isinstance(ch, dict):
                    channels_validos.append(ch)

        total_canais_dev = len(channels_validos)

        for ch in channels_validos:
            raw_ch_name = (ch.get("channelName") or ch.get("name") or f"Canal {canal_idx}").strip()
            ch_code = ch.get("channelCode") or ch.get("code") or str(ch.get("id", ""))
            status_raw = str(ch.get("status", "0")).strip()
            is_online = (status_raw == "1" or status_raw.lower() in ("online", "ok", "true"))
            ch_ip = ch.get("deviceIp") or ch.get("ip") or dev_ip
            ch_model = ch.get("deviceModelStr") or dev_model or ch.get("model", "")

            # Determina o nome mais amigável para exibição:
            # 1. Se o dispositivo tem canal único e possui dev_name (ex: "LATERAL TERRENO"), prioriza dev_name
            # 2. Se o dispositivo tem múltiplos canais (ex: DVR-CATANDUVA), compõe "dev_name - raw_ch_name"
            #    (nunca substitui apenas por dev_name para evitar colisão entre múltiplos canais do DVR)
            if total_canais_dev <= 1 and dev_name:
                nome_final = dev_name
            elif total_canais_dev > 1 and dev_name:
                if dev_name.lower() not in raw_ch_name.lower():
                    nome_final = f"{dev_name} - {raw_ch_name}"
                else:
                    nome_final = raw_ch_name
            else:
                nome_final = raw_ch_name or dev_name or f"Camera {canal_idx}"

            cameras.append({
                "canal": canal_idx,
                "nome": nome_final,
                "codigo": ch_code,
                "ip": ch_ip,
                "modelo": ch_model,
                "online": is_online,
                "status_comunicacao": "ONLINE" if is_online else "OFFLINE",
                "dev_name": dev_name,
                "canal_nome_original": raw_ch_name,
                "is_single_channel": (total_canais_dev <= 1),
            })
            canal_idx += 1

    return cameras


def consultar_gravacoes_defense_api(
    base_url: str,
    token: str,
    lista_cameras: list,
    dias_historico: int = 15,
    timeout: int = 6
) -> dict[str, dict]:
    """
    Consulta o histórico de gravações dia a dia no Storage Server (SS) do Defense IA BRMS
    via POST /brms/api/v1.0/SS/Record/QueryRecords (recordSource="3").
    Retorna um dicionário indexado por codigo (channelCode), ip e nome da câmera contendo:
      - dias_com_gravacao: lista de datas 'YYYY-MM-DD'
      - total_dias: contagem de dias com gravação
      - mapa: string de 15 caracteres ('█' gravado, '░' sem gravação)
      - status_gravacao: 'COM_GRAVACAO' ou 'SEM_GRAVACAO'
    """
    import time
    from concurrent.futures import ThreadPoolExecutor

    if not base_url or not token or not lista_cameras:
        return {}

    hoje = datetime.now().date()
    dias_ord = [(hoje - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(dias_historico - 1, -1, -1)]
    inicio_dt = datetime.combine(hoje - timedelta(days=dias_historico - 1), datetime.min.time())
    fim_dt = datetime.combine(hoje, datetime.max.time())
    inicio = int(inicio_dt.timestamp())
    agora = int(fim_dt.timestamp())

    headers = {
        "Content-Type": "application/json",
        "X-Subject-Token": token,
        "User-Agent": "WINPC_V2",
    }

    session = requests.Session()
    session.verify = False

    def _consultar_uma_camera(cam: dict) -> dict:
        ch_id = cam.get("codigo")
        if not ch_id:
            return {
                "cam": cam,
                "total_dias": 0,
                "mapa": "░" * dias_historico,
                "dias_com_gravacao": [],
                "status_gravacao": "SEM_GRAVACAO",
            }

        payload = {
            "data": {
                "channelId": ch_id,
                "startTime": str(inicio),
                "endTime": str(agora),
                "streamType": "1",
                "recordType": "0",
                "recordSource": "3",  # 3 = Servidor de armazenamento central (SS)
                "page": "1",
                "pageSize": "1000",
            }
        }
        try:
            resp = session.post(
                f"{base_url}/brms/api/v1.0/SS/Record/QueryRecords",
                json=payload,
                headers=headers,
                timeout=timeout,
            )
            data = resp.json().get("data") if resp.status_code == 200 else {}
            records = (data.get("records") if isinstance(data, dict) else []) or []

            dias_grav = set()
            for rec in records:
                if not isinstance(rec, dict):
                    continue
                try:
                    raw_st = rec.get("startTime")
                    if raw_st is None:
                        continue
                    st = int(float(raw_st))
                    if st > 1e11:  # Timestamp em milissegundos
                        st = int(st / 1000)
                    if st > 0:
                        dias_grav.add(datetime.fromtimestamp(st).strftime("%Y-%m-%d"))
                except (ValueError, TypeError, OSError):
                    continue

            dias_na_janela = dias_grav.intersection(set(dias_ord))
            total = len(dias_na_janela)
            mapa = "".join(["█" if d in dias_grav else "░" for d in dias_ord])
            return {
                "cam": cam,
                "total_dias": total,
                "mapa": mapa,
                "dias_com_gravacao": [d for d in dias_ord if d in dias_grav],
                "status_gravacao": "COM_GRAVACAO" if total > 0 else "SEM_GRAVACAO",
            }
        except Exception as e:
            logging.debug(f"  [DEFENSE] Falha ao consultar gravações para {ch_id}: {e}")
            return {
                "cam": cam,
                "total_dias": 0,
                "mapa": "░" * dias_historico,
                "dias_com_gravacao": [],
                "status_gravacao": "SEM_GRAVACAO",
            }

    try:
        with ThreadPoolExecutor(max_workers=6) as executor:
            resultados = list(executor.map(_consultar_uma_camera, lista_cameras))
    finally:
        session.close()

    mapa_final = {}
    for res in resultados:
        cam = res["cam"]
        info = {
            "total_dias": res["total_dias"],
            "mapa": res["mapa"],
            "dias_com_gravacao": res["dias_com_gravacao"],
            "status_gravacao": res["status_gravacao"],
        }
        codigo = cam.get("codigo")
        nome = cam.get("nome")
        dev_name = cam.get("dev_name")
        raw_name = cam.get("canal_nome_original")
        ip_cam = cam.get("ip")
        is_single = cam.get("is_single_channel", False)

        if codigo:
            mapa_final[codigo] = info
        if nome:
            mapa_final[nome] = info
            mapa_final[nome.lower()] = info
        if raw_name:
            mapa_final[raw_name] = info
            mapa_final[raw_name.lower()] = info
        if is_single:
            if dev_name:
                mapa_final[dev_name] = info
                mapa_final[dev_name.lower()] = info
            if ip_cam and ip_cam != "N/A":
                mapa_final[ip_cam] = info

    return mapa_final


def consultar_status_cameras_defense_api(
    ip: str,
    username: str,
    password: str,
    porta_api: int = 4433,
    timeout: int = 10
) -> tuple[dict, list, dict]:
    """
    Consulta o status em tempo real e o histórico de gravações das câmeras na API REST nativa do Intelbras Defense IA (BRMS porta 4433 HTTPS).
    Retorna (status_dict, lista_cameras, gravacoes_map).
    status_dict contém chaves por {nome: is_ok, dev_name: is_ok, ip: is_ok}.
    gravacoes_map contém histórico dia a dia por canal/IP/nome.
    Em caso de falha de conexão, credenciais inválidas ou timeout, registra aviso e retorna ({}, [], {}).
    """
    if not ip or not username or not password:
        return {}, [], {}

    base_url = f"https://{ip}:{porta_api}"
    session = requests.Session()
    session.verify = False

    try:
        # Etapa 1: Handshake inicial para obter realm e randomKey
        resp1 = session.post(
            f"{base_url}/brms/api/v1.0/accounts/authorize",
            json={"userName": username, "clientType": "WINPC_V2"},
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )

        if resp1.status_code not in (200, 401):
            logging.warning(
                f"  [DEFENSE] Falha no handshake inicial com API do Defense IA em {ip}:{porta_api} (HTTP {resp1.status_code})"
            )
            return {}, [], {}

        data1 = resp1.json() if resp1.text else {}
        realm = data1.get("realm") or (data1.get("data") or {}).get("realm")
        random_key = data1.get("randomKey") or (data1.get("data") or {}).get("randomKey")

        if not realm or not random_key:
            logging.warning(
                f"  [DEFENSE] Parâmetros realm/randomKey ausentes no handshake da API em {ip}:{porta_api}"
            )
            return {}, [], {}

        # Etapa 2: Autorização com cálculo de assinatura MD5
        signature = calcular_assinatura_defense(username, password, realm, random_key)
        auth_payload = {
            "userName": username,
            "signature": signature,
            "randomKey": random_key,
            "encryptType": "MD5",
            "clientType": "WINPC_V2",
        }

        resp2 = session.post(
            f"{base_url}/brms/api/v1.0/accounts/authorize",
            json=auth_payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )

        if resp2.status_code != 200:
            logging.warning(
                f"  [DEFENSE] Falha na autenticação da API do Defense IA em {ip}:{porta_api} (HTTP {resp2.status_code}). Verifique usuário e senha."
            )
            return {}, [], {}

        token = resp2.headers.get("X-Subject-Token")
        if not token and resp2.text:
            try:
                data2 = resp2.json()
                token = data2.get("token") or (data2.get("data") or {}).get("token")
            except Exception:
                token = None

        if not token:
            logging.warning(
                f"  [DEFENSE] Token de autenticação não retornado pela API em {ip}:{porta_api}"
            )
            return {}, [], {}

        # Etapa 3: Consulta da árvore de dispositivos
        tree_payload = {
            "containVirtualDevice": "1",
            "resourceTypes": ["1"],
        }
        resp3 = session.post(
            f"{base_url}/brms/api/v1.0/tree/devices",
            json=tree_payload,
            headers={
                "Content-Type": "application/json",
                "X-Subject-Token": token,
            },
            timeout=timeout,
        )

        if resp3.status_code != 200:
            logging.warning(
                f"  [DEFENSE] Falha ao consultar árvore de dispositivos da API em {ip}:{porta_api} (HTTP {resp3.status_code})"
            )
            return {}, [], {}

        data3 = resp3.json() if resp3.text else {}
        devices = []
        if isinstance(data3, list):
            devices = data3
        elif isinstance(data3, dict):
            if isinstance(data3.get("devices"), list):
                devices = data3["devices"]
            elif isinstance(data3.get("data"), list):
                devices = data3["data"]
            elif isinstance(data3.get("data"), dict) and isinstance(data3["data"].get("devices"), list):
                devices = data3["data"]["devices"]

        lista_cameras = extrair_cameras_defense_tree(devices)

        status_dict = {}
        for cam in lista_cameras:
            is_ok = cam.get("online", False)
            nome = cam.get("nome")
            dev_name = cam.get("dev_name")
            raw_name = cam.get("canal_nome_original")
            ip_cam = cam.get("ip")
            is_single = cam.get("is_single_channel", False)

            if nome:
                status_dict[nome] = is_ok
                status_dict[nome.lower()] = is_ok
            if raw_name:
                status_dict[raw_name] = is_ok
                status_dict[raw_name.lower()] = is_ok
            if is_single:
                if dev_name:
                    status_dict[dev_name] = is_ok
                    status_dict[dev_name.lower()] = is_ok
                if ip_cam and ip_cam != "N/A":
                    status_dict[ip_cam] = is_ok

        # Etapa 4: Consulta paralela de gravações dia a dia via Storage Server
        gravacoes_map = consultar_gravacoes_defense_api(base_url, token, lista_cameras, dias_historico=15)

        logging.info(
            f"  [DEFENSE] Consulta API concluída com sucesso: {len(lista_cameras)} câmeras encontradas ({len(gravacoes_map)} índices de gravação mapeados)."
        )
        return status_dict, lista_cameras, gravacoes_map

    except requests.exceptions.Timeout:
        logging.warning(
            f"  [DEFENSE] Timeout ({timeout}s) ao consultar API do Defense IA em {ip}:{porta_api}"
        )
        return {}, [], {}
    except requests.exceptions.RequestException as e:
        logging.warning(
            f"  [DEFENSE] Erro de rede ao conectar à API do Defense IA ({ip}:{porta_api}): {e}"
        )
        return {}, [], {}
    except Exception as e:
        logging.warning(
            f"  [DEFENSE] Erro inesperado ao consultar API do Defense IA ({ip}:{porta_api}): {e}"
        )
        return {}, [], {}
    finally:
        session.close()


def _montar_status_cameras_defense(equipamento: dict, conf: dict = None) -> list:
    """
    Monta o status das câmeras (canal 1..N):
    1. Tenta consultar a API nativa do Defense IA (BRMS HTTPS) para status online e histórico de gravações.
    2. Se cameras_config da Galeria existir: cruza com os status e gravações obtidos na API.
    3. Se cameras_config não existir mas a API retornou câmeras: usa diretamente as câmeras da API.
    4. Fallback legado: se a API estiver inacessível, cruza cameras_config com o Webhook CSV.
    5. Captura imagem da noite via RTSP se conf for fornecido e a câmera possuir senha individual cadastrada.
    """
    config_extra = parse_config_extra(equipamento)
    ip = equipamento.get("ip", "127.0.0.1")
    username = equipamento.get("username", "system")
    password = equipamento.get("password", "")
    try:
        porta_api = int(config_extra.get("porta_api") or 4433)
    except (ValueError, TypeError):
        porta_api = 4433
    cameras_config = equipamento.get("cameras_config") or []

    # Consulta à API REST BRMS se houver senha cadastrada
    status_dict, cameras_api, gravacoes_map = {}, [], {}
    if password:
        ret = consultar_status_cameras_defense_api(
            ip=ip, username=username, password=password, porta_api=porta_api
        )
        if len(ret) == 3:
            status_dict, cameras_api, gravacoes_map = ret
        elif len(ret) == 2:
            status_dict, cameras_api = ret

    hoje = datetime.now().date()
    dias_15_ord = [(hoje - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(14, -1, -1)]

    status_cameras = []
    cameras_para_captura = []

    if cameras_config:
        # Caso 1: Galeria possui câmeras cadastradas pelo usuário
        status_webhook = None
        for idx, cam in enumerate(cameras_config, start=1):
            canal = cam.get("canal") or idx
            nome_cam = cam.get("nome") or f"Camera {canal}"
            ip_cam = cam.get("ip") or "N/A"

            # Busca status na API (por nome exato, minúsculo ou IP)
            is_ok = None
            if status_dict:
                is_ok = status_dict.get(nome_cam)
                if is_ok is None:
                    is_ok = status_dict.get(nome_cam.lower())
                if is_ok is None and ip_cam != "N/A":
                    is_ok = status_dict.get(ip_cam)

            # Fallback para webhook CSV legado se a API estava inacessível
            if is_ok is None:
                if not status_dict:
                    if status_webhook is None:
                        try:
                            from src.application.webhook_defense import get_status_cameras_defense
                            caminho_log = config_extra.get("pasta_origem", "")
                            status_webhook = get_status_cameras_defense(caminho_log)
                        except Exception:
                            status_webhook = {}
                    is_ok = status_webhook.get(nome_cam, "OK") == "OK"
                else:
                    # A API respondeu com sucesso, mas a câmera não está cadastrada no Defense IA
                    is_ok = False

            # Busca dados reais de gravação na API
            info_grav = gravacoes_map.get(nome_cam) or gravacoes_map.get(nome_cam.lower()) or (gravacoes_map.get(ip_cam) if ip_cam != "N/A" else None)
            if info_grav:
                total_dias = info_grav["total_dias"]
                mapa = info_grav["mapa"]
                dias_grav = info_grav["dias_com_gravacao"]
                status_grav = info_grav["status_gravacao"]
            else:
                total_dias = 15 if is_ok else 0
                mapa = ("█" * 15) if is_ok else ("░" * 15)
                dias_grav = dias_15_ord if is_ok else []
                status_grav = "COM_GRAVACAO" if is_ok else "SEM_GRAVACAO"

            status_cameras.append({
                "canal": canal,
                "nome": nome_cam,
                "ip": ip_cam,
                "online": is_ok,
                "status_comunicacao": "ONLINE" if is_ok else "OFFLINE",
                "status_gravacao": status_grav,
                "total_dias": total_dias,
                "mapa": mapa,
                "dias_com_gravacao": dias_grav,
            })
            if cam.get("password"):
                cameras_para_captura.append({**cam, "canal": canal, "nome": nome_cam})

    elif cameras_api:
        # Caso 2: Galeria vazia, mas a API descobriu câmeras dinamicamente
        for cam in cameras_api:
            canal = cam.get("canal")
            nome_cam = cam.get("nome")
            ip_cam = cam.get("ip") or "N/A"
            ch_code = cam.get("codigo") or ""
            is_ok = cam.get("online", False)

            # Busca dados reais de gravação na API
            info_grav = (
                gravacoes_map.get(ch_code)
                or gravacoes_map.get(nome_cam)
                or gravacoes_map.get(nome_cam.lower())
                or (gravacoes_map.get(ip_cam) if ip_cam != "N/A" else None)
            )
            if info_grav:
                total_dias = info_grav["total_dias"]
                mapa = info_grav["mapa"]
                dias_grav = info_grav["dias_com_gravacao"]
                status_grav = info_grav["status_gravacao"]
            else:
                total_dias = 15 if is_ok else 0
                mapa = ("█" * 15) if is_ok else ("░" * 15)
                dias_grav = dias_15_ord if is_ok else []
                status_grav = "COM_GRAVACAO" if is_ok else "SEM_GRAVACAO"

            status_cameras.append({
                "canal": canal,
                "nome": nome_cam,
                "ip": ip_cam,
                "online": is_ok,
                "status_comunicacao": "ONLINE" if is_ok else "OFFLINE",
                "status_gravacao": status_grav,
                "total_dias": total_dias,
                "mapa": mapa,
                "dias_com_gravacao": dias_grav,
            })
            if cam.get("password"):
                cameras_para_captura.append({**cam, "canal": canal, "nome": nome_cam})

    else:
        # Caso 3: Nem cameras_config nem a API retornaram nada
        return None

    # Captura opcional de imagens noturnas RTSP
    if conf is not None and cameras_para_captura:
        try:
            from src.camera.rtsp_client import capturar_imagens_noite_vms
            capturar_imagens_noite_vms(equipamento.get("name", "Defense"), cameras_para_captura, conf)
            por_canal = {c["canal"]: c for c in cameras_para_captura}
            for st in status_cameras:
                cap = por_canal.get(st["canal"])
                if cap and "imagem_noite" in cap:
                    st["imagem_noite"] = cap["imagem_noite"]
        except Exception as e:
            logging.warning(f"  [DEFENSE] Falha ao capturar imagens RTSP da noite: {e}")

    return status_cameras


def realizar_backup_defense(equipamento: dict, pasta_destino: Path, conf: dict = None) -> dict:
    """
    Realiza o backup do Intelbras Defense IA.
    Modo 1: Coleta o arquivo de backup (.dbk, .zip, etc) gerado automaticamente pelo Defense
            (requer 'pasta_origem' no config_extra).
    Modo 2: Fallback para extrair um dump direto do banco de dados MySQL nativo.
    """
    nome = equipamento.get("name", "Defense")
    logging.info(f"\n{'='*50}\n{nome} [DEFENSE]\n{'='*50}")

    # Extrai configurações que podem vir do painel
    config_extra = parse_config_extra(equipamento)

    pasta_origem_str = config_extra.get("pasta_origem")
    status_cameras = _montar_status_cameras_defense(equipamento, conf)

    # ==========================================
    # MODO 1: Coleta do arquivo nativo do Defense
    # ==========================================
    if pasta_origem_str:
        logging.info(f"  [DEFENSE] Coletando arquivo de backup nativo na pasta: {pasta_origem_str}")
        pasta_origem = Path(pasta_origem_str)
        if not pasta_origem.exists() or not pasta_origem.is_dir():
            logging.error(f"  [DEFENSE] Pasta de origem não encontrada: {pasta_origem}")
            return {"nome": nome, "status": "ERRO", "cameras": status_cameras}

        # Busca apenas os arquivos de backup (.enc, .zip, .dbk) ignorando .cfg e temporários
        extensoes_validas = {".enc", ".zip", ".dbk", ".bak"}
        arquivos = [f for f in pasta_origem.iterdir() if f.is_file() and f.suffix.lower() in extensoes_validas]

        if not arquivos:
            logging.warning(f"  [DEFENSE] Nenhum arquivo encontrado na pasta: {pasta_origem}")
            return {"nome": nome, "status": "SEM_ARQUIVOS", "cameras": status_cameras}

        # Pega o arquivo mais recente baseado na data de modificação
        arquivo_mais_recente = max(arquivos, key=lambda f: f.stat().st_mtime)
        destino_arquivo = pasta_destino / arquivo_mais_recente.name

        try:
            shutil.copy2(arquivo_mais_recente, destino_arquivo)
            logging.info(f"  [DEFENSE] Arquivo de backup copiado com sucesso: {arquivo_mais_recente.name}")
            return {"nome": nome, "status": "OK", "cameras": status_cameras}
        except Exception as e:
            logging.error(f"  [DEFENSE] Erro ao copiar arquivo de backup: {e}")
            return {"nome": nome, "status": "ERRO", "cameras": status_cameras}

    # ==========================================
    # MODO 2: Dump do Banco de Dados MySQL
    # ==========================================
    logging.info(f"  [DEFENSE] Iniciando backup via Dump de Banco de Dados MySQL para {nome}...")
    
    db_host = equipamento.get("ip", "127.0.0.1")
    db_port = config_extra.get("db_port", "3307") # Porta padrao do MySQL no Defense IA
    db_user = equipamento.get("username", "root")
    db_pass = equipamento.get("password", "")
    db_name = config_extra.get("db_name", "defense") # Nome provável do BD
    
    data_atual = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_safe = re.sub(r"[^\w.-]", "_", nome)
    arquivo_dump = pasta_destino / f"DUMP_{nome_safe}_{data_atual}.sql"

    # Define a variável de ambiente para a senha do MySQL
    env = os.environ.copy()
    if db_pass:
        env["MYSQL_PWD"] = db_pass

    # Comando mysqldump
    comando = [
        "mysqldump",
        "-h", db_host,
        "-P", str(db_port),
        "-u", db_user,
        "--single-transaction",
        "--quick",
        "--routines",
        "--events",
        db_name
    ]

    logging.info(f"  Executando comando mysqldump para o banco '{db_name}' em {db_host}:{db_port}...")
    
    try:
        with open(arquivo_dump, 'w', encoding='utf-8') as f_out:
            subprocess.run(comando, env=env, stdout=f_out, stderr=subprocess.PIPE, text=True, check=True, timeout=600)
            
        logging.info(f"  [DEFENSE] Dump gerado com sucesso: {arquivo_dump.name}")
        return {"nome": nome, "status": "OK", "cameras": status_cameras}

    except subprocess.TimeoutExpired:
        logging.error("  Erro: mysqldump excedeu o tempo limite (600s) e foi interrompido.")
        if arquivo_dump.exists():
            arquivo_dump.unlink()
        return {"nome": nome, "status": "ERRO", "cameras": status_cameras}
    except FileNotFoundError:
        logging.error("  Erro: Utilitário 'mysqldump' não encontrado. Verifique se o MySQL Client está instalado e no PATH do sistema.")
        return {"nome": nome, "status": "ERRO", "cameras": status_cameras}
    except subprocess.CalledProcessError as e:
        logging.error(f"  Erro ao executar mysqldump (Código {e.returncode}): {e.stderr.strip()}")
        if arquivo_dump.exists():
            arquivo_dump.unlink() # Remove o arquivo vazio/incompleto
        return {"nome": nome, "status": "ERRO", "cameras": status_cameras}
    except Exception as e:
        logging.error(f"  Erro inesperado durante o dump: {e}")
        return {"nome": nome, "status": "ERRO", "cameras": status_cameras}
