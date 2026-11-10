import logging
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload, selectinload

from auth import generate_api_key, Contexto, get_contexto
from database import get_db
from models import Machine, Customer, Backup, AgentLog
from schemas import MachineCreate, MachineUpdate, MachineResponse, MachineWithKey, AgentLogResponse
from services.crypto_service import encrypt
from services.escopo import (
    filtrar_por_conta,
    obter_cliente,
    obter_maquina,
    conta_para_criacao,
)
from services.storage_service import (
    move_machine_to_trash,
    mover_pasta_imagens,
    mover_imagens_para_lixeira,
    pasta_imagens_da_maquina,
)

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


def _get_machine_or_404(machine_id: UUID, db: Session, ctx: Contexto) -> Machine:
    return obter_maquina(db, ctx, machine_id)


def next_queue_order(db: Session, customer_id: UUID, exclude_machine_id: Optional[UUID] = None) -> int:
    """Próxima posição (último + 1) na fila do Cliente."""
    q = db.query(func.max(Machine.queue_order)).filter(Machine.customer_id == customer_id)
    if exclude_machine_id is not None:
        q = q.filter(Machine.id != exclude_machine_id)
    current_max = q.scalar()
    return 0 if current_max is None else current_max + 1


@router.get("", response_model=List[MachineResponse])
def list_machines(
    customer_id: Optional[UUID] = Query(None, description="Só máquinas deste Cliente"),
    unassigned: bool = Query(False, description="Só máquinas sem Cliente"),
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
):
    # Carrega equipamentos e cliente em lote para evitar N+1 em machine_to_response
    q = db.query(Machine).options(selectinload(Machine.equipamentos), joinedload(Machine.customer))
    if customer_id is not None:
        q = q.filter(Machine.customer_id == customer_id)
    if unassigned:
        q = q.filter(Machine.customer_id.is_(None))
    q = filtrar_por_conta(q, Machine.conta_id, ctx)
    machines = q.order_by(Machine.created_at.desc()).all()
    return [machine_to_response(m) for m in machines]


