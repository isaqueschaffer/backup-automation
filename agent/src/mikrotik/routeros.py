from paramiko import ssh_exception
import paramiko
import re
import time
import logging
from pathlib import Path

def realizar_backup_mikrotik(equipamento: dict, pasta_destino: Path) -> dict:
    ip = equipamento.get("ip")
    username = equipamento.get("username")
    password = equipamento.get("password")
    nome = re.sub(r"[^\w.-]", "_", equipamento.get("name") or "Mikrotik")
    
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
        stdin, stdout, stderr = ssh.exec_command(f"/system backup save name={file_base}", timeout=120)
        stdout.channel.settimeout(120)
        stdout.read() # Espera o comando terminar (com timeout)
        
        # 2. Gerar o arquivo .rsc (texto puro - script de configuração)
        logging.info(f"[MIKROTIK] Gerando arquivo .rsc em {ip}...")
        stdin, stdout, stderr = ssh.exec_command(f"/export file={file_base}", timeout=120)
        stdout.channel.settimeout(120)
        stdout.read() # Espera o comando terminar (com timeout)
        
        # MikroTik leva uns segundos para salvar o arquivo rsc no disco
        time.sleep(3)
        
        # 3. Baixar os arquivos via SFTP
        logging.info(f"[MIKROTIK] Iniciando transferencia SFTP de {ip}...")
        sftp = ssh.open_sftp()
        sftp.get_channel().settimeout(600)
        
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


def preparar_backup_mikrotik_tunel(equipamento: dict) -> dict:
    """Túnel do Mikrotik (nada em disco do agente): no PRÓPRIO roteador-alvo gera `/system backup save` e `/export`
    e devolve os dois arquivos como origem SFTP (lidos em blocos para o ZIP). Os arquivos do alvo são apagados no
    fim do envio pelas funções em `_limpeza` (e já aqui, se a preparação falhar). A chave do host é verificada
    (TOFU ou `ssh_fingerprint`)."""
    from src.backup.file_manager.models import BackupFile
    from src.backup.sftp_origem import ErroSftp, PastaSftp, obter_conexao
    from src.core.config import parse_config_extra

    ip = equipamento.get("ip")
    username = equipamento.get("username")
    password = equipamento.get("password")
    nome = re.sub(r"[^\w.-]", "_", equipamento.get("name") or "Mikrotik")
    res = {"nome": nome, "status": "ERRO", "cameras": None}
    if not ip or not username or not password:
        logging.error(f"[MIKROTIK] {nome} - Faltam credenciais ou IP.")
        return res

    file_base = f"backup_{nome.lower()}"
    backup_file, rsc_file = f"{file_base}.backup", f"{file_base}.rsc"
    criados = []
    con = None

    def apagar():
        # nomes vêm de re.sub(\w.-): seguros dentro de aspas do RouterOS
        for arq in criados:
            try:
                _, out, _ = con.ssh.exec_command(f'/file remove [find name="{arq}"]', timeout=30)
                out.channel.settimeout(30)
                out.read()
            except Exception as e:
                logging.warning(f"[MIKROTIK] Nao foi possivel apagar {arq} do roteador {ip}: {e}")
        if criados:
            logging.info(f"[MIKROTIK] Arquivos temporarios excluidos do roteador {ip}")
        criados.clear()

    def rodar(cmd):
        _, out, _ = con.ssh.exec_command(cmd, timeout=120)
        out.channel.settimeout(120)
        out.read()

    try:
        porta = int(equipamento.get("porta") or equipamento.get("port") or 22)
        cfg = parse_config_extra(equipamento)
        logging.info(f"[MIKROTIK] Conectando via SSH em {ip}:{porta}...")
        con = obter_conexao(ip, porta, username, password, None, cfg.get("ssh_fingerprint") or None)
        logging.info(f"[MIKROTIK] Gerando arquivo .backup em {ip}...")
        criados.append(backup_file)
        rodar(f"/system backup save name={file_base}")
        logging.info(f"[MIKROTIK] Gerando arquivo .rsc em {ip}...")
        criados.append(rsc_file)
        rodar(f"/export file={file_base}")

        pasta = PastaSftp(con, "", relativo=True)
        for _ in range(15):         # o RouterOS leva uns segundos para gravar o .rsc
            try:
                if pasta.stat(rsc_file).size > 0 and pasta.stat(backup_file).size > 0:
                    break
            except ErroSftp:
                pass
            time.sleep(1)
        origens = []
        for arq in (backup_file, rsc_file):
            tam = pasta.stat(arq).size
            if tam <= 0:
                raise ErroSftp(f"{arq} ficou vazio no roteador")
            origens.append((BackupFile(path=Path(arq), file_type="MIKROTIK", remote_path=arq, is_sftp=True,
                                       sftp=pasta, _size=tam), arq))
        logging.info(f"[MIKROTIK] {nome}: arquivos prontos no roteador ({', '.join(str(o.size_bytes) for o, _ in origens)} bytes).")
        return {"nome": nome, "status": "PRONTO", "arquivos_origem": origens, "cameras": None,
                "_limpeza": [apagar]}
    except Exception as e:
        logging.error(f"[MIKROTIK] Falha em {ip}: {e}")
        if con is not None:
            apagar()
        return res
