# -*- coding: utf-8 -*-

"""
Módulo OLT — Backup via VSOL

Realiza:
    1. Login na OLT VSOL
    2. Download do arquivo usrcfg.conf
    3. Validação do arquivo
    4. Salvamento no diretório de destino

Chamado pelo backup_job.py através de:
    processar_olt(equipamento, pasta_data)
"""

import logging
import datetime
from pathlib import Path

import requests
import ssl
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# --------------------------------------------------------
# ADAPTER PARA PERMITIR PROTOCOLOS TLS E CIFRAS LEGADOS DA OLT
# --------------------------------------------------------
class LegacySSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1
        ctx.set_ciphers("DEFAULT@SECLEVEL=0")
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        return super(LegacySSLAdapter, self).init_poolmanager(*args, **kwargs)

# ============================================================
# CONFIGURAÇÃO
# ============================================================

TIMEOUT = 30


# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================

def realizar_backup_vsol(
    equipamento: dict,
    pasta_destino: Path
) -> dict:

    nome = equipamento.get("name", "OLT_desconhecida")
    config_extra = equipamento.get("config_extra") or {}

    ip = (
        equipamento.get("ip")
        or config_extra.get("pasta_origem")
        or config_extra.get("ip")
    )

    usuario = (
        equipamento.get("username")
        or config_extra.get("username")
    )

    senha = (
        equipamento.get("password")
        or config_extra.get("password")
    )

    logging.info(
        f"\n{'=' * 50}\n"
        f"{nome} [OLT/VSOL]\n"
        f"{'=' * 50}"
    )

    # --------------------------------------------------------
    # VALIDA CONFIGURAÇÃO
    # --------------------------------------------------------

    if not ip:
        logging.error(
            f"  [VSOL] IP não informado para {nome}."
        )

        return {
            "nome": nome,
            "status": "ERRO",
            "cameras": None,
        }

    if not usuario:
        logging.error(
            f"  [VSOL] Usuário não informado para {nome}."
        )

        return {
            "nome": nome,
            "status": "ERRO",
            "cameras": None,
        }

    if not senha:
        logging.error(
            f"  [VSOL] Senha não informada para {nome}."
        )

        return {
            "nome": nome,
            "status": "ERRO",
            "cameras": None,
        }

    # --------------------------------------------------------
    # GARANTE PASTA DO EQUIPAMENTO
    # --------------------------------------------------------

    pasta_eq = pasta_destino / nome.replace(" ", "_")

    pasta_eq.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # NOME DO BACKUP
    # --------------------------------------------------------

    agora = datetime.datetime.now()

    nome_arquivo = (
        f"backup_olt_"
        f"{agora.strftime('%Y-%m-%d_%H-%M-%S')}"
        f".conf"
    )

    arquivo_destino = pasta_eq / nome_arquivo

# --------------------------------------------------------
    # URLS
    # --------------------------------------------------------

    protocolo = config_extra.get("protocolo", "https")
    porta = config_extra.get("porta")

    if porta:
        base_url = f"{protocolo}://{ip}:{porta}"
    else:
        base_url = f"{protocolo}://{ip}"

    logging.info(f"   [VSOL] OLT: {ip}")
    logging.info(f"   [VSOL] Iniciando login...")

    # --------------------------------------------------------
    # SESSION COM ADAPTER SSL LEGADO
    # --------------------------------------------------------

    session = requests.Session()
    adapter = LegacySSLAdapter()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.verify = False

    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": f"{base_url}/",
        "Origin": base_url,
    })

# --------------------------------------------------------
    # LOGIN
    # --------------------------------------------------------

    endpoints_login = [
        f"{base_url}/action/login.html",
        f"{base_url}/action/main.html",
        f"{base_url}/login.cgi"
    ]

    login_sucesso = False

    for url in endpoints_login:
        try:
            resposta_login = session.post(
                url,
                data={
                    "user": usuario,
                    "pass": senha,
                    "username": usuario,
                    "password": senha
                },
                timeout=TIMEOUT,
            )

            if resposta_login.status_code == 200 and not ("login_error" in resposta_login.text.lower()):
                login_sucesso = True
                logging.info(f"   [VSOL] Autenticado com sucesso via: {url}")
                break

        except requests.RequestException:
            continue

    if not login_sucesso:
        logging.error("   [VSOL] Falha na autenticação (todas as URLs de login falharam).")
        return {
            "nome": nome,
            "status": "ERRO",
            "cameras": None,
        }

 # --------------------------------------------------------
    # DOWNLOAD DO BACKUP
    # --------------------------------------------------------

    logging.info(f"   [VSOL] Baixando configuração...")

    endpoints_backup = [
        f"{base_url}/usrcfg.conf",
        f"{base_url}/usrcfg.conf?action=download",
        f"{base_url}/action/usrcfg.conf"
    ]

    resposta_backup = None

    for url_backup in endpoints_backup:
        try:
            session.headers.update({"Referer": f"{base_url}/action/main.html"})
            resp = session.get(url_backup, timeout=TIMEOUT)

            # Garante que baixou um arquivo e não a tela de login HTML
            if resp.status_code == 200 and not (b"<html" in resp.content.lower() or b"<!doctype" in resp.content.lower()):
                resposta_backup = resp
                break
        except requests.RequestException:
            continue

    if not resposta_backup:
        logging.error("   [VSOL] Falha ao baixar arquivo de configuração ou sessão expirada.")
        return {
            "nome": nome,
            "status": "ERRO",
            "cameras": None,
        }

    # --------------------------------------------------------
    # VALIDAÇÃO
    # --------------------------------------------------------

    conteudo = resposta_backup.content
    tamanho = len(conteudo)

    if tamanho == 0:
        logging.error(f"   [VSOL] Backup retornou arquivo vazio.")
        return {
            "nome": nome,
            "status": "ERRO",
            "cameras": None,
        }

    # --------------------------------------------------------
    # SALVA BACKUP
    # --------------------------------------------------------

    try:

        with open(
            arquivo_destino,
            "wb"
        ) as arquivo:

            arquivo.write(conteudo)

    except OSError as erro:

        logging.error(
            f"  [VSOL] Erro ao salvar backup: {erro}"
        )

        return {
            "nome": nome,
            "status": "ERRO",
            "cameras": None,
        }

    tamanho_mb = tamanho / (1024 * 1024)

    logging.info(
        f"  [VSOL] Backup realizado com sucesso."
    )

    logging.info(
        f"  [VSOL] Arquivo: "
        f"{arquivo_destino}"
    )

    logging.info(
        f"  [VSOL] Tamanho: "
        f"{tamanho_mb:.2f} MB"
    )

    # --------------------------------------------------------
    # RETORNO PADRONIZADO
    # --------------------------------------------------------

    return {
        "nome": nome,
        "status": "OK",
        "arquivo": nome_arquivo,
        "destino": str(arquivo_destino),
        "tamanho_mb": tamanho_mb,
        "cameras": None,
    }