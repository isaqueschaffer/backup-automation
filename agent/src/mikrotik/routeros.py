from paramiko import ssh_exception
import paramiko
import time
import logging
from pathlib import Path

def realizar_backup_mikrotik(equipamento: dict, pasta_destino: Path) -> dict:
    ip = equipamento.get("ip")
    username = equipamento.get("username")
    password = equipamento.get("password")
    nome = equipamento.get("name", "Mikrotik").replace(" ", "_")
    
    res = {"nome": nome, "status": "ERRO", "cameras": None}
    
    if not ip or not username or not password:
        logging.error(f"[MIKROTIK] {nome} - Faltam credenciais ou IP.")
        return res
        
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        porta = equipamento.get("porta") or equipamento.get("port") or 22
        porta = int(porta)
        logging.info(f"[MIKROTIK] Conectando via SSH em {ip}:{porta}...")
        ssh.connect(ip, port=porta, username=username, password=password, timeout=20, look_for_keys=False, allow_agent=False)
        
        # O nome do arquivo no roteador
        file_base = f"backup_{nome.lower()}"
        
        # 1. Gerar o arquivo .backup (binário criptografado)
        logging.info(f"[MIKROTIK] Gerando arquivo .backup em {ip}...")
        stdin, stdout, stderr = ssh.exec_command(f"/system backup save name={file_base}")
        stdout.read() # Espera o comando terminar
        
        # 2. Gerar o arquivo .rsc (texto puro - script de configuração)
        logging.info(f"[MIKROTIK] Gerando arquivo .rsc em {ip}...")
        stdin, stdout, stderr = ssh.exec_command(f"/export file={file_base}")
        stdout.read() # Espera o comando terminar
        
        # MikroTik leva uns segundos para salvar o arquivo rsc no disco
        time.sleep(3)
        
        # 3. Baixar os arquivos via SFTP
        logging.info(f"[MIKROTIK] Iniciando transferencia SFTP de {ip}...")
        sftp = ssh.open_sftp()
        
        backup_file = f"{file_base}.backup"
        rsc_file = f"{file_base}.rsc"
        
        local_backup = pasta_destino / backup_file
        local_rsc = pasta_destino / rsc_file
        
        sucesso = False
        
        try:
            sftp.get(backup_file, str(local_backup))
            sftp.get(rsc_file, str(local_rsc))
            sucesso = True
            logging.info(f"[MIKROTIK] Arquivos baixados com sucesso para {nome}")
        except Exception as e:
            logging.error(f"[MIKROTIK] Erro ao baixar arquivos de {ip}: {e}")
            
        # 4. Limpeza (apagar do router para não lotar a flash)
        try:
            sftp.remove(backup_file)
            sftp.remove(rsc_file)
            logging.info(f"[MIKROTIK] Arquivos temporarios excluidos do roteador {ip}")
        except Exception as e:
            logging.warning(f"[MIKROTIK] Nao foi possivel apagar temporarios de {ip}: {e}")
            
        sftp.close()
        
        if sucesso:
            res["status"] = "OK"
            
    except Exception as e:
        logging.error(f"[MIKROTIK] Falha geral em {ip}: {e}")
    finally:
        ssh.close()
        
    return res
