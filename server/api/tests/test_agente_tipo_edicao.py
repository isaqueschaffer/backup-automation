"""Troca de "onde o agente roda" depois de criada a máquina: PUT /machines/{id} aceita agente_tipo (WINDOWS <-> MIKROTIK),
grava e registra nos Eventos do Agente; valor fora da lista é recusado. SQLite em memória, como tests/test_auditoria.py."""
import os
import sys
import uuid
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
os.environ["FERNET_KEY"] = "dGVzdF9mZXJuZXRfa2V5XzMyX2J5dGVzX2xvbmdfISE="  # 32 bytes válidos
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("ADMIN_PASSWORD", "senha_de_teste")

import pytest
from pydantic import ValidationError
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import ARRAY

from auth import Contexto
from database import Base, engine, SessionLocal
from models import AgentLog, Conta, Machine
from routers.machines import update_machine
from schemas import MachineUpdate


def _db():
    for tabela in Base.metadata.tables.values():
        for coluna in tabela.columns:
            if isinstance(coluna.type, ARRAY):
                coluna.type = JSON()
    Base.metadata.create_all(bind=engine)
    return SessionLocal()


def _cenario(db, tipo="WINDOWS"):
    conta = Conta(id=uuid.uuid4(), nome="Conta Teste", tipo="INTEGRADOR")
    mid = uuid.uuid4()
    machine = Machine(id=mid, conta_id=conta.id, name="Servidor OLT", api_key_hash=mid.hex, api_key_prefix="sk_t",
                      backup_hour=4, backup_minute=0, active=True, agente_tipo=tipo)
    db.add_all([conta, machine])
    db.commit()
    ctx = Contexto(usuario_id=uuid.uuid4(), nome="Admin", email="admin@trilan.com", papel="ADMIN",
                   conta_id=conta.id, conta=conta, somente_leitura=False)
    return machine, ctx


def _eventos(db, machine):
    return [l.message for l in db.query(AgentLog).filter_by(machine_id=machine.id, event_type="alteracao_usuario")]


def test_troca_windows_para_mikrotik_e_volta():
    db = _db()
    machine, ctx = _cenario(db, "WINDOWS")

    update_machine(machine.id, MachineUpdate(agente_tipo="MIKROTIK"), db=db, ctx=ctx)
    db.refresh(machine)
    assert machine.agente_tipo == "MIKROTIK"
    assert any("onde o agente roda" in m for m in _eventos(db, machine))

    update_machine(machine.id, MachineUpdate(agente_tipo="WINDOWS"), db=db, ctx=ctx)
    db.refresh(machine)
    assert machine.agente_tipo == "WINDOWS"
    db.close()


def test_editar_outros_campos_nao_mexe_no_tipo():
    db = _db()
    machine, ctx = _cenario(db, "MIKROTIK")
    update_machine(machine.id, MachineUpdate(name="Servidor OLT Novo"), db=db, ctx=ctx)
    db.refresh(machine)
    assert machine.agente_tipo == "MIKROTIK" and machine.name == "Servidor OLT Novo"
    db.close()


def test_tipo_invalido_e_recusado():
    with pytest.raises(ValidationError):
        MachineUpdate(agente_tipo="LINUX")
