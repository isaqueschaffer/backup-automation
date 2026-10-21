"""
Agent-facing router.
Windows agent authenticates with X-Client-ID + X-API-Key headers.
"""
import asyncio
import logging
import re
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
from services.galeria_vms import parear_cameras
from services.storage_service import save_zip_stream, UploadTooLargeError, _sanitize_name
from services.email_service import send_backup_report
from services.backup_runs import attach_report_to_run, finish_queue_run
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


def _build_cameras_config(machine: Machine, nvr: NVR):
    """Monta a lista de câmeras RTSP (ip/usuário/senha decriptada/modelo) de um equipamento
    DIGIFORT/DEFENSE para o agente capturar a imagem da noite no backup. None para outros tipos."""
    if (nvr.tipo or "NVR").upper() not in ("DIGIFORT", "DEFENSE"):
        return None
    cams_db = sorted(nvr.cameras_status or [], key=lambda c: c.canal)
    out = []
    for c in cams_db:
        if not c.ip:
            continue
        try:
            pwd = decrypt(c.password) if c.password else "navarro@123"
        except Exception:
            pwd = c.password or "navarro@123"
        out.append({
            "canal": c.canal,
            "nome": c.nome,
            "ip": c.ip,
            "username": c.username or "admin",
            "password": pwd,
            "modelo": c.modelo or "Hikvision",
        })
    if out:
        return out
    # Fallback: usa câmeras avulsas (tipo == "CAMERA") cadastradas na máquina
    machine_cams = [e for e in machine.equipamentos if (e.tipo or "").upper() == "CAMERA" and e.active and e.ip]
    for idx, mc in enumerate(machine_cams, start=1):
        try:
            pwd = decrypt(mc.password) if mc.password else "navarro@123"
        except Exception:
            pwd = mc.password or "navarro@123"
        out.append({
            "canal": idx,
            "nome": mc.name,
            "ip": mc.ip,
            "username": mc.username or "admin",
            "password": pwd,
            "modelo": (mc.config_extra or {}).get("modelo") or "Hikvision",
        })
    return out


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
            cameras_config=_build_cameras_config(machine, nvr),
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


_URL_COM_CREDENCIAIS = re.compile(r"//[^@/\s'\"]*@")


def mascarar_credenciais(texto):
    """Oculta usuário/senha de URLs (rtsp://user:senha@host) em mensagens vindas do agente."""
    return _URL_COM_CREDENCIAIS.sub("//***@", texto) if isinstance(texto, str) else texto


def _limpar_motivos(cameras):
    """Mascara credenciais no motivo de `imagem_noite` das câmeras do relatório."""
    saida = []
    for st in cameras or []:
        info = st.get("imagem_noite") if isinstance(st, dict) else None
        if isinstance(info, dict) and isinstance(info.get("motivo"), str):
            st = {**st, "imagem_noite": {**info, "motivo": mascarar_credenciais(info["motivo"])}}
        saida.append(st)
    return saida


def _canal_chave(valor):
    try:
        return int(valor)
    except (ValueError, TypeError):
        return str(valor)


