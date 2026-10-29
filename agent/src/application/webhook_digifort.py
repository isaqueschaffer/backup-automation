import logging
import datetime
import csv
import io
import os
import re
import sys
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# CONFIGURAÇÃO
# ==========================================
ARQUIVO_CSV = r"C:\Relatorios_Digifort\quedas_cameras.csv"
ARQUIVO_EXPORT_CAMERAS = ""
DICIONARIO_CAMERAS_NOME = {} # Nome / Descricao / Normalizado -> info
DICIONARIO_CAMERAS_IP = {}   # IP -> info
LISTA_CAMERAS_UNICAS = []    # Lista canônica de câmeras
ULTIMO_CAMINHO_EXPORT = ""

_cameras_lock = threading.Lock()
INTERVALO_MONITORAMENTO_PING_S = 60
monitor_ping_thread = None
monitor_stop_event = threading.Event()
_ultimo_status_cameras = {}

def normalizar_texto(texto):
    """Normaliza texto removendo caracteres especiais e espaços extras."""
    if not texto:
        return ""
    t = re.sub(r'[^a-zA-Z0-9]', ' ', str(texto).lower())
    return ' '.join(t.split())

def ler_linhas_csv(caminho_arquivo):
    """Lê arquivo CSV tentando UTF-8 com fallback para CP1252 (ANSI do Windows)."""
    encodings_para_tentar = ['utf-8-sig', 'cp1252', 'latin1']
    for enc in encodings_para_tentar:
        try:
            with open(caminho_arquivo, mode='r', encoding=enc) as f:
                content = f.read()
                if '\ufffd' not in content:
                    f_io = io.StringIO(content)
                    reader = csv.DictReader(f_io, delimiter=';')
                    if reader.fieldnames:
                        return list(reader), reader.fieldnames
        except UnicodeDecodeError:
            continue
        except Exception:
            break
            
    with open(caminho_arquivo, mode='r', encoding='utf-8-sig', errors='replace') as f:
        reader = csv.DictReader(f, delimiter=';')
        return list(reader), reader.fieldnames or []

def obter_valor_coluna(row, *nomes_possiveis):
    """Busca o valor da coluna correspondente ignorando maiúsculas/minúsculas e acentuação básica."""
    for chave, valor in row.items():
        if not chave:
            continue
        chave_limpa = chave.strip().lstrip('\ufeff').lower()
        for np in nomes_possiveis:
            if np.lower() == chave_limpa:
                return valor.strip() if valor else ''
    for chave, valor in row.items():
        if not chave:
            continue
        chave_limpa = chave.strip().lstrip('\ufeff').lower()
        for np in nomes_possiveis:
            if np.lower() in chave_limpa:
                return valor.strip() if valor else ''
    return ''

def carregar_dicionario_cameras(caminho_arquivo):
    dicionario_nome = {}
    dicionario_ip = {}
    lista_unicas = []
    
    if caminho_arquivo and os.path.isfile(caminho_arquivo):
        try:
            linhas, colunas = ler_linhas_csv(caminho_arquivo)
            is_novo_formato = any(k in [c.lower() for c in colunas] for k in ['endereço', 'endereco', 'nome', 'ip'])
            
            for index, row in enumerate(linhas, start=1):
                if is_novo_formato:
                    ip = obter_valor_coluna(row, 'endereço', 'endereco', 'ip')
                    nome = obter_valor_coluna(row, 'nome')
                    descricao = obter_valor_coluna(row, 'descrição', 'descricao')
                else:
                    ip = ''
                    nome = f"{index:02d}"
                    descricao = obter_valor_coluna(row, 'descrição', 'descricao')
                
                if nome.isdigit() and descricao:
                    nome_exibicao = descricao
                elif descricao and len(descricao) > len(nome):
                    nome_exibicao = descricao
                else:
                    nome_exibicao = nome or descricao or f"Camera {index:02d}"
                    
                info = {
                    'Nome': nome_exibicao,
                    'NomeCurto': nome,
                    'Descricao': descricao,
                    'IP': ip
                }
                lista_unicas.append(info)
                
                if nome:
                    dicionario_nome[nome] = info
                    dicionario_nome[nome.lower()] = info
                    dicionario_nome[normalizar_texto(nome)] = info
                if descricao:
                    dicionario_nome[descricao] = info
                    dicionario_nome[descricao.lower()] = info
                    dicionario_nome[normalizar_texto(descricao)] = info
                    
                num_str = f"{index:02d}"
                dicionario_nome[num_str] = info
                dicionario_nome[str(index)] = info
                
                if ip:
                    dicionario_ip[ip] = info
                    
            logging.info(f"[OK] {len(lista_unicas)} cameras carregadas do arquivo {caminho_arquivo}")
        except Exception as e:
            logging.error(f"[ERRO] ao ler {caminho_arquivo}: {e}")
    else:
        if caminho_arquivo:
            logging.warning(f"[AVISO] Arquivo de exportacao '{caminho_arquivo}' nao encontrado.")
        
    return dicionario_nome, dicionario_ip, lista_unicas

