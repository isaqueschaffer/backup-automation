"""Horário agendado do backup e o "esperado × realizado" (REGRA-001: tudo naive, UTC no banco).

O agente agenda pela hora local da máquina (`utc_offset_min` da telemetria; sem ele, Brasília). A máquina de um
Cliente usa o horário do Cliente (é o que `GET /agent/config` entrega ao agente).

Usado pela recuperação de backup perdido (routers/agent.py) e pela Visão Geral (`GET /api/v1/stats`).
"""
from datetime import date, datetime, time, timedelta
from typing import Optional

from services.datas import para_utc_naive

OFFSET_UTC_PADRAO_MIN = -180  # Brasília (UTC-3): agentes < 1.1.34 não informam o fuso
RECUPERACAO_TOLERANCIA_MIN = 30  # a recuperação só considera o horário "perdido" 30 min depois dele
ATRASO_SEM_BACKUP_MIN = 120  # a Visão Geral só aponta "sem backup" 2 h depois do horário (fila do Cliente leva tempo)
ONLINE_LIMITE_S = 180  # igual a routers/machines.check_machine_online


def offset_utc_min(telemetria_ping, telemetria_maquina) -> int:
    """Fuso local da máquina em minutos em relação ao UTC (`utc_offset_min` da telemetria, agente >= 1.1.34):
    o do corpo do ping ou, se ausente, o último gravado na máquina. Fora de -720..840 ou inválido: -180."""
    valor = None
    for tel in (telemetria_ping, telemetria_maquina):
        if isinstance(tel, dict) and tel.get("utc_offset_min") is not None:
            valor = tel.get("utc_offset_min")
            break
    if isinstance(valor, bool):
        return OFFSET_UTC_PADRAO_MIN
    try:
        offset = int(valor)
    except (TypeError, ValueError):
        return OFFSET_UTC_PADRAO_MIN
    return offset if -720 <= offset <= 840 else OFFSET_UTC_PADRAO_MIN


def ultimo_horario_agendado(agora_local: datetime, hora: int, minuto: int,
                            tolerancia_min: int = RECUPERACAO_TOLERANCIA_MIN) -> Optional[datetime]:
    """Último horário agendado (hora local da máquina, naive) que já passou há mais de `tolerancia_min`:
    o de hoje, se já passou, senão o de ontem (ou anteontem, quando o de ontem ainda está dentro da tolerância:
    00:30 com agendamento às 23:00 e tolerância de 2 h)."""
    try:
        horario = agora_local.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    except (TypeError, ValueError):
        return None
    while agora_local <= horario + timedelta(minutes=tolerancia_min):
        horario -= timedelta(days=1)
    return horario


def horario_da_maquina(machine) -> tuple:
    """(hora, minuto) que o agente usa: o do Cliente, se a máquina tiver um; senão o dela."""
    if machine.customer is not None:
        return machine.customer.backup_hour, machine.customer.backup_minute
    return machine.backup_hour, machine.backup_minute


def inicio_do_dia_brasilia_utc(agora_utc: Optional[datetime] = None) -> datetime:
    """Meia-noite de hoje em Brasília, em UTC naive (o "hoje" que o painel mostra)."""
    agora_utc = agora_utc or datetime.utcnow()
    dia_brt: date = (agora_utc + timedelta(minutes=OFFSET_UTC_PADRAO_MIN)).date()
    return datetime.combine(dia_brt, time.min) - timedelta(minutes=OFFSET_UTC_PADRAO_MIN)


def maquina_online(machine, agora_utc: datetime) -> bool:
    visto = para_utc_naive(machine.last_seen)
    return bool(machine.active and visto and (agora_utc - visto).total_seconds() < ONLINE_LIMITE_S)


def sem_backup_desde_o_agendado(machine, agora_utc: Optional[datetime] = None,
                                atraso_min: int = ATRASO_SEM_BACKUP_MIN) -> Optional[dict]:
    """Se a máquina ativa, com equipamento ativo, não fez backup desde o último horário agendado (passado há mais de
    `atraso_min`), devolve o resumo para a Visão Geral; senão None."""
    if not machine.active or not any(e.active for e in machine.equipamentos):
        return None
    hora, minuto = horario_da_maquina(machine)
    if hora is None or minuto is None:
        return None
    agora_utc = agora_utc or datetime.utcnow()
    offset = offset_utc_min(None, machine.telemetry)
    agendado_local = ultimo_horario_agendado(agora_utc + timedelta(minutes=offset), hora, minuto, atraso_min)
    if agendado_local is None:
        return None
    agendado_utc = agendado_local - timedelta(minutes=offset)
    ultimo = para_utc_naive(machine.last_backup_at)
    if ultimo is not None and ultimo >= agendado_utc:
        return None
    if ultimo is None and para_utc_naive(machine.created_at) and para_utc_naive(machine.created_at) > agendado_utc:
        return None  # cadastrada depois do horário: o primeiro backup ainda não era esperado
    return {
        "machine_id": machine.id,
        "machine_name": machine.name,
        "customer_id": machine.customer_id,
        "customer_name": machine.customer.name if machine.customer is not None else None,
        "agendado_em": agendado_utc,
        "minutos_de_atraso": int((agora_utc - agendado_utc).total_seconds() // 60),
        "last_backup_at": ultimo,
        "last_backup_status": machine.last_backup_status,
        "online": maquina_online(machine, agora_utc),
        "last_seen": para_utc_naive(machine.last_seen),
    }
