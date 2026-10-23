import sys
import json
import time
import shutil
import logging
import hashlib
import smtplib
from base64 import b64encode
from datetime import datetime
from pathlib import Path
from email.message import EmailMessage

import requests
from requests.auth import HTTPDigestAuth
import pyzipper
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

# ============================================================
# CONFIGURAÇÕES GERAIS
# ============================================================
DIR_ATUAL = Path(__file__).resolve().parent
AES_KEY_HEX = bytes.fromhex("bf8a6df8640f38f3812c19d2aaca7743")
TIMEOUT = 60
LIMITE_ANEXO_BYTES = 5 * 1024 * 1024  # 5 MB

def data_hoje(): 
    return datetime.now().strftime("%d-%m-%Y")

# ============================================================
# UTILITÁRIOS E CONFIGURAÇÃO
# ============================================================
def configurar_log(pasta):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Remove APENAS os prints de tela de execuções passadas (evita prints duplicados)
    for h in logger.handlers[:]:
        if type(h) is logging.StreamHandler:
            logger.removeHandler(h)
    
    # Verifica se o arquivo de log já está aberto (evita abrir duas vezes e dar erro)
    caminho_log = str(pasta / "backup.log")
    log_ja_aberto = any(hasattr(h, "baseFilename") and caminho_log in str(h.baseFilename) for h in logger.handlers)
    
    if not log_ja_aberto:
        fmt_file = logging.Formatter('[%(asctime)s] %(message)s', '%Y-%m-%d %H:%M:%S')
        fh = logging.FileHandler(pasta / "backup.log", encoding="utf-8")
        fh.setFormatter(fmt_file)
        logger.addHandler(fh)
        
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(ch)

def carregar_config(caminho, campos_obrigatorios):
    if not caminho.exists():
        sys.exit(f"❌ ERRO: Arquivo {caminho.name} não encontrado.")
    try:
        config = json.loads(caminho.read_text(encoding="utf-8"))
        if faltantes := [c for c in campos_obrigatorios if c not in config]:
            sys.exit(f"❌ ERRO: Campos ausentes em {caminho.name}: {faltantes}")
        return config
    except Exception as e:
        sys.exit(f"❌ ERRO ao carregar {caminho.name}: {e}")

# ============================================================
# CRIPTOGRAFIA (HIKVISION)
# ============================================================
def gerar_secretkey(senha):
    timestamp = str(int(time.time() * 1000))
    iv_hex = hashlib.md5(timestamp.encode("utf-8")).hexdigest()
    
    senha_escapada = senha.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    texto = b64encode(senha_escapada.encode("utf-8"))
    
    cipher = AES.new(AES_KEY_HEX, AES.MODE_CBC, bytes.fromhex(iv_hex))
    return cipher.encrypt(pad(texto, AES.block_size)).hex(), iv_hex

