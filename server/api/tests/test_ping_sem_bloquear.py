"""O ping do agente não pode fazer consulta síncrona no laço de eventos: com o pool cheio o laço parava 30 s
esperando conexão e as conexões presas só seriam devolvidas por pings que precisavam do próprio laço
(impasse que derrubou a API em 23/11/2026). SQLite em arquivo: as consultas rodam em outra thread."""
import asyncio
import os
import sys
import tempfile
import threading
import uuid
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

_ARQ = Path(tempfile.mkdtemp()) / "ping.db"
os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
os.environ["FERNET_KEY"] = "dGVzdF9mZXJuZXRfa2V5XzMyX2J5dGVzX2xvbmdfISE="
os.environ["DATABASE_URL"] = f"sqlite:///{_ARQ.as_posix()}"
os.environ.setdefault("ADMIN_PASSWORD", "senha_de_teste")

import pytest
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import ARRAY

import database
from database import Base, SessionLocal
from models import AgentLog, Conta, Machine
from routers import agent as agent_router
from schemas import PingRequest


@pytest.fixture()
def cenario():
    if database.engine.url.database != _ARQ.as_posix():
        pytest.skip("outro teste já criou o engine com SQLite em memória")
    for tabela in Base.metadata.tables.values():
        for coluna in tabela.columns:
            if isinstance(coluna.type, ARRAY):
                coluna.type = JSON()
    Base.metadata.create_all(bind=database.engine)
    db = SessionLocal()
    conta = Conta(id=uuid.uuid4(), nome="Conta", tipo="INTEGRADOR")
    mid = uuid.uuid4()
    m = Machine(id=mid, conta_id=conta.id, name="M", api_key_hash=mid.hex, api_key_prefix="sk_t",
                backup_hour=None, backup_minute=None, active=True, restart_requested=True)
    db.add_all([conta, m])
    db.commit()
    yield db, m
    db.close()


def test_ping_consulta_o_banco_fora_do_laco(cenario, monkeypatch):
    db, machine = cenario
    laco = {}
    original = agent_router._read_request_flags

    def flags(mid):
        laco["thread"] = threading.current_thread() is threading.main_thread()
        return original(mid)

    monkeypatch.setattr(agent_router, "_read_request_flags", flags)
    resp = asyncio.run(agent_router.ping_agent(body=PingRequest(versao="1.1.61"), machine=machine, db=db))

    assert resp.restart is True
    assert laco["thread"] is False  # leitura das flags não rodou na thread do laço
    s = SessionLocal()
    m = s.get(Machine, machine.id)
    assert m.agent_version == "1.1.61" and m.last_seen is not None and m.restart_requested is False
    assert s.query(AgentLog).filter(AgentLog.machine_id == machine.id, AgentLog.event_type == "ping").count() == 1
    s.close()
