import logging
import datetime
import csv
import io
import os
import socket
import re
import threading

# ==========================================
# CONFIGURAÇÃO
# ==========================================
PORTA_SNMP = 162
ARQUIVO_CSV = r"C:\Relatorios_Digifort\quedas_cameras.csv"

ARQUIVO_EXPORT_CAMERAS = ""
DICIONARIO_CAMERAS_NOME = {} # Nome / Descricao / Normalizado -> info
DICIONARIO_CAMERAS_IP = {}   # IP -> info
LISTA_CAMERAS_UNICAS = []    # Lista canônica de câmeras
ULTIMO_CAMINHO_EXPORT = ""

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
    
    if os.path.isfile(caminho_arquivo):
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
                
                # Nome de exibição principal:
                # Se 'nome' for apenas número (ex: '01', '44') e tiver descrição, usa a descrição.
                # Se descrição for mais detalhada, prioriza a descrição pois é o que vem nos alarmes do Digifort.
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
                
                # Mapeia todas as formas de busca para o mesmo objeto info
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
        logging.warning(f"[AVISO] Arquivo de exportacao '{caminho_arquivo}' nao encontrado.")
        
    return dicionario_nome, dicionario_ip, lista_unicas

def registrar_queda(nome_camera, nome_evento):
    agora = datetime.datetime.now()
    data = agora.strftime("%Y-%m-%d")
    hora = agora.strftime("%H:%M:%S")
    
    pasta = os.path.dirname(ARQUIVO_CSV)
    if pasta and not os.path.exists(pasta):
        os.makedirs(pasta)
        
    arquivo_existe = os.path.isfile(ARQUIVO_CSV)
    
    with open(ARQUIVO_CSV, mode='a', newline='', encoding='utf-8-sig') as file:
        writer = csv.writer(file, delimiter=';')
        if not arquivo_existe:
            writer.writerow(['Data', 'Hora', 'Camera', 'Evento'])
            
        writer.writerow([data, hora, nome_camera, nome_evento])


def get_status_cameras(caminho_export="", caminho_log=""):
    """Lê o histórico do CSV e retorna o dicionário com o status de cada câmera"""
    global ULTIMO_CAMINHO_EXPORT
    
    # Recarrega se o caminho mudou ou se o dicionário estiver vazio
    if caminho_export and (caminho_export != ULTIMO_CAMINHO_EXPORT or not DICIONARIO_CAMERAS_NOME):
        nomes, ips, unicas = carregar_dicionario_cameras(caminho_export)
        DICIONARIO_CAMERAS_NOME.clear()
        DICIONARIO_CAMERAS_IP.clear()
        LISTA_CAMERAS_UNICAS.clear()
        DICIONARIO_CAMERAS_NOME.update(nomes)
        DICIONARIO_CAMERAS_IP.update(ips)
        LISTA_CAMERAS_UNICAS.extend(unicas)
        ULTIMO_CAMINHO_EXPORT = caminho_export
        
    status_cameras = {}
    if LISTA_CAMERAS_UNICAS:
        for cam in LISTA_CAMERAS_UNICAS:
            status_cameras[cam['Nome']] = "OK"
    else:
        for nome in DICIONARIO_CAMERAS_NOME.keys():
            if not nome.isdigit():
                status_cameras[nome] = "OK"
            
    arquivo_alvo = caminho_log if caminho_log else ARQUIVO_CSV
        
    if os.path.isfile(arquivo_alvo):
        linhas_log, _ = ler_linhas_csv(arquivo_alvo)
        for row in linhas_log:
            camera_raw = obter_valor_coluna(row, 'camera')
            evento = obter_valor_coluna(row, 'evento')
            if not camera_raw or not evento:
                continue
                
            info = (DICIONARIO_CAMERAS_NOME.get(camera_raw) or 
                    DICIONARIO_CAMERAS_NOME.get(camera_raw.lower()) or 
                    DICIONARIO_CAMERAS_NOME.get(normalizar_texto(camera_raw)))
                    
            nome_alvo = info['Nome'] if info else camera_raw
            is_ok = ('restaurada' in evento.lower() or 'online' in evento.lower() or evento.lower() == 'ok')
            status_cameras[nome_alvo] = "OK" if is_ok else "FALHA"
                        
    return status_cameras

def get_caminho_csv(caminho_log=""):
    """Retorna o caminho do arquivo de quedas"""
    return caminho_log if caminho_log else ARQUIVO_CSV


def get_detalhes_cameras(caminho_export="", caminho_log=""):
    """Retorna a lista ordenada de câmeras do export_cameras.csv, com canal sequencial (1..N),
    nome, ip e status ("OK"/"FALHA"). Usada pelo backup para capturar a imagem da noite via RTSP."""
    status_dict = get_status_cameras(caminho_export, caminho_log)  # garante LISTA_CAMERAS_UNICAS carregada
    detalhes = []
    for idx, cam in enumerate(LISTA_CAMERAS_UNICAS, start=1):
        nome = cam.get("Nome")
        detalhes.append({
            "canal": idx,
            "nome": nome,
            "ip": cam.get("IP") or "",
            "status": status_dict.get(nome, "OK"),
        })
    return detalhes


# =============== SNIFFER SNMP ===============
sniffer_socket = None

