"""
Serviço de retenção e poda de logs do agente (tabela agent_logs).
"""
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from models import AgentLog

DIAS_RETENCAO = 30
MAX_PINGS = 50
MAX_LOGS_POR_MAQUINA = 5000


def podar_logs(db: Session, machine_id: UUID, agora: datetime) -> None:
    """Executa a poda de logs da máquina sem realizar commit (quem chama commita).

    (a) Mantém apenas os MAX_PINGS pings mais recentes da máquina.
    (b) Remove eventos que NÃO são ping com created_at anterior a DIAS_RETENCAO.
    (c) Mantém apenas os MAX_LOGS_POR_MAQUINA eventos que NÃO são ping mais recentes.
    """
    db.flush()

    # (a) Pings: mantém apenas os MAX_PINGS mais recentes
    ids_pings_antigos = (
        select(AgentLog.id)
        .where(AgentLog.machine_id == machine_id, AgentLog.event_type == "ping")
        .order_by(AgentLog.created_at.desc())
        .offset(MAX_PINGS)
    )
    db.execute(delete(AgentLog).where(AgentLog.id.in_(ids_pings_antigos)))

    # (b) Eventos que NÃO são ping mais antigos que DIAS_RETENCAO dias
    limite_data = agora - timedelta(days=DIAS_RETENCAO)
    db.execute(
        delete(AgentLog).where(
            AgentLog.machine_id == machine_id,
            AgentLog.event_type != "ping",
            AgentLog.created_at < limite_data,
        )
    )

    # (c) Eventos que NÃO são ping além dos MAX_LOGS_POR_MAQUINA mais recentes
    ids_logs_antigos = (
        select(AgentLog.id)
        .where(AgentLog.machine_id == machine_id, AgentLog.event_type != "ping")
        .order_by(AgentLog.created_at.desc())
        .offset(MAX_LOGS_POR_MAQUINA)
    )
    db.execute(delete(AgentLog).where(AgentLog.id.in_(ids_logs_antigos)))
