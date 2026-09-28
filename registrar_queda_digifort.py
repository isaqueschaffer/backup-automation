import sys
import datetime
import csv
import os

# ==========================================
# CONFIGURAÇÃO: Onde o CSV será salvo
# ==========================================
# Pode ser a pasta do OneDrive da Trilan
ARQUIVO_CSV = r"C:\Users\Helena\OneDrive - Trilan\Relatorios_Digifort\quedas_cameras.csv"

def registrar_queda(nome_camera, tipo_falha):
    # Pega a data e hora exata do momento
    agora = datetime.datetime.now()
    data = agora.strftime("%Y-%m-%d")
    hora = agora.strftime("%H:%M:%S")
    
    # Cria a pasta caso não exista
    pasta = os.path.dirname(ARQUIVO_CSV)
    if not os.path.exists(pasta):
        os.makedirs(pasta)
        
    # Verifica se o arquivo já existe para colocar o cabeçalho
    arquivo_existe = os.path.isfile(ARQUIVO_CSV)
    
    # Salva a informação no arquivo CSV
    with open(ARQUIVO_CSV, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file, delimiter=';')
        
        # Se o arquivo for novo, cria o cabeçalho das colunas
        if not arquivo_existe:
            writer.writerow(['Data', 'Hora', 'Camera', 'Tipo de Falha'])
            
        # Grava a linha da queda
        writer.writerow([data, hora, nome_camera, tipo_falha])

if __name__ == "__main__":
    # O Digifort vai mandar os nomes como argumentos na hora de rodar o programa.
    # Ex: python.exe registrar_queda.py "Camera Portaria" "Falha Comunicacao"
    
    if len(sys.argv) >= 3:
        nome_cam = sys.argv[1]
        tipo = sys.argv[2]
        registrar_queda(nome_cam, tipo)
    else:
        # Fallback caso alguém rode sem argumentos para testar
        registrar_queda("Camera_Teste", "Teste_Manual")
