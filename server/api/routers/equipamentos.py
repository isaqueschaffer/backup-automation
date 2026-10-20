"""
Router de Equipamentos.
Substitui o antigo router de NVRs, agora suportando múltiplos tipos:
NVR, OLT, ONU, PABX (e futuros).
"""
import asyncio
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from auth import verify_admin_token
from database import get_db
from models import Machine, NVR, NVRCamera
from routers.agent import pending_rtsp_tasks
from schemas import (
    NVRCreate, NVRUpdate, NVRResponse, TIPOS_EQUIPAMENTO, NVRCameraResponse,
    NVRCameraSetPerfect, RTSPTestResponse,
)
from services.crypto_service import encrypt, decrypt

router = APIRouter(prefix="/api/v1/machines/{machine_id}/equipamentos", tags=["Equipamentos"])


def _canal_int(valor):
    # Motorola (agentes < 1.1.4) reportava o canal como GUID "{0000000N-0000-...}"
    try:
        return int(valor)
    except (ValueError, TypeError):
        try:
            return int(str(valor).strip("{}").split("-")[0], 16)
        except ValueError:
            return None


def _get_machine_or_404(machine_id: UUID, db: Session) -> Machine:
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Máquina não encontrada")
    return machine


@router.get("", response_model=List[NVRResponse], dependencies=[Depends(verify_admin_token)])
def list_equipamentos(
    machine_id: UUID,
    tipo: Optional[str] = Query(None, description="Filtrar por tipo: NVR, OLT, ONU, PABX"),
    db: Session = Depends(get_db),
):
    """Lista todos os equipamentos de uma máquina, com filtro opcional por tipo."""
    _get_machine_or_404(machine_id, db)
    q = db.query(NVR).filter(NVR.machine_id == machine_id)
    if tipo:
        if tipo.upper() not in TIPOS_EQUIPAMENTO:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo inválido. Tipos suportados: {TIPOS_EQUIPAMENTO}",
            )
        q = q.filter(NVR.tipo == tipo.upper())
    return q.all()


@router.post(
    "",
    response_model=NVRResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_token)],
)
def create_equipamento(machine_id: UUID, body: NVRCreate, db: Session = Depends(get_db)):
    """Cadastra um novo equipamento para uma máquina."""
    _get_machine_or_404(machine_id, db)

    tipo = (body.tipo or "NVR").upper()
    if tipo not in TIPOS_EQUIPAMENTO:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo inválido. Tipos suportados: {TIPOS_EQUIPAMENTO}",
        )

    equipamento = NVR(
        machine_id=machine_id,
        tipo=tipo,
        name=body.name,
        ip=body.ip,
        username=body.username,
        password=encrypt(body.password),
        config_extra=body.config_extra,
        active=body.active,
    )
    db.add(equipamento)
    db.commit()
    db.refresh(equipamento)
    return equipamento


@router.put(
    "/{equipamento_id}",
    response_model=NVRResponse,
    dependencies=[Depends(verify_admin_token)],
)
def update_equipamento(
    machine_id: UUID,
    equipamento_id: UUID,
    body: NVRUpdate,
    db: Session = Depends(get_db),
):
    """Atualiza um equipamento existente."""
    eq = db.query(NVR).filter(NVR.id == equipamento_id, NVR.machine_id == machine_id).first()
    if not eq:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")

    for field, value in body.model_dump(exclude_none=True).items():
        if field == "password" and value:
            eq.password = encrypt(value)
        elif field == "tipo" and value:
            if value.upper() not in TIPOS_EQUIPAMENTO:
                raise HTTPException(
                    status_code=400,
                    detail=f"Tipo inválido. Tipos suportados: {TIPOS_EQUIPAMENTO}",
                )
            eq.tipo = value.upper()
        else:
            setattr(eq, field, value)

    db.commit()
    db.refresh(eq)
    return eq


@router.delete(
    "/{equipamento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_admin_token)],
)
def delete_equipamento(machine_id: UUID, equipamento_id: UUID, db: Session = Depends(get_db)):
    """Remove um equipamento."""
    eq = db.query(NVR).filter(NVR.id == equipamento_id, NVR.machine_id == machine_id).first()
    if not eq:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    db.delete(eq)
    db.commit()