def registrar_queda(nome_camera, nome_evento):
    agora = datetime.datetime.now()
    data = agora.strftime("%Y-%m-%d")
    hora = agora.strftime("%H:%M:%S")
    
    pasta = os.path.dirname(ARQUIVO_CSV)
    if pasta and not os.path.exists(pasta):
        try:
            os.makedirs(pasta, exist_ok=True)
        except Exception:
            pass
        
    arquivo_existe = os.path.isfile(ARQUIVO_CSV)
    
    try:
        with open(ARQUIVO_CSV, mode='a', newline='', encoding='utf-8-sig') as file:
            writer = csv.writer(file, delimiter=';')
            if not arquivo_existe:
                writer.writerow(['Data', 'Hora', 'Camera', 'Evento'])
                
            writer.writerow([data, hora, nome_camera, nome_evento])
    except Exception as e:
        logging.error(f"[DIGIFORT] Erro ao gravar log de queda no CSV '{ARQUIVO_CSV}': {e}")


# ==========================================
# TESTES DE STATUS VIA PING ICMP
# ==========================================

def ping_camera(ip: str, timeout_ms: int = 1000) -> bool:
    """
    Executa ping ICMP seguro na câmera usando o utilitário nativo do sistema operacional.
    Retorna True se responder com sucesso (TTL), False em caso de timeout, host inacessível ou IP inválido.
    """
    if not ip or not isinstance(ip, str):
        return False
    
    ip_limpo = ip.strip()
    if not ip_limpo or ip_limpo.upper() in ("N/A", "NONE", "NULL", "0.0.0.0"):
        return False
    
    # Sanitização rígida: primeiro caractere deve ser alfanumérico (evita CLI Argument Injection como '-t')
    if ip_limpo.startswith("-") or not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9.\-_:]*$', ip_limpo):
        return False

    timeout_ms = max(200, int(timeout_ms))
    
    if sys.platform == "win32":
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip_limpo]
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    else:
        timeout_s = max(1, timeout_ms // 1000)
        cmd = ["ping", "-c", "1", "-W", str(timeout_s), ip_limpo]
        creation_flags = 0

    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=(timeout_ms / 1000.0) + 1.5,
            creationflags=creation_flags
        )
        if res.returncode != 0:
            return False
            
        saida = (res.stdout or "").lower()
        
        # Rejeita respostas de erro (host inacessível, esgotado o tempo, perda total)
        termos_erro = ("inacess", "unreachable", "esgotado", "timed out", "100% loss", "100% de perda")
        if any(termo in saida for termo in termos_erro):
            return False
            
        # Sucesso é confirmado pela presença de TTL na resposta
        if "ttl=" in saida:
            return True
            
        return False
    except Exception as e:
        logging.debug(f"[PING] Erro ao disparar ping para {ip_limpo}: {e}")
        return False


def testar_cameras_por_ping(cameras: list, timeout_ms: int = 1000, max_workers: int = 20) -> dict:
    """
    Testa uma lista de câmeras via Ping ICMP em paralelo.
    'cameras' pode ser uma lista de dicts (contendo 'Nome'/'IP' ou 'nome'/'ip') ou lista de strings de IP.
    Retorna dicionário mapeando identificador (Nome e/ou IP) -> bool (True=OK/Online, False=FALHA/Offline).
    """
    resultados = {}
    if not cameras:
        return resultados

    tarefas = {}
    workers = min(max_workers, max(1, len(cameras)))
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for cam in cameras:
            if isinstance(cam, dict):
                nome = cam.get("Nome") or cam.get("nome") or ""
                ip = (cam.get("IP") or cam.get("ip") or "").strip()
                chave = nome or ip
            else:
                chave = str(cam).strip()
                ip = chave
                nome = chave
                
            if not ip or ip.upper() in ("N/A", "NONE"):
                resultados[chave] = False
                if nome:
                    resultados[nome] = False
                continue
                
            futuro = executor.submit(ping_camera, ip, timeout_ms)
            tarefas[futuro] = (chave, ip, nome)
            
        for futuro in as_completed(tarefas):
            chave, ip, nome = tarefas[futuro]
            try:
                ok = futuro.result()
            except Exception:
                ok = False
            resultados[chave] = ok
            if nome:
                resultados[nome] = ok
            if ip:
                resultados[ip] = ok
                
    return resultados


