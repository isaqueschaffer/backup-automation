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
    CentralAlarmeNotificacaoResponse,
    CentralAlarmeNotificarUpdate,
    ConfiguracaoNotificacaoResponse,
    ConfiguracaoNotificacaoUpdate,
    EquipamentoAlarmesNotificacaoResponse,
    EquipamentoCamerasNotificacaoResponse,
    EquipamentoOltNotificacaoResponse,
    OltNotificarUpdate,
    NotificacaoPersonalizadaCreate,
    NotificacaoPersonalizadaResponse,
    NotificacaoPersonalizadaUpdate,
    NotificacaoResponse,
)
from services.camera_offline import segundos_offline
from services.escopo import filtrar_por_conta
from services.galeria_vms import status_por_camera
from services.notificacoes import TIPOS, id_central, verificar_alarmes_equipamento, verificar_olt_equipamento

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


# ─── Alarmes (centrais Intelbras do DEFENSE) ────────────────────────────────────────────────
# Opt-in por central (NVR.alarmes_notificar); ver services/notificacoes.py para a verificação.

def _centrais_para_resposta(nvr: NVR) -> list:
    marcadas = {str(c) for c in (nvr.alarmes_notificar or [])}
    saida = []
    for central in (nvr.last_alarm_status or {}).get("alarmes") or []:
        if not isinstance(central, dict):
            continue
        particoes = [p for p in central.get("particoes") or [] if isinstance(p, dict)]
        cid = id_central(central)
        saida.append({
            "central_id": cid, "nome": central.get("nome") or "Central sem nome",
            "conectada": central.get("status") == 1,
            "disparada": any(p.get("disparada") for p in particoes),
            "particoes_total": len(particoes),
            "particoes_desarmadas": sum(1 for p in particoes if not p.get("armada")),
            "notificar": cid in marcadas,
        })
    return sorted(saida, key=lambda c: c["nome"].lower())


def _alarmes_do_equipamento(nvr: NVR) -> dict:
    status = nvr.last_alarm_status or {}
    return {
        "nvr_id": nvr.id, "nvr_nome": nvr.name, "machine_id": nvr.machine_id, "machine_nome": nvr.machine.name,
        "atualizado_em": status.get("atualizado_em"), "erro": status.get("erro"),
        "centrais": _centrais_para_resposta(nvr),
    }


@router.get("/alarmes", response_model=List[EquipamentoAlarmesNotificacaoResponse])
def listar_alarmes_notificacao(
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
):
    """DEFENSE ativos com as centrais de alarme do último status do agente, para escolher quais notificam."""
    consulta = db.query(NVR).join(Machine, NVR.machine_id == Machine.id).filter(
        NVR.tipo == "DEFENSE", NVR.active == True, Machine.active == True
    )
    consulta = filtrar_por_conta(consulta, Machine.conta_id, ctx)
    return [_alarmes_do_equipamento(nvr) for nvr in consulta.order_by(Machine.name, NVR.name).all()]


@router.put("/alarmes/{nvr_id}/{central_id}", response_model=CentralAlarmeNotificacaoResponse)
def atualizar_central_notificacao(
    nvr_id: UUID,
    central_id: str,
    body: CentralAlarmeNotificarUpdate,
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(exigir_admin_conta),
):
    """Liga/desliga as notificações de uma central de alarme (admin da conta ou super admin)."""
    consulta = db.query(NVR).join(Machine, NVR.machine_id == Machine.id).filter(NVR.id == nvr_id, NVR.tipo == "DEFENSE")
    nvr = filtrar_por_conta(consulta, Machine.conta_id, ctx).first()
    if not nvr:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    central = next((c for c in _centrais_para_resposta(nvr) if c["central_id"] == central_id), None)
    if not central:
        raise HTTPException(status_code=404, detail="Central de alarme não encontrada")

    marcadas = [str(c) for c in (nvr.alarmes_notificar or []) if str(c) != central_id]
    if body.notificar:
        marcadas.append(central_id)
    nvr.alarmes_notificar = marcadas  # lista nova: o SQLAlchemy só detecta mudança em JSON por atribuição
    verificar_alarmes_equipamento(db, nvr)
    db.commit()
    return {**central, "notificar": body.notificar}


# ─── OLTs: ONUs offline e sinal óptico crítico ──────────────────────────────────────────────────
# Opt-in por equipamento OLT (NVR.olt_notificar); ver services/notificacoes.verificar_olt_equipamento.

def _olt_para_resposta(nvr: NVR) -> dict:
    status = nvr.olt_status or {}
    opcoes = nvr.olt_notificar or {}
    contagem = {"total": 0, "OFFLINE": 0, "SEM_ENERGIA": 0, "FALHA": 0, "sinal": 0}
    erros = []
    for olt in status.get("olts") or []:
        if not isinstance(olt, dict):
            continue
        if olt.get("erro"):
            erros.append(f"{olt.get('nome') or olt.get('ip') or nvr.name}: {olt['erro']}")
            continue
        for onu in olt.get("onus") or []:
            if not isinstance(onu, dict):
                continue
            contagem["total"] += 1
            if onu.get("estado") in contagem:
                contagem[onu["estado"]] += 1
            if onu.get("estado") == "ONLINE" and onu.get("qualidade") == "RUIM":
                contagem["sinal"] += 1
    return {
        "nvr_id": nvr.id, "nvr_nome": nvr.name, "machine_id": nvr.machine_id, "machine_nome": nvr.machine.name,
        "fabricante": (nvr.config_extra or {}).get("fabricante_olt"),
        "atualizado_em": status.get("atualizado_em"), "erro": " | ".join(erros)[:500] or None,
        "total_onus": contagem["total"], "onus_offline": contagem["OFFLINE"], "onus_sem_energia": contagem["SEM_ENERGIA"],
        "onus_fibra": contagem["FALHA"], "onus_sinal_critico": contagem["sinal"],
        "onu_offline": bool(opcoes.get("onu_offline")), "sinal_critico": bool(opcoes.get("sinal_critico")),
    }


@router.get("/olts", response_model=List[EquipamentoOltNotificacaoResponse])
def listar_olts_notificacao(
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
):
    """OLTs ativas com o resumo das ONUs do último status do agente, para escolher os avisos de cada uma."""
    consulta = db.query(NVR).join(Machine, NVR.machine_id == Machine.id).filter(
        NVR.tipo == "OLT", NVR.active == True, Machine.active == True
    )
    consulta = filtrar_por_conta(consulta, Machine.conta_id, ctx)
    return [_olt_para_resposta(nvr) for nvr in consulta.order_by(Machine.name, NVR.name).all()]


@router.put("/olts/{nvr_id}", response_model=EquipamentoOltNotificacaoResponse)
def atualizar_olt_notificacao(
    nvr_id: UUID,
    body: OltNotificarUpdate,
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(exigir_admin_conta),
):
    """Liga/desliga os avisos de ONU offline e/ou de sinal óptico crítico de uma OLT (admin da conta ou super admin)."""
    consulta = db.query(NVR).join(Machine, NVR.machine_id == Machine.id).filter(NVR.id == nvr_id, NVR.tipo == "OLT")
    nvr = filtrar_por_conta(consulta, Machine.conta_id, ctx).first()
    if not nvr:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    opcoes = dict(nvr.olt_notificar or {})
    for campo, valor in body.model_dump(exclude_none=True).items():
        opcoes[campo] = valor
    nvr.olt_notificar = opcoes  # dict novo: o SQLAlchemy só detecta mudança em JSON por atribuição
    verificar_olt_equipamento(db, nvr)
    db.commit()
    return _olt_para_resposta(nvr)


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
