import io
import zipfile
from typing import List
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from auth import verify_admin_token
from database import get_db
from models import Client, ClientGroup, Backup
from schemas import (
    ClientGroupCreate,
    ClientGroupUpdate,
    ClientGroupResponse,
    ClientResponse,
)
from routers.clients import _to_response as client_to_response, check_client_online
from services.storage_service import get_zip_path

router = APIRouter(prefix="/api/v1/groups", tags=["groups"])


def _compute_health(clients: list) -> str:
    if not clients:
        return "NO_DATA"
    any_backup = any(c.last_backup_at for c in clients)
    if not any_backup:
        return "NO_DATA"
    statuses = [c.last_backup_status for c in clients if c.last_backup_status]
    if not statuses:
        return "NO_DATA"
    if all(s == "OK" for s in statuses):
        return "ALL_OK"
    if all(s == "ERROR" for s in statuses):
        return "ALL_ERROR"
    return "PARTIAL"


def _to_response(group: ClientGroup, db: Session) -> ClientGroupResponse:
    now = datetime.now(timezone.utc)
    clients_resp = [client_to_response(c) for c in group.clients]
    agents_online = sum(1 for c in clients_resp if c.is_online)
    last_backups = [c.last_backup_at for c in group.clients if c.last_backup_at]
    last_backup_at = max(last_backups) if last_backups else None

    # Auto-destravamento de segurança: se a fila está ativa mas o agente atual está offline ou inexistente
    if group.queue_active:
        active_clients = sorted([c for c in group.clients if c.active], key=lambda c: c.queue_order)
        curr_idx = group.queue_current_index if group.queue_current_index is not None else 0
        curr_client = active_clients[curr_idx] if curr_idx < len(active_clients) else None
        
        # Se não há cliente ou o cliente atual da fila está offline:
        if not curr_client or not check_client_online(curr_client):
            group.queue_active = False
            group.queue_current_index = None
            db.commit()

    return ClientGroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        active=group.active,
        backup_hour=group.backup_hour,
        backup_minute=group.backup_minute,
        created_at=group.created_at,
        agents_total=len(group.clients),
        agents_online=agents_online,
        health=_compute_health(group.clients),
        last_backup_at=last_backup_at,
        queue_active=group.queue_active,
        clients=clients_resp,
    )


@router.get("", response_model=List[ClientGroupResponse], dependencies=[Depends(verify_admin_token)])
def list_groups(db: Session = Depends(get_db)):
    groups = db.query(ClientGroup).order_by(ClientGroup.name).all()
    return [_to_response(g, db) for g in groups]


