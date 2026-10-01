import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
import datetime
import csv
import os

# ==========================================
# CONFIGURAÇÃO
# ==========================================
PORTA = 8080
ARQUIVO_CSV = r"C:\Relatorios_Digifort\quedas_cameras.csv"

ARQUIVO_EXPORT_CAMERAS = ""
DICIONARIO_CAMERAS = {}

def carregar_dicionario_cameras(caminho_arquivo):
    dicionario = {}
    if os.path.isfile(caminho_arquivo):
        try:
            # Tenta ler com utf-8-sig (para lidar com arquivos com e sem BOM do Windows)
            with open(caminho_arquivo, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f, delimiter=';')
                for index, row in enumerate(reader, start=1):
                    numero = f"{index:02d}"
                    descricao = row.get("Descrição", "")
                    if descricao:
                        dicionario[numero] = descricao.strip()
            print(f"✅ {len(dicionario)} cameras carregadas do arquivo {caminho_arquivo}")
        except Exception as e:
            print(f"❌ Erro ao ler {caminho_arquivo}: {e}")
    else:
        print(f"⚠️ AVISO: Arquivo de exportacao '{caminho_arquivo}' nao encontrado.")
        print("⚠️ Gere o relatorio CSV de cameras no Digifort e salve neste caminho para mapear as descricoes.")
        
    return dicionario

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
        parsed_path = urllib.parse.urlparse(self.path)
        
        if parsed_path.path == '/status':
            self._handle_status()
            return
            
        if parsed_path.path == '/csv':
            self._handle_csv()
            return
            
        # Lê a URL chamada pelo Digifort
        parsed_path = urllib.parse.urlparse(self.path)
        parametros = urllib.parse.parse_qs(parsed_path.query)
        
        # Pega o número da câmera (aceita '?c=01' para ser o mais curto possível)
        numero_camera = parametros.get('c', parametros.get('camera', ['Desconhecida']))[0]
        
        # Se tiver o parâmetro '&r=1' na URL, significa que Restaurou. Senão, é Falha.
        if 'r' in parametros:
            nome_evento = 'Câmera Restaurada'
        else:
            nome_evento = 'Falha de Comunicação'
        
        # Faz a tradução mágica do número para o nome completo!
        nome_completo = DICIONARIO_CAMERAS.get(numero_camera, numero_camera)
        
        # Chama a função para escrever no CSV
        registrar_queda(nome_completo, nome_evento)
        
        # Responde pro Digifort que deu tudo certo
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(f"Registrado {nome_evento} na camera: {nome_completo}".encode("utf-8"))
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Registrado: {nome_completo} | {nome_evento}")

    def _handle_status(self):
        status_cameras = {}
        # Inicializa todas as câmeras como OK
        for num, nome in DICIONARIO_CAMERAS.items():
            status_cameras[nome] = "OK"
            
        if os.path.isfile(ARQUIVO_CSV):
            with open(ARQUIVO_CSV, mode='r', encoding='utf-8-sig') as file:
                reader = csv.DictReader(file, delimiter=';')
                for row in reader:
                    camera = row.get('Camera')
                    evento = row.get('Evento')
                    if camera in status_cameras:
                        if evento == 'Câmera Restaurada':
                            status_cameras[camera] = "OK"
                        else:
                            status_cameras[camera] = "FALHA"
                            
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        import json
        self.wfile.write(json.dumps(status_cameras).encode("utf-8"))

    def _handle_csv(self):
        if not os.path.isfile(ARQUIVO_CSV):
            self.send_response(404)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"CSV nao encontrado")
            return
            
        self.send_response(200)
        self.send_header("Content-type", "text/csv")
        self.send_header("Content-Disposition", "attachment; filename=quedas_cameras.csv")
        self.end_headers()
        with open(ARQUIVO_CSV, 'rb') as file:
            self.wfile.write(file.read())

def rodar_servidor():
    server_address = ('', PORTA)
    httpd = HTTPServer(server_address, TrilanWebhookHandler)
    print(f"✅ Agente Trilan rodando na porta {PORTA}...")
    print("Aguardando avisos do Digifort...")
    httpd.serve_forever()

if __name__ == '__main__':
    import sys
    print("="*60)
    print("  AGENTE WEBHOOK DIGIFORT - TRILAN NVR BACKUP")
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
        caminho_log = input(f"Digite o caminho para salvar o CSV de histórico de quedas (ou Enter para o padrao '{ARQUIVO_CSV}'): ").strip()
        if caminho_log:
            ARQUIVO_CSV = caminho_log
            
    DICIONARIO_CAMERAS.update(carregar_dicionario_cameras(ARQUIVO_EXPORT_CAMERAS))
    rodar_servidor()
