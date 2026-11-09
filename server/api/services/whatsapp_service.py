"""Envio de WhatsApp pelo container `whatsapp` (ponte Baileys, conexão por QR code), com o mesmo conteúdo do e-mail.

A ponte fica na rede interna do Docker e é configurada só por variáveis de ambiente (ver config.py):
  WHATSAPP_BRIDGE_KEY   chave compartilhada com o container (sem ela o WhatsApp fica desligado)
  WHATSAPP_BRIDGE_URL   padrão http://whatsapp:3000
  WHATSAPP_INSTANCE     padrão trilan
As rotas de envio da ponte são /message/sendText|sendMedia/{instância}, com a chave no header `apikey`.

Nenhuma função daqui levanta exceção para o chamador: o WhatsApp nunca pode derrubar o envio do e-mail
nem o fechamento da rodada. Falha vira log e retorno False.
"""
import base64
import logging
import time
from typing import List, Optional, Sequence, Tuple

import requests
from sqlalchemy.orm import Session

from config import settings

logger = logging.getLogger("trilan.whatsapp")

TIMEOUT_S = 30
MAX_TENTATIVAS = 3
PAUSA_ENTRE_MENSAGENS_S = 1.0   # espaçamento entre mensagens ao mesmo número (reduz risco de bloqueio do número)
PAUSA_ENTRE_NUMEROS_S = 2.0

# (nome do arquivo, bytes JPEG), o mesmo formato de email_service._collect_offline_images
Imagem = Tuple[str, bytes]


def whatsapp_config() -> Optional[dict]:
    """Configuração da ponte, ou None (sem erro) se `WHATSAPP_BRIDGE_KEY` não estiver definida."""
    url = (settings.WHATSAPP_BRIDGE_URL or "").strip().rstrip("/")
    instancia = (settings.WHATSAPP_INSTANCE or "").strip()
    apikey = (settings.WHATSAPP_BRIDGE_KEY or "").strip()
    if not url or not instancia or not apikey:
        logger.debug("WhatsApp desligado: WHATSAPP_BRIDGE_KEY não definida.")
        return None
    return {"url": url, "instance": instancia, "apikey": apikey}


def _post(cfg: dict, rota: str, corpo: dict, numero: str) -> bool:
    """POST na ponte do WhatsApp com retentativas só para falha de rede/5xx (4xx não adianta repetir)."""
    url = f"{cfg['url']}/message/{rota}/{cfg['instance']}"
    ultimo_erro = None
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            resp = requests.post(url, json=corpo, headers={"apikey": cfg["apikey"]}, timeout=TIMEOUT_S)
            if resp.status_code < 300:
                return True
            ultimo_erro = f"HTTP {resp.status_code}: {resp.text[:200]}"
            if resp.status_code < 500:
                break
        except requests.RequestException as exc:
            ultimo_erro = str(exc)
        logger.warning("[WhatsApp] %s para %s, tentativa %d/%d falhou: %s", rota, numero, tentativa, MAX_TENTATIVAS, ultimo_erro)
        if tentativa < MAX_TENTATIVAS:
            time.sleep(2 * tentativa)
    logger.error("[WhatsApp] Falha definitiva em %s para %s: %s", rota, numero, ultimo_erro)
    return False


def enviar_texto(cfg: dict, numero: str, texto: str) -> bool:
    return _post(cfg, "sendText", {"number": numero, "text": texto}, numero)


def enviar_imagem(cfg: dict, numero: str, nome_arquivo: str, dados: bytes, legenda: str = "") -> bool:
    corpo = {
        "number": numero,
        "mediatype": "image",
        "mimetype": "image/jpeg",
        "caption": legenda,
        "media": base64.b64encode(dados).decode("ascii"),
        "fileName": nome_arquivo,
    }
    return _post(cfg, "sendMedia", corpo, numero)


def enviar_whatsapp(
    db: Session,
    numeros: Optional[Sequence[str]],
    texto: str,
    imagens: Optional[List[Imagem]] = None,
    contexto: str = "",
) -> bool:
    """Envia o texto (e depois as imagens) a cada número. True se o texto chegou a pelo menos um número.

    Sem números ou com o WhatsApp desligado (sem WHATSAPP_BRIDGE_KEY), não faz nada e devolve False. Nunca levanta exceção.
    """
    try:
        destinos = list(dict.fromkeys(n for n in (numeros or []) if n))
        if not destinos:
            return False
        cfg = whatsapp_config()
        if cfg is None:
            return False

        algum_ok = False
        for i, numero in enumerate(destinos):
            if i:
                time.sleep(PAUSA_ENTRE_NUMEROS_S)
            if not enviar_texto(cfg, numero, texto):
                continue
            algum_ok = True
            for nome, dados in imagens or []:
                time.sleep(PAUSA_ENTRE_MENSAGENS_S)
                legenda = nome.rsplit(".", 1)[0]
                if not enviar_imagem(cfg, numero, nome, dados, f"📷 {legenda}"):
                    logger.warning("[WhatsApp] Imagem '%s' não enviada para %s (%s).", nome, numero, contexto)
        if algum_ok:
            logger.info("[WhatsApp] %s enviado para %d número(s).", contexto or "Mensagem", len(destinos))
        return algum_ok
    except Exception:
        logger.exception("[WhatsApp] Erro inesperado ao enviar (%s).", contexto)
        return False
