"""
Serviço de retenção e poda de logs do agente (tabela agent_logs).
"""
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from models import AgentLog

DIAS_RETENCAO = 30
MAX_PINGS = 50
MAX_LOGS_POR_MAQUINA = 5000
DIAS_RETENCAO_AUDITORIA = 365  # ações de usuários no painel (tela de Auditoria) ficam bem mais que os eventos do agente


EVENTO_ALTERACAO = "alteracao_usuario"


def registrar_alteracao(
    db: Session,
    machine_id: UUID,
    feito_por: str,
    mensagem: str,
    equipamento: Optional[str] = None,
) -> None:
    """Registra nos Eventos do Agente da máquina que um usuário/admin alterou algo pelo painel
    ("fulano@x.com alterou o equipamento 'Y': IP"). Só adiciona na sessão: quem chama commita junto com a
    alteração, então o evento só existe se a alteração foi gravada. O horário é o created_at do evento.
    Nunca coloque senhas nem valores de campos secretos na mensagem, só os nomes dos campos."""
    db.add(AgentLog(
        machine_id=machine_id,
        event_type=EVENTO_ALTERACAO,
        message=f"{feito_por} {mensagem}",
        nivel="INFO",
        equipamento=equipamento,
        usuario=feito_por,
    ))


def podar_logs(db: Session, machine_id: UUID, agora: datetime) -> None:
    """Executa a poda de logs da máquina sem realizar commit (quem chama commita).

    (a) Mantém apenas os MAX_PINGS pings mais recentes da máquina.
    (b) Remove eventos que NÃO são ping com created_at anterior a DIAS_RETENCAO.
    (c) Mantém apenas os MAX_LOGS_POR_MAQUINA eventos que NÃO são ping mais recentes.
    (d) Ações de usuários no painel (usuario preenchido) não entram em (b) nem em (c): ficam por
        DIAS_RETENCAO_AUDITORIA dias, pois são o histórico da tela de Auditoria.
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
            AgentLog.usuario.is_(None),
            AgentLog.created_at < limite_data,
        )
    )
    db.execute(
        delete(AgentLog).where(
            AgentLog.machine_id == machine_id,
            AgentLog.usuario.isnot(None),
            AgentLog.created_at < agora - timedelta(days=DIAS_RETENCAO_AUDITORIA),
        )
    )

    # (c) Eventos que NÃO são ping além dos MAX_LOGS_POR_MAQUINA mais recentes
    ids_logs_antigos = (
        select(AgentLog.id)
        .where(AgentLog.machine_id == machine_id, AgentLog.event_type != "ping", AgentLog.usuario.is_(None))
        .order_by(AgentLog.created_at.desc())
        .offset(MAX_LOGS_POR_MAQUINA)
    )
    db.execute(delete(AgentLog).where(AgentLog.id.in_(ids_logs_antigos)))
