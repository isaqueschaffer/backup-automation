import socket
import time

IP_DESTINO = "127.0.0.1"
PORTA_SNMP = 162

# Códigos exatos de evento do Digifort que o nosso sniffer identifica
OID_OFFLINE = b'\x06\x0d\x2b\x06\x01\x04\x01\x82\xf7\x04\x01\x01\x64\x02\x04'
OID_ONLINE  = b'\x06\x0d\x2b\x06\x01\x04\x01\x82\xf7\x04\x01\x01\x64\x02\x05'

def disparar_trap_snmp(identificador_camera, evento_tipo):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    if evento_tipo == "falha":
        print(f"🔴 Simulando SNMP Queda (Offline) da Câmera: {identificador_camera}")
        oid = OID_OFFLINE
    else:
        print(f"🟢 Simulando SNMP Retorno (Online) da Câmera: {identificador_camera}")
        oid = OID_ONLINE
        
    # Montamos um pacote falso que contém o OID correto e o nome da câmera em formato texto visível
    # O sniffer varre o binário com Regex buscando letras/números (comprimento >= 4)
    pacote_falso = oid + b' PAD_TEXTO_ASN1 ' + identificador_camera.encode('utf-8') + b' PAD'
    
    try:
        sock.sendto(pacote_falso, (IP_DESTINO, PORTA_SNMP))
        print("   ✅ Pacote UDP SNMP disparado com sucesso!\n")
    except PermissionError:
        print("   ❌ Erro de permissão ao enviar pacote (Isso é raro no lado do cliente UDP)\n")
    except Exception as e:
        print(f"   ❌ Erro de rede ao disparar pacote: {e}\n")
    finally:
        sock.close()

if __name__ == "__main__":
    print("==================================================")
    print("🤖 SIMULADOR SNMP DIGIFORT - TRILAN")
    print("==================================================\n")
    print("Certifique-se de que o 'agente_webhook_digifort.py' esteja rodando")
    print("COMO ADMINISTRADOR em outro terminal!\n")
    
    # Testando com IPs ou Nomes que estão na sua planilha cameras.csv
    
    # Simula a câmera "1 ANDAR" caindo
    disparar_trap_snmp("1 ANDAR", "falha")
    time.sleep(2)
    
    # Simula a câmera "1 ANDAR" voltando
    disparar_trap_snmp("1 ANDAR", "retorno")
    time.sleep(2)
    
    # Simula usando o IP de outra câmera, ex: "192.168.5.32" (CATRACA 1 SUB1)
    disparar_trap_snmp("192.168.5.32", "falha")
    time.sleep(2)
    
    # Simula uma câmera que não está na planilha
    disparar_trap_snmp("CAMERA INVENTADA TESTE", "falha")
    
    print("Teste finalizado! Verifique o terminal do Agente para ver se ele identificou os pacotes.")
    input("Pressione ENTER para sair...")