@router.post(
    "/{equipamento_id}/test-rtsp",
    response_model=RTSPTestResponse,
    dependencies=[Depends(verify_admin_token)],
)
async def test_equipamento_rtsp(
    machine_id: UUID,
    equipamento_id: UUID,
    canal: Optional[int] = Query(None),
    modo: str = Query("ao_vivo", pattern="^(ao_vivo|referencia|noite)$"),
    nome: Optional[str] = Query(None, max_length=200),
    db: Session = Depends(get_db),
):
    """Captura um frame delegando a tarefa ao agente local via long-polling.

    modo "ao_vivo": frame ao vivo (teste de conexão).
    modo "referencia": ao vivo; se a câmera estiver offline, o frame mais recente da gravação (agente >= 1.1.6).
    modo "noite": madrugada mais recente com gravação; o servidor já salva como imagem da noite do canal.
    """
    eq = db.query(NVR).filter(NVR.id == equipamento_id, NVR.machine_id == machine_id).first()
    if not eq:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    if modo != "ao_vivo" and not canal:
        raise HTTPException(status_code=422, detail="Informe o canal para capturar da gravação.")

    machine_id_str = str(machine_id)

    # Só 1 teste RTSP por máquina por vez (o dicionário é indexado pela máquina).
    # LIMITAÇÃO: o estado fica na memória do processo; requer 1 worker uvicorn.
    if machine_id_str in pending_rtsp_tasks:
        raise HTTPException(
            status_code=409,
            detail="Já existe um teste RTSP em andamento para esta máquina. Aguarde a conclusão e tente novamente.",
        )

    try:
        senha_pura = decrypt(eq.password) if eq.password else "navarro@123"
    except Exception:
        senha_pura = eq.password or "navarro@123"

    event = asyncio.Event()

    marca = (eq.config_extra or {}).get("marca", "") or ""
    if not marca and any(isinstance(st, dict) and st.get("canal_guid") for st in (eq.last_recording_status or [])):
        # NVR sem marca cadastrada: o backup detecta sozinho, mas o teste RTSP precisa saber.
        # Só NVR Motorola (NVMS-9000) reporta `canal_guid` no relatório de gravação.
        marca = "Motorola"

    task_data = {
        "equipamento_id": str(eq.id),
        "ip": eq.ip.strip(),
        "modelo": (eq.config_extra or {}).get("modelo", ""),
        "marca": marca,
        "username": eq.username or "admin",
        "password": senha_pura,
        "canal": canal,
        "modo": modo,  # agentes < 1.1.6 ignoram e capturam ao vivo
    }

    entry = {
        "task": task_data,
        "event": event,
        "result": None,
        "sent": False
    }
    pending_rtsp_tasks[machine_id_str] = entry
    # Libera a conexão do banco durante a espera (a captura pela gravação pode levar ~2 min)
    db.close()

    # Ao vivo: até 35s. Pela gravação: busca dia a dia no NVR (o agente desiste em ~100s + envio).
    espera = 35.0 if modo == "ao_vivo" else 130.0
    try:
        await asyncio.wait_for(event.wait(), timeout=espera)
    except asyncio.TimeoutError:
        return RTSPTestResponse(success=False, error_message="FALHA: O Agente local não respondeu ao comando a tempo. Verifique se o agente está online.")
    finally:
        # Sempre remove a tarefa (timeout, cancelamento ou sucesso); pop evita KeyError
        if pending_rtsp_tasks.get(machine_id_str) is entry:
            pending_rtsp_tasks.pop(machine_id_str, None)

    result = entry.get("result")
    if not result:
        return RTSPTestResponse(success=False, error_message="FALHA: Agente respondeu, mas sem dados válidos.")

    if modo == "noite" and result.success:
        if not result.horario:
            # Agente antigo capturou ao vivo: não é imagem da noite
            return RTSPTestResponse(success=False, error_message="Atualize o agente desta máquina para a versão 1.1.6 ou superior para capturar a imagem da noite pelo painel.")
        _salvar_imagem_noite(db, equipamento_id, canal, nome, result)
    elif modo == "noite":
        # Mostra o motivo na galeria (a imagem anterior, se houver, é mantida)
        nvr = db.query(NVR).filter(NVR.id == equipamento_id).first()
        if nvr is not None:
            _marcar_imagem_noite(nvr, canal, {"status": "FALHA", "motivo": result.error_message, "horario": None})
            db.commit()

    return result


