"""
Router de Equipamentos.
Substitui o antigo router de NVRs, agora suportando múltiplos tipos:
NVR, OLT, ONU, PABX (e futuros).
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from auth import verify_admin_token
from database import get_db
from models import Client, NVR, NVRCamera
from schemas import NVRCreate, NVRUpdate, NVRResponse, TIPOS_EQUIPAMENTO, NVRCameraResponse, NVRCameraSetPerfect
from services.crypto_service import encrypt

router = APIRouter(prefix="/api/v1/clients/{client_id}/equipamentos", tags=["equipamentos"])


def _get_client_or_404(client_id: UUID, db: Session) -> Client:
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.get("", response_model=List[NVRResponse], dependencies=[Depends(verify_admin_token)])
def list_equipamentos(
    client_id: UUID,
    tipo: Optional[str] = Query(None, description="Filtrar por tipo: NVR, OLT, ONU, PABX"),
    db: Session = Depends(get_db),
):
    """Lista todos os equipamentos de um cliente, com filtro opcional por tipo."""
    _get_client_or_404(client_id, db)
    q = db.query(NVR).filter(NVR.client_id == client_id)
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
def create_equipamento(client_id: UUID, body: NVRCreate, db: Session = Depends(get_db)):
    """Cadastra um novo equipamento para um cliente."""
    _get_client_or_404(client_id, db)

    tipo = (body.tipo or "NVR").upper()
    if tipo not in TIPOS_EQUIPAMENTO:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo inválido. Tipos suportados: {TIPOS_EQUIPAMENTO}",
        )

    equipamento = NVR(
        client_id=client_id,
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
    client_id: UUID,
    equipamento_id: UUID,
    body: NVRUpdate,
    db: Session = Depends(get_db),
):
    """Atualiza um equipamento existente."""
    eq = db.query(NVR).filter(NVR.id == equipamento_id, NVR.client_id == client_id).first()
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
def delete_equipamento(client_id: UUID, equipamento_id: UUID, db: Session = Depends(get_db)):
    """Remove um equipamento."""
    eq = db.query(NVR).filter(NVR.id == equipamento_id, NVR.client_id == client_id).first()
    if not eq:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    db.delete(eq)
    db.commit()

from schemas import RTSPTestResponse
@router.post(
    "/{equipamento_id}/test-rtsp",
    response_model=RTSPTestResponse,
    dependencies=[Depends(verify_admin_token)],
)
async def test_equipamento_rtsp(client_id: UUID, equipamento_id: UUID, canal: Optional[int] = Query(None), db: Session = Depends(get_db)):
    """Testa a conexao RTSP delegando a tarefa ao agente local via long-polling."""
    eq = db.query(NVR).filter(NVR.id == equipamento_id, NVR.client_id == client_id).first()
    if not eq:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    
    from services.crypto_service import decrypt
    import asyncio
    from routers.agent import pending_rtsp_tasks

    try:
        senha_pura = decrypt(eq.password) if eq.password else "navarro@123"
    except:
        senha_pura = eq.password or "navarro@123"

    client_id_str = str(client_id)
    event = asyncio.Event()

    task_data = {
        "equipamento_id": str(eq.id),
        "ip": eq.ip.strip(),
        "modelo": (eq.config_extra or {}).get("modelo", ""),
        "username": eq.username or "admin",
        "password": senha_pura,
        "canal": canal,
    }

    pending_rtsp_tasks[client_id_str] = {
        "task": task_data,
        "event": event,
        "result": None,
        "sent": False
    }

    try:
        # Wait up to 35 seconds for the agent to reply (Dashboard UI expects ~30s max usually, we give 35s)
        await asyncio.wait_for(event.wait(), timeout=35.0)
    except asyncio.TimeoutError:
        # Se timeout, removemos a tarefa e retornamos erro
        if client_id_str in pending_rtsp_tasks:
            del pending_rtsp_tasks[client_id_str]
        return RTSPTestResponse(success=False, error_message="FALHA: O Agente local não respondeu ao comando de teste a tempo. Verifique se o agente está online.")
    
    result = pending_rtsp_tasks[client_id_str].get("result")
    if client_id_str in pending_rtsp_tasks:
        del pending_rtsp_tasks[client_id_str]
        
    if not result:
        return RTSPTestResponse(success=False, error_message="FALHA: Agente respondeu, mas sem dados válidos.")

    return result


# ─── NVR Cameras Gallery ───────────────────────────────────────────────────

@router.get("/{id}/cameras", response_model=List[NVRCameraResponse])
def get_nvr_cameras(
    client_id: UUID,
    id: UUID,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin_token)
):
    """Retorna todas as câmeras de um NVR específico (com suas imagens)."""
    nvr = db.query(NVR).filter(NVR.id == id, NVR.client_id == client_id).first()
    if not nvr:
        raise HTTPException(status_code=404, detail="NVR não encontrado")
    
    cameras_db = db.query(NVRCamera).filter(NVRCamera.nvr_id == id).order_by(NVRCamera.canal).all()
    db_dict = {c.canal: c for c in cameras_db}
    
    report_status = nvr.last_recording_status or []
    
    canais_set = set(db_dict.keys())
    for st in report_status:
        try:
            canais_set.add(int(st["canal"]))
        except ValueError:
            pass

    merged_cameras = []
    for ch in sorted(canais_set):
        c_db = db_dict.get(ch)
        c_report = next((x for x in report_status if str(x.get("canal")) == str(ch)), None)
        
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
    client_id: UUID,
    id: UUID,
    payload: NVRCameraSetPerfect,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin_token)
):
    """Salva a 'Imagem Perfeita' de um canal específico."""
    nvr = db.query(NVR).filter(NVR.id == id, NVR.client_id == client_id).first()
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
