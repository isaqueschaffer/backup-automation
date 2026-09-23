"""
Agent-facing router.
Windows agent authenticates with X-Client-ID + X-API-Key headers.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Request, Query
from sqlalchemy.orm import Session

from auth import get_current_client
from database import get_db
from models import Client, Backup, NVR
from schemas import (
    AgentConfigResponse,
    AgentEquipamento,
    BackupReportCreate,
    BackupReportResponse,
    PingResponse,
    TIPOS_EQUIPAMENTO,
)
from services.crypto_service import decrypt
from services.storage_service import save_zip
from services.email_service import send_backup_report
from config import settings

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


@router.get("/config", response_model=AgentConfigResponse)
def get_agent_config(client: Client = Depends(get_current_client), db: Session = Depends(get_db)):
    """Return full config needed by the Windows agent."""
    equipamentos = [
        AgentEquipamento(
            tipo=nvr.tipo or "NVR",
            name=nvr.name,
            ip=nvr.ip,
            username=nvr.username,
            password=decrypt(nvr.password),
            config_extra=nvr.config_extra,
        )
        for nvr in client.nvrs
    ]
    zip_pw = decrypt(client.zip_password) if client.zip_password else None
    
    # Update last_seen
    client.last_seen = datetime.utcnow()
    db.commit()
    
    return AgentConfigResponse(
        client_name=client.name,
        backup_hour=client.backup_hour,
        backup_minute=client.backup_minute,
        zip_password=zip_pw,
        equipamentos=equipamentos,
        nvrs=equipamentos,  # alias de compatibilidade
    )


@router.post("/ping", response_model=PingResponse)
def ping_agent(client: Client = Depends(get_current_client), db: Session = Depends(get_db)):
    """Agent heartbeat to mark it as online. Returns restart flag if requested."""
    client.last_seen = datetime.utcnow()
    should_restart = bool(client.restart_requested)
    if should_restart:
        client.restart_requested = False  # Consume the flag — restart only once
    db.commit()
    return PingResponse(status="ok", restart=should_restart)


@router.post("/backup/report", response_model=BackupReportResponse, status_code=201)
def receive_backup_report(
    body: BackupReportCreate,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    """Agent posts the backup result. Server creates a Backup record."""
    backup = Backup(
        client_id=client.id,
        started_at=body.started_at,
        finished_at=body.finished_at,
        status=body.status,
        nvr_results=[r.model_dump() for r in body.nvr_results],
        trigger=body.trigger,
    )
    db.add(backup)

    # Update client last backup info
    client.last_backup_at = body.finished_at
    client.last_backup_status = body.status

    # Update NVRs with latest recording status
    for r in body.nvr_results:
        if r.cameras is not None:
            nvr = db.query(NVR).filter(NVR.client_id == client.id, NVR.name == r.nome).first()
            if nvr:
                nvr.last_recording_status = r.cameras

    db.commit()
    db.refresh(backup)
    return BackupReportResponse(backup_id=backup.id)


@router.post("/backup/upload/{backup_id}")
async def upload_backup_zip(
    backup_id: str,
    request: Request,
    device_type: str = Query("NVR", description="Tipo de equipamento: NVR, OLT, ONU, PABX"),
    file: UploadFile = File(...),
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    """Agent uploads the ZIP file. Server stores it and sends email."""
    backup = db.query(Backup).filter(
        Backup.id == backup_id, Backup.client_id == client.id
    ).first()
    if not backup:
        raise HTTPException(status_code=404, detail="Backup record not found")

    clean_device_type = device_type.strip().upper()
    if clean_device_type not in TIPOS_EQUIPAMENTO and clean_device_type != "MIXED":
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de equipamento inválido: '{clean_device_type}'. Tipos permitidos: {TIPOS_EQUIPAMENTO} ou MIXED",
        )

    date_str = (backup.started_at or datetime.utcnow()).strftime("%d-%m-%Y")
    data = await file.read()

    filename = file.filename or f"backup_{clean_device_type.lower()}_{date_str}.zip"

    zip_path = save_zip(
        client_id=client.id,
        client_name=client.name,
        date_str=date_str,
        device_type=clean_device_type,
        filename=filename,
        data=data,
    )

    backup.zip_filename = zip_path.name
    backup.zip_size = (backup.zip_size or 0) + len(data)
    db.commit()

    # Send email
    nvr_results = backup.nvr_results or []
    
    email_sent = send_backup_report(
        client_name=client.name,
        date_str=date_str,
        nvr_results=nvr_results,
        recipients=client.email_to or [],
        db=db,
        zip_path=zip_path,
        backup_id=backup_id,
        base_url=str(request.base_url),
        public_url=settings.PUBLIC_URL,
    )
    backup.email_sent = email_sent or backup.email_sent
    db.commit()

    return {"status": "ok", "zip_size": len(data), "email_sent": email_sent}
