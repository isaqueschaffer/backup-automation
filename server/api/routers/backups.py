from typing import List, Optional
from uuid import UUID
from datetime import date
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, cast, Date

from auth import verify_admin_token
from database import get_db
from models import Backup, Client
from schemas import BackupResponse, PaginatedBackups
from services.storage_service import get_zip_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/backups", tags=["backups"])


def _to_response(b: Backup) -> BackupResponse:
    r = BackupResponse.model_validate(b)
    r.client_name = b.client.name if b.client else None
    return r


@router.get("", response_model=PaginatedBackups, dependencies=[Depends(verify_admin_token)])
def list_backups(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    client_id: Optional[UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Backup).options(joinedload(Backup.client))

    if client_id:
        q = q.filter(Backup.client_id == client_id)
    if status_filter:
        q = q.filter(Backup.status == status_filter.upper())
    if date_from:
        from datetime import datetime, time, timedelta
        # Considera fuso do Brasil (UTC-3)
        # O início do dia no Brasil (00:00:00) equivale a 03:00:00 do mesmo dia em UTC
        start_utc = datetime.combine(date_from, time.min) + timedelta(hours=3)
        q = q.filter(Backup.started_at >= start_utc)
    
    if date_to:
        from datetime import datetime, time, timedelta
        # O fim do dia no Brasil (23:59:59) equivale a 02:59:59 do dia seguinte em UTC
        end_utc = datetime.combine(date_to, time.max) + timedelta(hours=3)
        q = q.filter(Backup.started_at <= end_utc)

    total = q.count()
    items = q.order_by(Backup.started_at.desc()).offset((page - 1) * size).limit(size).all()
    pages = (total + size - 1) // size or 1

    return PaginatedBackups(
        items=[_to_response(b) for b in items],
        total=total,
        page=page,
        pages=pages,
    )


@router.get("/{backup_id}", response_model=BackupResponse, dependencies=[Depends(verify_admin_token)])
def get_backup(backup_id: UUID, db: Session = Depends(get_db)):
    b = db.query(Backup).options(joinedload(Backup.client)).filter(Backup.id == backup_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Backup not found")
    return _to_response(b)


@router.get("/{backup_id}/download", dependencies=[Depends(verify_admin_token)])
def download_backup_zip(backup_id: UUID, db: Session = Depends(get_db)):
    b = db.query(Backup).filter(Backup.id == backup_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Backup not found")
    if not b.zip_filename:
        raise HTTPException(status_code=404, detail="ZIP nao disponivel para este backup")

    date_str = (b.started_at or b.created_at).strftime("%d-%m-%Y")
    path = get_zip_path(b.client_id, b.client.name, b.zip_filename, date_str=date_str)
    if not path:
        from pathlib import Path
        from config import settings
        from services.storage_service import _get_client_dir_name
        search_base = Path(settings.BACKUP_STORAGE_PATH) / _get_client_dir_name(b.client_id, b.client.name)
        logger.error(
            "ZIP nao encontrado em disco. backup_id=%s filename=%s search_base=%s exists=%s",
            backup_id, b.zip_filename, search_base, search_base.exists()
        )
        raise HTTPException(
            status_code=404,
            detail=f"Arquivo ZIP '{b.zip_filename}' nao encontrado no servidor. O backup pode ter sido feito antes da configuracao do armazenamento persistente."
        )

    return FileResponse(path=str(path), filename=b.zip_filename, media_type="application/zip")


@router.get("/public-download/{backup_id}")
def public_download_backup_zip(backup_id: UUID, db: Session = Depends(get_db)):
    """Public endpoint for downloading a backup ZIP using the backup ID as token."""
    b = db.query(Backup).filter(Backup.id == backup_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Backup not found")
    if not b.zip_filename:
        raise HTTPException(status_code=404, detail="ZIP nao disponivel para este backup")

    date_str = (b.started_at or b.created_at).strftime("%d-%m-%Y")
    path = get_zip_path(b.client_id, b.client.name, b.zip_filename, date_str=date_str)
    if not path:
        raise HTTPException(status_code=404, detail="Arquivo ZIP nao encontrado no servidor.")

    return FileResponse(path=str(path), filename=b.zip_filename, media_type="application/zip")

