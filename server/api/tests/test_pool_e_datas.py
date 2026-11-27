"""Datas com fuso no fechamento das rodadas e isolamento das etapas de notificação (pool esgotado em 24/11/2026)."""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
os.environ["FERNET_KEY"] = "dHJpbGFuLWNoYXZlLWRlLXRlc3RlLTMyLWJ5dGVzISE="
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("ADMIN_PASSWORD", "senha_de_teste")

from services.datas import para_utc_naive
from services import backup_runs
from services import notificacoes
from database import _engine_kwargs


def test_para_utc_naive():
    assert para_utc_naive(None) is None
    naive = datetime(2026, 11, 24, 19, 0)
    assert para_utc_naive(naive) is naive
    aware = datetime(2026, 11, 24, 16, 0, tzinfo=timezone(timedelta(hours=-3)))
    assert para_utc_naive(aware) == datetime(2026, 11, 24, 19, 0)


def test_is_due_com_prazo_vindo_do_banco_com_fuso():
    agora = datetime(2026, 11, 24, 19, 35)
    run = SimpleNamespace(
        deadline_at=datetime(2026, 11, 24, 19, 30, tzinfo=timezone.utc),  # timestamptz em produção
        started_at=datetime(2026, 11, 24, 19, 0, tzinfo=timezone.utc),
        customer=None, backups=[], expected_machine_ids=[],
    )
    # Antes: TypeError "can't subtract offset-naive and offset-aware datetimes"
    assert backup_runs._is_due(run, agora) is True


class _SessaoFalsa:
    def __init__(self):
        self.commits = self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_etapa_que_falha_nao_derruba_as_outras(monkeypatch):
    chamadas = []

    def ok(nome, valor=0):
        def f(db):
            chamadas.append(nome)
            return valor
        return f

    def falha(db):
        chamadas.append("licenca")
        raise RuntimeError("banco")

    monkeypatch.setattr(notificacoes, "verificar_licencas_unm2000", falha)
    for nome in ("verificar_backups_falhos", "verificar_agentes_offline", "verificar_cameras_offline",
                 "verificar_alarmes", "verificar_olts", "verificar_antenas"):
        monkeypatch.setattr(notificacoes, nome, ok(nome))
    monkeypatch.setattr(notificacoes, "verificar_personalizadas", ok("personalizadas", 2))
    db = _SessaoFalsa()
    resumo = notificacoes.verificar_notificacoes(db)
    assert len(chamadas) == 8
    assert db.rollbacks == 1 and db.commits == 7
    assert resumo["emails_licenca"] == 0 and resumo["emails_personalizadas"] == 2


def test_engine_postgres_tem_limites_e_sqlite_nao():
    pg = _engine_kwargs("postgresql://u:p@h/db")
    assert pg["pool_pre_ping"] and pg["pool_timeout"] == 10
    assert "idle_in_transaction_session_timeout=120000" in pg["connect_args"]["options"]
    assert _engine_kwargs("sqlite:///:memory:") == {"pool_pre_ping": True}
