import socket
import re
import datetime

# Porta padrão para SNMP Traps
PORTA = 162

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
        
        # O SNMP é um pacote binário criptografado/codificado (ASN.1).
        # Vamos usar uma expressão regular para tentar extrair e ler 
        # qualquer texto humano legível que esteja escondido dentro dos dados binários.
        textos_encontrados = re.findall(b'[ -~]{4,}', dados)
        
        for texto in textos_encontrados:
            try:
                # Converte os bytes para texto (ignorando erros de acentos para não travar)
                texto_limpo = texto.decode('utf-8', errors='ignore')
                print(f"  -> {texto_limpo}")
            except:
                pass
                
        print("-" * 50)

if __name__ == "__main__":
    iniciar_sniffer()
