"""Rodadas de backup do Cliente: agrupam os backups das máquinas e geram 1 e-mail por rodada.

Tipos (`CustomerBackupRun.trigger`):
- scheduled: aberta no 1º relatório agendado de uma máquina do Cliente; esperadas = máquinas ativas.
- queue: aberta em POST /clients/{id}/trigger-backup; esperadas = máquinas ativas da fila.
- manual_machine: backup avulso de uma máquina do Cliente; esperada = só ela (1 rodada por relatório).

Fechamento (`close_due_runs`): todas as esperadas reportaram e o último relatório tem mais de
RUN_UPLOAD_GRACE_SECONDS (tempo para o ZIP chegar), ou `now >= deadline_at`.
Datetimes gravados são naive UTC (REGRA-001).
"""
import logging
from pathlib import Path
import tempfile
import zipfile
from datetime import datetime, timedelta
from typing import Iterator, List, Optional
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from config import settings
from models import AgentLog, Backup, Customer, CustomerBackupRun, Machine
from services.email_service import send_customer_report
from services.storage_service import get_zip_path, _sanitize_name

logger = logging.getLogger(__name__)

RUN_OPEN_STATUS = "EM_ANDAMENTO"
TRIGGER_SCHEDULED = "scheduled"
TRIGGER_QUEUE = "queue"
TRIGGER_MANUAL = "manual_machine"
# Valor de `body.trigger` que o agente envia no backup agendado
AGENT_TRIGGER_SCHEDULED = "scheduled"

NOT_EXECUTED = "NAO_EXECUTOU"
_OK_STATUSES = {"OK", "SEM_ARQUIVOS"}
_ERROR_STATUSES = {"ERROR", "ERRO"}


def _utcnow() -> datetime:
    return datetime.utcnow()


def is_ok_status(status: Optional[str]) -> bool:
    return str(status or "").strip().upper() in _OK_STATUSES


def _is_error_status(status: Optional[str]) -> bool:
    return str(status or "").strip().upper() in _ERROR_STATUSES


# ─── Abertura / associação ─────────────────────────────────────────────────

def _active_machine_ids(customer: Customer) -> List[str]:
    """IDs (str) das máquinas ativas do Cliente na ordem da fila."""
    return [str(m.id) for m in sorted(customer.machines, key=lambda m: m.queue_order) if m.active]


def _new_run(db: Session, customer_id: UUID, trigger: str, expected_ids: List[str],
             now: Optional[datetime] = None) -> CustomerBackupRun:
    now = now or _utcnow()
    run = CustomerBackupRun(
        customer_id=customer_id,
        trigger=trigger,
        started_at=now,
        deadline_at=now + timedelta(hours=settings.RUN_DEADLINE_HOURS),
        closed_at=None,
        status=RUN_OPEN_STATUS,
        expected_machine_ids=list(expected_ids),
        email_sent=False,
        created_at=now,
    )
    db.add(run)
    db.flush()
    return run


def _open_runs(db: Session, customer_id: UUID, trigger: str, now: Optional[datetime] = None) -> List[CustomerBackupRun]:
    """Rodadas abertas (e ainda no prazo) do Cliente, mais antigas primeiro."""
    q = db.query(CustomerBackupRun).filter(
        CustomerBackupRun.customer_id == customer_id,
        CustomerBackupRun.trigger == trigger,
        CustomerBackupRun.closed_at.is_(None),
    )
    if now is not None:
        q = q.filter(CustomerBackupRun.deadline_at > now)
    return q.order_by(CustomerBackupRun.started_at, CustomerBackupRun.created_at, CustomerBackupRun.id).all()


def _ensure_expected(run: CustomerBackupRun, machine_id: UUID) -> None:
    ids = list(run.expected_machine_ids or [])
    if str(machine_id) not in ids:
        ids.append(str(machine_id))
        run.expected_machine_ids = ids  # reatribui: JSON não detecta mutação in-place


def open_queue_run(db: Session, customer: Customer, machine_ids: List[str]) -> CustomerBackupRun:
    """Abre (ou reaproveita, se já houver uma aberta) a rodada `queue` do Cliente. Não dá commit."""
    now = _utcnow()
    existing = _open_runs(db, customer.id, TRIGGER_QUEUE, now)
    if existing:
        run = existing[0]
        for mid in machine_ids:
            _ensure_expected(run, mid)
        return run
    return _new_run(db, customer.id, TRIGGER_QUEUE, machine_ids, now)


