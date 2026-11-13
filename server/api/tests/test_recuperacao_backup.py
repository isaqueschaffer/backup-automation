"""Testes do cálculo do último horário agendado usado na recuperação de backup perdido (routers/agent.py)."""
import os
import sys
from datetime import datetime
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
os.environ["FERNET_KEY"] = "dGVzdF9mZXJuZXRfa2V5XzMyX2J5dGVzX2xvbmdfIQ=="
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("ADMIN_PASSWORD", "senha_de_teste")

from routers.agent import _ultimo_horario_agendado


def test_agendamento_de_hoje_ja_passou():
    # 10:00 com agendamento às 03:00: o último é o de hoje
    agora = datetime(2026, 11, 13, 10, 0)
    assert _ultimo_horario_agendado(agora, 3, 0) == datetime(2026, 11, 13, 3, 0)


def test_madrugada_apos_agendamento_noturno_usa_o_de_ontem():
    # Caso real de 12-13/11/2026: servidor fora do ar às 23:00 e de volta às 08:40.
    # Antes a recuperação comparava com as 23:00 de hoje (ainda no futuro) e nunca disparava.
    agora = datetime(2026, 11, 13, 8, 40)
    assert _ultimo_horario_agendado(agora, 23, 0) == datetime(2026, 11, 12, 23, 0)


def test_dentro_da_tolerancia_ainda_conta_o_anterior():
    # 23:15 com agendamento às 23:00: o backup de hoje pode estar rodando; o último "perdido" é o de ontem
    agora = datetime(2026, 11, 12, 23, 15)
    assert _ultimo_horario_agendado(agora, 23, 0) == datetime(2026, 11, 11, 23, 0)


def test_depois_da_tolerancia_conta_o_de_hoje():
    agora = datetime(2026, 11, 12, 23, 31)
    assert _ultimo_horario_agendado(agora, 23, 0) == datetime(2026, 11, 12, 23, 0)


def test_horario_invalido():
    assert _ultimo_horario_agendado(datetime(2026, 11, 13, 10, 0), 25, 0) is None


if __name__ == "__main__":
    for nome, fn in list(globals().items()):
        if nome.startswith("test_") and callable(fn):
            fn()
            print(f"ok {nome}")
