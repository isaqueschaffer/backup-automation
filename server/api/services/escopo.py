"""Escopo por conta: toda consulta do painel passa por aqui. Recurso de outra conta = 404."""
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from auth import Contexto
from models import Customer, Machine
from services.contas import obter_conta_plataforma_id


def filtrar_por_conta(consulta, coluna_conta_id, ctx: Contexto):
    """Aplica o filtro da conta do contexto (super admin sem conta escolhida vê tudo)."""
    if ctx.conta_id is not None:
        consulta = consulta.filter(coluna_conta_id == ctx.conta_id)
    return consulta


# ── Isolamento por máquina (usuário VISUALIZADOR/LEITURA com máquinas marcadas pelo admin) ──────────

def maquina_permitida(ctx: Contexto, machine_id) -> bool:
    """True se o usuário vê essa máquina (sem restrição, vê todas as da conta)."""
    return ctx.maquinas_permitidas is None or machine_id in ctx.maquinas_permitidas


def filtrar_maquinas(consulta, coluna_machine_id, ctx: Contexto):
    """Restringe a consulta às máquinas liberadas para o usuário (não muda nada para quem vê todas)."""
    if ctx.maquinas_permitidas is not None:
        consulta = consulta.filter(coluna_machine_id.in_(list(ctx.maquinas_permitidas)))
    return consulta


def maquinas_visiveis(ctx: Contexto, maquinas) -> list:
    return [m for m in maquinas if maquina_permitida(ctx, m.id)]


def ve_cliente_inteiro(ctx: Contexto, cliente: Customer) -> bool:
    """O usuário vê todas as máquinas do Cliente (exigido para o que junta dados de todas: ZIP do Cliente, rodadas,
    dashboard)."""
    return ctx.maquinas_permitidas is None or all(m.id in ctx.maquinas_permitidas for m in cliente.machines)


def exigir_cliente_inteiro(ctx: Contexto, cliente: Customer) -> None:
    if not ve_cliente_inteiro(ctx, cliente):
        raise HTTPException(status_code=403, detail="Seu usuário não tem acesso a todas as máquinas deste cliente.")


def obter_cliente(db: Session, ctx: Contexto, customer_id: UUID, consulta=None) -> Customer:
    consulta = consulta if consulta is not None else db.query(Customer)
    cliente = filtrar_por_conta(consulta.filter(Customer.id == customer_id), Customer.conta_id, ctx).first()
    if not cliente or (ctx.maquinas_permitidas is not None and not maquinas_visiveis(ctx, cliente.machines)):
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return cliente


def obter_maquina(db: Session, ctx: Contexto, machine_id: UUID, consulta=None) -> Machine:
    consulta = consulta if consulta is not None else db.query(Machine)
    maquina = filtrar_por_conta(consulta.filter(Machine.id == machine_id), Machine.conta_id, ctx).first()
    if not maquina or not maquina_permitida(ctx, maquina.id):
        raise HTTPException(status_code=404, detail="Máquina não encontrada")
    return maquina


def conta_para_criacao(db: Session, ctx: Contexto) -> UUID:
    """Conta que recebe um Cliente/Máquina novo: a do contexto; super admin sem conta usa a da plataforma."""
    conta_id: Optional[UUID] = ctx.conta_id or obter_conta_plataforma_id(db)
    if conta_id is None:
        raise HTTPException(status_code=400, detail="Selecione uma conta.")
    return conta_id
