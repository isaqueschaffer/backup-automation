import io
import zipfile
import tempfile
from typing import List
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, selectinload

from auth import verify_admin_token
from database import get_db
from models import Machine, Customer, Backup, AgentLog, CustomerBackupRun
from schemas import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerQueueOrder,
    CustomerRunResponse,
)
from routers.machines import machine_to_response, check_machine_online, next_queue_order
from services.storage_service import get_zip_path
from services.backup_runs import (
    build_run_zip,
    close_queue_run_on_cancel,
    iter_file,
    open_queue_run,
    run_to_dict,
    run_zip_filename,
    send_run_email,
)

router = APIRouter(prefix="/api/v1/clients", tags=["Clientes"])

QUEUE_ACTIVE_DETAIL = "Fila de backup do cliente {name} em andamento. Aguarde a conclusão ou cancele a fila."


def _compute_health(machines: list) -> str:
    if not machines:
        return "NO_DATA"
    any_backup = any(m.last_backup_at for m in machines)
    if not any_backup:
        return "NO_DATA"
    statuses = [m.last_backup_status for m in machines if m.last_backup_status]
    if not statuses:
        return "NO_DATA"
    if all(s == "OK" for s in statuses):
        return "ALL_OK"
    if all(s == "ERROR" for s in statuses):
        return "ALL_ERROR"
    return "PARTIAL"


def _load_customers_query(db: Session):
    """Query de clientes com máquinas e equipamentos carregados em lote (evita N+1)."""
    return db.query(Customer).options(
        selectinload(Customer.machines).selectinload(Machine.equipamentos)
    )


def _get_customer_or_404(customer_id: UUID, db: Session) -> Customer:
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return customer


def _active_queue_machines(customer: Customer) -> list:
    """Máquinas ativas do cliente na ordem da fila."""
    return sorted([m for m in customer.machines if m.active], key=lambda m: m.queue_order)


def _auto_unlock_queue(customer: Customer) -> bool:
    """Destrava a fila se ela está ativa mas a máquina atual está offline ou não existe.

    Não dá commit (o chamador decide). Retorna True se destravou.
    """
    if not customer.queue_active:
        return False
    queue = _active_queue_machines(customer)
    curr_idx = customer.queue_current_index if customer.queue_current_index is not None else 0
    curr_machine = queue[curr_idx] if 0 <= curr_idx < len(queue) else None
    if not curr_machine or not check_machine_online(curr_machine):
        customer.queue_active = False
        customer.queue_current_index = None
        return True
    return False


def _ensure_queue_idle(customer: Customer, db: Session) -> None:
    """409 se a fila do cliente estiver em andamento (depois do auto-destravamento)."""
    if _auto_unlock_queue(customer):
        db.commit()
    if customer.queue_active:
        raise HTTPException(status_code=409, detail=QUEUE_ACTIVE_DETAIL.format(name=customer.name))


def _to_response(customer: Customer, db: Session, commit: bool = True) -> CustomerResponse:
    # NOTA: este helper também é usado em rotas GET e pode gravar (auto-destravamento
    # da fila). Com commit=False o chamador fica responsável por dar o commit.
    if _auto_unlock_queue(customer) and commit:
        db.commit()

    machines_resp = [machine_to_response(m) for m in customer.machines]
    machines_online = sum(1 for m in machines_resp if m.is_online)
    last_backups = [m.last_backup_at for m in customer.machines if m.last_backup_at]
    last_backup_at = max(last_backups) if last_backups else None

    return CustomerResponse(
        id=customer.id,
        name=customer.name,
        description=customer.description,
        active=customer.active,
        backup_hour=customer.backup_hour,
        backup_minute=customer.backup_minute,
        created_at=customer.created_at,
        email_to=list(customer.email_to or []),
        machines_total=len(customer.machines),
        machines_online=machines_online,
        health=_compute_health(customer.machines),
        last_backup_at=last_backup_at,
        queue_active=customer.queue_active,
        queue_current_index=customer.queue_current_index,
        machines=machines_resp,
    )


