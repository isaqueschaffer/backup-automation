import hashlib
import logging
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Deque, Dict, Optional

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from models import CustomerDashboard

logger = logging.getLogger(__name__)

PREFIXO_TOKEN = "dsh_"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def gerar_token() -> tuple:
    """Retorna (token em texto puro, hash para gravar). 256 bits aleatórios, imprevisível."""
    bruto = PREFIXO_TOKEN + secrets.token_urlsafe(32)
    return bruto, hash_token(bruto)


class LimitadorJanela:
    """Limite de eventos por chave numa janela deslizante (em memória: vale para 1 worker uvicorn)."""

    def __init__(self, maximo: int, janela_s: int):
        self.maximo = maximo
        self.janela_s = janela_s
        self._eventos: Dict[str, Deque[float]] = defaultdict(deque)
        self._trava = threading.Lock()

    def _podar(self, fila: Deque[float], agora: float) -> None:
        while fila and agora - fila[0] > self.janela_s:
            fila.popleft()

    def disponivel(self, chave: str) -> bool:
        """True se a chave ainda não atingiu o máximo (não registra evento)."""
        agora = time.monotonic()
        with self._trava:
            fila = self._eventos[chave]
            self._podar(fila, agora)
            return len(fila) < self.maximo

    def registrar(self, chave: str) -> None:
        agora = time.monotonic()
        with self._trava:
            fila = self._eventos[chave]
            self._podar(fila, agora)
            fila.append(agora)
            if len(self._eventos) > 5000:  # limpeza esporádica de chaves ociosas
                for k in [k for k, f in self._eventos.items() if not f or agora - f[-1] > self.janela_s]:
                    self._eventos.pop(k, None)


# Requisições por IP e tentativas com token inválido por IP
limite_requisicoes = LimitadorJanela(maximo=240, janela_s=60)
limite_falhas = LimitadorJanela(maximo=10, janela_s=300)


def ip_do_cliente(request: Request) -> str:
    """IP de origem: último salto de X-Forwarded-For (o do proxy mais próximo) ou o do socket."""
    encaminhado = request.headers.get("x-forwarded-for", "")
    if encaminhado:
        return encaminhado.split(",")[-1].strip() or "desconhecido"
    return request.client.host if request.client else "desconhecido"


@dataclass
class AcessoDashboard:
    dashboard: CustomerDashboard
    pode_editar: bool


def acesso_publico(
    request: Request,
    x_dashboard_token: Optional[str] = Header(None, alias="X-Dashboard-Token"),
    db: Session = Depends(get_db),
) -> AcessoDashboard:
    """Autoriza o acesso público pelo token do link. Qualquer falha devolve o mesmo 404 genérico."""
    ip = ip_do_cliente(request)
    limite_requisicoes.registrar(ip)
    if not limite_requisicoes.disponivel(ip) or not limite_falhas.disponivel(ip):
        raise HTTPException(status_code=429, detail="Muitas requisições. Tente novamente em alguns minutos.")

    dashboard = None
    token = (x_dashboard_token or "").strip()
    if 20 <= len(token) <= 200:
        dashboard = db.query(CustomerDashboard).filter(
            CustomerDashboard.share_token_hash == hash_token(token)
        ).first()

    agora = datetime.utcnow()
    valido = (
        dashboard is not None
        and dashboard.share_enabled
        and (dashboard.share_expires_at is None or dashboard.share_expires_at > agora)
        and dashboard.customer is not None
        and dashboard.customer.active
    )
    if not valido:
        limite_falhas.registrar(ip)
        raise HTTPException(status_code=404, detail="Link inválido ou expirado.")

    if dashboard.last_viewed_at is None or agora - dashboard.last_viewed_at > timedelta(minutes=1):
        dashboard.last_viewed_at = agora
        db.commit()
    return AcessoDashboard(dashboard=dashboard, pode_editar=bool(dashboard.share_allow_edit))
