import cv2
import os
import time
from datetime import datetime

# Define a pasta de destino dentro do mesmo diretório deste script
PASTA_DESTINO = os.path.join(os.path.dirname(__file__), "prints_teste")
os.makedirs(PASTA_DESTINO, exist_ok=True)

# ---------------------------------------------------------
# CORREÇÃO 1: A senha original "navarro@123" contém o caractere "@".
# Em URLs (como rtsp://), o "@" confunde o leitor, pois ele acha que o IP 
# começa depois do primeiro "@". Para evitar erros, o "@" da senha DEVE ser 
# convertido para "%40" (que é o código universal para ele em URLs).
# A senha correta para a URL fica: navarro%40123
# ---------------------------------------------------------
SENHA_ENCODADA = "navarro%40123"

# Dicionário com todos os nomes e IPs da imagem fornecida
cameras = {
    "1 ANDAR- ACESSO ELEVADORES SHAFT": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.27:554/Streaming/Channels/102",
    "2 ANDAR - ACESSO ELEVADORES SHAFT": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.24:554/Streaming/Channels/102",
    "3 ANDAR - ACESSO ELEVADORES SHAFT": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.26:554/Streaming/Channels/102",
    "4 ANDAR - ACESSO ELEVADORES SHAFT": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.43:554/Streaming/Channels/102",
    "5 ANDAR - ACESSO ELEVADORES SHAFT": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.29:554/Streaming/Channels/102",
    "6 ANDAR - ACESSO ELEVADORES SHAFT": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.25:554/Streaming/Channels/102",
    "7 ANDAR - ACESSO ELEVADORES SHAFT": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.31:554/Streaming/Channels/102",
    "8 ANDAR - ACESSO ELEVADORES SHAFT": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.28:554/Streaming/Channels/102",
    "9 ANDAR - ACESSO ELEVADORES SHAFT": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.21:554/Streaming/Channels/102",
    "10 ANDAR - ACESSO ELEVADORES SHAFT": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.23:554/Streaming/Channels/102",
    "11 ANDAR - ACESSO ELEVADORES SHAFT": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.20:554/Streaming/Channels/102",
    "12 ANDAR - ACESSO ELEVADORES SHAFT": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.30:554/Streaming/Channels/102",
    "13 ANDAR - ACESSO ELEVADORES SHAFT": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.22:554/Streaming/Channels/102",
    "SALA ADMINISTRATIVA - SUBSOLO 2": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.49:554/Streaming/Channels/102",
    "CATRACA (B) - SUBSOLO 1": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.32:554/Streaming/Channels/102",
    "CATRACA (A) - SUBSOLO 2": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.47:554/Streaming/Channels/102",
    "CATRACA (A) - SUBSOLO 3": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.48:554/Streaming/Channels/102",
    "CATRACA (B) - SUBSOLO 2": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.45:554/Streaming/Channels/102",
    "CATRACA (A) - SUBSOLO 1": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.34:554/Streaming/Channels/102",
    "CATRACA (B) - SUBSOLO 3": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.44:554/Streaming/Channels/102",
    "CANCELA DE ACESSO - ESTAC. TERREO": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.59:554/Streaming/Channels/102",
    "RAMPA DE ACESSO (A) - SUBSOLO 01": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.15:554/Streaming/Channels/102",
    "TÉRREO - ESPERA LADO A": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.251:554/Streaming/Channels/102",
    "ACESSO ESTACIONAMENTO - SUBSOLO 2": f"rtsp://admin:{SENHA_ENCODADA}@192.168.5.46:554/Streaming/Channels/102"
}

print("Iniciando teste de captura com OpenCV para câmeras Hikvision...\n")

# Força a conexão via TCP
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

for nome_cam, rtsp_url in cameras.items():
    url_censurada = rtsp_url.replace(SENHA_ENCODADA, '***')
    print(f"[{nome_cam}] Conectando...") 
    
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    
    if not cap.isOpened():
        print(f"[{nome_cam}] 🔴 FALHA: Não foi possível conectar ao RTSP.\n")
        continue

    # CORREÇÃO 2: Problema da "mesma imagem". 
    # O buffer de stream costuma prender o frame antigo. Em vez de read(), 
    # usamos grab() 30 vezes que é super rápido e limpa totalmente o buffer.
    for _ in range(30):
        cap.grab()
        
    # Depois de limpar o buffer, resgatamos o frame atual de fato
    sucesso, frame = cap.retrieve()
    
    if sucesso:
        agora = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        # CORREÇÃO 3: Os nomes continham barra "/", isso quebra a criação de arquivos no Windows!
        # Trocamos qualquer "/" por "-"
        nome_seguro = nome_cam.replace("/", "-").replace("\\", "-")
        nome_arquivo = f"{nome_seguro}_{agora}.jpg"
        caminho_arquivo = os.path.join(PASTA_DESTINO, nome_arquivo)
        
        cv2.imwrite(caminho_arquivo, frame)
        print(f"[{nome_cam}] 🟢 Sucesso! Print salvo: {nome_arquivo}\n")
    else:
        print(f"[{nome_cam}] 🔴 FALHA: Conectou, mas não obteve a imagem.\n")
    
    cap.release()
    
    # Pausa de 1 segundo para garantir que a conexão de rede encerre completamente 
    # antes de abrir a da próxima câmera (ajuda no problema de sobreposição de imagem).
    time.sleep(1)

print(f"Teste finalizado! Verifique a pasta: {PASTA_DESTINO}")
