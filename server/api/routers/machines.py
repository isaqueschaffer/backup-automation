import logging
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload, selectinload

from auth import verify_admin_token, generate_api_key
from database import get_db
from models import Machine, Customer, Backup, AgentLog
from schemas import MachineCreate, MachineUpdate, MachineResponse, MachineWithKey, AgentLogResponse
from services.crypto_service import encrypt
from services.storage_service import move_machine_to_trash

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/machines", tags=["Máquinas"])


def check_machine_online(machine: Machine) -> bool:
    if not machine.active or not machine.last_seen:
        return False
    now = datetime.now(timezone.utc)
    last_seen = machine.last_seen
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    diff_seconds = (now - last_seen).total_seconds()
    return diff_seconds < 180


def machine_to_response(machine: Machine, schema=MachineResponse):
    data = schema.model_validate(machine)
    data.nvr_count = len(machine.equipamentos)

    # Usa datetime com fuso UTC explícito para compatibilidade
    # total com PostgreSQL (que retorna timestamps timezone-aware)
    data.current_server_time = datetime.now(timezone.utc)
    data.is_online = check_machine_online(machine)

    # Máquina vinculada a um Cliente usa o horário do Cliente
    data.schedule_from_customer = machine.customer_id is not None
    # ...e os e-mails do relatório também são os do Cliente (1 e-mail por rodada)
    data.email_from_customer = machine.customer_id is not None
    if machine.customer is not None:
        data.customer_name = machine.customer.name

    return data


def _get_machine_or_404(machine_id: UUID, db: Session) -> Machine:
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Máquina não encontrada")
    return machine


def next_queue_order(db: Session, customer_id: UUID, exclude_machine_id: Optional[UUID] = None) -> int:
    """Próxima posição (último + 1) na fila do Cliente."""
    q = db.query(func.max(Machine.queue_order)).filter(Machine.customer_id == customer_id)
    if exclude_machine_id is not None:
        q = q.filter(Machine.id != exclude_machine_id)
    current_max = q.scalar()
    return 0 if current_max is None else current_max + 1


@router.get("", response_model=List[MachineResponse], dependencies=[Depends(verify_admin_token)])
def list_machines(
    customer_id: Optional[UUID] = Query(None, description="Só máquinas deste Cliente"),
    unassigned: bool = Query(False, description="Só máquinas sem Cliente"),
    db: Session = Depends(get_db),
):
    # Carrega equipamentos e cliente em lote para evitar N+1 em machine_to_response
    q = db.query(Machine).options(selectinload(Machine.equipamentos), joinedload(Machine.customer))
    if customer_id is not None:
        q = q.filter(Machine.customer_id == customer_id)
    if unassigned:
        q = q.filter(Machine.customer_id.is_(None))
    machines = q.order_by(Machine.created_at.desc()).all()
    return [machine_to_response(m) for m in machines]


@router.post("", response_model=MachineWithKey, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(verify_admin_token)])
def create_machine(body: MachineCreate, db: Session = Depends(get_db)):
    backup_hour, backup_minute = body.backup_hour, body.backup_minute
    queue_order = 0
    customer = None
    if body.customer_id is not None:
        customer = db.query(Customer).filter(Customer.id == body.customer_id).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        # Vinculada: herda o horário do Cliente e entra no fim da fila
        backup_hour, backup_minute = customer.backup_hour, customer.backup_minute
        queue_order = next_queue_order(db, customer.id)

    raw_key, key_hash = generate_api_key()
    machine = Machine(
        name=body.name,
        api_key_hash=key_hash,
        api_key_prefix=raw_key[:16],
        backup_hour=backup_hour,
        backup_minute=backup_minute,
        zip_password=encrypt(body.zip_password) if body.zip_password else None,
        email_to=body.email_to,
        active=body.active,
        customer_id=customer.id if customer else None,
        queue_order=queue_order,
    )
    db.add(machine)
    db.commit()
    db.refresh(machine)

    # Atributo temporário para o Pydantic v2 ler a chave em texto puro
    machine.api_key = raw_key
    return machine_to_response(machine, MachineWithKey)


@router.get("/{machine_id}", response_model=MachineResponse, dependencies=[Depends(verify_admin_token)])
def get_machine(machine_id: UUID, db: Session = Depends(get_db)):
    return machine_to_response(_get_machine_or_404(machine_id, db))


