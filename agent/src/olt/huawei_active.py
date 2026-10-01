import os
import time
import socket
import logging
import threading
from pathlib import Path
from datetime import datetime
import paramiko
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

# Usaremos a porta 21 padrao, agora que o WFTPD sera desinstalado
FTP_PORT = 21


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


class HuaweiAuthorizer(DummyAuthorizer):
    """
    Authorizer customizado que aceita QUALQUER usuario e senha.
    A OLT Huawei frequentemente usa credenciais globais obscuras (ex: user '1').
    """
    def __init__(self, dest_dir: str):
        super().__init__()
        self.dest_dir = dest_dir
        
    def validate_authentication(self, username, password, handler):
        # Se o usuario nao existe na tabela ainda, adiciona com a senha fornecida
        if username not in self.user_table:
            self.add_user(username, password, self.dest_dir, perm="elradfmwMT")
        return super().validate_authentication(username, password, handler)


def realizar_backup_huawei_ativo(equipamento: dict, pasta_destino: Path) -> dict:
    """
    Realiza backup ativo de uma OLT Huawei (MA5800 e similares) via SSH.
    Como a OLT Huawei e engessada (nao permite porta customizada e as vezes falha com user/pass),
    subimos um FTP efemero na porta 21 com acesso anonimo habilitado para escrita.
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
    
    # ── SUBIR SERVIDOR FTP TEMPORÁRIO (Porta 21) ────────────────
    logging.info(f"[HUAWEI] Iniciando servidor FTP temporario na porta {FTP_PORT}...")
    authorizer = HuaweiAuthorizer(str(pasta_destino))
    # Mantem o anonimo por precaucao
    authorizer.add_anonymous(str(pasta_destino), perm="elradfmwMT")
    
    handler = FTPHandler
    handler.authorizer = authorizer
    handler.banner = "Trilan Agent Temp FTP Ready."
    
    try:
        server = FTPServer(("0.0.0.0", FTP_PORT), handler)
        server.max_cons = 5
        server.max_cons_per_ip = 5
    except Exception as e:
        logging.error(f"[HUAWEI] FALHA ao subir FTP na porta {FTP_PORT}: {e}")
        logging.error(f"[HUAWEI] Verifique se o WFTPD foi realmente desinstalado ou parado (porta 21 ocupada).")
        return res
        
    ftp_thread = threading.Thread(target=run_ftp_server, args=(server,), daemon=True)
    ftp_thread.start()
    
    # ── CONECTAR VIA SSH NA OLT ───────────────────────────────────────
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    cfg_filename = f"hw_config_{nome.lower()}_{timestamp}.txt"
    data_filename = f"hw_data_{nome.lower()}_{timestamp}.dat"
    
    try:
        porta = equipamento.get("porta") or equipamento.get("port") or 22
        porta = int(porta)
        logging.info(f"[HUAWEI] Conectando via SSH em {ip}:{porta} (usuario: {username})...")
        
        # OLTs Huawei antigas usam apenas o algoritmo ssh-rsa (SHA-1).
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
        
        shell = ssh.invoke_shell()
        shell.settimeout(15)
        
        def wait_prompt(expected_list: list, timeout: int = 15) -> str:
            end_time = time.time() + timeout
            output = ""
            while time.time() < end_time:
                if shell.recv_ready():
                    chunk = shell.recv(4096).decode("utf-8", errors="ignore")
                    output += chunk
                    for expected in expected_list:
                        if expected in output:
                            return output
                time.sleep(0.5)
            raise TimeoutError(f"Prompt nao encontrado apos {timeout}s. Output: {output[-500:]}")

        # Aguardar prompt inicial
        logging.info(f"[HUAWEI] Aguardando prompt inicial da OLT...")
        wait_prompt([">"])
        
        # Entrar no modo enable
        logging.info(f"[HUAWEI] Entrando em modo privilegiado (enable)...")
        shell.send("enable\n")
        wait_prompt(["#"])
        
        # Desabilitar paginacao
        shell.send("undo smart\n")
        time.sleep(1)
        if shell.recv_ready():
            shell.recv(4096)
            
        # ── BACKUP CONFIGURATION ─────────────────────────────────────
        logging.info(f"[HUAWEI] Enviando comando: backup configuration ftp {local_ip} {cfg_filename}")
        shell.send(f"backup configuration ftp {local_ip} {cfg_filename}\n")
        
        # Aguardar confirmacao (y/n)[n]:
        out = wait_prompt(["(y/n)[n]:", "(y/n) [n]:"], timeout=30)
        if "(y/n)" in out:
            logging.info(f"[HUAWEI] OLT pediu confirmacao. Respondendo 'y'...")
            shell.send("y\n")
            
        # Aguardar sucesso ou falha (ignora o '#' porque a OLT cospe logs assincronos)
        out = wait_prompt(["is successful", "failed"], timeout=60)
        if "is successful" in out.lower() or "success" in out.lower():
            logging.info(f"[HUAWEI] Backup de configuracao reportou sucesso.")
        else:
            logging.warning(f"[HUAWEI] OLT nao reportou sucesso claro no backup de configuracao.")
            
        # ── BACKUP DATA ───────────────────────────────────────────────
        logging.info(f"[HUAWEI] Enviando comando: backup data ftp {local_ip} {data_filename}")
        shell.send(f"backup data ftp {local_ip} {data_filename}\n")
        
        # Aguardar confirmacao (y/n)[n]:
        out = wait_prompt(["(y/n)[n]:", "(y/n) [n]:"], timeout=30)
        if "(y/n)" in out:
            logging.info(f"[HUAWEI] OLT pediu confirmacao. Respondendo 'y'...")
            shell.send("y\n")
            
        # Aguardar sucesso ou falha
        out = wait_prompt(["is successful", "failed"], timeout=120)
        
        # ── VERIFICAR ARQUIVOS RECEBIDOS NO FTP EFÊMERO ─────────────
        cfg_path = pasta_destino / cfg_filename
        data_path = pasta_destino / data_filename
        
        arquivos_recebidos = []
        if cfg_path.exists():
            arquivos_recebidos.append(f"{cfg_filename} ({cfg_path.stat().st_size} bytes)")
        if data_path.exists():
            arquivos_recebidos.append(f"{data_filename} ({data_path.stat().st_size} bytes)")
        
        if arquivos_recebidos:
            logging.info(f"[HUAWEI] Arquivos recebidos com sucesso via FTP temporario:")
            for arq in arquivos_recebidos:
                logging.info(f"[HUAWEI]   -> {arq}")
            res["status"] = "OK"
        else:
            logging.error(f"[HUAWEI] FALHA — Nenhum arquivo foi recebido no FTP temporario.")
            logging.error(f"[HUAWEI] Verifique se a OLT consegue alcançar {local_ip}:21")
            
    except paramiko.ssh_exception.AuthenticationException as e:
        logging.error(f"[HUAWEI] FALHA DE AUTENTICACAO em {ip}:{porta} — Usuario ou senha incorretos.")
    except paramiko.ssh_exception.SSHException as e:
        logging.error(f"[HUAWEI] FALHA SSH em {ip}:{porta} — {e}")
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
