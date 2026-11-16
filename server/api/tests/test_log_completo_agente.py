"""Log completo do agente: POST /api/v1/agent/logs grava as linhas comuns (detalhe=True, INFO) como
"agent_log_detalhe", e podar_logs as poda à parte (prazo e teto próprios), sem empurrar para fora os eventos
principais (avisos, erros, marcos). SQLite em memória, como tests/test_olt_notificacao.py."""
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
os.environ["FERNET_KEY"] = "dGVzdF9mZXJuZXRfa2V5XzMyX2J5dGVzX2xvbmdfISE="  # 32 bytes válidos
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("ADMIN_PASSWORD", "senha_de_teste")

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import ARRAY

from database import Base, engine, SessionLocal
from models import AgentLog, Conta, Machine
from routers.agent import receive_agent_logs
from schemas import LogsAgenteReport
from services import agent_logs as servico

T0 = datetime(2026, 11, 16, 12, 0, 0)
_TABELAS = [Base.metadata.tables[n] for n in ("contas", "clients", "agent_logs")]


def _db():
    for tabela in _TABELAS:
        for coluna in tabela.columns:
            if isinstance(coluna.type, ARRAY):
                coluna.type = JSON()
    Base.metadata.create_all(bind=engine, tables=_TABELAS)
    db = SessionLocal()
    db.query(AgentLog).delete()
    db.commit()
    return db


def _maquina(db):
    conta = Conta(id=uuid.uuid4(), nome="Conta Teste", tipo="INTEGRADOR")
    mid = uuid.uuid4()
    machine = Machine(id=mid, conta_id=conta.id, name="Maquina", api_key_hash=mid.hex, api_key_prefix="sk_t",
                      backup_hour=2, backup_minute=0, active=True)
    db.add_all([conta, machine])
    db.commit()
    return machine


def _tipos(db, machine):
    return sorted((l.event_type, l.nivel, l.message) for l in db.query(AgentLog).filter_by(machine_id=machine.id))


def test_post_separa_detalhe_dos_eventos_principais():
    db = _db()
    machine = _maquina(db)
    body = LogsAgenteReport(logs=[
        {"nivel": "INFO", "mensagem": "Conectando ao NVR", "detalhe": True},
        {"nivel": "INFO", "mensagem": "BACKUP FINALIZADO."},  # marco: agente não manda detalhe
        {"nivel": "ERROR", "mensagem": "Falha", "detalhe": True},  # erro nunca é detalhe
        {"nivel": "WARNING", "mensagem": "Aviso"},
    ])
    receive_agent_logs(body, machine=machine, db=db)
    assert _tipos(db, machine) == [
        ("agent_log", "ERROR", "Falha"),
        ("agent_log", "INFO", "BACKUP FINALIZADO."),
        ("agent_log", "WARNING", "Aviso"),
        ("agent_log_detalhe", "INFO", "Conectando ao NVR"),
    ]


def test_agente_antigo_sem_campo_detalhe_continua_agent_log():
    db = _db()
    machine = _maquina(db)
    receive_agent_logs(LogsAgenteReport(logs=[{"nivel": "INFO", "mensagem": "x"}]), machine=machine, db=db)
    assert _tipos(db, machine) == [("agent_log", "INFO", "x")]


def test_detalhe_nao_empurra_eventos_principais_para_fora():
    db = _db()
    machine = _maquina(db)
    db.add(AgentLog(machine_id=machine.id, event_type="agent_log", nivel="ERROR", message="erro antigo",
                    created_at=T0 - timedelta(hours=1)))
    for i in range(6):
        db.add(AgentLog(machine_id=machine.id, event_type=servico.EVENTO_DETALHE, nivel="INFO",
                        message=f"linha {i}", created_at=T0 - timedelta(minutes=i)))
    db.commit()
    with patch.object(servico, "MAX_LOGS_POR_MAQUINA", 1), patch.object(servico, "MAX_LOGS_DETALHE_POR_MAQUINA", 3):
        servico.podar_logs(db, machine.id, T0)
    db.commit()
    tipos = _tipos(db, machine)
    assert ("agent_log", "ERROR", "erro antigo") in tipos
    assert [m for t, _, m in tipos if t == servico.EVENTO_DETALHE] == ["linha 0", "linha 1", "linha 2"]


def test_detalhe_expira_antes_dos_eventos_principais():
    db = _db()
    machine = _maquina(db)
    velho = T0 - timedelta(days=servico.DIAS_RETENCAO_DETALHE + 1)
    db.add(AgentLog(machine_id=machine.id, event_type=servico.EVENTO_DETALHE, nivel="INFO", message="velha",
                    created_at=velho))
    db.add(AgentLog(machine_id=machine.id, event_type="agent_log", nivel="WARNING", message="aviso",
                    created_at=velho))
    db.commit()
    servico.podar_logs(db, machine.id, T0)
    db.commit()
    assert _tipos(db, machine) == [("agent_log", "WARNING", "aviso")]