@router.get("", response_model=List[CustomerResponse], dependencies=[Depends(verify_admin_token)])
def list_customers(db: Session = Depends(get_db)):
    customers = _load_customers_query(db).order_by(Customer.name).all()
    # Um único commit no final (um commit por cliente expiraria os objetos já carregados
    # e reintroduziria o N+1). Esta rota GET grava apenas no auto-destravamento da fila.
    result = [_to_response(c, db, commit=False) for c in customers]
    db.commit()
    return result


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(verify_admin_token)])
def create_customer(body: CustomerCreate, db: Session = Depends(get_db)):
    customer = Customer(
        name=body.name,
        description=body.description or None,
        active=body.active,
        backup_hour=body.backup_hour,
        backup_minute=body.backup_minute,
        email_to=body.email_to,
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return _to_response(customer, db)


@router.get("/{customer_id}", response_model=CustomerResponse, dependencies=[Depends(verify_admin_token)])
def get_customer(customer_id: UUID, db: Session = Depends(get_db)):
    customer = _load_customers_query(db).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return _to_response(customer, db)


@router.put("/{customer_id}", response_model=CustomerResponse, dependencies=[Depends(verify_admin_token)])
def update_customer(customer_id: UUID, body: CustomerUpdate, db: Session = Depends(get_db)):
    customer = _get_customer_or_404(customer_id, db)

    schedule_changed = (
        (body.backup_hour is not None and body.backup_hour != customer.backup_hour) or
        (body.backup_minute is not None and body.backup_minute != customer.backup_minute)
    )

    for field, value in body.model_dump(exclude_none=True).items():
        if field == "description":
            continue
        setattr(customer, field, value)

    # Descrição: "" ou null explícito limpam o campo; ausente mantém
    if "description" in body.model_fields_set:
        customer.description = (body.description or "").strip() or None

    # Propaga horário para todas as máquinas do cliente e solicita restart
    if schedule_changed:
        for machine in customer.machines:
            machine.backup_hour = customer.backup_hour
            machine.backup_minute = customer.backup_minute
            machine.restart_requested = True

    db.commit()
    db.refresh(customer)
    return _to_response(customer, db)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(verify_admin_token)])
def delete_customer(customer_id: UUID, db: Session = Depends(get_db)):
    customer = _get_customer_or_404(customer_id, db)
    # Máquinas ficam sem cliente (mantêm o horário atual)
    for machine in customer.machines:
        machine.customer_id = None
        machine.queue_order = 0
    db.delete(customer)
    db.commit()


# ─── Vínculo de máquinas e ordem da fila ───────────────────────────────────

@router.post("/{customer_id}/machines/{machine_id}", response_model=CustomerResponse,
             dependencies=[Depends(verify_admin_token)])
def link_machine(customer_id: UUID, machine_id: UUID, db: Session = Depends(get_db)):
    """Vincula a máquina ao cliente (movendo de outro cliente, se for o caso) no fim da fila."""
    customer = _get_customer_or_404(customer_id, db)
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Máquina não encontrada")

    if machine.customer_id == customer.id:
        # Já vinculada: nada a fazer (mantém a posição na fila)
        return _to_response(customer, db)

    _ensure_queue_idle(customer, db)
    origin = machine.customer
    if origin is not None:
        _ensure_queue_idle(origin, db)

    machine.customer_id = customer.id
    machine.queue_order = next_queue_order(db, customer.id, exclude_machine_id=machine.id)

    # Máquina vinculada usa o horário do cliente
    if machine.backup_hour != customer.backup_hour or machine.backup_minute != customer.backup_minute:
        machine.backup_hour = customer.backup_hour
        machine.backup_minute = customer.backup_minute
        machine.restart_requested = True

    db.commit()
    db.refresh(customer)
    return _to_response(customer, db)


@router.delete("/{customer_id}/machines/{machine_id}", response_model=CustomerResponse,
               dependencies=[Depends(verify_admin_token)])
