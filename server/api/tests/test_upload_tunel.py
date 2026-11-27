"""Envio em túnel do agente do Mikrotik: PUT /backup/upload-stream grava o ZIP recebido em pedaços (sem multipart),
descarta o .part se a conexão cair ou passar do limite, e POST /backup/{id}/resultado corrige o status de um
equipamento depois do relatório. SQLite em memória, como tests/test_log_completo_agente.py."""
import asyncio
import os
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
os.environ["FERNET_KEY"] = "dGVzdF9mZXJuZXRfa2V5XzMyX2J5dGVzX2xvbmdfISE="  # 32 bytes válidos
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("ADMIN_PASSWORD", "senha_de_teste")

import pytest
from fastapi import HTTPException
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import ARRAY
from starlette.requests import ClientDisconnect

from config import settings
from database import Base, engine, SessionLocal
from models import Backup, Conta, Machine
from routers.agent import ResultadoEquipamento, corrigir_resultado_equipamento, upload_backup_zip_stream

_TABELAS = [Base.metadata.tables[n] for n in ("contas", "clients", "backups", "agent_logs")]


def _db():
    for tabela in _TABELAS:
        for coluna in tabela.columns:
            if isinstance(coluna.type, ARRAY):
                coluna.type = JSON()
    Base.metadata.create_all(bind=engine, tables=_TABELAS)
    db = SessionLocal()
    db.query(Backup).delete()
    db.commit()
    return db


def _maquina_e_backup(db):
    conta = Conta(id=uuid.uuid4(), nome="Conta Teste", tipo="INTEGRADOR")
    mid = uuid.uuid4()
    machine = Machine(id=mid, conta_id=conta.id, name="Maquina MK", api_key_hash=mid.hex, api_key_prefix="sk_t",
                      backup_hour=2, backup_minute=0, active=True)
    db.add_all([conta, machine])
    db.commit()
    agora = datetime.utcnow()
    backup = Backup(id=uuid.uuid4(), machine_id=machine.id, started_at=agora, finished_at=agora, status="OK",
                    nvr_results=[{"nome": "UNM A", "tipo": "OLT", "status": "OK", "cameras": []},
                                 {"nome": "UNM B", "tipo": "OLT", "status": "OK", "cameras": []}],
                    trigger="scheduled")
    machine.last_backup_at = agora
    machine.last_backup_status = "OK"
    db.add(backup)
    db.commit()
    return machine, backup


def _requisicao(pedacos, cai_no_fim=False):
    async def _fluxo():
        for p in pedacos:
            yield p
        if cai_no_fim:
            raise ClientDisconnect()
    return SimpleNamespace(stream=_fluxo, base_url="http://teste/")


@pytest.fixture
def pasta(monkeypatch):
    async def _na_mesma_thread(func, *args, **kwargs):  # SQLite em memória não troca de thread; Postgres troca sem problema
        return func(*args, **kwargs)
    monkeypatch.setattr("starlette.concurrency.run_in_threadpool", _na_mesma_thread)
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(settings, "BACKUP_STORAGE_PATH", d)
        yield Path(d)


def _enviar(req, machine, backup, db, nome="backup_Maquina_MK_18-11-2026.zip"):
    return asyncio.run(upload_backup_zip_stream(
        str(backup.id), req, device_type="MIXED", nome=nome, machine=machine, db=db))


def test_recebe_zip_em_pedacos_e_registra_tamanho(pasta):
    db = _db()
    machine, backup = _maquina_e_backup(db)
    pedacos = [b"PK" + b"a" * 1000, b"b" * 2000, b"c" * 500]
    with patch("routers.agent.send_backup_report", return_value=True) as envio:
        r = _enviar(_requisicao(pedacos), machine, backup, db)
    assert r["status"] == "ok" and r["zip_size"] == sum(len(p) for p in pedacos)
    gravados = [p for p in pasta.rglob("*.zip")]
    assert len(gravados) == 1 and gravados[0].stat().st_size == r["zip_size"]
    assert not list(pasta.rglob("*.part"))
    db.refresh(backup)
    assert backup.zip_size == r["zip_size"] and backup.zip_filename == gravados[0].name
    envio.assert_called_once()  # máquina sem Cliente: e-mail do relatório sai no upload, como no envio comum


def test_conexao_caida_no_meio_nao_deixa_arquivo(pasta):
    db = _db()
    machine, backup = _maquina_e_backup(db)
    with pytest.raises(HTTPException) as e:
        _enviar(_requisicao([b"x" * 4096], cai_no_fim=True), machine, backup, db)
    assert e.value.status_code == 400
    assert not list(pasta.rglob("*.zip")) and not list(pasta.rglob("*.part"))
    db.refresh(backup)
    assert not backup.zip_filename


def test_passou_do_limite_devolve_413_e_limpa(pasta, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    db = _db()
    machine, backup = _maquina_e_backup(db)
    with pytest.raises(HTTPException) as e:
        _enviar(_requisicao([b"x" * (600 * 1024)] * 2), machine, backup, db)
    assert e.value.status_code == 413
    assert not list(pasta.rglob("*.zip")) and not list(pasta.rglob("*.part"))


def test_corpo_vazio_e_backup_de_outra_maquina_sao_recusados(pasta):
    db = _db()
    machine, backup = _maquina_e_backup(db)
    with pytest.raises(HTTPException) as e:
        _enviar(_requisicao([]), machine, backup, db)
    assert e.value.status_code == 400
    outra = SimpleNamespace(id=uuid.uuid4(), name="Outra", customer=None, customer_id=None, conta_id=None)
    with patch("routers.agent.maquina_bloqueada", return_value=False):
        with pytest.raises(HTTPException) as e2:
            _enviar(_requisicao([b"x"]), outra, backup, db)
    assert e2.value.status_code == 404


def test_corrige_status_de_um_equipamento_e_recalcula_o_geral():
    db = _db()
    machine, backup = _maquina_e_backup(db)
    r = corrigir_resultado_equipamento(str(backup.id), ResultadoEquipamento(nome="UNM B", status="corrompido"),
                                       machine=machine, db=db)
    assert r["geral"] == "PARTIAL"
    db.refresh(backup)
    db.refresh(machine)
    assert [i["status"] for i in backup.nvr_results] == ["OK", "CORROMPIDO"]
    assert backup.status == "PARTIAL" and machine.last_backup_status == "PARTIAL"


def test_corrigir_equipamento_inexistente_da_404():
    db = _db()
    machine, backup = _maquina_e_backup(db)
    with pytest.raises(HTTPException) as e:
        corrigir_resultado_equipamento(str(backup.id), ResultadoEquipamento(nome="Nao existe", status="ERRO"),
                                       machine=machine, db=db)
    assert e.value.status_code == 404
