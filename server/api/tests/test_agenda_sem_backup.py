"""Visão Geral (26/11/2026): "hoje" no dia de Brasília e máquinas sem backup desde o último horário agendado."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from services.agenda import inicio_do_dia_brasilia_utc, sem_backup_desde_o_agendado, ultimo_horario_agendado


def _maquina(**kw):
    base = dict(id="m1", name="Servidor", active=True, equipamentos=[SimpleNamespace(active=True)],
                backup_hour=23, backup_minute=0, customer=None, customer_id=None, telemetry=None,
                last_backup_at=None, last_backup_status=None, last_seen=None,
                created_at=datetime(2026, 1, 1))
    base.update(kw)
    return SimpleNamespace(**base)


def test_dia_de_brasilia_depois_das_21h_ainda_e_hoje():
    # 26/11 23:30 UTC = 26/11 20:30 em Brasília: o dia começa em 26/11 03:00 UTC (antes contava o dia 26 UTC inteiro)
    assert inicio_do_dia_brasilia_utc(datetime(2026, 11, 26, 23, 30)) == datetime(2026, 11, 26, 3, 0)
    # 27/11 01:00 UTC = 26/11 22:00 em Brasília: continua o dia 26
    assert inicio_do_dia_brasilia_utc(datetime(2026, 11, 27, 1, 0)) == datetime(2026, 11, 26, 3, 0)


def test_tolerancia_maior_que_o_tempo_desde_a_meia_noite_volta_dois_dias():
    # 00:30 com agendamento às 23:00 e 2 h de tolerância: o de ontem ainda está no prazo; vale o de anteontem
    assert ultimo_horario_agendado(datetime(2026, 11, 27, 0, 30), 23, 0, 120) == datetime(2026, 11, 25, 23, 0)
    assert ultimo_horario_agendado(datetime(2026, 11, 27, 1, 1), 23, 0, 120) == datetime(2026, 11, 26, 23, 0)


def test_maquina_sem_backup_desde_ontem_23h():
    # 27/11 12:00 UTC (09:00 BRT); agendado 26/11 23:00 BRT = 27/11 02:00 UTC; último backup em 26/11 02:10 UTC
    agora = datetime(2026, 11, 27, 12, 0)
    m = _maquina(last_backup_at=datetime(2026, 11, 26, 2, 10, tzinfo=timezone.utc), last_backup_status="OK",
                 customer=SimpleNamespace(name="Georgina", backup_hour=23, backup_minute=0), customer_id="c1",
                 backup_hour=2)  # a máquina do Cliente usa o horário do Cliente
    s = sem_backup_desde_o_agendado(m, agora)
    assert s["agendado_em"] == datetime(2026, 11, 27, 2, 0)
    assert s["minutos_de_atraso"] == 600
    assert s["customer_name"] == "Georgina" and s["online"] is False
    assert s["last_backup_at"] == datetime(2026, 11, 26, 2, 10)


def test_backup_feito_depois_do_horario_nao_aparece():
    agora = datetime(2026, 11, 27, 12, 0)
    assert sem_backup_desde_o_agendado(_maquina(last_backup_at=datetime(2026, 11, 27, 2, 20)), agora) is None


def test_dentro_do_prazo_da_fila_nao_aparece():
    # 27/11 03:30 UTC = 00:30 BRT: o das 23:00 ainda está nas 2 h de folga; o anterior (25/11) foi feito
    agora = datetime(2026, 11, 27, 3, 30)
    assert sem_backup_desde_o_agendado(_maquina(last_backup_at=datetime(2026, 11, 26, 2, 5)), agora) is None


def test_inativa_sem_equipamento_ou_recem_cadastrada_nao_aparece():
    agora = datetime(2026, 11, 27, 12, 0)
    assert sem_backup_desde_o_agendado(_maquina(active=False), agora) is None
    assert sem_backup_desde_o_agendado(_maquina(equipamentos=[SimpleNamespace(active=False)]), agora) is None
    assert sem_backup_desde_o_agendado(_maquina(created_at=agora - timedelta(hours=1)), agora) is None
    assert sem_backup_desde_o_agendado(_maquina(), agora) is not None


def test_online_pelo_last_seen_e_fuso_da_telemetria():
    agora = datetime(2026, 11, 27, 12, 0)
    # Máquina em UTC+0 com agendamento às 11:00: 1 h atrás, dentro das 2 h -> vale o de ontem (26/11 11:00)
    m = _maquina(backup_hour=11, telemetry={"utc_offset_min": 0}, last_seen=agora - timedelta(seconds=30),
                 last_backup_at=datetime(2026, 11, 25, 11, 5))
    s = sem_backup_desde_o_agendado(m, agora)
    assert s["agendado_em"] == datetime(2026, 11, 26, 11, 0) and s["online"] is True
