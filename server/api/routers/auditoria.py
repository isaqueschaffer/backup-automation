"""Auditoria: o que usuários e admins alteraram pelo painel (equipamentos, câmeras, máquinas, comandos...).

Lê os eventos de `agent_logs` que têm `usuario` preenchido (gravados por `services.agent_logs.registrar_alteracao`),
sempre limitados às máquinas da conta do contexto (REGRA-010)."""
from datetime import date, datetime, time, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from auth import Contexto, get_contexto
from database import get_db
from models import AgentLog, Machine
from schemas import AuditoriaItem, PaginatedAuditoria
from services.agent_logs import DIAS_RETENCAO_AUDITORIA
from services.escopo import filtrar_por_conta

router = APIRouter(prefix="/api/v1/auditoria", tags=["Auditoria"])


def _exigir_acesso(ctx: Contexto) -> None:
    """Só ADMIN da conta e super admin veem quem alterou o quê; VISUALIZADOR e LEITURA não."""
    if ctx.papel in ("LEITURA", "VISUALIZADOR"):
        raise HTTPException(status_code=403, detail="Seu perfil não tem acesso à auditoria.")


def _consulta_base(db: Session, ctx: Contexto):
    maquinas = filtrar_por_conta(db.query(Machine.id), Machine.conta_id, ctx)
    return db.query(AgentLog).filter(AgentLog.usuario.isnot(None), AgentLog.machine_id.in_(maquinas))


@router.get("", response_model=PaginatedAuditoria)
def listar_auditoria(
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=100),
    machine_id: Optional[UUID] = None,
    customer_id: Optional[UUID] = None,
    usuario: Optional[str] = Query(None, max_length=255),
    q: Optional[str] = Query(None, max_length=100),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    ctx: Contexto = Depends(get_contexto),
):
    _exigir_acesso(ctx)
    consulta = _consulta_base(db, ctx).options(joinedload(AgentLog.machine).joinedload(Machine.customer))

    if machine_id:
        consulta = consulta.filter(AgentLog.machine_id == machine_id)
    if customer_id:
        consulta = consulta.filter(AgentLog.machine_id.in_(db.query(Machine.id).filter(Machine.customer_id == customer_id)))
    if usuario:
        consulta = consulta.filter(AgentLog.usuario == usuario)
    if q:
        escapado = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        consulta = consulta.filter(AgentLog.message.ilike(f"%{escapado}%", escape="\\"))
    # Mesma convenção da lista de backups: o dia vai de 00:00 a 23:59 no horário do Brasil (UTC-3)
    if date_from:
        consulta = consulta.filter(AgentLog.created_at >= datetime.combine(date_from, time.min) + timedelta(hours=3))
    if date_to:
        consulta = consulta.filter(AgentLog.created_at <= datetime.combine(date_to, time.max) + timedelta(hours=3))

    total = consulta.count()
    registros = consulta.order_by(AgentLog.created_at.desc()).offset((page - 1) * size).limit(size).all()
    itens: List[AuditoriaItem] = []
    for r in registros:
        maquina = r.machine
        cliente = maquina.customer if maquina else None
        itens.append(AuditoriaItem(
            id=r.id,
            created_at=r.created_at,
            usuario=r.usuario,
            message=r.message,
            equipamento=r.equipamento,
            machine_id=r.machine_id,
            machine_name=maquina.name if maquina else None,
            customer_id=cliente.id if cliente else None,
            customer_name=cliente.name if cliente else None,
        ))
    return PaginatedAuditoria(
        items=itens, total=total, page=page, pages=(total + size - 1) // size or 1,
        dias_retencao=DIAS_RETENCAO_AUDITORIA,
    )


@router.get("/usuarios", response_model=List[str])
def listar_usuarios_da_auditoria(db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    """Quem já fez alguma alteração nas máquinas da conta (para o filtro de usuário)."""
    _exigir_acesso(ctx)
    base = _consulta_base(db, ctx).with_entities(AgentLog.usuario).distinct().order_by(AgentLog.usuario)
    return [u for (u,) in base.all()]