def rodar_sniffer_snmp():
    global sniffer_socket
    sniffer_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sniffer_socket.bind(('0.0.0.0', PORTA_SNMP))
        logging.info(f"[OK] Sniffer SNMP rodando na porta {PORTA_SNMP}...")
    except Exception as e:
        logging.error(f"[ERRO] ao iniciar Sniffer SNMP na porta {PORTA_SNMP}: {e}")
        return

    while True:
        try:
            dados, endereco = sniffer_socket.recvfrom(4096)
        except Exception:
            break
            
        status_encontrado = None
        
        # OIDs Digifort
        if b'\x06\x0d\x2b\x06\x01\x04\x01\x82\xf7\x04\x01\x01\x64\x02\x04' in dados:
            status_encontrado = "Falha de Comunicacao"
        elif b'\x06\x0d\x2b\x06\x01\x04\x01\x82\xf7\x04\x01\x01\x64\x02\x05' in dados:
            status_encontrado = "Camera Restaurada"
        else:
            status_encontrado = "Outro Evento"

        textos_encontrados = re.findall(b'[ -~]{4,}', dados)
        camera_identificada = None
        
        for texto in textos_encontrados:
            try:
                texto_limpo = texto.decode('utf-8', errors='ignore').strip()
                
                if texto_limpo.endswith('0') and len(texto_limpo) > 1 and texto_limpo[:-1] in DICIONARIO_CAMERAS_NOME:
                    texto_limpo = texto_limpo[:-1]
                
                texto_lower = texto_limpo.lower()
                
                ip_match = re.search(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', texto_limpo)
                if ip_match:
                    ip_achado = ip_match.group(0)
                    if ip_achado in DICIONARIO_CAMERAS_IP:
                        camera_identificada = DICIONARIO_CAMERAS_IP[ip_achado]

                if not camera_identificada:
                    for nome, info in DICIONARIO_CAMERAS_NOME.items():
                        if not nome.isdigit() and (nome.lower() in texto_lower or normalizar_texto(nome) in normalizar_texto(texto_limpo)):
                            camera_identificada = info
                            break
            except Exception:
                logging.debug("Falha ao interpretar trap SNMP", exc_info=True)
                
        if camera_identificada and status_encontrado != "Outro Evento":
            registrar_queda(camera_identificada['Nome'], status_encontrado)
            logging.info(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] SNMP TRAP: {camera_identificada['Nome']} | {status_encontrado}")

snmp_thread = None

def start_webhook(caminho_csv_export: str, caminho_log: str):
    """
    Mantido o nome original 'start_webhook' para não quebrar o service.py,
    mas agora inicia apenas o sniffer SNMP e não mais um servidor HTTP.
    """
    global ARQUIVO_EXPORT_CAMERAS, ARQUIVO_CSV, snmp_thread, LISTA_CAMERAS_UNICAS, ULTIMO_CAMINHO_EXPORT
    if snmp_thread is not None:
        return 
    
    ARQUIVO_EXPORT_CAMERAS = caminho_csv_export
    ARQUIVO_CSV = caminho_log
    
    DICIONARIO_CAMERAS_NOME.clear()
    DICIONARIO_CAMERAS_IP.clear()
    LISTA_CAMERAS_UNICAS.clear()
    nomes, ips, unicas = carregar_dicionario_cameras(ARQUIVO_EXPORT_CAMERAS)
    DICIONARIO_CAMERAS_NOME.update(nomes)
    DICIONARIO_CAMERAS_IP.update(ips)
    LISTA_CAMERAS_UNICAS.extend(unicas)
    ULTIMO_CAMINHO_EXPORT = ARQUIVO_EXPORT_CAMERAS
    
    # Inicia o Sniffer SNMP na 162
    snmp_thread = threading.Thread(target=rodar_sniffer_snmp, daemon=True)
    snmp_thread.start()
    
    logging.info(f"[OK] Agente Digifort iniciado (Modo SNMP na {PORTA_SNMP}).")

def stop_webhook():
    global snmp_thread, sniffer_socket
    if sniffer_socket:
        sniffer_socket.close()
        sniffer_socket = None
    snmp_thread = None
    logging.info("[PARADO] Agente Digifort SNMP parado.")

def rodar_servidor():
    start_webhook(ARQUIVO_EXPORT_CAMERAS, ARQUIVO_CSV)
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        stop_webhook()

if __name__ == '__main__':
    import sys
    print("="*60)
    print("  AGENTE DIGIFORT (SNMP ONLY) - TRILAN NVR BACKUP")
    print("="*60)
    
    if len(sys.argv) > 1:
        ARQUIVO_EXPORT_CAMERAS = sys.argv[1]
    else:
        caminho = input(r"Digite o caminho do arquivo CSV exportado do Digifort (ou Enter para 'export_cameras.csv'): ").strip()
        if caminho:
            ARQUIVO_EXPORT_CAMERAS = caminho
        else:
            ARQUIVO_EXPORT_CAMERAS = "export_cameras.csv"
            
    if len(sys.argv) > 2:
        ARQUIVO_CSV = sys.argv[2]
    else:
        caminho_log = input(f"Digite o caminho para salvar o CSV de historico de quedas (ou Enter para o padrao '{ARQUIVO_CSV}'): ").strip()
        if caminho_log:
            ARQUIVO_CSV = caminho_log
            
    rodar_servidor()