def get_status_cameras(caminho_export="", caminho_log="", realizar_ping=True):
    """
    Retorna dicionário {nome_camera: "OK" | "FALHA"}.
    Se realizar_ping=True, executa ping concorrente nas câmeras.
    Se realizar_ping=False, consulta o histórico do CSV de quedas.
    """
    global ULTIMO_CAMINHO_EXPORT
    
    with _cameras_lock:
        if caminho_export and (caminho_export != ULTIMO_CAMINHO_EXPORT or not DICIONARIO_CAMERAS_NOME):
            nomes, ips, unicas = carregar_dicionario_cameras(caminho_export)
            DICIONARIO_CAMERAS_NOME.clear()
            DICIONARIO_CAMERAS_IP.clear()
            LISTA_CAMERAS_UNICAS.clear()
            DICIONARIO_CAMERAS_NOME.update(nomes)
            DICIONARIO_CAMERAS_IP.update(ips)
            LISTA_CAMERAS_UNICAS.extend(unicas)
            ULTIMO_CAMINHO_EXPORT = caminho_export

        cameras_snapshot = list(LISTA_CAMERAS_UNICAS)
        dicionario_nome_snapshot = dict(DICIONARIO_CAMERAS_NOME)
        
    status_cameras = {}

    if realizar_ping:
        cameras_para_testar = []
        if cameras_snapshot:
            for cam in cameras_snapshot:
                cameras_para_testar.append(cam)
        else:
            vistos = set()
            for _, info in dicionario_nome_snapshot.items():
                if info['Nome'] not in vistos:
                    vistos.add(info['Nome'])
                    cameras_para_testar.append(info)

        if cameras_para_testar:
            res_ping = testar_cameras_por_ping(cameras_para_testar, timeout_ms=1000)
            for cam in cameras_para_testar:
                nome = cam['Nome']
                ip = cam.get('IP') or ''
                is_ok = bool(res_ping.get(nome, False) or (ip and res_ping.get(ip, False)))
                status_cameras[nome] = "OK" if is_ok else "FALHA"
        return status_cameras

    # Modo histórico (realizar_ping=False)
    if cameras_snapshot:
        for cam in cameras_snapshot:
            status_cameras[cam['Nome']] = "OK"
    else:
        for nome in dicionario_nome_snapshot.keys():
            if not str(nome).isdigit():
                status_cameras[nome] = "OK"
            
    arquivo_alvo = caminho_log if caminho_log else ARQUIVO_CSV
    if os.path.isfile(arquivo_alvo):
        linhas_log, _ = ler_linhas_csv(arquivo_alvo)
        for row in linhas_log:
            camera_raw = obter_valor_coluna(row, 'camera')
            evento = obter_valor_coluna(row, 'evento')
            if not camera_raw or not evento:
                continue
                
            info = (dicionario_nome_snapshot.get(camera_raw) or 
                    dicionario_nome_snapshot.get(camera_raw.lower()) or 
                    dicionario_nome_snapshot.get(normalizar_texto(camera_raw)))
                    
            nome_alvo = info['Nome'] if info else camera_raw
            is_ok = ('restaurada' in evento.lower() or 'online' in evento.lower() or evento.lower() == 'ok')
            status_cameras[nome_alvo] = "OK" if is_ok else "FALHA"

    return status_cameras


def get_caminho_csv(caminho_log=""):
    """Retorna o caminho do arquivo de quedas"""
    return caminho_log if caminho_log else ARQUIVO_CSV


def get_detalhes_cameras(caminho_export="", caminho_log="", realizar_ping=True, status_dict=None):
    """
    Retorna a lista ordenada de câmeras do export_cameras.csv, com canal sequencial (1..N),
    nome, ip e status ("OK"/"FALHA"). Usada pelo backup para capturar a imagem da noite via RTSP.
    Permite passar 'status_dict' pré-calculado para evitar testes duplicados de ping.
    """
    if status_dict is None:
        status_dict = get_status_cameras(caminho_export, caminho_log, realizar_ping=realizar_ping)
    
    with _cameras_lock:
        cameras_snapshot = list(LISTA_CAMERAS_UNICAS)

    detalhes = []
    for idx, cam in enumerate(cameras_snapshot, start=1):
        nome = cam.get("Nome")
        detalhes.append({
            "canal": idx,
            "nome": nome,
            "ip": cam.get("IP") or "",
            "status": status_dict.get(nome, "FALHA" if realizar_ping else "OK"),
        })
    return detalhes


# ==========================================
# MONITOR EM BACKGROUND (SUBSTITUI O SNIFFER SNMP)
# ==========================================

