"""
Agent-facing router.
Windows agent authenticates with X-Client-ID + X-API-Key headers.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Request, Query
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from auth import get_current_machine
from database import get_db, SessionLocal
from models import Machine, Backup, NVR, NVRCamera, AgentLog
from schemas import (
    AgentConfigResponse,
    AgentEquipamento,
    BackupReportCreate,
    BackupReportResponse,
    NVRCameraNightImage,
    PingResponse,
    PingRequest,
    RTSPTestResponse,
    TIPOS_EQUIPAMENTO,
)
from routers.machines import check_machine_online
from services.crypto_service import decrypt
from services.storage_service import save_zip_stream, UploadTooLargeError
from services.email_service import send_backup_report
from config import settings

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


@router.get("/config", response_model=AgentConfigResponse)
def get_agent_config(machine: Machine = Depends(get_current_machine), db: Session = Depends(get_db)):
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
        for nvr in machine.equipamentos if nvr.active
    ]
    zip_pw = decrypt(machine.zip_password) if machine.zip_password else None

    # Usa horário do Cliente se a máquina pertencer a um Cliente
    backup_hour = machine.backup_hour
    backup_minute = machine.backup_minute
    if machine.customer is not None:
        backup_hour = machine.customer.backup_hour
        backup_minute = machine.customer.backup_minute

    # Update last_seen
    machine.last_seen = datetime.utcnow()
    db.commit()

    # `client_name` é campo do contrato JSON com o agente: não renomear
    return AgentConfigResponse(
        client_name=machine.name,
        backup_hour=backup_hour,
        backup_minute=backup_minute,
        zip_password=zip_pw,
        equipamentos=equipamentos,
        nvrs=equipamentos,  # alias de compatibilidade
    )


# Dicionário global de tarefas RTSP pendentes (long-polling entre dashboard e agente).
# Formato: { machine_id_str: {"task": dict, "event": asyncio.Event(), "result": None, "sent": bool} }
# LIMITAÇÃO: o estado vive na memória do processo, então só funciona com 1 worker
# uvicorn. Com múltiplos workers o ping do agente e o test-rtsp poderiam cair em
# processos diferentes e a tarefa nunca seria entregue.
pending_rtsp_tasks: Dict[str, Any] = {}


def _read_request_flags(machine_id: UUID) -> tuple[bool, bool]:
    """Lê restart/backup solicitados usando uma sessão curta (não segura conexão no long-poll)."""
    with SessionLocal() as session:
        row = session.query(
            Machine.restart_requested, Machine.backup_requested
        ).filter(Machine.id == machine_id).first()
    if not row:
        return False, False
    return bool(row[0]), bool(row[1])


@router.post("/ping", response_model=PingResponse)
async def ping_agent(
    body: PingRequest | None = None,
    machine: Machine = Depends(get_current_machine),
    db: Session = Depends(get_db)
):
    """Heartbeat do agente. Usa long-polling (5 iterações de 1s) para entregar comandos de teste RTSP rapidamente."""
    # Commit imediato: persiste last_seen/telemetry antes de liberar a conexão para o long-polling
    machine.last_seen = datetime.utcnow()
    if body and body.telemetry:
        machine.telemetry = body.telemetry
    db.commit()
    machine_id = machine.id
    machine_id_str = str(machine_id)

    # Libera a conexão do pool durante a espera: o long-poll não pode segurar a sessão
    # do banco por vários segundos (esgotaria o pool com muitos agentes). A mesma
    # sessão é reutilizada (nova transação) logo após o polling.
    db.close()

    # ── Espera por tarefas (long-polling: 5 iterações de 1s) ──
    for _ in range(5):
        # Há tarefa RTSP pendente (ainda não entregue) para esta máquina?
        task_data = pending_rtsp_tasks.get(machine_id_str)
        if task_data is not None and not task_data.get("sent", False):
            task_data["sent"] = True
            return PingResponse(
                status="ok",
                restart=False,
                backup=False,
                rtsp_task=task_data["task"]
            )

        # Flags normais de restart/backup: só retorna imediatamente se estiverem marcadas
        restart_flag, backup_flag = _read_request_flags(machine_id)
        if restart_flag or backup_flag:
            break

        await asyncio.sleep(1)

    # Recarrega a máquina na sessão (ela foi liberada antes do polling)
    machine = db.get(Machine, machine_id)
    if machine is None:
        return PingResponse(status="ok", restart=False, backup=False)

    should_restart = bool(machine.restart_requested)
    should_backup = bool(machine.backup_requested)
    
    # ── Auto-recovery de backup perdido ──
    # Não aciona se should_backup já for True
    # Não aciona se a máquina pertence a um Cliente com fila ativa (a fila comanda o sequenciamento)
    is_in_active_queue = bool(machine.customer is not None and machine.customer.queue_active)
    if not should_backup and not is_in_active_queue and machine.backup_hour is not None and machine.backup_minute is not None:
        brt_tz = timezone(timedelta(hours=-3))
        now_brt = datetime.now(brt_tz)
        scheduled_time_today = now_brt.replace(hour=machine.backup_hour, minute=machine.backup_minute, second=0, microsecond=0)
        
        if now_brt > scheduled_time_today + timedelta(minutes=30):
            # 1. Verifica se já concluiu backup hoje
            made_backup_today = False
            if machine.last_backup_at:
                last_backup_brt = machine.last_backup_at.replace(tzinfo=timezone.utc).astimezone(brt_tz)
                if last_backup_brt.date() == now_brt.date():
                    made_backup_today = True

            # 2. Verifica se houve backup recente (últimas 2 horas) para evitar disparos duplicados
            recent_backup = db.query(Backup).filter(
                Backup.machine_id == machine.id,
                Backup.created_at >= (datetime.utcnow() - timedelta(hours=2))
            ).first()
            if recent_backup:
                made_backup_today = True

            # 3. Verifica se já disparou ping_recovery hoje
            today_utc_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            already_recovered_today = db.query(AgentLog).filter(
                AgentLog.machine_id == machine.id,
                AgentLog.event_type == "ping_recovery",
                AgentLog.created_at >= today_utc_start
            ).first() is not None

            if not made_backup_today and not already_recovered_today:
                should_backup = True
                machine.backup_requested = False 
                log_msg = f"Ping recebido. Disparando BACKUP DE RECUPERACAO. Agente falhou em executar no horario agendado ({machine.backup_hour:02d}:{machine.backup_minute:02d})."
                db.add(AgentLog(machine_id=machine.id, event_type="ping_recovery", message=log_msg))

    if should_restart:
        machine.restart_requested = False
    if should_backup and machine.backup_requested:
        machine.backup_requested = False

    log_msg = f"Ping recebido. Instruções pendentes: restart={should_restart}, backup={should_backup}"
    db.add(AgentLog(machine_id=machine.id, event_type="ping", message=log_msg))
    
    # Poda dos logs: mantém apenas os 50 mais recentes por máquina, com um único DELETE
    db.flush()
    ids_antigos = (
        select(AgentLog.id)
        .where(AgentLog.machine_id == machine.id)
        .order_by(AgentLog.created_at.desc())
        .offset(50)
    )
    db.execute(delete(AgentLog).where(AgentLog.id.in_(ids_antigos)))

    db.commit()
    return PingResponse(status="ok", restart=should_restart, backup=should_backup)

@router.post("/rtsp-result")
async def receive_rtsp_result(
    result: RTSPTestResponse,
    machine: Machine = Depends(get_current_machine),
):
    """Agent posts the result of an RTSP task."""
    machine_id_str = str(machine.id)
    task_data = pending_rtsp_tasks.get(machine_id_str)
    if task_data is not None:
        task_data["result"] = result
        task_data["event"].set()
    return {"status": "ok"}

@router.post("/nvr-cameras/night-image")
def receive_night_image(
    body: NVRCameraNightImage,
    machine: Machine = Depends(get_current_machine),
    db: Session = Depends(get_db),
):
    """Agent posts the night image of an NVR channel."""
    nvr = db.query(NVR).filter(
        NVR.machine_id == machine.id, 
        NVR.name == body.nvr_name,
        NVR.active == True
    ).first()
    if not nvr:
        return {"status": "error", "message": "NVR não encontrado ou inativo"}

    camera = db.query(NVRCamera).filter(NVRCamera.nvr_id == nvr.id, NVRCamera.canal == body.canal).first()
    if not camera:
        camera = NVRCamera(
            nvr_id=nvr.id,
            canal=body.canal,
            nome=body.nome,
            night_image_base64=body.image_base64,
            night_image_date=body.night_image_date
        )
        db.add(camera)
    else:
        camera.nome = body.nome
        camera.night_image_base64 = body.image_base64
        camera.night_image_date = body.night_image_date

    db.commit()
    return {"status": "ok"}

@router.post("/backup/report", response_model=BackupReportResponse, status_code=201)
def receive_backup_report(
    body: BackupReportCreate,
    machine: Machine = Depends(get_current_machine),
    db: Session = Depends(get_db),
):
    """Agent posts the backup result. Server creates a Backup record."""
    from datetime import datetime
    
    # Usa a hora real do servidor, ignorando o relógio da máquina
    server_finished_at = datetime.utcnow()
    # Subtrai o tempo que a máquina diz que levou para achar o "started_at" real do servidor
    duration = body.finished_at - body.started_at
    server_started_at = server_finished_at - duration

    nvr_results_with_type = []
    for r in body.nvr_results:
        r_dict = r.model_dump()
        nvr = db.query(NVR).filter(NVR.machine_id == machine.id, NVR.name == r.nome).first()
        if nvr:
            r_dict["tipo"] = nvr.tipo
            if r.cameras is not None:
                nvr.last_recording_status = r.cameras
        else:
            r_dict["tipo"] = "NVR" # default fallback se foi excluido
        nvr_results_with_type.append(r_dict)

    backup = Backup(
        machine_id=machine.id,
        started_at=server_started_at,
        finished_at=server_finished_at,
        status=body.status,
        nvr_results=nvr_results_with_type,
        trigger=body.trigger,
    )
    db.add(backup)

    # Atualiza o último backup da máquina
    machine.last_backup_at = server_finished_at
    machine.last_backup_status = body.status

    db.commit()
    db.refresh(backup)

    # ── Avançar fila de backup sequencial do Cliente ──
    customer = machine.customer
    if customer is not None and customer.queue_active:
        queue = sorted(
            [m for m in customer.machines if m.active],
            key=lambda m: m.queue_order
        )
        # Localiza a posição da máquina que está reportando
        try:
            reporting_idx = [m.id for m in queue].index(machine.id)
        except ValueError:
            reporting_idx = customer.queue_current_index if customer.queue_current_index is not None else 0

        next_online_machine = None
        next_idx = None
        for idx in range(reporting_idx + 1, len(queue)):
            m = queue[idx]
            if check_machine_online(m):
                next_online_machine = m
                next_idx = idx
                break
            else:
                db.add(AgentLog(
                    machine_id=m.id,
                    event_type="queue_backup_skipped",
                    message=f"Máquina '{m.name}' está OFFLINE. Pulada na fila do Cliente '{customer.name}'."
                ))

        if next_online_machine is not None:
            customer.queue_current_index = next_idx
            next_online_machine.backup_requested = True
            db.add(AgentLog(
                machine_id=next_online_machine.id,
                event_type="queue_backup",
                message=f"Backup em fila disparado pelo Cliente '{customer.name}'. Posição {next_idx + 1}/{len(queue)} ({next_online_machine.name})."
            ))
        else:
            # Nenhuma próxima máquina online ou fim da fila atingido
            customer.queue_active = False
            customer.queue_current_index = None
        db.commit()

    return BackupReportResponse(backup_id=backup.id)


# Rota síncrona (def): o FastAPI a executa no threadpool, então DB, disco e SMTP
# (que pode levar dezenas de segundos) não bloqueiam o event loop.
@router.post("/backup/upload/{backup_id}")
def upload_backup_zip(
    backup_id: str,
    request: Request,
    device_type: str = Query("NVR", description="Tipo de equipamento: NVR, OLT, ONU, PABX"),
    file: UploadFile = File(...),
    machine: Machine = Depends(get_current_machine),
    db: Session = Depends(get_db),
):
    """Agent uploads the ZIP file. Server stores it and sends email."""
    try:
        backup_uuid = UUID(backup_id)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=404, detail="Backup record not found")

    backup = db.query(Backup).filter(
        Backup.id == backup_uuid, Backup.machine_id == machine.id
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
    filename = file.filename or f"backup_{clean_device_type.lower()}_{date_str}.zip"

    # Grava em streaming (chunks) com limite de tamanho; o nome é sanitizado e o
    # caminho final validado dentro do diretório da máquina (anti path traversal).
    try:
        zip_path, zip_size = save_zip_stream(
            machine_id=machine.id,
            machine_name=machine.name,
            date_str=date_str,
            device_type=clean_device_type,
            filename=filename,
            source=file.file,
            max_bytes=settings.MAX_UPLOAD_MB * 1024 * 1024,
        )
    except UploadTooLargeError:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo excede o limite de {settings.MAX_UPLOAD_MB} MB",
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido")

    backup.zip_filename = zip_path.name
    backup.zip_size = (backup.zip_size or 0) + zip_size
    db.commit()

    # Send email
    nvr_results = backup.nvr_results or []

    email_sent = send_backup_report(
        machine_name=machine.name,
        date_str=date_str,
        nvr_results=nvr_results,
        recipients=machine.email_to or [],
        db=db,
        zip_path=zip_path,
        backup_id=backup_id,
        base_url=str(request.base_url),
        public_url=settings.PUBLIC_URL,
    )
    backup.email_sent = email_sent or backup.email_sent

    if email_sent:
        recipients_str = ", ".join(machine.email_to) if machine.email_to else "destinatários configurados"
        db.add(AgentLog(
            machine_id=machine.id,
            event_type="email_sent",
            message=f"E-mail de relatório enviado com sucesso para: {recipients_str}."
        ))
    else:
        recipients_str = ", ".join(machine.email_to) if machine.email_to else "nenhum destinatário cadastrado"
        db.add(AgentLog(
            machine_id=machine.id,
            event_type="email_error",
            message=f"Falha no envio de e-mail de relatório ({recipients_str}). Verifique configurações SMTP e destinatários."
        ))

    db.commit()

    return {"status": "ok", "zip_size": zip_size, "email_sent": email_sent}
