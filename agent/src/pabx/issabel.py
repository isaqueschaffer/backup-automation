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



def _abrir_download(session: requests.Session, host: str, filename: str):
    """GET do arquivo gerado, em fluxo, pedindo o corpo sem compressão (o tamanho do Content-Length tem de bater
    com os bytes lidos). Devolve a resposta (aberta)."""
    download_url = (
        f"{host}/index.php?menu=backup_restore"
        f"&action=download_file&file_name={filename}&rawmode=yes"
    )
    resp = session.get(download_url, stream=True, verify=False, timeout=60, headers={"Accept-Encoding": "identity"})
    resp.raise_for_status()
    return resp


def _tamanho_resposta(resp) -> int | None:
    try:
        n = int(resp.headers.get("Content-Length", ""))
        return n if n >= 0 and not resp.headers.get("Content-Encoding") else None
    except (TypeError, ValueError):
        return None


def preparar_backup_issabel_tunel(equipamento: dict, limite_memoria: int) -> dict:
    """Túnel do Mikrotik: nada em disco. Gera o backup no Issabel e baixa o .tar:
    - com Content-Length até `limite_memoria`: o arquivo fica em memória (e a nova tentativa do túnel não baixa de novo);
    - maior, ou sem Content-Length: devolve a origem "http" (`abrir_fluxo`), lida em blocos direto para o ZIP; sem
      Content-Length não há conferência de tamanho, mas o download precisa terminar sem erro.
    Devolve {"nome", "status": "PRONTO"|"ERRO", "arquivos_origem": [(BackupFile, nome_no_zip)]}."""
    from src.backup.file_manager.models import BackupFile

    nome = equipamento.get("name", "PABX_Issabel")
    ip = equipamento.get("ip")
    user = equipamento.get("username")
    pwd = equipamento.get("password")
    erro = {"nome": nome, "status": "ERRO", "cameras": None}
    if not ip or not user:
        logging.error(f"  [PABX] {nome}: faltam IP ou usuário.")
        return erro
    host = f"https://{ip}" if not ip.startswith("http") else ip

    logging.info(f"{'='*50} {nome} [PABX Issabel / túnel] (IP: {ip}) {'='*50}")
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"{host}/index.php?menu=backup_restore"
    })
    s.cookies.set("lang", "pt_BR")
    try:
        if not login(s, host, user, pwd):
            logging.error("  Falha no login do Issabel (credenciais invalidas ou servico indisponivel).")
            return erro
        nome_arquivo = disparar_backup(s, host)
        logging.info(f"  Backup gerado com sucesso: {nome_arquivo}")

        resp = _abrir_download(s, host, nome_arquivo)
        tamanho = _tamanho_resposta(resp)
        if tamanho is not None and tamanho <= limite_memoria:
            try:
                dados = b"".join(c for c in resp.iter_content(chunk_size=1024 * 1024) if c)
            finally:
                resp.close()
            if len(dados) != tamanho:
                raise ValueError(f"download incompleto ({len(dados)} de {tamanho} bytes)")
            bf = BackupFile(path=Path(nome_arquivo), file_type="PABX_TAR", dados=dados)
            logging.info(f"  [PABX] {nome}: {nome_arquivo} em memória ({tamanho:,} bytes).")
        else:
            resp.close()        # grande ou sem tamanho: relido em blocos na hora de montar o ZIP

            def abrir_fluxo():
                r = _abrir_download(s, host, nome_arquivo)

                def blocos():
                    try:
                        for c in r.iter_content(chunk_size=1024 * 1024):
                            if c:
                                yield c
                    finally:
                        r.close()
                return blocos(), _tamanho_resposta(r)

            bf = BackupFile(path=Path(nome_arquivo), file_type="PABX_TAR", abrir_fluxo=abrir_fluxo)
            logging.info(f"  [PABX] {nome}: {nome_arquivo} será lido em blocos "
                         f"({'tamanho informado ' + format(tamanho, ',') if tamanho is not None else 'sem Content-Length'}).")
        return {"nome": nome, "status": "PRONTO", "arquivos_origem": [(bf, nome_arquivo)], "cameras": None}
    except Exception as e:
        logging.error(f"  Erro durante o processo PABX: {e}")
        return erro
