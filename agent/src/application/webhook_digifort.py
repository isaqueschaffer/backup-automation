import datetime
import csv
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
DICIONARIO_CAMERAS_NOME = {} # Nome -> info
DICIONARIO_CAMERAS_IP = {} # IP -> info

def carregar_dicionario_cameras(caminho_arquivo):
    dicionario_nome = {}
    dicionario_ip = {}
    if os.path.isfile(caminho_arquivo):
        try:
            with open(caminho_arquivo, mode='r', encoding='utf-8-sig', errors='replace') as f:
                reader = csv.DictReader(f, delimiter=';')
                
                colunas = reader.fieldnames or []
                is_novo_formato = 'Endereço' in colunas or 'Nome' in colunas
                
                for index, row in enumerate(reader, start=1):
                    if is_novo_formato:
                        ip = row.get('Endereço', '')
                        nome = row.get('Nome', '')
                        descricao = row.get('Descrição', '')
                        
                        info = {'Nome': nome or descricao, 'IP': ip}
                        if nome:
                            dicionario_nome[nome] = info
                        elif descricao:
                            dicionario_nome[descricao] = info
                        if ip:
                            dicionario_ip[ip] = info
                    else:
                        numero = f"{index:02d}"
                        descricao = row.get("Descrição", "")
                        if descricao:
                            info = {'Nome': descricao.strip(), 'IP': ''}
                            dicionario_nome[descricao.strip()] = info
                            dicionario_nome[numero] = info
                            
            print(f"[OK] Cameras carregadas do arquivo {caminho_arquivo}")
        except Exception as e:
            print(f"[ERRO] ao ler {caminho_arquivo}: {e}")
    else:
        print(f"[AVISO] Arquivo de exportacao '{caminho_arquivo}' nao encontrado.")
        
    return dicionario_nome, dicionario_ip

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
    
    # Usa o cache se estiver vazio e o caminho foi passado
    if caminho_export and not DICIONARIO_CAMERAS_NOME:
        nomes, ips = carregar_dicionario_cameras(caminho_export)
        DICIONARIO_CAMERAS_NOME.update(nomes)
        DICIONARIO_CAMERAS_IP.update(ips)
        
    status_cameras = {}
    for nome in DICIONARIO_CAMERAS_NOME.keys():
        if not nome.isdigit():
            status_cameras[nome] = "OK"
            
    arquivo_alvo = caminho_log if caminho_log else ARQUIVO_CSV
        
    if os.path.isfile(arquivo_alvo):
        with open(arquivo_alvo, mode='r', encoding='utf-8-sig', errors='replace') as file:
            reader = csv.DictReader(file, delimiter=';')
            for row in reader:
                camera = row.get('Camera')
                evento = row.get('Evento')
                if camera and evento:
                    # 'Restaurada' in evento previne problemas com 'Câmera Restaurada' em CP1252 vs UTF8
                    if 'Restaurada' in evento or 'Online' in evento:
                        status_cameras[camera] = "OK"
                    else:
                        status_cameras[camera] = "FALHA"
                        
    return status_cameras

def get_caminho_csv(caminho_log=""):
    """Retorna o caminho do arquivo de quedas"""
    return caminho_log if caminho_log else ARQUIVO_CSV


# =============== SNIFFER SNMP ===============
sniffer_socket = None

def rodar_sniffer_snmp():
    global sniffer_socket
    sniffer_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sniffer_socket.bind(('0.0.0.0', PORTA_SNMP))
        print(f"[OK] Sniffer SNMP rodando na porta {PORTA_SNMP}...")
    except Exception as e:
        print(f"[ERRO] ao iniciar Sniffer SNMP na porta {PORTA_SNMP}: {e}")
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
                        if not nome.isdigit() and nome.lower() in texto_lower:
                            camera_identificada = info
                            break
            except:
                pass
                
        if camera_identificada and status_encontrado != "Outro Evento":
            registrar_queda(camera_identificada['Nome'], status_encontrado)
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] SNMP TRAP: {camera_identificada['Nome']} | {status_encontrado}")

snmp_thread = None

def start_webhook(caminho_csv_export: str, caminho_log: str):
    """
    Mantido o nome original 'start_webhook' para não quebrar o service.py,
    mas agora inicia apenas o sniffer SNMP e não mais um servidor HTTP.
    """
    global ARQUIVO_EXPORT_CAMERAS, ARQUIVO_CSV, snmp_thread
    if snmp_thread is not None:
        return 
    
    ARQUIVO_EXPORT_CAMERAS = caminho_csv_export
    ARQUIVO_CSV = caminho_log
    
    DICIONARIO_CAMERAS_NOME.clear()
    DICIONARIO_CAMERAS_IP.clear()
    nomes, ips = carregar_dicionario_cameras(ARQUIVO_EXPORT_CAMERAS)
    DICIONARIO_CAMERAS_NOME.update(nomes)
    DICIONARIO_CAMERAS_IP.update(ips)
    
    # Inicia o Sniffer SNMP na 162
    snmp_thread = threading.Thread(target=rodar_sniffer_snmp, daemon=True)
    snmp_thread.start()
    
    print(f"[OK] Agente Digifort iniciado (Modo SNMP na {PORTA_SNMP}).")

def stop_webhook():
    global snmp_thread, sniffer_socket
    if sniffer_socket:
        sniffer_socket.close()
        sniffer_socket = None
    snmp_thread = None
    print("[PARADO] Agente Digifort SNMP parado.")

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