def unlink_machine(customer_id: UUID, machine_id: UUID, db: Session = Depends(get_db)):
    """Desvincula a máquina do cliente (ela mantém o horário atual)."""
    customer = _get_customer_or_404(customer_id, db)
    machine = db.query(Machine).filter(
        Machine.id == machine_id, Machine.customer_id == customer.id
    ).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Máquina não encontrada neste cliente")

    _ensure_queue_idle(customer, db)

    machine.customer_id = None
    machine.queue_order = 0
    db.flush()
    # Renumera a fila das máquinas que ficaram (0..n-1, sem buracos)
    restantes = db.query(Machine).filter(Machine.customer_id == customer.id).order_by(Machine.queue_order).all()
    for pos, m in enumerate(restantes):
        m.queue_order = pos
    db.commit()
    db.refresh(customer)
    return _to_response(customer, db)


@router.put("/{customer_id}/queue-order", response_model=CustomerResponse,
            dependencies=[Depends(verify_admin_token)])
def reorder_queue(customer_id: UUID, body: CustomerQueueOrder, db: Session = Depends(get_db)):
    """Grava a ordem da fila (queue_order 0..n-1) na sequência de `machine_ids`."""
    customer = _get_customer_or_404(customer_id, db)
    _ensure_queue_idle(customer, db)

    machines_by_id = {m.id: m for m in customer.machines}
    if len(body.machine_ids) != len(set(body.machine_ids)) or set(body.machine_ids) != set(machines_by_id):
        raise HTTPException(
            status_code=400,
            detail="A lista deve conter exatamente as máquinas do cliente, sem repetição.",
        )

    for position, mid in enumerate(body.machine_ids):
        machines_by_id[mid].queue_order = position

    db.commit()
    db.refresh(customer)
    return _to_response(customer, db)


# ─── Fila de backup e download ─────────────────────────────────────────────

@router.post("/{customer_id}/trigger-backup", dependencies=[Depends(verify_admin_token)])
def trigger_customer_backup(customer_id: UUID, db: Session = Depends(get_db)):
    """Dispara backup em fila para todas as máquinas do cliente (uma de cada vez, por ordem queue_order)."""
    customer = _get_customer_or_404(customer_id, db)

    queue = _active_queue_machines(customer)
    if not queue:
        raise HTTPException(status_code=400, detail="Nenhuma máquina ativa neste cliente")

    # Procura a primeira máquina que esteja ONLINE
    first_online = None
    first_idx = None
    for idx, m in enumerate(queue):
        if check_machine_online(m):
            first_online = m
            first_idx = idx
            break

    if not first_online:
        raise HTTPException(
            status_code=400,
            detail="Nenhuma máquina online neste cliente no momento para iniciar o backup"
        )

    # Inicia fila e dispara a primeira máquina online
    customer.queue_active = True
    customer.queue_current_index = first_idx
    first_online.backup_requested = True

    # Rodada `queue`: esperadas = máquinas ativas da fila (1 e-mail ao fechar)
    open_queue_run(db, customer, [str(m.id) for m in queue])

    db.add(AgentLog(
        machine_id=first_online.id,
        event_type="queue_backup",
        message=f"Backup em fila iniciado pelo Cliente '{customer.name}'. Posição {first_idx + 1}/{len(queue)} ({first_online.name})."
    ))

    db.commit()
    return {
        "status": "ok",
        "message": f"Fila iniciada. Primeira máquina online: {first_online.name}",
        "queue_size": len(queue),
    }


@router.post("/{customer_id}/cancel-queue", dependencies=[Depends(verify_admin_token)])
def cancel_customer_queue(customer_id: UUID, db: Session = Depends(get_db)):
    """Cancela e destrava a fila de backup do cliente imediatamente."""
    customer = _get_customer_or_404(customer_id, db)

    customer.queue_active = False
    customer.queue_current_index = None
    for m in customer.machines:
        m.backup_requested = False

    db.commit()

    # Fecha a rodada `queue` aberta; e-mail só se pelo menos 1 máquina reportou
    close_queue_run_on_cancel(db, customer)
    return {"status": "ok", "message": "Fila cancelada com sucesso"}


