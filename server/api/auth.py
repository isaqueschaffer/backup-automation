import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Conta, Machine, Usuario
from services.contas import conta_bloqueada

# ──────────────────────────────────────────────────────────────
# JWT (Admin dashboard authentication)
# ──────────────────────────────────────────────────────────────
ALGORITHM = "HS256"
bearer_scheme = HTTPBearer()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_access_token_usuario(usuario: Usuario) -> str:
    return create_access_token({"sub": str(usuario.id), "tv": usuario.token_versao})


@dataclass
class Contexto:
    """Quem está usando o painel e em qual conta. conta_id None só para super admin sem conta escolhida (vê tudo)."""
    usuario_id: Optional[UUID]  # None = admin legado (login só com senha)
    nome: str
    email: Optional[str]
    papel: str  # SUPER_ADMIN | ADMIN | LEITURA
    conta_id: Optional[UUID]
    conta: Optional[Conta]
    somente_leitura: bool

    @property
    def super_admin(self) -> bool:
        return self.papel == "SUPER_ADMIN"

    @property
    def feito_por(self) -> str:
        return self.email or "admin"


def _decodificar(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _montar_contexto(token: str, x_conta_id: Optional[str], db: Session) -> Contexto:
    payload = _decodificar(token)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if sub == "admin":
        usuario_id = None
        nome = "Administrador"
        email = None
        papel = "SUPER_ADMIN"
    else:
        try:
            usuario_uuid = UUID(str(sub))
        except (ValueError, AttributeError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        usuario = db.query(Usuario).filter(Usuario.id == usuario_uuid).first()
        if not usuario or not usuario.ativo or payload.get("tv") != usuario.token_versao:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sessão expirada. Entre novamente.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        usuario_id = usuario.id
        nome = usuario.nome
        email = usuario.email
        papel = usuario.papel

    if papel == "SUPER_ADMIN":
        conta_id = None
        conta = None
        if x_conta_id:
            try:
                conta_uuid = UUID(str(x_conta_id).strip())
            except (ValueError, AttributeError, TypeError):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conta não encontrada",
                )
            conta = db.query(Conta).filter(Conta.id == conta_uuid).first()
            if not conta:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conta não encontrada",
                )
            conta_id = conta.id

        return Contexto(
            usuario_id=usuario_id,
            nome=nome,
            email=email,
            papel="SUPER_ADMIN",
            conta_id=conta_id,
            conta=conta,
            somente_leitura=False,
        )

    # Usuário ADMIN ou LEITURA (ignora X-Conta-ID)
    conta = usuario.conta
    if not conta:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Conta não encontrada",
        )

    somente_leitura = (papel == "LEITURA" or conta_bloqueada(conta))
    return Contexto(
        usuario_id=usuario_id,
        nome=nome,
        email=email,
        papel=papel,
        conta_id=conta.id,
        conta=conta,
        somente_leitura=somente_leitura,
    )


def _bloquear_escrita(request: Request, ctx: Contexto) -> None:
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and ctx.somente_leitura:
        if ctx.conta and conta_bloqueada(ctx.conta):
            detail = "Conta vencida ou suspensa: o painel está em modo somente leitura. Fale com a Trilan para renovar."
        else:
            detail = "Seu usuário tem acesso somente leitura."
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def get_contexto(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    x_conta_id: Optional[str] = Header(None, alias="X-Conta-ID"),
    db: Session = Depends(get_db),
) -> Contexto:
    ctx = _montar_contexto(credentials.credentials, x_conta_id, db)
    _bloquear_escrita(request, ctx)
    return ctx


def get_contexto_sem_bloqueio(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    x_conta_id: Optional[str] = Header(None, alias="X-Conta-ID"),
    db: Session = Depends(get_db),
) -> Contexto:
    return _montar_contexto(credentials.credentials, x_conta_id, db)


def exigir_super_admin(ctx: Contexto = Depends(get_contexto)) -> Contexto:
    if not ctx.super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito ao administrador da plataforma.",
        )
    return ctx


def exigir_admin_conta(ctx: Contexto = Depends(get_contexto)) -> Contexto:
    if not ctx.conta_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selecione uma conta.",
        )
    if ctx.papel != "ADMIN" and not ctx.super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito ao administrador da conta.",
        )
    return ctx


def verify_admin_token(ctx: Contexto = Depends(exigir_super_admin)) -> Contexto:
    """Compatibilidade: rotas ainda não migradas para o escopo por conta aceitam só o super admin."""
    return ctx


bearer_opcional = HTTPBearer(auto_error=False)
PUBLISH_TOKEN_HEADER = APIKeyHeader(name="X-Publish-Token", auto_error=False)


def verify_publish_or_admin(
    publish_token: Optional[str] = Security(PUBLISH_TOKEN_HEADER),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_opcional),
    db: Session = Depends(get_db),
) -> dict:
    """Aceita o token de publicação (X-Publish-Token) ou o admin do painel. Só para registrar versões."""
    esperado = settings.PUBLISH_TOKEN
    if publish_token and esperado:
        if hmac.compare_digest(publish_token.encode(), esperado.encode()):
            return {"sub": "publisher"}
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid publish token")
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    ctx = _montar_contexto(credentials.credentials, None, db)
    if not ctx.super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito ao administrador da plataforma.",
        )
    return {"sub": "admin"}


# ──────────────────────────────────────────────────────────────
# API Key (Agent authentication)
# ──────────────────────────────────────────────────────────────
CLIENT_ID_HEADER = APIKeyHeader(name="X-Client-ID", auto_error=False)
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_api_key() -> tuple[str, str]:
    """Generate a new API key. Returns (raw_key, hashed_key)."""
    raw = "sk_trilan_" + secrets.token_urlsafe(32)
    return raw, hash_api_key(raw)


def get_current_machine(
    client_id: Optional[str] = Security(CLIENT_ID_HEADER),
    api_key: Optional[str] = Security(API_KEY_HEADER),
    db: Session = Depends(get_db),
) -> Machine:
    """Autentica a Máquina pelos headers X-Client-ID / X-API-Key (contrato do agente: não mudar)."""
    if not client_id or not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Client-ID or X-API-Key headers",
        )
    # X-Client-ID que não é UUID válido -> 401 (em vez de erro 500 no banco)
    try:
        machine_uuid = UUID(client_id)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Client not found")

    machine = db.query(Machine).filter(Machine.id == machine_uuid, Machine.active == True).first()
    if not machine:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Client not found")

    # Comparação em tempo constante do hash da API key
    if not hmac.compare_digest(machine.api_key_hash.encode(), hash_api_key(api_key).encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    return machine
