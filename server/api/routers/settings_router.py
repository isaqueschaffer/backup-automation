from typing import Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import verify_admin_token
from database import get_db
from models import Setting
from routers.auth_router import CHAVE_SENHA_ADMIN, gravar_senha_admin
from schemas import SettingsResponse
from services import senhas

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

ALLOWED_KEYS = {"smtp_server", "smtp_port", "smtp_email", "smtp_password", "retention_days"}
# A tela de Configurações manda a NOVA senha do administrador da plataforma (texto) nesta chave. Ela nunca é gravada
# como veio: vira hash bcrypt (routers.auth_router.gravar_senha_admin). Um valor já em formato de hash é recusado,
# para ninguém trocar a senha gravando um hash escolhido por ele. O GET nunca devolve a chave.


@router.get("", response_model=SettingsResponse, dependencies=[Depends(verify_admin_token)])
def get_settings(db: Session = Depends(get_db)):
    rows = {r.key: r.value for r in db.query(Setting).all()}
    return SettingsResponse(
        smtp_server=rows.get("smtp_server"),
        smtp_port=rows.get("smtp_port"),
        smtp_email=rows.get("smtp_email"),
        retention_days=rows.get("retention_days"),
    )


@router.put("", response_model=SettingsResponse, dependencies=[Depends(verify_admin_token)])
def update_settings(body: Dict[str, str], db: Session = Depends(get_db)):
    nova_senha_admin = body.get(CHAVE_SENHA_ADMIN)
    if nova_senha_admin:
        if senhas.eh_hash_bcrypt(nova_senha_admin):
            raise HTTPException(status_code=422, detail="Informe a nova senha, não um hash.")
        try:
            gravar_senha_admin(db, nova_senha_admin)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    for key, value in body.items():
        if key not in ALLOWED_KEYS:
            continue
        row = db.query(Setting).filter(Setting.key == key).first()
        if row:
            row.value = value
        else:
            db.add(Setting(key=key, value=value))
    db.commit()
    rows = {r.key: r.value for r in db.query(Setting).all()}
    return SettingsResponse(
        smtp_server=rows.get("smtp_server"),
        smtp_port=rows.get("smtp_port"),
        smtp_email=rows.get("smtp_email"),
        retention_days=rows.get("retention_days"),
    )
