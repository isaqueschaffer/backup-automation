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
    logging.info(f"[HUAWEI] Servidor FTP efemero iniciado em {server.address}")
    server.serve_forever()


def realizar_backup_huawei_ativo(equipamento: dict, pasta_destino: Path) -> dict:
    """
    Realiza backup ativo de uma OLT Huawei (MA5800 e similares).
    
    Fluxo:
    1. Sobe um servidor FTP temporario na maquina do agente
    2. Conecta via SSH na OLT
    3. Envia comandos de backup que fazem a OLT enviar os arquivos via FTP
    4. Verifica se os arquivos chegaram
    5. Desliga o FTP temporario
    """
    ip = equipamento.get("ip")
    username = equipamento.get("username")
    password = equipamento.get("password")
    nome = equipamento.get("name", "Huawei").replace(" ", "_")
    
    res = {"nome": nome, "status": "ERRO", "cameras": None}
    
    if not ip or not username or not password:
        logging.error(f"[HUAWEI] {nome} — Faltam credenciais (ip/usuario/senha). Abortando.")
        return res

    local_ip = get_local_ip(ip)
    logging.info(f"[HUAWEI] IP local detectado para rota ate {ip}: {local_ip}")
    
    # ── 1. SUBIR SERVIDOR FTP TEMPORÁRIO ─────────────────────────────────
    logging.info(f"[HUAWEI] Iniciando servidor FTP temporario na porta {FTP_PORT}...")
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
        logging.error(f"[HUAWEI] FALHA ao subir FTP na porta {FTP_PORT}: {e}")
        logging.error(f"[HUAWEI] Verifique se a porta {FTP_PORT} nao esta em uso por outro processo.")
        return res
        
    ftp_thread = threading.Thread(target=run_ftp_server, args=(server,), daemon=True)
    ftp_thread.start()
    
    # ── 2. CONECTAR VIA SSH NA OLT ───────────────────────────────────────
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        porta = equipamento.get("porta") or equipamento.get("port") or 22
        porta = int(porta)
        logging.info(f"[HUAWEI] Conectando via SSH em {ip}:{porta} (usuario: {username})...")
        
        # OLTs Huawei antigas (MA5800 etc.) usam apenas o algoritmo ssh-rsa (SHA-1).
        # No Paramiko 3.x, ssh-rsa esta desabilitado por padrão.
        # Passamos disabled_algorithms vazio para reabilitar ssh-rsa na negociacao.
        ssh.connect(
            ip,
            port=porta,
            username=username,
            password=password,
            timeout=20,
            look_for_keys=False,
            allow_agent=False,
            disabled_algorithms={"keys": [], "pubkeys": []},
        )
        logging.info(f"[HUAWEI] Conexao SSH estabelecida com sucesso em {ip}:{porta}")
        
        # ── 3. SHELL INTERATIVO ──────────────────────────────────────────
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
            raise TimeoutError(f"Prompt '{expected}' nao encontrado apos {timeout}s. Output: {output[:500]}")

        # Aguardar prompt inicial (normalmente termina em '>')
        logging.info(f"[HUAWEI] Aguardando prompt inicial da OLT...")
        wait_prompt(">")
        
        # Entrar no modo enable
        logging.info(f"[HUAWEI] Entrando em modo privilegiado (enable)...")
        shell.send("enable\n")
        wait_prompt("#")
        
        # Desabilitar paginacao para o output nao travar com "--More--"
        shell.send("undo smart\n")
        time.sleep(1)
        if shell.recv_ready():
            shell.recv(4096)
            
        # ── 4. BACKUP CONFIGURATION ─────────────────────────────────────
        cfg_filename = f"hw_config_{nome.lower()}.txt"
        logging.info(f"[HUAWEI] Enviando comando: backup configuration -> FTP {local_ip}:{FTP_PORT}")
        shell.send(f"backup configuration ftp {local_ip} {FTP_PORT} {cfg_filename} {FTP_USER} {FTP_PASS}\n")
        
        out = wait_prompt("#", timeout=60)
        if "successfully" in out.lower() or "success" in out.lower():
            logging.info(f"[HUAWEI] Backup de configuracao reportou sucesso.")
        else:
            logging.warning(f"[HUAWEI] OLT nao reportou sucesso claro no backup de configuracao.")
            
        # ── 5. BACKUP DATA ───────────────────────────────────────────────
        data_filename = f"hw_data_{nome.lower()}.dat"
        logging.info(f"[HUAWEI] Enviando comando: backup data -> FTP {local_ip}:{FTP_PORT}")
        shell.send(f"backup data ftp {local_ip} {FTP_PORT} {data_filename} {FTP_USER} {FTP_PASS}\n")
        
        out = wait_prompt("#", timeout=120)
        
        # ── 6. VERIFICAR ARQUIVOS RECEBIDOS ──────────────────────────────
        cfg_path = pasta_destino / cfg_filename
        data_path = pasta_destino / data_filename
        
        arquivos_recebidos = []
        if cfg_path.exists():
            arquivos_recebidos.append(f"{cfg_filename} ({cfg_path.stat().st_size} bytes)")
        if data_path.exists():
            arquivos_recebidos.append(f"{data_filename} ({data_path.stat().st_size} bytes)")
        
        if arquivos_recebidos:
            logging.info(f"[HUAWEI] Arquivos recebidos com sucesso via FTP:")
            for arq in arquivos_recebidos:
                logging.info(f"[HUAWEI]   -> {arq}")
            res["status"] = "OK"
        else:
            logging.error(f"[HUAWEI] FALHA — Nenhum arquivo foi recebido no FTP.")
            logging.error(f"[HUAWEI] Verifique se a OLT consegue alcançar {local_ip}:{FTP_PORT}")
            
    except paramiko.ssh_exception.AuthenticationException as e:
        logging.error(f"[HUAWEI] FALHA DE AUTENTICACAO em {ip}:{porta} — Usuario ou senha incorretos.")
        logging.error(f"[HUAWEI] Detalhe: {e}")
    except paramiko.ssh_exception.SSHException as e:
        logging.error(f"[HUAWEI] FALHA SSH em {ip}:{porta} — {e}")
        logging.error(f"[HUAWEI] Isso pode indicar incompatibilidade de algoritmos SSH com a OLT.")
    except TimeoutError as e:
        logging.error(f"[HUAWEI] TIMEOUT — A OLT nao respondeu a tempo: {e}")
    except ConnectionRefusedError:
        logging.error(f"[HUAWEI] CONEXAO RECUSADA — A OLT {ip}:{porta} recusou a conexao SSH.")
    except Exception as e:
        logging.error(f"[HUAWEI] ERRO INESPERADO em {ip}:{porta}: {type(e).__name__}: {e}")
    finally:
        try:
            ssh.close()
        except Exception:
            pass
        logging.info("[HUAWEI] Desligando servidor FTP temporario...")
        server.close_all()
        
    return res
