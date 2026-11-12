"""Notificações operacionais mostradas no painel (pop-up ao logar + aba Notificações): cada conta vê só as suas
(isolamento por conta, REGRA-010); o super admin sem conta escolhida vê de todas. Geradas por services/notificacoes.py."""
from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from auth import Contexto, exigir_admin_conta, get_contexto
from database import get_db
from models import ConfiguracaoNotificacao, Machine, NVR, NVRCamera, Notificacao, NotificacaoPersonalizada
from schemas import (
    CameraNotificacaoResponse,
    CameraNotificarUpdate,
    ConfiguracaoNotificacaoResponse,
    ConfiguracaoNotificacaoUpdate,
    EquipamentoCamerasNotificacaoResponse,
    NotificacaoPersonalizadaCreate,
    NotificacaoPersonalizadaResponse,
    NotificacaoPersonalizadaUpdate,
    NotificacaoResponse,
)
from services.camera_offline import segundos_offline
from services.escopo import filtrar_por_conta
from services.galeria_vms import status_por_camera
from services.notificacoes import TIPOS

router = APIRouter(prefix="/api/v1/notificacoes", tags=["Notificações"])


@router.get("", response_model=List[NotificacaoResponse])
def listar_notificacoes(
    apenas_abertas: bool = True,
    apenas_popup: bool = False,
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
):
    """Notificações da conta do contexto (super admin sem conta escolhida vê de todas). Mais recentes primeiro.
    `apenas_popup=true` (usado pelo pop-up de login) tira as personalizadas cuja definição está com
    `mostrar_popup=false` — elas continuam aparecendo normalmente na aba Notificações."""
    consulta = db.query(Notificacao)
    if apenas_abertas:
        consulta = consulta.filter(Notificacao.resolvido_em.is_(None))
    if apenas_popup:
        consulta = consulta.outerjoin(NotificacaoPersonalizada, Notificacao.definicao_id == NotificacaoPersonalizada.id).filter(
            or_(Notificacao.tipo != "PERSONALIZADA", NotificacaoPersonalizada.mostrar_popup == True)
        )
    consulta = filtrar_por_conta(consulta, Notificacao.conta_id, ctx)
    return consulta.order_by(Notificacao.criado_em.desc()).limit(200).all()


@router.get("/config", response_model=List[ConfiguracaoNotificacaoResponse])
def listar_config(
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
):
    """Preferência da conta para cada tipo de notificação (tipo ausente = ativo)."""
    if not ctx.conta_id:
        return [{"tipo": t, "ativo": True} for t in TIPOS]
    salvas = {
        c.tipo: c.ativo
        for c in db.query(ConfiguracaoNotificacao).filter(ConfiguracaoNotificacao.conta_id == ctx.conta_id).all()
    }
    return [{"tipo": t, "ativo": salvas.get(t, True)} for t in TIPOS]


@router.put("/config/{tipo}", response_model=ConfiguracaoNotificacaoResponse)
def atualizar_config(
    tipo: str,
    body: ConfiguracaoNotificacaoUpdate,
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(exigir_admin_conta),
):
    """Liga/desliga um tipo de notificação para a conta (admin da conta ou super admin)."""
    if tipo not in TIPOS:
        raise HTTPException(status_code=404, detail="Tipo de notificação inválido")
    row = db.query(ConfiguracaoNotificacao).filter_by(conta_id=ctx.conta_id, tipo=tipo).first()
    if row:
        row.ativo = body.ativo
    else:
        row = ConfiguracaoNotificacao(conta_id=ctx.conta_id, tipo=tipo, ativo=body.ativo)
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ─── Câmeras offline (NVR, DIGIFORT, DEFENSE) ───────────────────────────────────────────────
# Opt-in por câmera (NVRCamera.notificar_offline); ver services/notificacoes.py para a verificação periódica.

def _camera_para_resposta(camera: NVRCamera, status_por_camera_id: dict, agora: datetime) -> dict:
    st = status_por_camera_id.get(camera.id)
    seg, aprox = segundos_offline(st, agora) if st else (None, False)
    return {
        "id": camera.id, "nome": camera.nome, "notificar_offline": camera.notificar_offline,
        "status_comunicacao": (st or {}).get("status_comunicacao"),
        "offline_segundos": seg, "offline_aprox": aprox,
    }