@router.put("/{machine_id}", response_model=MachineResponse, dependencies=[Depends(verify_admin_token)])
def update_machine(machine_id: UUID, body: MachineUpdate, db: Session = Depends(get_db)):
    machine = _get_machine_or_404(machine_id, db)
    changes = body.model_dump(exclude_none=True)

    # Máquina vinculada: o horário é definido pelo Cliente
    if machine.customer is not None and (
        ("backup_hour" in changes and changes["backup_hour"] != machine.backup_hour) or
        ("backup_minute" in changes and changes["backup_minute"] != machine.backup_minute)
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Horário definido pelo cliente {machine.customer.name}. Altere no cliente.",
        )

    # Máquina vinculada: os e-mails do relatório são definidos pelo Cliente
    if machine.customer is not None and "email_to" in changes and list(changes["email_to"]) != list(machine.email_to or []):
        raise HTTPException(
            status_code=400,
            detail=f"E-mails definidos pelo cliente {machine.customer.name}. Altere no cliente.",
        )

    time_changed = False
    for field, value in changes.items():
        if field in ("backup_hour", "backup_minute") and getattr(machine, field) != value:
            time_changed = True

        if field == "zip_password":
            setattr(machine, field, encrypt(value.strip()) if (value and value.strip()) else None)
        else:
            setattr(machine, field, value)

    if time_changed:
        machine.restart_requested = True

    db.commit()
    db.refresh(machine)
    return machine_to_response(machine)


@router.delete("/{machine_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(verify_admin_token)])
def delete_machine(machine_id: UUID, db: Session = Depends(get_db)):
    machine = _get_machine_or_404(machine_id, db)

    # Guarda os dados necessários antes do commit (o objeto fica inválido após o delete)
    machine_pk = machine.id
    machine_name = machine.name

    # Remove os backups associados no banco para evitar erro de Foreign Key
    db.query(Backup).filter(Backup.machine_id == machine_id).delete(synchronize_session=False)

    db.delete(machine)
    db.commit()

    # Move a pasta de backups para a lixeira somente DEPOIS do commit do banco:
    # se o commit falhar, os arquivos permanecem no lugar.
    try:
        move_machine_to_trash(machine_pk, machine_name)
    except Exception:
        logger.exception("Máquina %s removida do banco, mas falhou ao mover os arquivos para a lixeira", machine_pk)


@router.post("/{machine_id}/rotate-key", response_model=MachineWithKey,
             dependencies=[Depends(verify_admin_token)])
def rotate_api_key(machine_id: UUID, db: Session = Depends(get_db)):
    machine = _get_machine_or_404(machine_id, db)
    raw_key, key_hash = generate_api_key()
    machine.api_key_hash = key_hash
    machine.api_key_prefix = raw_key[:16]
    db.commit()
    db.refresh(machine)

    # Atributo temporário para o Pydantic v2 ler a chave em texto puro
    machine.api_key = raw_key
    return machine_to_response(machine, MachineWithKey)


def _flag_all_online(db: Session, flag: str) -> dict:
    """Marca `flag` em todas as máquinas ativas e online; offline ficam de fora."""
    machines = db.query(Machine).filter(Machine.active == True).all()
    queued = skipped = 0
    for m in machines:
        if check_machine_online(m):
            setattr(m, flag, True)
            queued += 1
        else:
            skipped += 1
    db.commit()
    return {"queued": queued, "skipped_offline": skipped}


@router.post("/trigger-backup-all", dependencies=[Depends(verify_admin_token)])
def trigger_backup_all(db: Session = Depends(get_db)):
    """Solicita backup em todas as máquinas online."""
    return _flag_all_online(db, "backup_requested")


@router.post("/restart-agent-all", dependencies=[Depends(verify_admin_token)])
def restart_agent_all(db: Session = Depends(get_db)):
    """Solicita reinício do agente em todas as máquinas online."""
    return _flag_all_online(db, "restart_requested")


@router.post("/{machine_id}/trigger-backup", dependencies=[Depends(verify_admin_token)])
def trigger_backup(machine_id: UUID, db: Session = Depends(get_db)):
    machine = _get_machine_or_404(machine_id, db)
    machine.backup_requested = True
    db.commit()
    return {"status": "ok", "message": "Backup da máquina solicitado via dashboard"}


@router.post("/{machine_id}/restart-agent", dependencies=[Depends(verify_admin_token)])
def request_agent_restart(machine_id: UUID, db: Session = Depends(get_db)):
    """Solicita o reinício do agente da máquina no próximo ping."""
    machine = _get_machine_or_404(machine_id, db)
    machine.restart_requested = True
    db.commit()
    return {"queued": True}


@router.get("/{machine_id}/logs", response_model=List[AgentLogResponse], dependencies=[Depends(verify_admin_token)])
def get_machine_logs(machine_id: UUID, db: Session = Depends(get_db), limit: int = 50):
    _get_machine_or_404(machine_id, db)
    return (
        db.query(AgentLog)
        .filter(AgentLog.machine_id == machine_id)
        .order_by(AgentLog.created_at.desc())
        .limit(limit)
        .all()
    )