def rodar_monitor_ping():
    """
    Thread de monitoramento periódico via Ping ICMP.
    A cada intervalo pré-definido, testa as câmeras e registra transições de status
    (queda / retorno) no CSV de histórico.
    """
    global _ultimo_status_cameras
    logging.info(f"[OK] Monitor de Ping Digifort rodando (intervalo: {INTERVALO_MONITORAMENTO_PING_S}s)...")
    
    while not monitor_stop_event.is_set():
        try:
            with _cameras_lock:
                cameras_snapshot = list(LISTA_CAMERAS_UNICAS)

            if cameras_snapshot:
                res = testar_cameras_por_ping(cameras_snapshot, timeout_ms=1000)
                for cam in cameras_snapshot:
                    nome = cam['Nome']
                    ip = (cam.get('IP') or '').strip()
                    is_ok = bool(res.get(nome, False) or (ip and res.get(ip, False)))
                    status_atual = "OK" if is_ok else "FALHA"
                    
                    status_anterior = _ultimo_status_cameras.get(nome)
                    if status_anterior is not None and status_anterior != status_atual:
                        if status_atual == "FALHA":
                            registrar_queda(nome, "Falha de Comunicacao (Ping Timeout)")
                            logging.info(f"[DIGIFORT PING] Queda detectada: {nome} ({ip})")
                        else:
                            registrar_queda(nome, "Camera Restaurada (Ping OK)")
                            logging.info(f"[DIGIFORT PING] Câmera restaurada: {nome} ({ip})")
                            
                    _ultimo_status_cameras[nome] = status_atual
        except Exception as e:
            logging.error(f"[DIGIFORT PING] Erro no ciclo de monitoramento: {e}")
            
        monitor_stop_event.wait(timeout=INTERVALO_MONITORAMENTO_PING_S)


def start_webhook(caminho_csv_export: str = "", caminho_log: str = ""):
    """
    Mantido o nome original 'start_webhook' para compatibilidade com o service.py.
    Inicia a thread de monitoramento periódico das câmeras via Ping ICMP.
    """
    global ARQUIVO_EXPORT_CAMERAS, ARQUIVO_CSV, monitor_ping_thread, ULTIMO_CAMINHO_EXPORT
    if monitor_ping_thread is not None and monitor_ping_thread.is_alive():
        return 
    
    if caminho_csv_export:
        ARQUIVO_EXPORT_CAMERAS = caminho_csv_export
    if caminho_log:
        ARQUIVO_CSV = caminho_log
    
    with _cameras_lock:
        DICIONARIO_CAMERAS_NOME.clear()
        DICIONARIO_CAMERAS_IP.clear()
        LISTA_CAMERAS_UNICAS.clear()
        nomes, ips, unicas = carregar_dicionario_cameras(ARQUIVO_EXPORT_CAMERAS)
        DICIONARIO_CAMERAS_NOME.update(nomes)
        DICIONARIO_CAMERAS_IP.update(ips)
        LISTA_CAMERAS_UNICAS.extend(unicas)
        ULTIMO_CAMINHO_EXPORT = ARQUIVO_EXPORT_CAMERAS
    
    monitor_stop_event.clear()
    monitor_ping_thread = threading.Thread(target=rodar_monitor_ping, daemon=True)
    monitor_ping_thread.start()
    
    logging.info("[OK] Agente Digifort iniciado (Monitoramento via Ping ICMP).")


def stop_webhook():
    """Para a thread de monitoramento periódico por Ping."""
    global monitor_ping_thread
    monitor_stop_event.set()
    if monitor_ping_thread and monitor_ping_thread.is_alive():
        monitor_ping_thread.join(timeout=2.0)
    monitor_ping_thread = None
    logging.info("[PARADO] Agente Digifort (Monitoramento Ping) parado.")


def rodar_servidor():
    start_webhook(ARQUIVO_EXPORT_CAMERAS, ARQUIVO_CSV)
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_webhook()


if __name__ == '__main__':
    print("="*60)
    print("  AGENTE DIGIFORT (PING ICMP) - TRILAN NVR BACKUP")
    print("="*60)
    
    if len(sys.argv) > 1:
        ARQUIVO_EXPORT_CAMERAS = sys.argv[1]
    else:
        caminho = input(r"Digite o caminho do arquivo CSV exportado do Digifort (ou Enter para 'export_cameras.csv'): ").strip()
        ARQUIVO_EXPORT_CAMERAS = caminho if caminho else "export_cameras.csv"
            
    if len(sys.argv) > 2:
        ARQUIVO_CSV = sys.argv[2]
    else:
        caminho_log = input(f"Digite o caminho para salvar o CSV de historico de quedas (ou Enter para o padrao '{ARQUIVO_CSV}'): ").strip()
        if caminho_log:
            ARQUIVO_CSV = caminho_log
            
    rodar_servidor()
