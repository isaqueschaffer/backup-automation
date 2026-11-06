"""Contas (inquilinos): validade do plano e conta da plataforma."""
import logging
import math
from datetime import datetime, timedelta
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Conta, ContaRenovacao, Customer, Machine, Plano, Setting, Usuario

logger = logging.getLogger("trilan.contas")

TIPOS_CONTA = ("INTEGRADOR", "CLIENTE_FINAL")
PAPEIS = ("SUPER_ADMIN", "ADMIN", "LEITURA")
# Faixa de aviso no painel a partir de DIAS_AVISO; vermelha a partir de DIAS_CRITICO
DIAS_AVISO = 15
DIAS_CRITICO = 3
STATUS_BLOQUEIO = ("VENCIDA", "SUSPENSA")
# Settings: id da conta que recebe os dados anteriores ao multi-contas (conta da plataforma)
SETTING_CONTA_PLATAFORMA = "conta_plataforma_id"
NOME_CONTA_PLATAFORMA = "Trilan"
PLANOS_INICIAIS = (("Teste", 15), ("Mensal", 30), ("Trimestral", 90), ("Semestral", 180), ("Anual", 365))


def dias_restantes(expira_em: Optional[datetime], agora: datetime) -> Optional[int]:
    """Dias até o vencimento, arredondados para cima (1 = vence em até 24 h).
    Vencida: 0 nas primeiras 24 h depois do vencimento e negativo depois (-1, -2...)."""
    if expira_em is None:
        return None
    segundos = (expira_em - agora).total_seconds()
    if segundos > 0:
        return math.ceil(segundos / 86400)
    return -int(-segundos // 86400)


def status_da_conta(conta, agora: Optional[datetime] = None) -> Tuple[str, Optional[int]]:
    """(status, dias_restantes). Status: SUSPENSA, VITALICIA, VENCIDA, CRITICO, AVISO ou OK."""
    agora = agora or datetime.utcnow()
    dias = dias_restantes(conta.expira_em, agora)
    if not conta.ativo:
        return "SUSPENSA", dias
    if dias is None:
        return "VITALICIA", None
    if conta.expira_em <= agora:
        return "VENCIDA", dias
    if dias <= DIAS_CRITICO:
        return "CRITICO", dias
    if dias <= DIAS_AVISO:
        return "AVISO", dias
    return "OK", dias


def conta_bloqueada(conta, agora: Optional[datetime] = None) -> bool:
    """Conta vencida ou suspensa: painel só leitura e backups parados."""
    return status_da_conta(conta, agora)[0] in STATUS_BLOQUEIO


def obter_conta_plataforma_id(db: Session) -> Optional[UUID]:
    """Id da conta da plataforma (Settings), ou None se ausente/inválido."""
    row = db.query(Setting).filter(Setting.key == SETTING_CONTA_PLATAFORMA).first()
    if not row or not row.value:
        return None
    try:
        return UUID(row.value)
    except (ValueError, AttributeError, TypeError):
        return None


def garantir_conta_plataforma(db: Session) -> UUID:
    """Garante a conta da plataforma (INTEGRADOR, sem validade) e grava o id em Settings. Não faz commit."""
    conta_id = obter_conta_plataforma_id(db)
    if conta_id is not None and db.query(Conta.id).filter(Conta.id == conta_id).first():
        return conta_id
    conta = Conta(
        nome=NOME_CONTA_PLATAFORMA,
        tipo="INTEGRADOR",
        expira_em=None,
        avisos_enviados=[],
        observacoes="Conta da plataforma: recebe os dados anteriores ao multi-contas.",
    )
    db.add(conta)
    db.flush()
    row = db.query(Setting).filter(Setting.key == SETTING_CONTA_PLATAFORMA).first()
    if row:
        row.value = str(conta.id)
    else:
        db.add(Setting(key=SETTING_CONTA_PLATAFORMA, value=str(conta.id)))
    logger.info("Conta da plataforma criada: %s", conta.id)
    return conta.id


def rotulos_da_conta(conta) -> dict:
    """Rótulos da hierarquia conforme o tipo da conta."""
    tipo = getattr(conta, "tipo", None) if conta else None
    if tipo == "CLIENTE_FINAL":
        return {"grupo_singular": "Setor", "grupo_plural": "Setores"}
    return {"grupo_singular": "Cliente", "grupo_plural": "Clientes"}


def resumo_da_conta(conta, plataforma_id: Optional[UUID]) -> dict:
    """Dicionário com os campos de ContaResumo."""
    status, dias = status_da_conta(conta)
    plano_nome = conta.plano.nome if getattr(conta, "plano", None) else None
    return {
        "id": conta.id,
        "nome": conta.nome,
        "tipo": conta.tipo,
        "plano_nome": plano_nome,
        "expira_em": conta.expira_em,
        "dias_restantes": dias,
        "status": status,
        "bloqueada": status in STATUS_BLOQUEIO,
        "plataforma": (conta.id == plataforma_id) if plataforma_id else False,
    }


def contagens_por_conta(db: Session) -> dict[UUID, tuple[int, int, int]]:
    """Devolve {conta_id: (total_clientes, total_maquinas, total_usuarios)} para todas as contas."""
    res: dict[UUID, list[int]] = {}

    # Clientes
    q_cli = (
        db.query(Customer.conta_id, func.count(Customer.id))
        .filter(Customer.conta_id.isnot(None))
        .group_by(Customer.conta_id)
        .all()
    )
    for cid, cnt in q_cli:
        if cid:
            res.setdefault(cid, [0, 0, 0])[0] = cnt

    # Máquinas
    q_mac = (
        db.query(Machine.conta_id, func.count(Machine.id))
        .filter(Machine.conta_id.isnot(None))
        .group_by(Machine.conta_id)
        .all()
    )
    for cid, cnt in q_mac:
        if cid:
            res.setdefault(cid, [0, 0, 0])[1] = cnt

    # Usuários
    q_usr = (
        db.query(Usuario.conta_id, func.count(Usuario.id))
        .filter(Usuario.conta_id.isnot(None))
        .group_by(Usuario.conta_id)
        .all()
    )
    for cid, cnt in q_usr:
        if cid:
            res.setdefault(cid, [0, 0, 0])[2] = cnt

    return {cid: (vals[0], vals[1], vals[2]) for cid, vals in res.items()}


def renovar_conta(db: Session, conta: Conta, plano: Plano, feito_por: Optional[str] = None) -> ContaRenovacao:
    """Registra uma renovação de plano para a conta e estende sua validade. Não faz commit."""
    agora = datetime.utcnow()
    base = max(agora, conta.expira_em or agora)
    nova = base + timedelta(days=plano.duracao_dias)
    renovacao = ContaRenovacao(
        conta_id=conta.id,
        plano_id=plano.id,
        plano_nome=plano.nome,
        dias=plano.duracao_dias,
        expira_em_anterior=conta.expira_em,
        expira_em_nova=nova,
        feito_por=feito_por,
    )
    db.add(renovacao)
    conta.expira_em = nova
    conta.plano_id = plano.id
    conta.avisos_enviados = []
    return renovacao


def ajustar_validade(db: Session, conta: Conta, nova: datetime, feito_por: Optional[str] = None) -> ContaRenovacao:
    """Ajusta manualmente a validade da conta. Não faz commit."""
    if nova.tzinfo is not None:
        from datetime import timezone
        nova = nova.astimezone(timezone.utc).replace(tzinfo=None)
    agora = datetime.utcnow()
    dias = round((nova - (conta.expira_em or agora)).total_seconds() / 86400)
    renovacao = ContaRenovacao(
        conta_id=conta.id,
        plano_id=None,
        plano_nome="Ajuste manual",
        dias=dias,
        expira_em_anterior=conta.expira_em,
        expira_em_nova=nova,
        feito_por=feito_por,
    )
    db.add(renovacao)
    conta.expira_em = nova
    conta.avisos_enviados = []
    return renovacao


def maquina_bloqueada(machine) -> bool:
    """A conta da máquina está vencida ou suspensa (backups parados)."""
    return machine.conta is not None and conta_bloqueada(machine.conta)

