import os
import csv
import datetime
import threading
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

# ==========================================
# CONFIGURAÇÃO
# ==========================================
PORTA_WEBHOOK = 8181
ARQUIVO_CSV_DEFENSE = r"C:\Relatorios_Defense\status_cameras.csv"

def registrar_evento_defense(nome_camera, status_evento):
    """
    Grava o evento recebido via Webhook no arquivo CSV.
    status_evento: "FALHA" ou "OK"
    """
    agora = datetime.datetime.now()
    data = agora.strftime("%Y-%m-%d")
    hora = agora.strftime("%H:%M:%S")
    
    pasta = os.path.dirname(ARQUIVO_CSV_DEFENSE)
    if pasta and not os.path.exists(pasta):
        os.makedirs(pasta)
        
    arquivo_existe = os.path.isfile(ARQUIVO_CSV_DEFENSE)
    
    with open(ARQUIVO_CSV_DEFENSE, mode='a', newline='', encoding='utf-8-sig') as file:
        writer = csv.writer(file, delimiter=';')
        if not arquivo_existe:
            writer.writerow(['Data', 'Hora', 'Camera', 'Evento'])
            
        # O agente l "FALHA" e "OK" para gerar o status das cameras
        writer.writerow([data, hora, nome_camera, status_evento])
        print(f"[DEFENSE WEBHOOK] {data} {hora} - {nome_camera}: {status_evento}")

class DefenseWebhookHandler(BaseHTTPRequestHandler):
    """
    Servidor HTTP leve para receber chamadas de URL do Defense IA.
    """
    def do_GET(self):
        # Exemplo de URL que o Defense deve chamar:
        # http://127.0.0.1:8181/evento?camera=Cam_Recepcao&status=falha
        
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path == '/evento':
            query = urllib.parse.parse_qs(parsed_path.query)
            
            nome_camera = query.get('camera', ['Desconhecida'])[0]
            status_bruto = query.get('status', ['falha'])[0].lower()
            
            status_evento = "OK" if "restaura" in status_bruto or "online" in status_bruto or "ok" in status_bruto else "FALHA"
            
            registrar_evento_defense(nome_camera, status_evento)
            
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Evento registrado com sucesso.")
        else:
            self.send_response(404)
            self.end_headers()

    # O Defense IA pode mandar POST tambm, ento preparamos para aceitar
    def do_POST(self):
        self.do_GET()

    def log_message(self, format, *args):
        # Desativa os logs de acesso padro no console para no poluir
        pass

servidor_http = None
webhook_thread = None

def rodar_servidor_http():
    global servidor_http
    try:
        servidor_http = HTTPServer(('0.0.0.0', PORTA_WEBHOOK), DefenseWebhookHandler)
        print(f"[OK] Webhook Defense IA rodando na porta {PORTA_WEBHOOK}...")
        servidor_http.serve_forever()
    except Exception as e:
        print(f"[ERRO] ao iniciar Webhook Defense IA na porta {PORTA_WEBHOOK}: {e}")

def start_webhook_defense(caminho_log: str = ""):
    global ARQUIVO_CSV_DEFENSE, webhook_thread
    if webhook_thread is not None:
        return 
    
    if caminho_log:
        ARQUIVO_CSV_DEFENSE = caminho_log
        
    webhook_thread = threading.Thread(target=rodar_servidor_http, daemon=True)
    webhook_thread.start()

def stop_webhook_defense():
    global webhook_thread, servidor_http
    if servidor_http:
        servidor_http.shutdown()
        servidor_http.server_close()
        servidor_http = None
    webhook_thread = None
    print("[PARADO] Webhook Defense IA parado.")

if __name__ == '__main__':
    print("="*60)
    print("  AGENTE WEBHOOK DEFENSE IA - TRILAN NVR BACKUP")
    print("="*60)
    start_webhook_defense()
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_webhook_defense()

def get_status_cameras_defense(caminho_log=""):
    """
    Lê o CSV do Defense e retorna o status atual (mais recente) de cada câmera.
    """
    arquivo_alvo = caminho_log if caminho_log else ARQUIVO_CSV_DEFENSE
    status_cameras = {}
    
    if os.path.isfile(arquivo_alvo):
        with open(arquivo_alvo, mode='r', encoding='utf-8-sig', errors='replace') as file:
            reader = csv.DictReader(file, delimiter=';')
            for row in reader:
                camera = row.get('Camera')
                evento = row.get('Evento')
                if camera and evento:
                    # Como lemos de cima para baixo, o ltimo registro da camera vai sobrescrever e ser o status atual
                    status_cameras[camera] = evento
    return status_cameras
