from typing import List, Optional
from uuid import UUID
from datetime import date
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, cast, Date

from auth import Contexto, get_contexto
from database import get_db
from services.escopo import filtrar_por_conta
from models import Backup, Machine
from schemas import BackupResponse, PaginatedBackups
from services.storage_service import get_zip_path, pasta_canonica_da_maquina

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/backups", tags=["backups"])


def _to_response(b: Backup) -> BackupResponse:
    r = BackupResponse.model_validate(b)
    machine = b.machine
    r.machine_name = machine.name if machine else None
    # Cliente atual da máquina (não é histórico do momento do backup)
    if machine is not None and machine.customer is not None:
        r.customer_id = machine.customer.id
        r.customer_name = machine.customer.name
    return r


def _with_machine():
    """Carrega máquina e cliente junto com o backup (evita N+1 em _to_response)."""
    return joinedload(Backup.machine).joinedload(Machine.customer)


@router.get("", response_model=PaginatedBackups)
def list_backups(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    machine_id: Optional[UUID] = None,
    customer_id: Optional[UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
):
    q = db.query(Backup).options(_with_machine())

    if machine_id:
        q = q.filter(Backup.machine_id == machine_id)
    if customer_id:
        # Backups das máquinas que pertencem hoje ao Cliente
        q = q.filter(Backup.machine_id.in_(
            db.query(Machine.id).filter(Machine.customer_id == customer_id)
        ))
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

    if ctx.conta_id is not None:
        q = q.filter(Backup.machine_id.in_(filtrar_por_conta(db.query(Machine.id), Machine.conta_id, ctx)))

    total = q.count()
    items = q.order_by(Backup.started_at.desc()).offset((page - 1) * size).limit(size).all()
    pages = (total + size - 1) // size or 1

    return PaginatedBackups(
        items=[_to_response(b) for b in items],
        total=total,
        page=page,
        pages=pages,
    )


@router.get("/{backup_id}", response_model=BackupResponse)
def get_backup(backup_id: UUID, db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    b = db.query(Backup).options(_with_machine()).filter(Backup.id == backup_id).first()
    if not b or (ctx.conta_id is not None and (not b.machine or b.machine.conta_id != ctx.conta_id)):
        raise HTTPException(status_code=404, detail="Backup not found")
    return _to_response(b)


@router.get("/{backup_id}/download")
def download_backup_zip(
    backup_id: UUID,
    direct_machine: bool = Query(True, description="Download direto do backup da máquina"),
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
):
    """Download do arquivo ZIP do backup individual da máquina.
    Entrega o arquivo original gravado em disco com a senha individual da máquina e o nome da máquina.
    As senhas de máquina e cliente nunca se misturam.
    """
    from services.storage_service import _sanitize_name

    b = db.query(Backup).options(_with_machine()).filter(Backup.id == backup_id).first()
    if not b or (ctx.conta_id is not None and (not b.machine or b.machine.conta_id != ctx.conta_id)):
        raise HTTPException(status_code=404, detail="Backup not found")
    if not b.zip_filename:
        raise HTTPException(status_code=404, detail="ZIP nao disponivel para este backup")

    date_str = (b.started_at or b.created_at).strftime("%d-%m-%Y")
    path = get_zip_path(b.machine_id, b.machine.name, b.zip_filename, date_str=date_str, customer=b.machine.customer)
    if not path:
        search_base = pasta_canonica_da_maquina(b.machine_id, b.machine.name, b.machine.customer)
        logger.error(
            "ZIP nao encontrado em disco. backup_id=%s filename=%s search_base=%s exists=%s",
            backup_id, b.zip_filename, search_base, search_base.exists()
        )
        raise HTTPException(
            status_code=404,
            detail=f"Arquivo ZIP '{b.zip_filename}' nao encontrado no servidor."
        )

    # Garante que o nome do arquivo para download contenha o nome da máquina
    clean_machine = _sanitize_name(b.machine.name) if b.machine else "maquina"
    filename = b.zip_filename
    if filename:
        if clean_machine.lower() not in filename.lower():
            if filename.startswith("backup_"):
                filename = f"backup_{clean_machine}_{filename[7:]}"
            else:
                filename = f"backup_{clean_machine}_{filename}"
    else:
        filename = f"backup_{clean_machine}_{date_str}.zip"

    return FileResponse(path=str(path), filename=filename, media_type="application/zip")


@router.get("/public-download/{backup_id}")
def public_download_backup_zip(backup_id: UUID, db: Session = Depends(get_db)):
    """Public endpoint for downloading a backup ZIP using the backup ID as token."""
    from services.storage_service import _sanitize_name

    b = db.query(Backup).options(_with_machine()).filter(Backup.id == backup_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Backup not found")
    if not b.zip_filename:
        raise HTTPException(status_code=404, detail="ZIP nao disponivel para este backup")

    date_str = (b.started_at or b.created_at).strftime("%d-%m-%Y")
    path = get_zip_path(b.machine_id, b.machine.name, b.zip_filename, date_str=date_str, customer=b.machine.customer)
    if not path:
        raise HTTPException(status_code=404, detail="Arquivo ZIP nao encontrado no servidor.")

    clean_machine = _sanitize_name(b.machine.name) if b.machine else "maquina"
    filename = b.zip_filename
    if filename:
        if clean_machine.lower() not in filename.lower():
            if filename.startswith("backup_"):
                filename = f"backup_{clean_machine}_{filename[7:]}"
            else:
                filename = f"backup_{clean_machine}_{filename}"
    else:
        filename = f"backup_{clean_machine}_{date_str}.zip"

    return FileResponse(path=str(path), filename=filename, media_type="application/zip")


@router.get("/public-run-download/{run_id}")
def public_download_run_zip(run_id: UUID, db: Session = Depends(get_db)):
    """Endpoint público (link do e-mail do Cliente): ZIP unificado da rodada, usando o ID da rodada como token.

    Se o cliente tiver senha configurada, gera ZIP com senha (desencriptando os ZIPs das máquinas).
    Caso contrário, retorna o ZIP sem senha com os ZIPs das máquinas como estão.
    """
    from models import CustomerBackupRun
    from services.backup_runs import build_run_zip, build_client_zip_with_password, iter_file, run_zip_filename
    from services.crypto_service import decrypt as crypto_decrypt

    run = db.query(CustomerBackupRun).filter(CustomerBackupRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Rodada não encontrada")

    # Se o cliente tem senha, gera ZIP do cliente com senha (desencriptando os ZIPs das máquinas)
    customer = run.customer
    if customer and customer.zip_password:
        try:
            client_password = crypto_decrypt(customer.zip_password)
        except Exception:
            raise HTTPException(status_code=500, detail="Erro ao recuperar a senha do cliente.")
        f = build_client_zip_with_password(db, run, client_password)
        if f is None:
            raise HTTPException(status_code=404, detail="Nenhum ZIP disponível nesta rodada")
        return StreamingResponse(
            iter_file(f),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{run_zip_filename(run)}"'},
        )

    # Sem senha: retorna ZIP tradicional (com os ZIPs das máquinas dentro)
    f = build_run_zip(db, run)
    if f is None:
        raise HTTPException(status_code=404, detail="Nenhum ZIP disponível nesta rodada")
    return StreamingResponse(
        iter_file(f),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{run_zip_filename(run)}"'},
    )


@router.post("/{backup_id}/resend-email")
def resend_backup_email(
    backup_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
):
    """Reenvia o relatório de e-mail de um backup já existente."""
    b = db.query(Backup).options(_with_machine()).filter(Backup.id == backup_id).first()
    if not b or (ctx.conta_id is not None and (not b.machine or b.machine.conta_id != ctx.conta_id)):
        raise HTTPException(status_code=404, detail="Backup não encontrado")
    if not b.machine:
        raise HTTPException(status_code=400, detail="Máquina associada ao backup não encontrada")

    date_str = (b.started_at or b.created_at).strftime("%d-%m-%Y")
    zip_path = None
    if b.zip_filename:
        zip_path = get_zip_path(b.machine_id, b.machine.name, b.zip_filename, date_str=date_str, customer=b.machine.customer)

    from services.email_service import send_backup_report
    from config import settings
    from models import AgentLog

    nvr_results = b.nvr_results or []
    email_sent = send_backup_report(
        machine_name=b.machine.name,
        date_str=date_str,
        nvr_results=nvr_results,
        recipients=b.machine.email_to or [],
        db=db,
        zip_path=zip_path,
        backup_id=str(b.id),
        base_url=str(request.base_url),
        public_url=settings.PUBLIC_URL,
        machine_id=b.machine_id,
    )

    b.email_sent = email_sent or b.email_sent

    if email_sent:
        recipients_str = ", ".join(b.machine.email_to) if b.machine.email_to else "destinatários configurados"
        db.add(AgentLog(
            machine_id=b.machine.id,
            event_type="email_sent",
            message=f"Reenvio de e-mail de relatório realizado com sucesso para: {recipients_str}."
        ))
    else:
        recipients_str = ", ".join(b.machine.email_to) if b.machine.email_to else "nenhum destinatário cadastrado"
        db.add(AgentLog(
            machine_id=b.machine.id,
            event_type="email_error",
            nivel="ERROR",
            message=f"Falha no reenvio de e-mail de relatório ({recipients_str}). Verifique configurações SMTP e destinatários."
        ))

    db.commit()

    if not email_sent:
        raise HTTPException(status_code=500, detail="Falha ao reenviar e-mail. Verifique os logs e configurações SMTP.")

    return {"status": "ok", "message": "E-mail reenviado com sucesso!"}
