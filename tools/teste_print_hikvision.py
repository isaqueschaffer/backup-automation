import cv2
import os
import time
import csv
import urllib.parse
from datetime import datetime

# Define diretórios
DIRETORIO_BASE = os.path.dirname(__file__)
PASTA_DESTINO = os.path.join(DIRETORIO_BASE, "prints_teste")
ARQUIVO_CSV = os.path.join(DIRETORIO_BASE, "cameras.csv")

os.makedirs(PASTA_DESTINO, exist_ok=True)

# Configurações Padrão
USUARIO = "admin"

print("Lendo o arquivo CSV...")

cameras = {}
if not os.path.exists(ARQUIVO_CSV):
    print(f"ERRO: O arquivo {ARQUIVO_CSV} não foi encontrado!")
    exit()

# Lê os bytes brutos para descobrir a codificação real do arquivo
with open(ARQUIVO_CSV, mode='rb') as f:
    raw_data = f.read()

# Testa utf-8, depois cp1252 (Excel), e cp850 (Sistemas/DOS onde 0x90 é 'É' de TÉRREO)
codificacao = 'utf-8-sig'
for enc in ['utf-8-sig', 'cp1252', 'cp850', 'latin1']:
    try:
        raw_data.decode(enc)
        codificacao = enc
        break
    except UnicodeDecodeError:
        pass

# Abre o arquivo CSV com a codificação detectada e ignora qualquer sujeira de texto
with open(ARQUIVO_CSV, mode='r', encoding=codificacao, errors='replace') as f:
    # O csv usa ";" como separador
    leitor = csv.DictReader(f, delimiter=';', quotechar='"')
    
    for linha in leitor:
        # Pega os valores ignorando espaços em branco sobrando
        nome = linha.get("Descrição", "").strip()
        ip = linha.get("Endereço", "").strip()
        modelo = linha.get("Modelo", "").strip()
        
        # LÊ A NOVA COLUNA "Senha"
        # Se a coluna não existir no CSV ou se a célula estiver vazia, ele usa a senha padrão.
        senha_pura = linha.get("Senha", "").strip()
        if not senha_pura:
            senha_pura = "navarro@123"
            
        # O script faz o URL-Encode automático (transforma @ em %40 automaticamente)
        senha_encodada = urllib.parse.quote(senha_pura, safe='')
        
        if nome and ip:
            # Monta a URL RTSP baseada no Modelo
            if "Grandstream" in modelo:
                # 0 = Main Stream, 4 = Sub Stream no Grandstream
                rtsp_url = f"rtsp://{USUARIO}:{senha_encodada}@{ip}:554/4"
            elif "ONVIF" in modelo:
                # Padrão correto da Motorola descoberto
                rtsp_url = f"rtsp://{USUARIO}:{senha_encodada}@{ip}:554/profile2" 
            else:
                # Padrão Hikvision
                rtsp_url = f"rtsp://{USUARIO}:{senha_encodada}@{ip}:554/Streaming/Channels/102"
                
            cameras[nome] = rtsp_url

print(f"{len(cameras)} câmeras carregadas do CSV com sucesso!\n")
print("Iniciando captura com OpenCV...\n")

# Força a conexão via TCP
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

for nome_cam, rtsp_url in cameras.items():
    # Oculta a senha dinâmica no print do terminal por segurança
    prefixo = f"rtsp://{USUARIO}:"
    inicio_senha = rtsp_url.find(prefixo) + len(prefixo)
    fim_senha = rtsp_url.find("@", inicio_senha)
    url_censurada = rtsp_url[:inicio_senha] + "***" + rtsp_url[fim_senha:]
    
    print(f"[{nome_cam}] Conectando: {url_censurada}") 
    
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    
    if not cap.isOpened():
        print(f"[{nome_cam}] 🔴 FALHA: Não conectou (Verifique IP/Senha).\n")
        continue

    # Limpa o buffer para evitar imagem da câmera anterior
    for _ in range(30):
        cap.grab()
        
    sucesso, frame = cap.retrieve()
    
    if sucesso:
        agora = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        # Remove caracteres que quebram caminhos de arquivos no Windows
        nome_seguro = nome_cam.replace("/", "-").replace("\\", "-").replace(":", "")
        nome_arquivo = f"{nome_seguro}_{agora}.jpg"
        caminho_arquivo = os.path.join(PASTA_DESTINO, nome_arquivo)
        
        cv2.imwrite(caminho_arquivo, frame)
        print(f"[{nome_cam}] 🟢 Sucesso! Print salvo em: {nome_arquivo}\n")
    else:
        print(f"[{nome_cam}] 🔴 FALHA: Conectou, mas não obteve a imagem.\n")
    
    cap.release()
    time.sleep(1)

print(f"Teste finalizado! Verifique a pasta: {PASTA_DESTINO}")