def _salvar_imagem_noite(db: Session, nvr_id: UUID, canal: int, nome: Optional[str], result: RTSPTestResponse) -> None:
    """Salva a imagem da noite capturada pelo painel, como o envio do backup faria."""
    try:
        horario = datetime.fromisoformat(result.horario)  # horário exibido no NVR (naive), igual ao backup
    except ValueError:
        horario = None
    nvr = db.query(NVR).filter(NVR.id == nvr_id).first()
    if nvr is None:
        return
    camera = db.query(NVRCamera).filter(NVRCamera.nvr_id == nvr_id, NVRCamera.canal == canal).first()
    if camera is None:
        camera = NVRCamera(nvr_id=nvr_id, canal=canal, nome=nome or f"Canal {canal}")
        db.add(camera)
    elif nome:
        camera.nome = nome
    camera.night_image_base64 = result.image_base64
    camera.night_image_date = horario

    _marcar_imagem_noite(nvr, canal, {"status": "OK", "motivo": None, "horario": result.horario})
    db.commit()


def _marcar_imagem_noite(nvr: NVR, canal: int, info: dict) -> None:
    """Grava o status da captura da noite do canal em `last_recording_status` (lido pela galeria)."""
    status_rel = []
    for st in nvr.last_recording_status or []:
        if isinstance(st, dict) and _canal_int(st.get("canal")) == canal:
            st = {**st, "imagem_noite": info}
        status_rel.append(st)
    nvr.last_recording_status = status_rel


# ─── NVR Cameras Gallery ───────────────────────────────────────────────────

@router.get("/{id}/cameras", response_model=List[NVRCameraResponse])
def get_nvr_cameras(
    machine_id: UUID,
    id: UUID,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin_token)
):
    """Retorna todas as câmeras de um NVR específico (com suas imagens)."""
    nvr = db.query(NVR).filter(NVR.id == id, NVR.machine_id == machine_id).first()
    if not nvr:
        raise HTTPException(status_code=404, detail="NVR não encontrado")
    
    cameras_db = db.query(NVRCamera).filter(NVRCamera.nvr_id == id).order_by(NVRCamera.canal).all()
    db_dict = {c.canal: c for c in cameras_db}
    
    report_status = nvr.last_recording_status or []

    report_by_ch = {}
    for st in report_status:
        ch_int = _canal_int(st.get("canal"))
        if ch_int is not None:
            report_by_ch[ch_int] = st

    canais_set = set(db_dict.keys()) | set(report_by_ch.keys())

    merged_cameras = []
    for ch in sorted(canais_set):
        c_db = db_dict.get(ch)
        c_report = report_by_ch.get(ch)
        
        obj = {
            "id": c_db.id if c_db else None,
            "nvr_id": id,
            "canal": ch,
            "nome": (c_report.get("nome") if c_report else None) or (c_db.nome if c_db else f"Canal {ch}"),
            "perfect_image_base64": c_db.perfect_image_base64 if c_db else None,
            "night_image_base64": c_db.night_image_base64 if c_db else None,
            "night_image_date": c_db.night_image_date if c_db else None,
            "updated_at": c_db.updated_at if c_db else None,
            "status_comunicacao": c_report.get("status_comunicacao") if c_report else None,
            "status_gravacao": c_report.get("status_gravacao") if c_report else None,
            "captura_status": None,
            "captura_motivo": None,
            "captura_horario": None,
        }
        
        if c_report and "imagem_noite" in c_report:
            obj["captura_status"] = c_report["imagem_noite"].get("status")
            obj["captura_motivo"] = c_report["imagem_noite"].get("motivo")
            obj["captura_horario"] = c_report["imagem_noite"].get("horario")
        else:
            if obj["night_image_base64"]:
                obj["captura_status"] = "OK"
                
        merged_cameras.append(obj)
        
    return merged_cameras


@router.post("/{id}/cameras/perfect-image", response_model=NVRCameraResponse)
def set_perfect_image(
    machine_id: UUID,
    id: UUID,
    payload: NVRCameraSetPerfect,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin_token)
):
    """Salva a 'Imagem Perfeita' de um canal específico."""
    nvr = db.query(NVR).filter(NVR.id == id, NVR.machine_id == machine_id).first()
    if not nvr:
        raise HTTPException(status_code=404, detail="NVR não encontrado")

    camera = db.query(NVRCamera).filter(NVRCamera.nvr_id == id, NVRCamera.canal == payload.canal).first()
    if not camera:
        camera = NVRCamera(
            nvr_id=id,
            canal=payload.canal,
            nome=payload.nome,
            perfect_image_base64=payload.image_base64
        )
        db.add(camera)
    else:
        camera.nome = payload.nome
        camera.perfect_image_base64 = payload.image_base64

    db.commit()
    db.refresh(camera)
    return camera
