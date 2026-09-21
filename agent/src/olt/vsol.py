"""
Módulo OLT — Backup via VSOL

Suporta:
- VSOL real
- Servidor Flask de teste da VSOL
- HTTP e HTTPS
- Login via /action/login.html
- Sessão/cookies
- Download de /action/usrcfg.conf
- Validação do arquivo baixado
- Salvamento do backup no diretório do agente

Fluxo:
1. Obtém IP, porta, protocolo, usuário e senha
2. Cria uma requests.Session()
3. Faz login na OLT
4. Preserva os cookies da sessão
5. Acessa /action/usrcfg.conf
6. Valida se o retorno é realmente um arquivo de configuração
7. Salva o .conf
"""

import datetime
import logging
from pathlib import Path
import ssl
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# ============================================================
# CONFIGURAÇÕES
# ============================================================

TIMEOUT = 30

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============================================================
# ADAPTER SSL LEGADO
# ============================================================

class LegacySSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()

        try:
            ctx.minimum_version = ssl.TLSVersion.TLSv1
        except Exception:
            pass

        try:
            ctx.set_ciphers("DEFAULT@SECLEVEL=0")
        except Exception:
            pass

        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        kwargs["ssl_context"] = ctx

        return super().init_poolmanager(*args, **kwargs)


# ============================================================
# AUXILIARES
# ============================================================

def _obter_config_extra(equipamento: dict) -> dict:
    config_extra = equipamento.get("config_extra") or {}

    if isinstance(config_extra, str):
        try:
            import json
            config_extra = json.loads(config_extra)
        except Exception:
            logging.warning("[VSOL] Não foi possível interpretar config_extra.")
            config_extra = {}

    if not isinstance(config_extra, dict):
        config_extra = {}

    return config_extra


def _montar_base_url(ip: str, config_extra: dict) -> str:
    protocolo = (config_extra.get("protocolo") or "http").strip().lower()
    porta = config_extra.get("porta")

    # Permite informar IP já com protocolo.
    if ip.startswith("http://") or ip.startswith("https://"):
        base_url = ip.rstrip("/")

        # Se o IP já possui protocolo e porta, não adiciona outra porta.
        if porta:
            parsed = urlparse(base_url)
            if not parsed.port:
                base_url = f"{parsed.scheme}://{parsed.hostname}:{porta}"

        return base_url

    if porta:
        return f"{protocolo}://{ip}:{porta}"

    return f"{protocolo}://{ip}"


def _parece_html(conteudo: bytes) -> bool:
    """Verifica se o conteúdo retornado parece ser uma página HTML."""
    if not conteudo:
        return False

    inicio = conteudo[:4096].lower()

    indicadores = (
        b"<html",
        b"<!doctype",
        b"<head",
        b"<body",
        b"<title",
    )

    return any(indicador in inicio for indicador in indicadores)


def _parece_config(conteudo: bytes) -> bool:
    """Validação básica do arquivo de configuração.

    O objetivo principal é evitar salvar uma página HTML, página de login ou
    mensagem de erro com extensão .conf.
    """
    if not conteudo:
        return False

    if _parece_html(conteudo):
        return False

    # Arquivos muito pequenos provavelmente são respostas de erro ou mensagens inválidas.
    if len(conteudo) < 20:
        return False

    return True


def _mostrar_cookies(session: requests.Session) -> None:
    """Mostra no log os cookies obtidos após o login.

    Não registra valores das credenciais.
    """
    try:
        cookies = session.cookies.get_dict()
        if cookies:
            logging.info("[VSOL] Cookies da sessão: " + ", ".join(cookies.keys()))
        else:
            logging.info("[VSOL] Nenhum cookie retornado pela OLT.")
    except Exception:
        logging.debug("[VSOL] Não foi possível listar cookies.")


# ============================================================
# LOGIN
# ============================================================

def _fazer_login(
    session: requests.Session,
    base_url: str,
    usuario: str,
    senha: str
) -> bool:
    endpoints_login = [
        "/action/login.html",
        "/action/main.html",
        "/login.cgi",
        "/login.html",
    ]

    # Campos utilizados por diferentes versões/interfaces VSOL.
    dados_login = {
        "user": usuario,
        "pass": senha,
        "username": usuario,
        "password": senha,
    }

    for endpoint in endpoints_login:
        url = urljoin(base_url.rstrip("/") + "/", endpoint.lstrip("/"))

        try:
            logging.info(f"   [VSOL] Tentando login: {url}")

            resposta = session.post(
                url,
                data=dados_login,
                timeout=TIMEOUT,
                allow_redirects=False,
            )

            logging.info(f"   [VSOL] Login HTTP {resposta.status_code}")

            location = resposta.headers.get("Location", "")
            if location:
                logging.info(f"   [VSOL] Redirect: {location}")

            texto = resposta.text[:10000].lower() if resposta.text else ""

            # Caso 1: HTTP 302 é o comportamento esperado após login no Flask/Server
            if resposta.status_code in (301, 302, 303, 307, 308):
                if (
                    "login_error" not in texto
                    and "invalid" not in texto
                    and "incorrect" not in texto
                ):
                    logging.info(f"   [VSOL] Login aceito via: {url}")
                    _mostrar_cookies(session)
                    return True

            # Caso 2: Algumas versões podem retornar HTTP 200.
            if resposta.status_code == 200:
                if (
                    "login_error" not in texto
                    and "invalid" not in texto
                    and "incorrect" not in texto
                    and "wrong password" not in texto
                ):
                    # Verifica se a resposta parece ser uma página de login persistente.
                    indicadores_login = ("login", "password", "senha")
                    possui_tela_login = all(
                        palavra in texto for palavra in indicadores_login
                    )

                    if not possui_tela_login:
                        logging.info(f"   [VSOL] Login aceito via: {url}")
                        _mostrar_cookies(session)
                        return True

            logging.warning(f"   [VSOL] Login não confirmado via {url}.")

        except requests.RequestException as erro:
            logging.warning(f"   [VSOL] Falha ao acessar {url}: {erro}")

    logging.error("   [VSOL] Falha na autenticação (todas as URLs falharam).")
    return False


