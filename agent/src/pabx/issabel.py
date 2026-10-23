import logging
import re
import requests
from pathlib import Path
import urllib3

# Desativa avisos de certificado SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def login(session: requests.Session, host: str, user: str, password: str) -> bool:
    """Autentica no Issabel caso o cookie expire."""
    login_url = f"{host}/index.php"
    payload = {
        "input_user": user,
        "input_pass": password,
        "submit_login": "Submit"
    }
    resp = session.post(login_url, data=payload, verify=False, timeout=15)
    return "menu=backup_restore" in resp.text or resp.status_code == 200


def disparar_backup(session: requests.Session, host: str) -> str:
    """Dispara a criacao do backup completo e retorna o nome do arquivo .tar gerado."""
    backup_url = f"{host}/index.php?menu=backup_restore"

    payload = {
        "process": "Executar",
        "backup_total": "on",
        "backup_endpoint": "on",
        "ep_db": "ep_db",
        "ep_config_files": "ep_config_files",
        "backup_fax": "on",
        "fx_db": "fx_db",
        "fx_pdf": "fx_pdf",
        "backup_email": "on",
        "em_db": "em_db",
        "em_mailbox": "em_mailbox",
        "backup_asterisk": "on",
        "as_db": "as_db",
        "as_config_files": "as_config_files",
        "as_monitor": "as_monitor",
        "as_voicemail": "as_voicemail",
        "as_sounds": "as_sounds",
        "as_mohmp3": "as_mohmp3",
        "as_dahdi": "as_dahdi",
        "backup_others": "on",
        "sugar_db": "sugar_db",
        "vtiger_db": "vtiger_db",
        "a2billing_db": "a2billing_db",
        "mysql_db": "mysql_db",
        "menus_permissions": "menus_permissions",
        "backup_others_new": "on",
        "calendar_db": "calendar_db",
        "address_db": "address_db",
        "conference_db": "conference_db",
        "eop_db": "eop_db",
        "option_url": "backup",
        "backup_file": ""
    }

    logging.info("  Disparando a criacao do backup no servidor...")
    resp = session.post(backup_url, data=payload, verify=False, timeout=600)

    # 1. Tenta achar o nome do arquivo diretamente pelo padrão do Issabel no HTML retornado
    # (Tornado mais flexível para suportar sufixos como -ab.tar do servidor mock)
    match = re.search(r"(issabelbackup-\d{14}[a-zA-Z0-9_-]*\.tar)", resp.text)
    if match:
        return match.group(1)

    # 2. Alternativa via regex no link de download (ou id)
    link_match = re.search(r"(?:file_name|id)=(issabelbackup-[^&\"']+)", resp.text)
    if link_match:
        return link_match.group(1)

    logging.error(f"DEBUG: Nao encontrou nome do arquivo. HTML recebido:\n{resp.text}")
    raise ValueError("Nao foi possivel identificar o nome do arquivo gerado no retorno da pagina.")


def baixar_backup(session: requests.Session, host: str, filename: str, destino: Path):
    """Realiza o download em blocos do arquivo gerado."""
    download_url = (
        f"{host}/index.php?menu=backup_restore"
        f"&action=download_file&file_name={filename}&rawmode=yes"
    )

    logging.info(f"  Iniciando download de: {filename}")
    resp = session.get(download_url, stream=True, verify=False, timeout=60)
    
    resp.raise_for_status()
    with open(destino, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)


def realizar_backup_issabel(equipamento: dict, pasta_data: Path) -> dict:
    nome = equipamento.get("name", "PABX_Issabel")
    ip = equipamento.get("ip")
    user = equipamento.get("username")
    pwd = equipamento.get("password")
    
    host = f"https://{ip}" if not ip.startswith("http") else ip
    
    logging.info(f"\n{'='*50}\n{nome} [PABX Issabel] (IP: {ip})\n{'='*50}")
    
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"{host}/index.php?menu=backup_restore"
    })
    s.cookies.set("lang", "pt_BR")

    try:
        if not login(s, host, user, pwd):
            logging.error("  Falha no login do Issabel (credenciais invalidas ou servico indisponivel).")
            return {"nome": nome, "status": "ERRO", "cameras": None}
            
        nome_arquivo = disparar_backup(s, host)
        logging.info(f"  Backup gerado com sucesso: {nome_arquivo}")
        
        arquivo_destino = pasta_data / nome_arquivo
        baixar_backup(s, host, nome_arquivo, arquivo_destino)
        logging.info(f"  Download concluido com sucesso: {nome_arquivo}")
        
        return {"nome": nome, "status": "OK", "cameras": None}
    except Exception as e:
        logging.error(f"  Erro durante o processo PABX: {str(e)}")
        return {"nome": nome, "status": "ERRO", "cameras": None}