def finish_queue_run(db: Session, customer: Customer) -> None:
    """Fila terminou (inclusive pulando máquinas offline): encurta o prazo da rodada `queue`
    aberta para só o tempo do último ZIP chegar, em vez de esperar as 2h. Não dá commit."""
    now = _utcnow()
    limite = now + timedelta(seconds=settings.RUN_UPLOAD_GRACE_SECONDS)
    for run in _open_runs(db, customer.id, TRIGGER_QUEUE, now):
        if run.deadline_at > limite:
            run.deadline_at = limite


def merge_duplicate_open_runs(db: Session, customer_id: UUID, trigger: str = TRIGGER_SCHEDULED,
                              now: Optional[datetime] = None) -> int:
    """Une rodadas abertas duplicadas (condição de corrida) na mais antiga. Dá commit.

    Retorna quantas rodadas foram removidas.
    """
    runs = _open_runs(db, customer_id, trigger, now or _utcnow())
    if len(runs) <= 1:
        return 0
    keep, dups = runs[0], runs[1:]
    for dup in dups:
        for mid in (dup.expected_machine_ids or []):
            _ensure_expected(keep, mid)
        # Move pelo ORM (o backref tira o backup da coleção da duplicada antes do delete)
        for b in list(dup.backups):
            b.run = keep
        db.delete(dup)
    db.commit()
    logger.warning("Rodadas '%s' duplicadas do cliente %s unidas em %s (%d removida(s))",
                   trigger, customer_id, keep.id, len(dups))
    return len(dups)


def attach_report_to_run(db: Session, machine: Machine, backup: Backup, report_trigger: Optional[str]) -> Optional[CustomerBackupRun]:
    """Associa o backup recém-criado à rodada do Cliente da máquina (criando-a se preciso). Dá commit.

    Deve ser chamada ANTES de avançar a fila (usa `customer.queue_active` do momento do relatório).
    Máquina sem Cliente: não faz nada e retorna None.
    """
    customer = machine.customer
    if customer is None:
        return None

    now = _utcnow()
    run = None
    if report_trigger == AGENT_TRIGGER_SCHEDULED:
        opened = _open_runs(db, customer.id, TRIGGER_SCHEDULED, now)
        run = opened[0] if opened else _new_run(db, customer.id, TRIGGER_SCHEDULED, _active_machine_ids(customer), now)
    elif customer.queue_active:
        opened = _open_runs(db, customer.id, TRIGGER_QUEUE, now)
        run = opened[0] if opened else None

    if run is None:
        # Backup avulso (botão da máquina, recuperação de backup perdido, etc.)
        run = _new_run(db, customer.id, TRIGGER_MANUAL, [str(machine.id)], now)

    _ensure_expected(run, machine.id)
    backup.run_id = run.id
    db.commit()

    # Duas máquinas reportando ao mesmo tempo podem ter criado 2 rodadas agendadas:
    # re-consulta e une na mais antiga.
    if run.trigger == TRIGGER_SCHEDULED:
        try:
            merge_duplicate_open_runs(db, customer.id, TRIGGER_SCHEDULED, now)
        except Exception:
            db.rollback()
            logger.exception("Falha ao unir rodadas agendadas duplicadas do cliente %s", customer.id)
    return run


# ─── Situação da rodada ────────────────────────────────────────────────────

def _latest_backup_by_machine(run: CustomerBackupRun) -> dict:
    """{machine_id_str: Backup mais recente da máquina na rodada}."""
    latest: dict = {}
    for b in run.backups:
        key = str(b.machine_id)
        ref = b.finished_at or b.created_at or datetime.min
        cur = latest.get(key)
        if cur is None or ref >= (cur.finished_at or cur.created_at or datetime.min):
            latest[key] = b
    return latest


def run_machine_ids(run: CustomerBackupRun) -> List[str]:
    """Máquinas da rodada: esperadas (na ordem) + eventuais extras que reportaram."""
    ids = list(run.expected_machine_ids or [])
    for b in run.backups:
        if str(b.machine_id) not in ids:
            ids.append(str(b.machine_id))
    return ids


