import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import create_access_token
from config import settings
from database import get_db
from models import Setting
from schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def get_admin_password(db: Session) -> str:
    """Fetch admin password from DB settings or fall back to env var."""
    row = db.query(Setting).filter(Setting.key == "admin_password_hash").first()
    # If stored in settings table (plain for now — bcrypt optional upgrade)
    if row and row.value:
        return row.value
    return settings.ADMIN_PASSWORD


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    admin_pw = get_admin_password(db)
    # Comparação em tempo constante (bytes, para aceitar caracteres não-ASCII)
    if not secrets.compare_digest(body.password.encode(), admin_pw.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong password")
    token = create_access_token({"sub": "admin"})
    return TokenResponse(access_token=token)
