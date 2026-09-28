import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
import datetime
import csv
import os

# ==========================================
# CONFIGURAÇÃO
# ==========================================
PORTA = 8080
ARQUIVO_CSV = r"C:\Users\Helena\OneDrive - Trilan\Relatorios_Digifort\quedas_cameras.csv"

def registrar_queda(nome_camera, nome_evento):
    agora = datetime.datetime.now()
    data = agora.strftime("%Y-%m-%d")
    hora = agora.strftime("%H:%M:%S")
    
    pasta = os.path.dirname(ARQUIVO_CSV)
    if not os.path.exists(pasta):
        os.makedirs(pasta)
        
    arquivo_existe = os.path.isfile(ARQUIVO_CSV)
    
    with open(ARQUIVO_CSV, mode='a', newline='', encoding='utf-8-sig') as file:
        writer = csv.writer(file, delimiter=';')
        if not arquivo_existe:
            writer.writerow(['Data', 'Hora', 'Camera', 'Evento'])
            
        writer.writerow([data, hora, nome_camera, nome_evento])

class TrilanWebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Lê a URL chamada pelo Digifort
        parsed_path = urllib.parse.urlparse(self.path)
        parametros = urllib.parse.parse_qs(parsed_path.query)
        
        # Pega o nome da câmera e o evento na URL (ou usa padrão)
        nome_camera = parametros.get('camera', ['Camera_Desconhecida'])[0]
        nome_evento = parametros.get('evento', ['Falha de Comunicação'])[0]
        
        # Chama a função para escrever no CSV
        registrar_queda(nome_camera, nome_evento)
        
        # Responde pro Digifort que deu tudo certo
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(f"Registrado {nome_evento} na camera: {nome_camera}".encode("utf-8"))
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Registrado: {nome_camera} | {nome_evento}")

def rodar_servidor():
    server_address = ('', PORTA)
    httpd = HTTPServer(server_address, TrilanWebhookHandler)
    print(f"✅ Agente Trilan rodando na porta {PORTA}...")
    print("Aguardando avisos do Digifort...")
    httpd.serve_forever()

if __name__ == '__main__':
    rodar_servidor()