def _manter_imagem_noite(anterior, novo, por_nome=False):
    """Agentes >= 1.1.11 não capturam a imagem da noite no backup (ela vem da Galeria): mantém o
    status `imagem_noite` do relatório anterior nos canais em que o novo relatório não o traz
    (em DIGIFORT/DEFENSE casa pelo nome)."""
    def chave(st):
        if por_nome:
            return (st.get("nome") or "").strip().lower()
        return _canal_chave(st.get("canal"))

    antigos = {}
    for st in (anterior or []):
        if isinstance(st, dict) and st.get("imagem_noite"):
            k = chave(st)
            if por_nome and not k:
                continue
            antigos[k] = st.get("imagem_noite")

    if not antigos:
        return novo
    saida = []
    for st in novo or []:
        if isinstance(st, dict) and "imagem_noite" not in st:
            k = chave(st)
            if not (por_nome and not k):
                info = antigos.get(k)
                if info:
                    st = {**st, "imagem_noite": info}
        saida.append(st)
    return saida


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
    # Agente >= 1.1.8 informa que está fazendo backup: o reinício espera ele terminar (senão o backup se perde)
    em_backup = bool((body.telemetry or {}).get("backup_em_andamento")) if body else False

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
        if (restart_flag and not em_backup) or backup_flag:
            break

        await asyncio.sleep(1)

    # Recarrega a máquina na sessão (ela foi liberada antes do polling)
    machine = db.get(Machine, machine_id)
    if machine is None:
        return PingResponse(status="ok", restart=False, backup=False)

    should_restart = bool(machine.restart_requested) and not em_backup
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
    result.error_message = mascarar_credenciais(result.error_message)
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

    vms = (nvr.tipo or "NVR").upper() in ("DIGIFORT", "DEFENSE")
    canal = body.canal
    camera = None
    if vms:
        # O canal do agente (ordem do export local) não é o da Galeria: pareia por nome/IP.
        # Sem par, a câmera nova ganha um canal livre.
        cameras_db = list(nvr.cameras_status)
        entrada = [{"canal": canal, "nome": body.nome, "ip": body.ip}]
        _, _, camera, canal = parear_cameras(cameras_db, entrada)[0]
    else:
        camera = db.query(NVRCamera).filter(NVRCamera.nvr_id == nvr.id, NVRCamera.canal == canal).first()

    if not camera:
        camera = NVRCamera(
            nvr_id=nvr.id,
            canal=canal,
            nome=body.nome,
            night_image_base64=body.image_base64,
            night_image_date=body.night_image_date
        )
        db.add(camera)
    else:
        if not vms:
            camera.nome = body.nome
        camera.night_image_base64 = body.image_base64
        camera.night_image_date = body.night_image_date

    if body.ip and not camera.ip:
        camera.ip = body.ip
        camera.modelo = body.modelo or camera.modelo or "Hikvision"

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
                vms = (nvr.tipo or "NVR").upper() in ("DIGIFORT", "DEFENSE")
                nvr.last_recording_status = _manter_imagem_noite(
                    nvr.last_recording_status, _limpar_motivos(r.cameras), por_nome=vms)
            if r.telemetria is not None:
                nvr.last_telemetry_status = r.telemetria
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

    # ── Rodada do Cliente (1 e-mail por rodada) ──
    # Antes de avançar a fila: a escolha da rodada usa o estado da fila no momento do relatório.
    # Falha aqui nunca pode derrubar o relatório do agente (o Backup já foi gravado).
    if machine.customer_id is not None:
        try:
            attach_report_to_run(db, machine, backup, body.trigger)
        except Exception:
            db.rollback()
            logger.exception("Falha ao associar o backup %s à rodada do cliente", backup.id)

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
            # Máquinas puladas não vão reportar: fecha a rodada assim que o último ZIP chegar
            finish_queue_run(db, customer)
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
    clean_machine = _sanitize_name(machine.name)
    raw_filename = file.filename or f"backup_{clean_device_type.lower()}_{date_str}.zip"
    if clean_machine.lower() not in raw_filename.lower():
        if raw_filename.startswith("backup_"):
            filename = f"backup_{clean_machine}_{raw_filename[7:]}"
        else:
            filename = f"backup_{clean_machine}_{raw_filename}"
    else:
        filename = raw_filename

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

    # Máquina com Cliente: o e-mail sai 1 vez por rodada (ao fechar), não por upload.
    # O JSON de resposta ao agente é o mesmo (email_sent=False aqui).
    if machine.customer_id is not None and backup.run_id is not None:
        return {"status": "ok", "zip_size": zip_size, "email_sent": False}

    # Send email (máquina sem Cliente)
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
        machine_id=machine.id,
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
