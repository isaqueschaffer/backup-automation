import urllib.request
import time

URL_BASE = "http://127.0.0.1:8080"

def disparar_evento(camera_id, evento_tipo):
    if evento_tipo == "falha":
        url = f"{URL_BASE}/?c={camera_id}"
        print(f"🔴 Simulando Queda da Câmera {camera_id}...")
    else:
        url = f"{URL_BASE}/?c={camera_id}&r=1"
        print(f"🟢 Simulando Retorno da Câmera {camera_id}...")
        
    try:
        # Envia a requisição HTTP GET para o nosso Webhook
        resposta = urllib.request.urlopen(url)
        print(f"   Sucesso! O Webhook respondeu: {resposta.read().decode('utf-8')}\n")
    except Exception as e:
        print(f"   ❌ Erro ao conectar no Webhook. Ele está rodando na porta 8080? Erro: {e}\n")

if __name__ == "__main__":
    print("==================================================")
    print("🤖 SIMULADOR DE EVENTOS DO DIGIFORT")
    print("==================================================\n")
    
    # Simula a câmera 01 caindo
    disparar_evento("01", "falha")
    time.sleep(2) # Espera 2 segundos
    
    # Simula a câmera 01 voltando
    disparar_evento("01", "retorno")
    time.sleep(2)
    
    # Simula a câmera 15 caindo
    disparar_evento("15", "falha")
    time.sleep(2)
    
    # Simula uma câmera que não existe caindo (para ver o comportamento)
    disparar_evento("99", "falha")
    
    print("Teste finalizado! Abra o seu arquivo Excel para ver o resultado.")
    input("Pressione ENTER para sair...")
