import socket
import re
import datetime
import csv
import os

# Porta padrão para SNMP Traps
PORTA = 162
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAMERAS_CSV = os.path.join(BASE_DIR, 'cameras.csv')
STATUS_CSV = os.path.join(BASE_DIR, 'status_cameras.csv')

# Carregar câmeras do CSV
cameras_info_by_ip = {}
cameras_info_by_name = {}
try:
    with open(CAMERAS_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            ip = row.get('Endereço')
            nome = row.get('Nome')
            info = {
                'IP': ip,
                'Nome': nome,
                'Descrição': row.get('Descrição', ''),
                'Modelo': row.get('Modelo', '')
            }
            if ip:
                cameras_info_by_ip[ip] = info
            if nome:
                cameras_info_by_name[nome] = info
    print(f"✅ {len(cameras_info_by_ip)} câmeras carregadas do {CAMERAS_CSV}")
except FileNotFoundError:
    print(f"⚠️ Arquivo {CAMERAS_CSV} não encontrado. Não será possível associar nomes.")
except Exception as e:
    print(f"⚠️ Erro ao ler {CAMERAS_CSV}: {e}")

def registrar_status(camera_info, status, texto_bruto):
    agora = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    arquivo_existe = os.path.isfile(STATUS_CSV)
    
    try:
        with open(STATUS_CSV, 'a', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            if not arquivo_existe:
                writer.writerow(['DataHora', 'IP', 'Nome', 'Descrição', 'Modelo', 'Status', 'Texto_Bruto'])
            
            writer.writerow([
                agora, 
                camera_info.get('IP', 'N/A'), 
                camera_info.get('Nome', 'Desconhecido'), 
                camera_info.get('Descrição', 'Desconhecido'), 
                camera_info.get('Modelo', 'Desconhecido'), 
                status, 
                texto_bruto
            ])
        print(f"📝 Registrado no CSV: IP={camera_info.get('IP')} | Câmera={camera_info.get('Nome')} | Status={status}")
    except Exception as e:
        print(f"❌ Erro ao escrever no arquivo CSV: {e}")

def iniciar_sniffer():
    # Cria um servidor UDP simples para escutar na porta 162
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        # Tenta escutar em todos os IPs locais na porta 162
        sock.bind(('0.0.0.0', PORTA))
        print(f"✅ Sniffer SNMP rodando na porta {PORTA}...")
        print("Aguardando o Digifort enviar uma TRAP (force a queda de uma câmera)...\n")
    except PermissionError:
        print(f"❌ Erro de Permissão: O Windows não deixou abrir a porta {PORTA}.")
        print("Você precisa abrir o terminal (CMD) como Administrador para rodar este script!")
        return
    except OSError as e:
        print(f"❌ Erro na porta {PORTA}: Já existe outro programa usando ela? ({e})")
        return

    while True:
        # Fica esperando receber dados do Digifort
        dados, endereco = sock.recvfrom(4096)
        agora = datetime.datetime.now().strftime('%H:%M:%S')
        
        print(f"\n[{agora}] 📥 TRAP RECEBIDA DE {endereco[0]}:")
        
        status_encontrado = None
        
        # O SNMP é um pacote binário criptografado/codificado (ASN.1).
        # O Digifort não envia o texto "offline" ou "online", ele usa OIDs (códigos numéricos).
        # OID para evento "Falha de Conexão com Câmera" termina em .100.2.4 (Hex: 64 02 04)
        # OID para evento "Conexão com Câmera Restaurada" termina em .100.2.5 (Hex: 64 02 05)
        if b'\x06\x0d\x2b\x06\x01\x04\x01\x82\xf7\x04\x01\x01\x64\x02\x04' in dados:
            status_encontrado = "Offline"
        elif b'\x06\x0d\x2b\x06\x01\x04\x01\x82\xf7\x04\x01\x01\x64\x02\x05' in dados:
            status_encontrado = "Online"
        else:
            # Caso receba outro tipo de evento SNMP do Digifort
            status_encontrado = "Outro Evento"

        # Vamos usar uma expressão regular para tentar extrair o nome da câmera ou IP
        textos_encontrados = re.findall(b'[ -~]{4,}', dados)
        
        texto_completo = ""
        camera_identificada = None
        
        for texto in textos_encontrados:
            try:
                # Converte os bytes para texto (ignorando erros de acentos para não travar)
                texto_limpo = texto.decode('utf-8', errors='ignore').strip()
                
                # Se for apenas um '0' solto por causa de decodificação binária, a gente limpa
                if texto_limpo.endswith('0') and len(texto_limpo) > 1 and texto_limpo[:-1] in cameras_info_by_name:
                    texto_limpo = texto_limpo[:-1]
                    
                print(f"  -> Extraído: {texto_limpo}")
                texto_completo += texto_limpo + " | "
                
                texto_lower = texto_limpo.lower()
                
                # Procurar IP na string
                ip_match = re.search(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', texto_limpo)
                if ip_match:
                    ip_achado = ip_match.group(0)
                    if ip_achado in cameras_info_by_ip:
                        camera_identificada = cameras_info_by_ip[ip_achado]
                    elif not camera_identificada:
                        camera_identificada = {'IP': ip_achado, 'Nome': 'Desconhecido', 'Descrição': 'Desconhecido', 'Modelo': 'Desconhecido'}

                # Procurar por Nome (apenas se ainda não achou por IP)
                if not camera_identificada:
                    for nome, info in cameras_info_by_name.items():
                        if nome.lower() in texto_lower:
                            camera_identificada = info
                            break
                            
            except:
                pass
                
        if camera_identificada and status_encontrado != "Outro Evento":
            registrar_status(camera_identificada, status_encontrado, texto_completo)
        elif camera_identificada:
            # Se for outro evento de uma câmera, a gente registra também
            registrar_status(camera_identificada, status_encontrado, texto_completo)
            
        print("-" * 50)

if __name__ == "__main__":
    iniciar_sniffer()
