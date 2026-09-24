import os
import time
import socket
import logging
import shutil
from pathlib import Path
from datetime import datetime
import paramiko


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


def realizar_backup_huawei_ativo(equipamento: dict, pasta_destino: Path) -> dict:
    """
    Realiza backup ativo de uma OLT Huawei (MA5800 e similares) via SSH
    usando o servidor FTP (WFTPD) ja existente na porta 21 da maquina.
    """
    ip = equipamento.get("ip")
    username = equipamento.get("username")
    password = equipamento.get("password")
    nome = equipamento.get("name", "Huawei").replace(" ", "_")
    
    config_extra = equipamento.get("config_extra") or {}
    pasta_origem = config_extra.get("pasta_origem")
    
    res = {"nome": nome, "status": "ERRO", "cameras": None}
    
    if not ip or not username or not password:
        logging.error(f"[HUAWEI] {nome} — Faltam credenciais (ip/usuario/senha). Abortando.")
        return res
        
    if not pasta_origem:
        logging.error(f"[HUAWEI] {nome} — Pasta de origem (WFTPD) nao configurada. Configure no painel.")
        return res
        
    pasta_origem_path = Path(pasta_origem)
    if not pasta_origem_path.exists() or not pasta_origem_path.is_dir():
        logging.error(f"[HUAWEI] A pasta do WFTPD informada nao existe ou e invalida: {pasta_origem}")
        return res

    local_ip = get_local_ip(ip)
    logging.info(f"[HUAWEI] IP local detectado para rota ate {ip}: {local_ip}")
    
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
        
        # OLTs Huawei antigas (MA5800 etc.) usam apenas o algoritmo ssh-rsa (SHA-1).
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
        out = wait_prompt(["successful", "success", "failed", "failure"], timeout=60)
        if "successful" in out.lower() or "success" in out.lower():
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
        out = wait_prompt(["successful", "success", "failed", "failure"], timeout=120)
        
        # ── COPIAR ARQUIVOS DO WFTPD PARA A PASTA DE DESTINO ─────────────
        cfg_source = pasta_origem_path / cfg_filename
        data_source = pasta_origem_path / data_filename
        
        cfg_dest = pasta_destino / cfg_filename
        data_dest = pasta_destino / data_filename
        
        # Dar um tempo para o disco/SO terminar de escrever
        time.sleep(2)
        
        arquivos_recebidos = []
        if cfg_source.exists():
            shutil.copy2(cfg_source, cfg_dest)
            arquivos_recebidos.append(f"{cfg_filename} ({cfg_dest.stat().st_size} bytes)")
            # Tenta apagar da pasta de origem do wftpd
            try:
                os.remove(cfg_source)
            except Exception:
                pass
                
        if data_source.exists():
            shutil.copy2(data_source, data_dest)
            arquivos_recebidos.append(f"{data_filename} ({data_dest.stat().st_size} bytes)")
            try:
                os.remove(data_source)
            except Exception:
                pass
        
        if arquivos_recebidos:
            logging.info(f"[HUAWEI] Arquivos copiados com sucesso do WFTPD:")
            for arq in arquivos_recebidos:
                logging.info(f"[HUAWEI]   -> {arq}")
            res["status"] = "OK"
        else:
            logging.error(f"[HUAWEI] FALHA — Arquivos nao encontrados na pasta do WFTPD: {pasta_origem}")
            logging.error(f"[HUAWEI] O arquivo {cfg_filename} deveria ter chegado la.")
            
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
            
    return res
