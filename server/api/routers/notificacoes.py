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
from models import ConfiguracaoNotificacao, Notificacao, NotificacaoPersonalizada
from schemas import (
    ConfiguracaoNotificacaoResponse,
    ConfiguracaoNotificacaoUpdate,
    NotificacaoPersonalizadaCreate,
    NotificacaoPersonalizadaResponse,
    NotificacaoPersonalizadaUpdate,
    NotificacaoResponse,
)
from services.escopo import filtrar_por_conta
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
