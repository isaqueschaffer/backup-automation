import time
import socket
import logging
import threading
from pathlib import Path
import paramiko
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

# A porta que o agente vai usar temporariamente para subir o FTP
FTP_PORT = 2121
FTP_USER = "trilan"
FTP_PASS = "backup123"

# ─────────────────────────────────────────────────────────────────────────────
# CORREÇÃO CRÍTICA: Paramiko 5.x removeu 'ssh-rsa' completamente:
#   1) Da lista de algoritmos preferidos (_preferred_keys / _preferred_pubkeys)
#   2) Do registro interno de handlers (_key_info)
# OLTs Huawei (MA5800, etc.) antigas APENAS suportam 'ssh-rsa'.
# Restauramos tudo de volta para que a conexão funcione.
# ─────────────────────────────────────────────────────────────────────────────
if "ssh-rsa" not in paramiko.Transport._preferred_keys:
    paramiko.Transport._preferred_keys = ("ssh-rsa",) + paramiko.Transport._preferred_keys

if "ssh-rsa" not in paramiko.Transport._preferred_pubkeys:
    paramiko.Transport._preferred_pubkeys = ("ssh-rsa",) + paramiko.Transport._preferred_pubkeys

# Registrar o handler RSAKey para 'ssh-rsa' no mapa interno de verificação
if "ssh-rsa" not in paramiko.Transport._key_info:
    paramiko.Transport._key_info["ssh-rsa"] = paramiko.RSAKey


def get_local_ip(target_ip: str) -> str:
    """Descobre qual IP local desta maquina tem rota para o IP da OLT."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((target_ip, 22))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def run_ftp_server(server: FTPServer):
    """Roda o servidor FTP em uma thread separada."""
    logging.info(f"[HUAWEI] Servidor FTP efemero rodando em {server.address}")
    server.serve_forever()

def realizar_backup_huawei_ativo(equipamento: dict, pasta_destino: Path) -> dict:
    ip = equipamento.get("ip")
    username = equipamento.get("username")
    password = equipamento.get("password")
    nome = equipamento.get("name", "Huawei").replace(" ", "_")
    
    res = {"nome": nome, "status": "ERRO", "cameras": None}
    
    if not ip or not username or not password:
        logging.error(f"[HUAWEI] {nome} - Faltam credenciais ou IP.")
        return res

    local_ip = get_local_ip(ip)
    
    # 1. Configurar Servidor FTP Efemero
    authorizer = DummyAuthorizer()
    authorizer.add_user(FTP_USER, FTP_PASS, str(pasta_destino), perm="elradfmwMT")
    handler = FTPHandler
    handler.authorizer = authorizer
    handler.banner = "Trilan Agent Temp FTP Ready."
    
    try:
        server = FTPServer(("0.0.0.0", FTP_PORT), handler)
        server.max_cons = 5
        server.max_cons_per_ip = 5
    except Exception as e:
        logging.error(f"[HUAWEI] Nao foi possivel subir o FTP temporario na porta {FTP_PORT}: {e}")
        return res
        
    ftp_thread = threading.Thread(target=run_ftp_server, args=(server,), daemon=True)
    ftp_thread.start()
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        porta = equipamento.get("porta") or equipamento.get("port") or 22
        porta = int(porta)
        logging.info(f"[HUAWEI] Conectando via SSH em {ip}:{porta}...")
        ssh.connect(
            ip,
            port=porta,
            username=username,
            password=password,
            timeout=20,
            look_for_keys=False,
            allow_agent=False,
        )
        
        # Iniciar shell interativo porque a Huawei precisa do enable e scroll manual
        shell = ssh.invoke_shell()
        shell.settimeout(15)
        
        def wait_prompt(expected: str, timeout: int = 15):
            end_time = time.time() + timeout
            output = ""
            while time.time() < end_time:
                if shell.recv_ready():
                    chunk = shell.recv(4096).decode("utf-8", errors="ignore")
                    output += chunk
                    if expected in output:
                        return output
                time.sleep(0.5)
            raise TimeoutError(f"Prompt '{expected}' nao encontrado. Output final: {output}")

        # Aguardar prompt inicial (normalmente termina em '>')
        wait_prompt(">")
        
        # Entrar no modo enable
        shell.send("enable\n")
        wait_prompt("#")
        
        # Desabilitar paginacao para o output nao travar com "--More--"
        shell.send("undo smart\n")
        time.sleep(1)
        if shell.recv_ready():
            shell.recv(4096)
            
        # Comando para enviar arquivo de configuracao para o nosso FTP
        cfg_filename = f"hw_config_{nome.lower()}.txt"
        logging.info(f"[HUAWEI] Solicitando backup configuration para {local_ip} (FTP)...")
        shell.send(f"backup configuration ftp {local_ip} {cfg_filename} {FTP_USER} {FTP_PASS}\n")
        
        # Aguardar a finalizacao
        out = wait_prompt("#", timeout=60)
        if "successfully" not in out.lower() and "success" not in out.lower():
            logging.warning(f"[HUAWEI] OLT pode nao ter reportado sucesso claro do config. Verifique os logs.")
            
        # Comando para enviar arquivo de dados para o nosso FTP
        data_filename = f"hw_data_{nome.lower()}.dat"
        logging.info(f"[HUAWEI] Solicitando backup data para {local_ip} (FTP)...")
        shell.send(f"backup data ftp {local_ip} {data_filename} {FTP_USER} {FTP_PASS}\n")
        
        # Aguardar a finalizacao
        out = wait_prompt("#", timeout=120)
        
        # Validar se os arquivos chegaram na pasta destino
        cfg_path = pasta_destino / cfg_filename
        data_path = pasta_destino / data_filename
        
        if cfg_path.exists() or data_path.exists():
            logging.info(f"[HUAWEI] Arquivos recebidos com sucesso no FTP!")
            res["status"] = "OK"
        else:
            logging.error(f"[HUAWEI] Arquivos nao foram recebidos no FTP.")
            
    except Exception as e:
        logging.error(f"[HUAWEI] Falha no fluxo ativo: {e}")
    finally:
        try:
            ssh.close()
        except:
            pass
        logging.info("[HUAWEI] Desligando servidor FTP temporario...")
        server.close_all()
        
    return res