@router.get("/{customer_id}/download-latest", dependencies=[Depends(verify_admin_token)])
def download_customer_zip(customer_id: UUID, db: Session = Depends(get_db)):
    """Gera e retorna um ZIP agrupado com os backups mais recentes de cada máquina do cliente."""
    customer = _get_customer_or_404(customer_id, db)

    tmp = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024)
    found_any = False
    used_folders = set()

    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
            for machine in sorted(customer.machines, key=lambda m: m.queue_order):
                latest = (
                    db.query(Backup)
                    .filter(Backup.machine_id == machine.id, Backup.zip_filename.isnot(None))
                    .order_by(Backup.started_at.desc())
                    .first()
                )
                if not latest or not latest.zip_filename:
                    continue
                date_str = (latest.started_at or latest.created_at).strftime("%d-%m-%Y")
                zip_path = get_zip_path(machine.id, machine.name, latest.zip_filename, date_str=date_str)
                if not zip_path or not zip_path.exists():
                    continue
                safe_name = machine.name.replace(" ", "_").replace("/", "_")
                if safe_name in used_folders:
                    safe_name = f"{safe_name}_{str(machine.id)[:8]}"
                used_folders.add(safe_name)
                zf.write(str(zip_path), arcname=f"{safe_name}/{latest.zip_filename}")
                found_any = True
    except Exception:
        tmp.close()
        raise

    if not found_any:
        tmp.close()
        raise HTTPException(status_code=404, detail="Nenhum backup disponível para as máquinas deste cliente")

    tmp.seek(0)
    safe_customer_name = customer.name.replace(" ", "_").replace("/", "_")
    date_today = datetime.now().strftime("%d-%m-%Y")
    filename = f"cliente_{safe_customer_name}_{date_today}.zip"

    return StreamingResponse(
        iter_file(tmp),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── Rodadas de backup do Cliente ──────────────────────────────────────────

def _get_run_or_404(customer_id: UUID, run_id: UUID, db: Session) -> CustomerBackupRun:
    run = db.query(CustomerBackupRun).filter(
        CustomerBackupRun.id == run_id, CustomerBackupRun.customer_id == customer_id
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Rodada não encontrada")
    return run


@router.get("/{customer_id}/runs", response_model=List[CustomerRunResponse],
            dependencies=[Depends(verify_admin_token)])
def list_customer_runs(customer_id: UUID, limit: int = Query(20, ge=1, le=200), db: Session = Depends(get_db)):
    """Rodadas de backup do cliente (mais recentes primeiro)."""
    _get_customer_or_404(customer_id, db)
    runs = (
        db.query(CustomerBackupRun)
        .options(selectinload(CustomerBackupRun.backups))
        .filter(CustomerBackupRun.customer_id == customer_id)
        .order_by(CustomerBackupRun.started_at.desc(), CustomerBackupRun.created_at.desc())
        .limit(limit)
        .all()
    )
    return [CustomerRunResponse(**run_to_dict(db, r)) for r in runs]


@router.get("/{customer_id}/runs/{run_id}/download", dependencies=[Depends(verify_admin_token)])
def download_customer_run_zip(customer_id: UUID, run_id: UUID, db: Session = Depends(get_db)):
    """ZIP unificado da rodada: uma pasta por máquina com o ZIP do backup."""
    run = _get_run_or_404(customer_id, run_id, db)
    f = build_run_zip(db, run)
    if f is None:
        raise HTTPException(status_code=404, detail="Nenhum ZIP disponível nesta rodada")
    return StreamingResponse(
        iter_file(f),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{run_zip_filename(run)}"'},
    )


@router.post("/{customer_id}/runs/{run_id}/resend-email", dependencies=[Depends(verify_admin_token)])
def resend_customer_run_email(customer_id: UUID, run_id: UUID, request: Request, db: Session = Depends(get_db)):
    """Reenvia o e-mail de uma rodada já fechada (409 se ainda aberta)."""
    run = _get_run_or_404(customer_id, run_id, db)
    if run.closed_at is None:
        raise HTTPException(status_code=409, detail="Rodada ainda em andamento. Aguarde o fechamento.")
    sent = send_run_email(db, run, base_url=str(request.base_url), resend=True)
    return {"email_sent": sent}