@router.get("/cameras", response_model=List[EquipamentoCamerasNotificacaoResponse])
def listar_cameras_notificacao(
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
):
    """Equipamentos ativos com câmeras (NVR, DIGIFORT, DEFENSE), para escolher quais notificar quando
    ficarem offline. Agrupado por máquina e equipamento (`machine_id`/`nvr_id` em cada item)."""
    consulta = db.query(NVR).join(Machine, NVR.machine_id == Machine.id).filter(
        NVR.tipo.in_(("NVR", "DIGIFORT", "DEFENSE")), NVR.active == True, Machine.active == True
    )
    consulta = filtrar_por_conta(consulta, Machine.conta_id, ctx)
    agora = datetime.utcnow()
    saida = []
    for nvr in consulta.order_by(Machine.name, NVR.name).all():
        cameras = list(nvr.cameras_status)
        if not cameras:
            continue
        status_por_camera_id = status_por_camera(cameras, nvr.tipo, nvr.last_recording_status or [])
        saida.append({
            "nvr_id": nvr.id, "nvr_nome": nvr.name, "nvr_tipo": nvr.tipo,
            "machine_id": nvr.machine_id, "machine_nome": nvr.machine.name,
            "cameras": [
                _camera_para_resposta(c, status_por_camera_id, agora)
                for c in sorted(cameras, key=lambda c: (c.nome or "").lower())
            ],
        })
    return saida


@router.put("/cameras/{camera_id}", response_model=CameraNotificacaoResponse)
def atualizar_camera_notificacao(
    camera_id: UUID,
    body: CameraNotificarUpdate,
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(exigir_admin_conta),
):
    """Liga/desliga a notificação de offline de uma câmera (admin da conta ou super admin)."""
    consulta = (
        db.query(NVRCamera).join(NVR, NVRCamera.nvr_id == NVR.id).join(Machine, NVR.machine_id == Machine.id)
        .filter(NVRCamera.id == camera_id)
    )
    camera = filtrar_por_conta(consulta, Machine.conta_id, ctx).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Câmera não encontrada")
    camera.notificar_offline = body.notificar_offline
    db.commit()
    db.refresh(camera)

    agora = datetime.utcnow()
    nvr = camera.nvr
    status_por_camera_id = status_por_camera(list(nvr.cameras_status), nvr.tipo, nvr.last_recording_status or [])
    return _camera_para_resposta(camera, status_por_camera_id, agora)


# ─── Notificações personalizadas (criadas pelo usuário) ───────────────────────────────────────

def _obter_personalizada(db: Session, ctx: Contexto, id: UUID) -> NotificacaoPersonalizada:
    consulta = filtrar_por_conta(db.query(NotificacaoPersonalizada).filter(NotificacaoPersonalizada.id == id),
                                 NotificacaoPersonalizada.conta_id, ctx)
    definicao = consulta.first()
    if not definicao:
        raise HTTPException(status_code=404, detail="Notificação personalizada não encontrada")
    return definicao


@router.get("/personalizadas", response_model=List[NotificacaoPersonalizadaResponse])
def listar_personalizadas(
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
):
    """Definições personalizadas da conta (qualquer papel pode ver; só ADMIN cria/edita/apaga)."""
    consulta = filtrar_por_conta(db.query(NotificacaoPersonalizada), NotificacaoPersonalizada.conta_id, ctx)
    return consulta.order_by(NotificacaoPersonalizada.criado_em.desc()).all()


@router.post("/personalizadas", response_model=NotificacaoPersonalizadaResponse, status_code=201)
def criar_personalizada(
    body: NotificacaoPersonalizadaCreate,
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(exigir_admin_conta),
):
    definicao = NotificacaoPersonalizada(conta_id=ctx.conta_id, **body.model_dump())
    db.add(definicao)
    db.commit()
    db.refresh(definicao)
    return definicao


@router.put("/personalizadas/{id}", response_model=NotificacaoPersonalizadaResponse)
def atualizar_personalizada(
    id: UUID,
    body: NotificacaoPersonalizadaUpdate,
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(exigir_admin_conta),
):
    definicao = _obter_personalizada(db, ctx, id)
    for campo, valor in body.model_dump().items():
        setattr(definicao, campo, valor)
    db.commit()
    db.refresh(definicao)
    return definicao


@router.delete("/personalizadas/{id}", status_code=204)
def apagar_personalizada(
    id: UUID,
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(exigir_admin_conta),
):
    definicao = _obter_personalizada(db, ctx, id)
    # fecha o alerta aberto vinculado (se houver) antes de apagar a definição; o histórico já resolvido fica
    # (definicao_id vira NULL pelo ON DELETE SET NULL do banco)
    db.query(Notificacao).filter(
        Notificacao.definicao_id == id, Notificacao.resolvido_em.is_(None)
    ).update({"resolvido_em": datetime.utcnow()})
    db.delete(definicao)
    db.commit()