# ============================================================
# DOWNLOAD DO BACKUP
# ============================================================

def _baixar_backup(session: requests.Session, base_url: str):
    """Tenta baixar o arquivo de configuração da VSOL.

    Retorna requests.Response ou None.
    """
    endpoints_backup = [
        "/action/usrcfg.conf",
        "/usrcfg.conf",
        "/usrcfg.conf?action=download",
    ]

    for endpoint in endpoints_backup:
        url = urljoin(base_url.rstrip("/") + "/", endpoint.lstrip("/"))

        try:
            logging.info(f"   [VSOL] Tentando download: {url}")

            session.headers.update({"Referer": f"{base_url}/action/main.html"})

            resposta = session.get(
                url,
                timeout=TIMEOUT,
                allow_redirects=True,
            )

            logging.info(
                f"   [VSOL] Download HTTP {resposta.status_code} "
                f"({len(resposta.content)} bytes)"
            )

            if resposta.status_code != 200:
                continue

            conteudo = resposta.content

            # Não aceitar página HTML como backup.
            if _parece_html(conteudo):
                logging.warning(
                    "   [VSOL] Resposta parece ser HTML; "
                    "provavelmente sessão não autenticada."
                )
                continue

            # Validação mínima do arquivo.
            if not _parece_config(conteudo):
                logging.warning(
                    "   [VSOL] Conteúdo retornado não parece "
                    "ser um arquivo .conf válido."
                )
                continue

            return resposta

        except requests.RequestException as erro:
            logging.warning(f"   [VSOL] Erro no download {url}: {erro}")

    return None


# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================

def realizar_backup_vsol(equipamento: dict, pasta_destino: Path) -> dict:
    nome = equipamento.get("name", "OLT_desconhecida")
    config_extra = _obter_config_extra(equipamento)

    # Extração de parâmetros
    ip = (
        equipamento.get("ip")
        or config_extra.get("ip")
        or config_extra.get("host")
    )
    usuario = (
        equipamento.get("username")
        or config_extra.get("username")
        or config_extra.get("usuario")
    )
    senha = (
        equipamento.get("password")
        or config_extra.get("password")
        or config_extra.get("senha")
    )

    logging.info(f"\n{'=' * 50}\n{nome} [OLT/VSOL]\n{'=' * 50}")

    # Validações
    if not ip:
        logging.error(f"   [VSOL] IP não informado para {nome}.")
        return {"nome": nome, "status": "ERRO", "cameras": None}

    if not usuario:
        logging.error(f"   [VSOL] Usuário não informado para {nome}.")
        return {"nome": nome, "status": "ERRO", "cameras": None}

    if not senha:
        logging.error(f"   [VSOL] Senha não informada para {nome}.")
        return {"nome": nome, "status": "ERRO", "cameras": None}

    # Diretório e Arquivo de Destino
    pasta_eq = pasta_destino
    pasta_eq.mkdir(parents=True, exist_ok=True)

    agora = datetime.datetime.now()
    nome_arquivo = f"backup_olt_{agora.strftime('%Y-%m-%d_%H-%M-%S')}.conf"
    arquivo_destino = pasta_eq / nome_arquivo

    base_url = _montar_base_url(str(ip), config_extra)

    logging.info(f"   [VSOL] OLT: {base_url}")
    logging.info(f"   [VSOL] Usuário: {usuario}")
    logging.info("   [VSOL] Iniciando login...")

    # Sessão HTTP
    session = requests.Session()
    adapter = LegacySSLAdapter()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.verify = False

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/153.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": f"{base_url}/",
        "Origin": base_url,
    })

    # Autenticação
    login_sucesso = _fazer_login(session, base_url, usuario, senha)
    if not login_sucesso:
        return {"nome": nome, "status": "ERRO", "cameras": None}

    # Download
    logging.info("   [VSOL] Login concluído.")
    logging.info("   [VSOL] Baixando configuração...")

    resposta_backup = _baixar_backup(session, base_url)
    if resposta_backup is None:
        logging.error("   [VSOL] Falha ao baixar arquivo de configuração.")
        return {"nome": nome, "status": "ERRO", "cameras": None}

    conteudo = resposta_backup.content
    tamanho = len(conteudo)

    if tamanho == 0:
        logging.error("   [VSOL] Backup retornou arquivo vazio.")
        return {"nome": nome, "status": "ERRO", "cameras": None}

    if not _parece_config(conteudo):
        logging.error("   [VSOL] Conteúdo baixado não passou na validação.")
        return {"nome": nome, "status": "ERRO", "cameras": None}

    # Salvamento
    try:
        with open(arquivo_destino, "wb") as arquivo:
            arquivo.write(conteudo)
    except OSError as erro:
        logging.error(f"   [VSOL] Erro ao salvar backup: {erro}")
        return {"nome": nome, "status": "ERRO", "cameras": None}

    tamanho_mb = tamanho / (1024 * 1024)
    logging.info("   [VSOL] Backup realizado com sucesso.")
    logging.info(f"   [VSOL] Arquivo: {arquivo_destino}")
    logging.info(f"   [VSOL] Tamanho: {tamanho_mb:.2f} MB")

    return {"nome": nome, "status": "OK", "cameras": None}