def run_entries(db: Session, run: CustomerBackupRun) -> List[dict]:
    """Uma entrada por máquina da rodada: machine_id, name, machine, backup (ou None)."""
    latest = _latest_backup_by_machine(run)
    ids = run_machine_ids(run)
    machines = {}
    uuids = []
    for mid in ids:
        try:
            uuids.append(UUID(mid))
        except (ValueError, TypeError):
            pass
    if uuids:
        machines = {str(m.id): m for m in db.query(Machine).filter(Machine.id.in_(uuids)).all()}
    entries = []
    for mid in ids:
        m = machines.get(mid)
        entries.append({
            "machine_id": mid,
            "machine": m,
            "name": m.name if m else "(máquina removida)",
            "backup": latest.get(mid),
        })
    return entries


def compute_run_status(entries: List[dict]) -> str:
    """OK se todas reportaram OK/SEM_ARQUIVOS; ERRO se nenhuma reportou ou todas as que
    reportaram deram erro; senão PARCIAL."""
    reported = [e["backup"] for e in entries if e["backup"] is not None]
    if not reported or all(_is_error_status(b.status) for b in reported):
        return "ERRO"
    if len(reported) == len(entries) and all(is_ok_status(b.status) for b in reported):
        return "OK"
    return "PARCIAL"


def _is_due(run: CustomerBackupRun, now: datetime) -> bool:
    if now >= run.deadline_at:
        return True
    latest = _latest_backup_by_machine(run)
    expected = list(run.expected_machine_ids or [])
    if not expected or any(mid not in latest for mid in expected):
        return False
    last_report = max((b.finished_at or b.created_at) for b in run.backups)
    return (now - last_report).total_seconds() > settings.RUN_UPLOAD_GRACE_SECONDS


# ─── Fechamento e e-mail ───────────────────────────────────────────────────

def send_run_email(db: Session, run: CustomerBackupRun, base_url: Optional[str] = None,
                   resend: bool = False) -> bool:
    """Envia o e-mail da rodada, grava `email_sent` e registra AgentLog na 1ª máquina. Dá commit."""
    customer = run.customer
    entries = run_entries(db, run)
    has_zip = any(e["backup"] is not None and e["backup"].zip_filename for e in entries)
    manual_name = entries[0]["name"] if run.trigger == TRIGGER_MANUAL and entries else None

    sent = False
    try:
        sent = send_customer_report(
            customer_name=customer.name if customer else "?",
            run_id=str(run.id),
            run_trigger=run.trigger,
            started_at=run.started_at,
            entries=[{
                "machine_id": e["machine"].id if e["machine"] is not None else None,
                "name": e["name"],
                "status": e["backup"].status if e["backup"] is not None else None,
                "nvr_results": (e["backup"].nvr_results or []) if e["backup"] is not None else [],
            } for e in entries],
            recipients=(customer.email_to or []) if customer else [],
            db=db,
            has_zip=has_zip,
            public_url=settings.PUBLIC_URL,
            base_url=base_url,
            manual_machine_name=manual_name,
        )
    except Exception:
        logger.exception("Falha ao montar/enviar o e-mail da rodada %s", run.id)
        sent = False

    run.email_sent = bool(sent or run.email_sent)

    first_machine = next((e["machine"] for e in entries if e["machine"] is not None), None)
    if first_machine is not None:
        recipients = (customer.email_to if customer else None) or []
        prefixo = "Reenvio do e-mail" if resend else "E-mail"
        if sent:
            msg = f"{prefixo} da rodada do cliente '{customer.name}' enviado com sucesso para: {', '.join(recipients)}."
        else:
            dest = ", ".join(recipients) if recipients else "nenhum destinatário cadastrado no cliente"
            msg = f"Falha no {prefixo.lower()} da rodada do cliente '{customer.name if customer else '?'}' ({dest}). Verifique configurações SMTP e destinatários."
        db.add(AgentLog(machine_id=first_machine.id, event_type="email_sent" if sent else "email_error", message=msg))
    db.commit()
    return bool(sent)


