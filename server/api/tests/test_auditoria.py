"""Teste da tela de auditoria (routers/auditoria.py): resolução do nome do usuário."""
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
os.environ["FERNET_KEY"] = "dGVzdF9mZXJuZXRfa2V5XzMyX2J5dGVzX2xvbmdfISE="
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("ADMIN_PASSWORD", "senha_de_teste")

from auth import Contexto
from database import Base, engine, SessionLocal
from models import AgentLog, Conta, Customer, Machine, Usuario
from routers.auditoria import listar_auditoria, listar_usuarios_da_auditoria

AGORA = datetime(2026, 11, 16, 12, 0, 0)
_TABELAS = [Base.metadata.tables[n] for n in ("contas", "usuarios", "usuario_maquinas", "client_groups", "clients", "agent_logs")]


def _db():
    Base.metadata.create_all(bind=engine, tables=_TABELAS)
    return SessionLocal()


def test_auditoria_resolucao_nome_usuario():
    db = _db()
    try:
        conta = Conta(id=uuid.uuid4(), nome="Conta Teste", tipo="INTEGRADOR")
        user = Usuario(
            id=uuid.uuid4(),
            conta_id=conta.id,
            nome="Helena Silva",
            email="helena@trilan.com",
            senha_hash="hash",
            papel="ADMIN",
            ativo=True,
        )
        mid = uuid.uuid4()
        machine = Machine(
            id=mid,
            conta_id=conta.id,
            name="Servidor Teste",
            api_key_hash=mid.hex,
            api_key_prefix="sk_t",
            active=True,
        )
        log1 = AgentLog(
            machine_id=machine.id,
            event_type="alteracao_usuario",
            message="helena@trilan.com alterou o equipamento 'NVR 01'.",
            usuario="helena@trilan.com",
            created_at=AGORA,
        )
        log2 = AgentLog(
            machine_id=machine.id,
            event_type="alteracao_usuario",
            message="admin reiniciou o agente.",
            usuario="admin",
            created_at=AGORA,
        )
        db.add_all([conta, user, machine, log1, log2])
        db.commit()

        ctx = Contexto(
            usuario_id=user.id,
            nome=user.nome,
            email=user.email,
            papel="ADMIN",
            conta_id=conta.id,
            conta=conta,
            somente_leitura=False,
        )

        res = listar_auditoria(page=1, size=30, usuario=None, q=None, db=db, ctx=ctx)
        assert res.total == 2
        itens_por_usuario = {item.usuario: item for item in res.items}

        assert "helena@trilan.com" in itens_por_usuario
        assert itens_por_usuario["helena@trilan.com"].usuario_nome == "Helena Silva"

        assert "admin" in itens_por_usuario
        assert itens_por_usuario["admin"].usuario_nome == "Administrador"

        usuarios_opcoes = listar_usuarios_da_auditoria(db=db, ctx=ctx)
        assert len(usuarios_opcoes) == 2
        mapa_opcoes = {op.usuario: op.nome for op in usuarios_opcoes}
        assert mapa_opcoes["helena@trilan.com"] == "Helena Silva"
        assert mapa_opcoes["admin"] == "Administrador"
    finally:
        db.close()


if __name__ == "__main__":
    test_auditoria_resolucao_nome_usuario()
    print("ALL TESTS PASSED")
