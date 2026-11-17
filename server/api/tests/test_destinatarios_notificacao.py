"""Destinatários das notificações por e-mail (services/notificacoes.destinatarios_notificacao): e-mail de contato da conta
+ usuários ativos com notif_email, filtrados por tipo e por máquina. SQLite em memória, como tests/test_olt_notificacao.py."""
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

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import ARRAY

from database import Base, engine, SessionLocal
from models import Conta, Machine, Usuario, UsuarioMaquina
from schemas import UsuarioCreate, UsuarioUpdate
from services.notificacoes import destinatarios_notificacao

_TABELAS = [Base.metadata.tables[n] for n in ("contas", "clients", "usuarios", "usuario_maquinas")]


def _db():
    for tabela in _TABELAS:
        for coluna in tabela.columns:
            if isinstance(coluna.type, ARRAY):
                coluna.type = JSON()
    Base.metadata.create_all(bind=engine, tables=_TABELAS)
    return SessionLocal()


def _maquina(db, conta, nome):
    mid = uuid.uuid4()
    m = Machine(id=mid, conta_id=conta.id, name=nome, api_key_hash=mid.hex, api_key_prefix="sk_t",
                backup_hour=2, backup_minute=0, active=True)
    db.add(m)
    return m


def _usuario(db, conta, email, papel="ADMIN", notif=True, tipos=None, maquinas=(), ativo=True):
    u = Usuario(id=uuid.uuid4(), conta_id=conta.id, nome=email, email=email, senha_hash="x", papel=papel,
                ativo=ativo, notif_email=notif, notif_tipos=tipos)
    u.maquinas_vinculo = [UsuarioMaquina(machine_id=m) for m in maquinas]
    db.add(u)
    return u


def _cenario():
    db = _db()
    for modelo in (UsuarioMaquina, Usuario, Machine, Conta):  # banco em memória compartilhado entre os testes
        db.query(modelo).delete()
    db.commit()
    conta = Conta(id=uuid.uuid4(), nome=f"Conta {uuid.uuid4().hex[:6]}", tipo="INTEGRADOR", email_contato="contato@x.com")
    db.add(conta)
    m1, m2 = _maquina(db, conta, "M1"), _maquina(db, conta, "M2")
    db.commit()
    return db, conta, m1, m2


def test_contato_sempre_recebe_e_so_quem_esta_ligado():
    db, conta, m1, _ = _cenario()
    _usuario(db, conta, "adm@x.com")
    _usuario(db, conta, "leitor@x.com", papel="LEITURA", notif=False)
    db.commit()
    assert destinatarios_notificacao(db, conta, "CAMERA_OFFLINE", m1.id) == ["contato@x.com", "adm@x.com"]


def test_filtra_por_tipo():
    db, conta, m1, _ = _cenario()
    _usuario(db, conta, "so-olt@x.com", papel="VISUALIZADOR", tipos=["ONU_OFFLINE"])
    _usuario(db, conta, "todos@x.com", papel="VISUALIZADOR", tipos=None)
    db.commit()
    assert "so-olt@x.com" not in destinatarios_notificacao(db, conta, "CAMERA_OFFLINE", m1.id)
    assert "so-olt@x.com" in destinatarios_notificacao(db, conta, "ONU_OFFLINE", m1.id)
    assert "todos@x.com" in destinatarios_notificacao(db, conta, "CAMERA_OFFLINE", m1.id)


def test_filtra_por_maquina_do_usuario():
    db, conta, m1, m2 = _cenario()
    _usuario(db, conta, "so-m1@x.com", papel="LEITURA", maquinas=[m1.id])
    _usuario(db, conta, "todas@x.com", papel="LEITURA")  # sem máquinas marcadas = todas
    _usuario(db, conta, "adm@x.com")  # admin sempre vê todas
    db.commit()
    para_m1 = destinatarios_notificacao(db, conta, "ALARME", m1.id)
    para_m2 = destinatarios_notificacao(db, conta, "ALARME", m2.id)
    assert "so-m1@x.com" in para_m1
    assert "so-m1@x.com" not in para_m2
    assert {"todas@x.com", "adm@x.com"} <= set(para_m1) and {"todas@x.com", "adm@x.com"} <= set(para_m2)


def test_ignora_inativo_e_outra_conta():
    db, conta, m1, _ = _cenario()
    outra = Conta(id=uuid.uuid4(), nome=f"Outra {uuid.uuid4().hex[:6]}", tipo="INTEGRADOR")
    db.add(outra)
    _usuario(db, conta, "inativo@x.com", ativo=False)
    _usuario(db, outra, "outra@x.com")
    db.commit()
    assert destinatarios_notificacao(db, conta, "ALARME", m1.id) == ["contato@x.com"]


def test_personalizada_sem_maquina_vai_para_todos_os_ligados():
    db, conta, _, _ = _cenario()
    _usuario(db, conta, "so-m1@x.com", papel="LEITURA", maquinas=[uuid.uuid4()])
    db.commit()
    assert "so-m1@x.com" in destinatarios_notificacao(db, conta, "PERSONALIZADA")


def test_schema_rejeita_tipo_invalido_e_aceita_null():
    import pytest
    with pytest.raises(ValueError):
        UsuarioUpdate(notif_tipos=["INVENTADO"])
    assert UsuarioUpdate(notif_tipos=None).model_fields_set == {"notif_tipos"}
    assert UsuarioCreate(nome="Ana", email="ana@x.com", senha="umasenhaforte1", papel="LEITURA",
                         notif_tipos=["ALARME", "ALARME"]).notif_tipos == ["ALARME"]