# ============================================================
# DOWNLOAD E BACKUP
# ============================================================
def baixar_arquivo(sessao, url, destino, min_bytes=0, valida_xml=False):
    try:
        with sessao.get(url, stream=True, timeout=TIMEOUT) as r:
            if r.status_code not in (200, 401): # 401 apenas na checagem de status
                logging.error(f"ERRO HTTP {r.status_code}: {url}")
                return False
            with open(destino, "wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    if chunk: f.write(chunk)

        dados = destino.read_bytes()
        if len(dados) < min_bytes:
            raise ValueError("Arquivo muito pequeno (falha de autenticação/chave).")
        if valida_xml and b"<ResponseStatus" in dados[:500]:
            raise ValueError("XML de erro recebido ao invés do backup.")

        tamanho_kb = len(dados) / 1024
        sha256 = hashlib.sha256(dados).hexdigest()
        logging.info(f"Salvo: {destino.name} ({tamanho_kb:.2f} KB) | SHA-256: {sha256}")
        return True
    
    except Exception as e:
        logging.error(f"❌ Erro no download ({destino.name}): {e}")
        destino.unlink(missing_ok=True)
        return False

def processar_nvr(nvr, senha_encriptacao, pasta_data):
    nome, ip, user, pwd = nvr["nome"], nvr["ip"], nvr["usuario"], nvr["senha"]
    logging.info(f"\n{'='*60}\n{nome} (IP: {ip})\n{'='*60}")
    
    pasta_nvr = pasta_data / nome.replace(" ", "_")
    pasta_nvr.mkdir(parents=True, exist_ok=True)

    # Configurar sessão persistente com autenticação Digest
    sessao = requests.Session()
    sessao.auth = HTTPDigestAuth(user, pwd)

    try:
        # Testar conexão
        sessao.get(f"http://{ip}/ISAPI/System/status", timeout=10).raise_for_status()
        logging.info("NVR acessível.")
    except requests.exceptions.RequestException:
        logging.error("❌ NVR inacessível.")
        return {"nome": nome, "status": "ERRO"}

    sucessos = 0
    # 1. Config NVR (.bin)
    secretkey, iv = gerar_secretkey(senha_encriptacao)
    url_bin = f"http://{ip}/ISAPI/System/configurationData?secretkey={secretkey}&security=1&iv={iv}"
    arq_bin = pasta_nvr / f"CONFIG_NVR_{data_hoje()}.bin"
    if baixar_arquivo(sessao, url_bin, arq_bin, min_bytes=100000, valida_xml=True):
        logging.info("✅ Backup NVR concluído.")
        sucessos += 1

    # 2. Config IPCAM (.xls)
    url_xls = f"http://{ip}/ISAPI/ContentMgmt/InputProxy/ipcConfig"
    arq_xls = pasta_nvr / f"CONFIG_IPCAM_{data_hoje()}.xls"
    if baixar_arquivo(sessao, url_xls, arq_xls):
        logging.info("✅ Backup IPCAM concluído.")
        sucessos += 1

    status = "OK" if sucessos == 2 else "PARCIAL" if sucessos == 1 else "ERRO"
    return {"nome": nome, "status": status}

# ============================================================
# COMPACTAÇÃO E E-MAIL
# ============================================================
def criar_zip(pasta, cliente, senha):
    logging.info(f"\n{'='*60}\nCOMPACTANDO BACKUP\n{'='*60}")
    caminho_zip = pasta / f"BACKUP_{cliente.upper()}_{data_hoje()}.zip"
    
    try:
        with pyzipper.AESZipFile(caminho_zip, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zf:
            zf.setpassword(senha.encode("utf-8"))
            for arq in pasta.rglob("*"):
                if arq.is_file() and arq.name not in (caminho_zip.name, "backup.log", "relatorio_backup.json"):
                    zf.write(arq, arq.relative_to(pasta))

        # Testar integridade do ZIP nativamente
        with pyzipper.AESZipFile(caminho_zip, "r") as zf:
            zf.setpassword(senha.encode("utf-8"))
            if zf.testzip() is not None:
                raise ValueError("O ZIP está corrompido.")

        logging.info(f"✅ ZIP íntegro e criado com sucesso: {caminho_zip.name}")
        return caminho_zip
    except Exception as e:
        logging.error(f"❌ Erro ao criar ZIP: {e}")
        return None

def enviar_email(caminho_zip, cliente, resultados, cfg):
    logging.info(f"\n{'='*60}\nENVIO DO BACKUP POR E-MAIL\n{'='*60}")
    
    dests = cfg["destinatarios"] if isinstance(cfg["destinatarios"], list) else [cfg["destinatarios"]]
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = cfg["email"], ", ".join(dests), f"Backup NVR - {cliente} - {data_hoje()}"

    linhas_status = "\n".join(f"  {r['nome']}: {r['status']}" for r in resultados)
    corpo = f"Backup automático de NVR.\nCliente: {cliente}\nData: {data_hoje()}\n\nStatus:\n{linhas_status}\n\n"

    # Validar limite de tamanho
    anexar = caminho_zip and caminho_zip.stat().st_size <= LIMITE_ANEXO_BYTES
    if anexar:
        corpo += "O arquivo ZIP protegido com senha está anexado."
    else:
        corpo += f"⚠️ O ZIP excede o limite (5MB) e NÃO foi anexado.\nCaminho: {caminho_zip}"
        logging.warning("⚠️ ZIP excede limite de anexo, enviando apenas notificação.")

    # 1º PASSO: Definir o corpo de texto PRIMEIRO
    msg.set_content(corpo)

    # 2º PASSO: Adicionar o anexo DEPOIS
    if anexar:
        msg.add_attachment(caminho_zip.read_bytes(), maintype="application", subtype="zip", filename=caminho_zip.name)

    try:
        with smtplib.SMTP(cfg["smtp_server"], int(cfg["smtp_port"]), timeout=300) as server:
            server.starttls()
            server.login(cfg["email"], cfg["senha_app"])
            server.send_message(msg)
        logging.info("✅ E-mail enviado com sucesso.")
        return True
    except Exception as e:
        logging.error(f"❌ ERRO AO ENVIAR E-MAIL: {e}")
        return False

# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================
def main():
    cfg = carregar_config(DIR_ATUAL / "config.json", ["cliente", "pasta_backup", "senha_encriptacao", "nvrs"])
    cfg_email = carregar_config(DIR_ATUAL / "config_email.json", ["smtp_server", "smtp_port", "email", "senha_app", "destinatarios"])

    if not cfg["nvrs"]:
        sys.exit("❌ ERRO: Nenhum NVR configurado.")

    pasta_data = Path(cfg["pasta_backup"]) / data_hoje()
    pasta_data.mkdir(parents=True, exist_ok=True)

    # Varredura inteligente: Limpa tudo da pasta antiga EXCETO o backup.log
    for item in pasta_data.iterdir():
        try:
            if item.name == "backup.log":
                continue
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
        except Exception:
            pass  # Ignora erros silenciosamente se algo mais estiver bloqueado

    configurar_log(pasta_data)

    logging.info(f"\n{'='*60}\nBACKUP AUTOMÁTICO DE NVR\n{'='*60}")
    logging.info(f"Cliente : {cfg['cliente']}\nData    : {data_hoje()}\nPasta   : {pasta_data}\nNVRs    : {len(cfg['nvrs'])}\n{'='*60}")

    inicio = time.time()
    resultados = [processar_nvr(nvr, cfg["senha_encriptacao"], pasta_data) for nvr in cfg["nvrs"]]

    # Salvar Relatório
    arq_relatorio = pasta_data / "relatorio_backup.json"
    arq_relatorio.write_text(json.dumps({"cliente": cfg["cliente"], "data": datetime.now().isoformat(), "resultados": resultados}, indent=4))
    
    # Criar ZIP e Enviar Email
    zip_path = criar_zip(pasta_data, cfg["cliente"], cfg["senha_encriptacao"])
    if zip_path:
        email_enviado = enviar_email(zip_path, cfg["cliente"], resultados, cfg_email)
    
    # Resumo Final
    logging.info(f"\n{'='*60}\nRESULTADO FINAL\n{'='*60}")
    for r in resultados:
        icone = {"OK": "✅", "PARCIAL": "⚠️", "ERRO": "❌"}.get(r["status"])
        logging.info(f"{icone} {r['nome']:<10} {r['status']}")

    logging.info(f"\nTotal: {len(resultados)} | OK: {sum(1 for r in resultados if r['status'] == 'OK')} | Erro: {sum(1 for r in resultados if r['status'] == 'ERRO')}")
    logging.info(f"Tempo: {time.time() - inicio:.2f}s | ZIP: {'✅' if zip_path else '❌'} | E-mail: {'✅' if zip_path and email_enviado else '❌'}")

if __name__ == "__main__":
    main()