def close_run(db: Session, run: CustomerBackupRun, now: Optional[datetime] = None,
              send_email: bool = True) -> bool:
    """Fecha a rodada (closed_at/status) e envia o e-mail. Idempotente: só quem fecha envia.

    Retorna True se esta chamada fechou a rodada.
    """
    now = now or _utcnow()
    status = compute_run_status(run_entries(db, run))
    # UPDATE condicional: evita fechar (e mandar e-mail) duas vezes
    result = db.execute(
        update(CustomerBackupRun)
        .where(CustomerBackupRun.id == run.id, CustomerBackupRun.closed_at.is_(None))
        .values(closed_at=now, status=status)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        return False
    db.commit()
    db.refresh(run)
    if send_email:
        send_run_email(db, run)
    return True


def close_due_runs(db: Session, now: Optional[datetime] = None) -> List[UUID]:
    """Fecha as rodadas vencidas/completas e envia os e-mails. Idempotente.

    Chamada pela tarefa de fundo (a cada 30s) e exposta para testes. Retorna os IDs fechados.
    """
    now = now or _utcnow()

    # Une duplicadas que a re-consulta do relatório não tenha resolvido
    dup_customers = {
        cid for (cid,) in db.query(CustomerBackupRun.customer_id).filter(
            CustomerBackupRun.closed_at.is_(None), CustomerBackupRun.trigger == TRIGGER_SCHEDULED,
        ).all()
    }
    for cid in dup_customers:
        try:
            merge_duplicate_open_runs(db, cid, TRIGGER_SCHEDULED, now)
        except Exception:
            db.rollback()
            logger.exception("Falha ao unir rodadas duplicadas do cliente %s", cid)

    closed: List[UUID] = []
    open_runs = db.query(CustomerBackupRun).filter(CustomerBackupRun.closed_at.is_(None)) \
        .order_by(CustomerBackupRun.started_at).all()
    for run in open_runs:
        try:
            if _is_due(run, now) and close_run(db, run, now):
                closed.append(run.id)
        except Exception:
            db.rollback()
            logger.exception("Falha ao fechar a rodada %s", run.id)
    return closed


def close_queue_run_on_cancel(db: Session, customer: Customer) -> Optional[CustomerBackupRun]:
    """Cancelamento da fila: fecha a rodada `queue` aberta; envia e-mail só se ≥1 máquina reportou."""
    runs = _open_runs(db, customer.id, TRIGGER_QUEUE)
    last = None
    for run in runs:
        reported = any(e["backup"] is not None for e in run_entries(db, run))
        if close_run(db, run, send_email=False) and reported:
            send_run_email(db, run)
        last = run
    return last


# ─── Resposta da API e ZIP unificado ───────────────────────────────────────

def run_to_dict(db: Session, run: CustomerBackupRun) -> dict:
    """Dados de CustomerRunResponse."""
    entries = run_entries(db, run)
    is_closed = run.closed_at is not None
    machines = []
    for e in entries:
        b = e["backup"]
        machines.append({
            "machine_id": e["machine_id"],
            "machine_name": e["name"],
            "backup_id": b.id if b is not None else None,
            "status": b.status if b is not None else (NOT_EXECUTED if is_closed else None),
            "zip": bool(b is not None and b.zip_filename),
        })
    return {
        "id": run.id,
        "trigger": run.trigger,
        "started_at": run.started_at,
        "deadline_at": run.deadline_at,
        "closed_at": run.closed_at,
        "status": run.status,
        "email_sent": bool(run.email_sent),
        "machines_expected": len(run.expected_machine_ids or []),
        "machines_reported": sum(1 for e in entries if e["backup"] is not None),
        "machines_ok": sum(1 for e in entries if e["backup"] is not None and is_ok_status(e["backup"].status)),
        "has_zip": any(m["zip"] for m in machines),
        "machines": machines,
    }


def write_extracted_backup(
    zf_out,
    path: Path,
    machine_name: str,
    machine_id: UUID,
    machine_zip_password: Optional[str],
    backup_filename: str,
    used_folders: set,
) -> bool:
    """Extrai os arquivos do ZIP individual da máquina (desencriptando com a senha da máquina se houver)
    e grava diretamente no ZIP do cliente sob a pasta da máquina, sem senha interna.
    """
    import pyzipper
    from services.crypto_service import decrypt as crypto_decrypt

    folder = _sanitize_name(machine_name)
    if folder in used_folders:
        folder = f"{folder}_{str(machine_id)[:8]}"
    used_folders.add(folder)

    machine_pw_plain = None
    if machine_zip_password:
        try:
            machine_pw_plain = crypto_decrypt(machine_zip_password)
        except Exception:
            logger.warning("Falha ao decriptar a senha da máquina %s — tentando sem senha.", machine_name)

    extracted_any = False
    try:
        with pyzipper.AESZipFile(str(path), "r") as zf_in:
            if machine_pw_plain:
                zf_in.setpassword(machine_pw_plain.encode())
            for inner_name in zf_in.namelist():
                try:
                    data = zf_in.read(inner_name)
                    arcname = f"{folder}/{inner_name}"
                    zf_out.writestr(arcname, data)
                    extracted_any = True
                except Exception as ex:
                    logger.warning("Falha ao extrair '%s' do ZIP de %s: %s", inner_name, machine_name, ex)
    except Exception as ex:
        logger.warning("Não foi possível abrir/decriptar o ZIP de %s: %s — incluindo o ZIP original.", machine_name, ex)
        zf_out.write(str(path), arcname=f"{folder}/{backup_filename}")
        extracted_any = True

    return extracted_any


def build_run_zip(db: Session, run: CustomerBackupRun, client_password: Optional[str] = None):
    """Gera o ZIP consolidado da rodada do cliente.

    Se `client_password` for informado (ou configurado no cliente), protege o ZIP do cliente com essa senha (AES-WZ).
    Os arquivos dentro das pastas das máquinas ficam descompactados/sem senha interna.
    """
    import pyzipper

    if client_password is None and run.customer and run.customer.zip_password:
        from services.crypto_service import decrypt as crypto_decrypt
        try:
            client_password = crypto_decrypt(run.customer.zip_password)
        except Exception:
            logger.warning("Falha ao decriptar senha do cliente %s", run.customer.name)

    tmp = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)
    found_any = False
    used_folders: set = set()

    try:
        if client_password:
            zf_context = pyzipper.AESZipFile(
                tmp, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
            )
        else:
            zf_context = pyzipper.AESZipFile(
                tmp, "w", compression=pyzipper.ZIP_DEFLATED
            )

        with zf_context as zf_out:
            if client_password:
                zf_out.setpassword(client_password.encode())

            for e in run_entries(db, run):
                b, m = e["backup"], e["machine"]
                if b is None or m is None or not b.zip_filename:
                    continue
                date_str = (b.started_at or b.created_at).strftime("%d-%m-%Y")
                path = get_zip_path(m.id, m.name, b.zip_filename, date_str=date_str)
                if not path or not path.exists():
                    continue

                if write_extracted_backup(zf_out, path, m.name, m.id, m.zip_password, b.zip_filename, used_folders):
                    found_any = True
    except Exception:
        tmp.close()
        raise

    if not found_any:
        tmp.close()
        return None
    tmp.seek(0)
    return tmp