@router.post("", response_model=ClientGroupResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(verify_admin_token)])
def create_group(body: ClientGroupCreate, db: Session = Depends(get_db)):
    group = ClientGroup(
        name=body.name,
        description=body.description,
        active=body.active,
        backup_hour=body.backup_hour,
        backup_minute=body.backup_minute,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return _to_response(group, db)


@router.get("/{group_id}", response_model=ClientGroupResponse, dependencies=[Depends(verify_admin_token)])
def get_group(group_id: UUID, db: Session = Depends(get_db)):
    group = db.query(ClientGroup).filter(ClientGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Unidade não encontrada")
    return _to_response(group, db)


@router.put("/{group_id}", response_model=ClientGroupResponse, dependencies=[Depends(verify_admin_token)])
def update_group(group_id: UUID, body: ClientGroupUpdate, db: Session = Depends(get_db)):
    group = db.query(ClientGroup).filter(ClientGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Unidade não encontrada")

    schedule_changed = (
        (body.backup_hour is not None and body.backup_hour != group.backup_hour) or
        (body.backup_minute is not None and body.backup_minute != group.backup_minute)
    )

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(group, field, value)

    # Propaga horário para todos os agentes do grupo e solicita restart
    if schedule_changed:
        for client in group.clients:
            client.backup_hour = group.backup_hour
            client.backup_minute = group.backup_minute
            client.restart_requested = True

    db.commit()
    db.refresh(group)
    return _to_response(group, db)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(verify_admin_token)])
def delete_group(group_id: UUID, db: Session = Depends(get_db)):
    group = db.query(ClientGroup).filter(ClientGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Unidade não encontrada")
    for client in group.clients:
        client.group_id = None
        client.queue_order = 0
    db.delete(group)
    db.commit()


@router.post("/{group_id}/trigger-backup", dependencies=[Depends(verify_admin_token)])
def trigger_group_backup(group_id: UUID, db: Session = Depends(get_db)):
    """Dispara backup em fila para todos os agentes do grupo (um de cada vez, por ordem queue_order)."""
    group = db.query(ClientGroup).filter(ClientGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Unidade não encontrada")

    active_clients = sorted(
        [c for c in group.clients if c.active],
        key=lambda c: c.queue_order
    )
    if not active_clients:
        raise HTTPException(status_code=400, detail="Nenhum agente ativo nesta unidade")

    # Procura o primeiro agente que esteja ONLINE
    first_online = None
    first_idx = None
    for idx, c in enumerate(active_clients):
        if check_client_online(c):
            first_online = c
            first_idx = idx
            break

    if not first_online:
        raise HTTPException(
            status_code=400,
            detail="Nenhum agente online nesta unidade no momento para iniciar o backup"
        )

    # Inicia fila e dispara o primeiro agente online
    group.queue_active = True
    group.queue_current_index = first_idx
    first_online.backup_requested = True

    from models import AgentLog
    db.add(AgentLog(
        client_id=first_online.id,
        event_type="queue_backup",
        message=f"Backup em fila iniciado pela Unidade '{group.name}'. Posição {first_idx + 1}/{len(active_clients)} ({first_online.name})."
    ))

    db.commit()
    return {
        "status": "ok",
        "message": f"Fila iniciada. Primeiro agente online: {first_online.name}",
        "queue_size": len(active_clients),
    }


@router.post("/{group_id}/cancel-queue", dependencies=[Depends(verify_admin_token)])
def cancel_group_queue(group_id: UUID, db: Session = Depends(get_db)):
    """Cancela e destrava a fila de backup da unidade imediatamente."""
    group = db.query(ClientGroup).filter(ClientGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Unidade não encontrada")

    group.queue_active = False
    group.queue_current_index = None
    for c in group.clients:
        c.backup_requested = False

    db.commit()
    return {"status": "ok", "message": "Fila cancelada com sucesso"}


@router.get("/{group_id}/download-latest", dependencies=[Depends(verify_admin_token)])
def download_group_zip(group_id: UUID, db: Session = Depends(get_db)):
    """Gera e retorna um ZIP agrupado com os backups mais recentes de cada agente."""
    group = db.query(ClientGroup).filter(ClientGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Unidade não encontrada")

    zip_buffer = io.BytesIO()
    found_any = False

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for client in sorted(group.clients, key=lambda c: c.queue_order):
            latest = (
                db.query(Backup)
                .filter(Backup.client_id == client.id, Backup.zip_filename.isnot(None))
                .order_by(Backup.started_at.desc())
                .first()
            )
            if not latest or not latest.zip_filename:
                continue
            date_str = (latest.started_at or latest.created_at).strftime("%d-%m-%Y")
            zip_path = get_zip_path(client.id, client.name, latest.zip_filename, date_str=date_str)
            if not zip_path or not zip_path.exists():
                continue
            safe_name = client.name.replace(" ", "_").replace("/", "_")
            zf.write(str(zip_path), arcname=f"{safe_name}/{latest.zip_filename}")
            found_any = True

    if not found_any:
        raise HTTPException(status_code=404, detail="Nenhum backup disponível para os agentes desta unidade")

    zip_buffer.seek(0)
    safe_group_name = group.name.replace(" ", "_").replace("/", "_")
    date_today = datetime.now().strftime("%d-%m-%Y")
    filename = f"unidade_{safe_group_name}_{date_today}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
