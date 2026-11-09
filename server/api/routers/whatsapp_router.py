"""WhatsApp pelo painel: conexão por QR code e mensagem de teste, usando o container `whatsapp` (ponte Baileys).

Só o admin global acessa (mesma regra de Configurações). A ponte é configurada por variáveis de ambiente
(`WHATSAPP_BRIDGE_KEY` etc., ver config.py); sem a chave, o WhatsApp fica desligado e `configurado=false`.
"""
import logging

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import verify_admin_token
from services.whatsapp_service import enviar_texto, whatsapp_config
from whatsapp_numero import normalizar_numero

logger = logging.getLogger("trilan.whatsapp")

router = APIRouter(prefix="/api/v1/whatsapp", tags=["whatsapp"], dependencies=[Depends(verify_admin_token)])

TIMEOUT_S = 8


def _ponte(cfg: dict, metodo: str, rota: str):
    """Chama a ponte; devolve a resposta, ou None se ela não responde ou recusa."""
    try:
        resp = requests.request(metodo, f"{cfg['url']}{rota}", headers={"apikey": cfg["apikey"]}, timeout=TIMEOUT_S)
    except requests.RequestException as exc:
        logger.warning("Container do WhatsApp inacessível (%s): %s", rota, exc)
        return None
    return resp if resp.status_code < 300 else None


@router.get("/conexao")
def estado_da_conexao():
    """Estado da sessão: `connected` (e o número) ou o `qr` (PNG em data URL) para conectar.

    `configurado=false`: falta a chave no ambiente. `disponivel=false`: o container não respondeu.
    """
    cfg = whatsapp_config()
    if cfg is None:
        return {"configurado": False, "disponivel": False, "connected": False, "numero": None, "qr": None}
    status = _ponte(cfg, "GET", "/status")
    if status is None:
        return {"configurado": True, "disponivel": False, "connected": False, "numero": None, "qr": None}

    dados = status.json()
    qr = None
    if not dados.get("connected") and dados.get("hasQr"):
        resp_qr = _ponte(cfg, "GET", "/qr")
        qr = resp_qr.json().get("qr") if resp_qr is not None else None
    return {
        "configurado": True,
        "disponivel": True,
        "connected": bool(dados.get("connected")),
        "numero": dados.get("number"),
        "qr": qr,
    }


@router.post("/desconectar")
def desconectar():
    """Desconecta o aparelho e apaga a sessão; a ponte volta a gerar um QR code para conectar outro número."""
    cfg = whatsapp_config()
    if cfg is None or _ponte(cfg, "POST", "/logout") is None:
        raise HTTPException(status_code=502, detail="Não consegui falar com o container do WhatsApp.")
    return {"status": "ok"}


class TesteRequest(BaseModel):
    numero: str


@router.post("/teste")
def enviar_teste(body: TesteRequest):
    """Manda uma mensagem de teste para o número informado, para conferir que a conexão está funcionando."""
    try:
        numero = normalizar_numero(body.numero)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not numero:
        raise HTTPException(status_code=422, detail="Informe o número de WhatsApp para o teste.")
    cfg = whatsapp_config()
    if cfg is None:
        raise HTTPException(status_code=400, detail="WhatsApp desligado: falta definir WHATSAPP_BRIDGE_KEY no servidor.")
    if not enviar_texto(cfg, numero, "✅ Teste de WhatsApp — Trilan Backup. Se você recebeu esta mensagem, a integração está funcionando."):
        raise HTTPException(
            status_code=502,
            detail="Não foi possível enviar. Confira se o número está conectado (QR code) e se o destino tem WhatsApp.",
        )
    return {"status": "ok"}
