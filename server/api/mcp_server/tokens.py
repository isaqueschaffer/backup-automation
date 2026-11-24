"""Tokens do MCP: geração, hash e validação. Só o SHA-256 vai para o banco (tabela mcp_tokens)."""
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

from fastapi import Request
from sqlalchemy.orm import Session

from config import settings
from models import McpToken, Usuario

# Quem pode conectar uma IA (decisão de 24/11/2026): administradores da plataforma e das contas
PAPEIS_MCP = ("SUPER_ADMIN", "ADMIN")

PREFIXO_PESSOAL = "trilan_mcp_"
PREFIXO_ACCESS = "trilan_oat_"
PREFIXO_REFRESH = "trilan_ort_"

ACCESS_VALIDADE = timedelta(hours=1)
REFRESH_VALIDADE = timedelta(days=90)


def hash_token(bruto: str) -> str:
    return hashlib.sha256(bruto.encode()).hexdigest()


def gerar(prefixo: str) -> Tuple[str, str]:
    """(token bruto, hash)."""
    bruto = prefixo + secrets.token_urlsafe(32)
    return bruto, hash_token(bruto)


def usuario_pode_usar_mcp(usuario: Optional[Usuario]) -> bool:
    return bool(usuario and usuario.ativo and usuario.papel in PAPEIS_MCP)


def validar_access(db: Session, bruto: str) -> Optional[Tuple[McpToken, Usuario]]:
    """Token pessoal ou access OAuth válido -> (registro, usuário). Atualiza o último uso (no máximo 1x/min)."""
    if not bruto or not (bruto.startswith(PREFIXO_PESSOAL) or bruto.startswith(PREFIXO_ACCESS)):
        return None
    tok = db.query(McpToken).filter(McpToken.token_hash == hash_token(bruto)).first()
    agora = datetime.utcnow()
    if not tok or tok.revogado or (tok.expira_em is not None and tok.expira_em < agora):
        return None
    usuario = db.query(Usuario).filter(Usuario.id == tok.usuario_id).first()
    if not usuario_pode_usar_mcp(usuario) or usuario.token_versao != tok.token_versao:
        return None
    if tok.ultimo_uso is None or agora - tok.ultimo_uso > timedelta(minutes=1):
        tok.ultimo_uso = agora
        db.commit()
    return tok, usuario


def base_url(request: Request) -> str:
    """Endereço público da API (para os metadados OAuth e o endereço do MCP)."""
    if settings.MCP_BASE_URL:
        return settings.MCP_BASE_URL.rstrip("/")
    proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host.split(',')[0].strip()}"