@router.post("", response_model=MachineWithKey, status_code=status.HTTP_201_CREATED)
def create_machine(
    body: MachineCreate,
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
):
    backup_hour, backup_minute = body.backup_hour, body.backup_minute
    queue_order = 0
    customer = None
    if body.customer_id is not None:
        customer = obter_cliente(db, ctx, body.customer_id)
        # Vinculada: herda o horário do Cliente e entra no fim da fila
        backup_hour, backup_minute = customer.backup_hour, customer.backup_minute
        queue_order = next_queue_order(db, customer.id)
        conta_id = customer.conta_id
    else:
        conta_id = conta_para_criacao(db, ctx)

    raw_key, key_hash = generate_api_key()
    machine = Machine(
        conta_id=conta_id,
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


@router.get("/{machine_id}", response_model=MachineResponse)
def get_machine(
    machine_id: UUID,
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
):
    return machine_to_response(_get_machine_or_404(machine_id, db, ctx))


@router.put("/{machine_id}", response_model=MachineResponse)
def update_machine(
    machine_id: UUID,
    body: MachineUpdate,
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
):
    machine = _get_machine_or_404(machine_id, db, ctx)
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

    nome_antigo = machine.name
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

    if machine.name != nome_antigo:
        try:
            mover_pasta_imagens(
                pasta_imagens_da_maquina(machine.customer, nome_antigo),
                pasta_imagens_da_maquina(machine.customer, machine.name),
            )
        except Exception:
            logger.exception("Falha ao mover pasta de imagens da máquina %s após renomear", machine.id)

    return machine_to_response(machine)


@router.delete("/{machine_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_machine(
    machine_id: UUID,
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
):
    machine = _get_machine_or_404(machine_id, db, ctx)

    # Guarda os dados necessários antes do commit (o objeto fica inválido após o delete)
    machine_pk = machine.id
    machine_name = machine.name
    customer_ref = machine.customer

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

    try:
        mover_imagens_para_lixeira(customer_ref, machine_name)
    except Exception:
        logger.exception("Falha ao mover imagens da máquina %s para a lixeira", machine_name)


@router.post("/{machine_id}/rotate-key", response_model=MachineWithKey)
def rotate_api_key(
    machine_id: UUID,
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
):
    machine = _get_machine_or_404(machine_id, db, ctx)
    raw_key, key_hash = generate_api_key()
    machine.api_key_hash = key_hash
    machine.api_key_prefix = raw_key[:16]
    db.commit()
    db.refresh(machine)

    # Atributo temporário para o Pydantic v2 ler a chave em texto puro
    machine.api_key = raw_key
    return machine_to_response(machine, MachineWithKey)


def _flag_all_online(db: Session, flag: str, ctx: Contexto) -> dict:
    """Marca `flag` em todas as máquinas ativas e online; offline ficam de fora."""
    machines = filtrar_por_conta(db.query(Machine).filter(Machine.active == True), Machine.conta_id, ctx).all()
    queued = skipped = 0
    for m in machines:
        if check_machine_online(m):
            setattr(m, flag, True)
            queued += 1
        else:
            skipped += 1
    db.commit()
    return {"queued": queued, "skipped_offline": skipped}


@router.post("/trigger-backup-all")
def trigger_backup_all(
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
):
    """Solicita backup em todas as máquinas online."""
    return _flag_all_online(db, "backup_requested", ctx)


@router.post("/restart-agent-all")
def restart_agent_all(
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
):
    """Solicita reinício do agente em todas as máquinas online."""
    return _flag_all_online(db, "restart_requested", ctx)


@router.post("/{machine_id}/trigger-backup")
def trigger_backup(
    machine_id: UUID,
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
):
    machine = _get_machine_or_404(machine_id, db, ctx)
    machine.backup_requested = True
    db.commit()
    return {"status": "ok", "message": "Backup da máquina solicitado via dashboard"}


@router.post("/{machine_id}/restart-agent")
def request_agent_restart(
    machine_id: UUID,
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
):
    """Solicita o reinício do agente da máquina no próximo ping."""
    machine = _get_machine_or_404(machine_id, db, ctx)
    machine.restart_requested = True
    db.commit()
    return {"queued": True}


def _escapar_like(texto: str) -> str:
    """Escapa caracteres especiais do LIKE SQL (\\, %, _)."""
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/{machine_id}/logs", response_model=List[AgentLogResponse])
def get_machine_logs(
    machine_id: UUID,
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
    limit: int = Query(50, ge=1, le=500),
    incluir_pings: bool = True,
    nivel: Optional[str] = Query(None),
    q: Optional[str] = Query(None, max_length=100),
    equipamento: Optional[str] = Query(None, max_length=255),
):
    _get_machine_or_404(machine_id, db, ctx)
    query_logs = db.query(AgentLog).filter(AgentLog.machine_id == machine_id)
    if not incluir_pings:
        query_logs = query_logs.filter(AgentLog.event_type != "ping")

    if nivel is not None:
        partes = [p.strip().upper() for p in nivel.split(",")]
        partes = [p for p in partes if p]
        if partes:
            validos = {"INFO", "WARNING", "ERROR"}
            if any(p not in validos for p in partes):
                raise HTTPException(status_code=422, detail="Nível inválido")
            query_logs = query_logs.filter(AgentLog.nivel.in_(partes))

    if q:
        q_escapado = _escapar_like(q)
        query_logs = query_logs.filter(AgentLog.message.ilike(f"%{q_escapado}%", escape="\\"))

    if equipamento is not None:
        query_logs = query_logs.filter(AgentLog.equipamento == equipamento)

    return query_logs.order_by(AgentLog.created_at.desc()).limit(limit).all()