def build_client_zip_with_password(db: Session, run: CustomerBackupRun, client_password: str):
    """Alias compatível com código existente: chama build_run_zip com a senha informada."""
    return build_run_zip(db, run, client_password=client_password)


def build_customer_latest_zip(db: Session, customer: Customer, client_password: Optional[str] = None):
    """Gera o ZIP com os backups mais recentes de todas as máquinas do cliente.
    Se o cliente possuir senha configurada, protege o ZIP com essa senha (AES-WZ).
    Os arquivos dentro das pastas das máquinas ficam sem senha interna.
    """
    import pyzipper

    if client_password is None and customer.zip_password:
        from services.crypto_service import decrypt as crypto_decrypt
        try:
            client_password = crypto_decrypt(customer.zip_password)
        except Exception:
            logger.warning("Falha ao decriptar senha do cliente %s", customer.name)

    tmp = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)
    found_any = False
    used_folders: set = set()

    try:
        if client_password:
            zf_context = pyzipper.AESZipFile(
                tmp, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
            )
        else:
            zf_context = pyzipper.AESZipFile(
                tmp, "w", compression=pyzipper.ZIP_DEFLATED
            )

        with zf_context as zf_out:
            if client_password:
                zf_out.setpassword(client_password.encode())

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
                path = get_zip_path(machine.id, machine.name, latest.zip_filename, date_str=date_str)
                if not path or not path.exists():
                    continue

                if write_extracted_backup(zf_out, path, machine.name, machine.id, machine.zip_password, latest.zip_filename, used_folders):
                    found_any = True
    except Exception:
        tmp.close()
        raise

    if not found_any:
        tmp.close()
        return None
    tmp.seek(0)
    return tmp



def iter_file(f, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    """Lê o arquivo em blocos para StreamingResponse e fecha ao final."""
    try:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk
    finally:
        f.close()


def run_zip_filename(run: CustomerBackupRun) -> str:
    customer_name = _sanitize_name(run.customer.name if run.customer else "cliente")
    date_str = ((run.started_at or _utcnow()) - timedelta(hours=3)).strftime("%d-%m-%Y")
    return f"rodada_{customer_name}_{date_str}.zip"
