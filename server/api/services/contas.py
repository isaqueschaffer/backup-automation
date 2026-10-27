"""Contas (inquilinos): validade do plano e conta da plataforma."""
import logging
import math
from datetime import datetime
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from models import Conta, Setting

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
