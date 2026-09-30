"""
OTA Update router.
- GET  /api/v1/agent/update-check    → chamado pelo agente no Ping para verificar se há nova versão
- POST /api/v1/admin/agent-version   → admin registra uma nova versão (URL do GitHub Release + hash)
- GET  /api/v1/admin/agent-version   → admin lista versões cadastradas
- PUT  /api/v1/admin/agent-version/{version_id}/toggle → ativa/desativa uma versão
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_client, verify_admin_token
from database import get_db
from models import AgentVersion, Client
from schemas import AgentVersionCreate, AgentVersionResponse, UpdateCheckResponse

# ── Router para o agente (autenticado por X-Client-ID + X-API-Key) ──────────
agent_router = APIRouter(prefix="/api/v1/agent", tags=["agent-update"])

# ── Router para o admin (autenticado por Bearer token) ───────────────────────
admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin-update"])


@agent_router.get("/update-check", response_model=UpdateCheckResponse)
def check_for_update(
    current_version: str = "0.0.0",
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    """
    O agente envia sua versão atual como query param e recebe instruções de atualização.
    Exemplo: GET /api/v1/agent/update-check?current_version=1.0.0
    """
    latest = (
        db.query(AgentVersion)
        .filter(AgentVersion.active == True)
        .order_by(AgentVersion.created_at.desc())
        .first()
    )

    if not latest:
        return UpdateCheckResponse(has_update=False)

    # Compara versões semânticas (simples split em ints)
    def _parse(v: str):
        try:
            return tuple(int(x) for x in v.strip().split("."))
        except Exception:
            return (0, 0, 0)

    if _parse(latest.version) > _parse(current_version):
        return UpdateCheckResponse(
            has_update=True,
            version=latest.version,
            url_service=latest.url_service,
            url_tray=latest.url_tray,
            sha256_service=latest.sha256_service,
            sha256_tray=latest.sha256_tray,
            notes=latest.notes,
        )

    return UpdateCheckResponse(has_update=False)


# ── Admin endpoints ───────────────────────────────────────────────────────────

@admin_router.post(
    "/agent-version",
    response_model=AgentVersionResponse,
    status_code=201,
    dependencies=[Depends(verify_admin_token)],
)
def register_version(body: AgentVersionCreate, db: Session = Depends(get_db)):
    """Registra uma nova versão do agente (URL do GitHub Release + SHA256)."""
    existing = db.query(AgentVersion).filter(AgentVersion.version == body.version).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Versão {body.version} já cadastrada.")

    version = AgentVersion(
        version=body.version,
        notes=body.notes,
        url_service=body.url_service,
        url_tray=body.url_tray,
        sha256_service=body.sha256_service.lower(),
        sha256_tray=body.sha256_tray.lower() if body.sha256_tray else None,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


@admin_router.get(
    "/agent-version",
    response_model=List[AgentVersionResponse],
    dependencies=[Depends(verify_admin_token)],
)
def list_versions(db: Session = Depends(get_db)):
    """Lista todas as versões registradas, mais recentes primeiro."""
    return db.query(AgentVersion).order_by(AgentVersion.created_at.desc()).all()


@admin_router.put(
    "/agent-version/{version_id}/toggle",
    response_model=AgentVersionResponse,
    dependencies=[Depends(verify_admin_token)],
)
def toggle_version(version_id: UUID, db: Session = Depends(get_db)):
    """Ativa ou desativa uma versão (rollback de emergência)."""
    version = db.query(AgentVersion).filter(AgentVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Versão não encontrada.")
    version.active = not version.active
    db.commit()
    db.refresh(version)
    return version

@admin_router.delete(
    "/agent-version/{version_id}",
    dependencies=[Depends(verify_admin_token)],
)
def delete_version(version_id: UUID, db: Session = Depends(get_db)):
    """Deleta uma versão."""
    version = db.query(AgentVersion).filter(AgentVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Versão não encontrada.")
    db.delete(version)
    db.commit()
    return {"status": "ok"}
