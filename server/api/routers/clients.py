from typing import List
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import verify_admin_token, generate_api_key
from database import get_db
from models import Client, Backup
from schemas import ClientCreate, ClientUpdate, ClientResponse, ClientWithKey, AgentLogResponse
from services.crypto_service import encrypt
from services.storage_service import move_client_to_trash

router = APIRouter(prefix="/api/v1/clients", tags=["clients"])


def check_client_online(client: Client) -> bool:
    if not client.active or not client.last_seen:
        return False
    now = datetime.now(timezone.utc)
    last_seen = client.last_seen
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    diff_seconds = (now - last_seen).total_seconds()
    return diff_seconds < 180


def _to_response(client: Client) -> ClientResponse:
    data = ClientResponse.model_validate(client)
    data.nvr_count = len(client.nvrs)

    # Usa datetime com fuso UTC explícito para compatibilidade
    # total com PostgreSQL (que retorna timestamps timezone-aware)
    now = datetime.now(timezone.utc)
    data.current_server_time = now
    data.is_online = check_client_online(client)

    # Preenche nome do grupo se o agente estiver em uma Unidade
    if getattr(client, 'group', None):
        data.group_name = client.group.name

    return data


@router.get("", response_model=List[ClientResponse], dependencies=[Depends(verify_admin_token)])
def list_clients(db: Session = Depends(get_db)):
    clients = db.query(Client).order_by(Client.created_at.desc()).all()
    return [_to_response(c) for c in clients]


@router.post("", response_model=ClientWithKey, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(verify_admin_token)])
def create_client(body: ClientCreate, db: Session = Depends(get_db)):
    raw_key, key_hash = generate_api_key()
    client = Client(
        name=body.name,
        api_key_hash=key_hash,
        api_key_prefix=raw_key[:16],
        backup_hour=body.backup_hour,
        backup_minute=body.backup_minute,
        zip_password=encrypt(body.zip_password) if body.zip_password else None,
        email_to=body.email_to,
        active=body.active,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    
    # Injeta atributos temporários para o Pydantic v2 ler sem dar erro
    client.nvr_count = 0
    client.api_key = raw_key
    return ClientWithKey.model_validate(client)


@router.get("/{client_id}", response_model=ClientResponse, dependencies=[Depends(verify_admin_token)])
def get_client(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return _to_response(client)


@router.put("/{client_id}", response_model=ClientResponse, dependencies=[Depends(verify_admin_token)])
def update_client(client_id: UUID, body: ClientUpdate, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
        
    time_changed = False
    for field, value in body.model_dump(exclude_none=True).items():
        if field in ("backup_hour", "backup_minute") and getattr(client, field) != value:
            time_changed = True
            
        if field == "zip_password" and value:
            setattr(client, field, encrypt(value))
        else:
            setattr(client, field, value)
            
    if time_changed:
        client.restart_requested = True
        
    db.commit()
    db.refresh(client)
    return _to_response(client)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(verify_admin_token)])
def delete_client(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
        
    # Remove os backups associados no banco para evitar erro de Foreign Key
    db.query(Backup).filter(Backup.client_id == client_id).delete(synchronize_session=False)
    
    # Move a pasta de backups do cliente para a lixeira
    move_client_to_trash(client.id, client.name)
    
    db.delete(client)
    db.commit()


@router.post("/{client_id}/rotate-key", response_model=ClientWithKey,
             dependencies=[Depends(verify_admin_token)])
def rotate_api_key(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    raw_key, key_hash = generate_api_key()
    client.api_key_hash = key_hash
    client.api_key_prefix = raw_key[:16]
    db.commit()
    db.refresh(client)
    
    # Injeta atributos temporários para o Pydantic v2 ler
    client.nvr_count = len(client.nvrs)
    client.api_key = raw_key
    return ClientWithKey.model_validate(client)


def _flag_all_online(db: Session, flag: str) -> dict:
    """Marca `flag` em todos os clientes ativos e online; offline ficam de fora."""
    clients = db.query(Client).filter(Client.active == True).all()
    queued = skipped = 0
    for c in clients:
        if _to_response(c).is_online:
            setattr(c, flag, True)
            queued += 1
        else:
            skipped += 1
    db.commit()
    return {"queued": queued, "skipped_offline": skipped}


@router.post("/trigger-backup-all", dependencies=[Depends(verify_admin_token)])
def trigger_backup_all(db: Session = Depends(get_db)):
    """Solicita backup em todos os clientes online."""
    return _flag_all_online(db, "backup_requested")


@router.post("/restart-agent-all", dependencies=[Depends(verify_admin_token)])
def restart_agent_all(db: Session = Depends(get_db)):
    """Solicita reinício do agente em todos os clientes online."""
    return _flag_all_online(db, "restart_requested")


@router.post("/{client_id}/trigger-backup", dependencies=[Depends(verify_admin_token)])
def trigger_backup(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    client.backup_requested = True
    db.commit()
    return {"status": "ok", "message": "Backup solicitado via dashboard"}

@router.post("/{client_id}/restart-agent", dependencies=[Depends(verify_admin_token)])
def request_agent_restart(client_id: UUID, db: Session = Depends(get_db)):
    """Signal the Windows agent to restart on next ping."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    client.restart_requested = True
    db.commit()
    return {"queued": True}


@router.get("/{client_id}/logs", response_model=List[AgentLogResponse], dependencies=[Depends(verify_admin_token)])
def get_client_logs(client_id: UUID, db: Session = Depends(get_db), limit: int = 50):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    from models import AgentLog
    logs = db.query(AgentLog).filter(AgentLog.client_id == client_id).order_by(AgentLog.created_at.desc()).limit(limit).all()
    return logs

