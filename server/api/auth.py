import hashlib
import hmac
import secrets
from uuid import UUID
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Client

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


def verify_admin_token(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> dict:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("sub") != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not admin")
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


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


def get_current_client(
    client_id: Optional[str] = Security(CLIENT_ID_HEADER),
    api_key: Optional[str] = Security(API_KEY_HEADER),
    db: Session = Depends(get_db),
) -> Client:
    if not client_id or not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Client-ID or X-API-Key headers",
        )
    # X-Client-ID que não é UUID válido -> 401 (em vez de erro 500 no banco)
    try:
        client_uuid = UUID(client_id)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Client not found")

    client = db.query(Client).filter(Client.id == client_uuid, Client.active == True).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Client not found")

    # Comparação em tempo constante do hash da API key
    if not hmac.compare_digest(client.api_key_hash.encode(), hash_api_key(api_key).encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    return client
