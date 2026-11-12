"""Notificação de alarmes das centrais do DEFENSE (ALARME, services/notificacoes.py): opt-in por central
(NVR.alarmes_notificar), uma notificação por situação (disparo, central desconectada, partição desarmada, falha
na consulta), separadas por Notificacao.referencia. Roda com SQLite em memória (como tests/test_contas_status.py)."""
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
os.environ["FERNET_KEY"] = "dGVzdF9mZXJuZXRfa2V5XzMyX2J5dGVzX2xvbmdfIQ=="
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("ADMIN_PASSWORD", "senha_de_teste")

from database import Base, engine, SessionLocal
from models import Conta, Machine, Notificacao, NVR
from services import notificacoes as servico

AGORA = datetime(2026, 11, 12, 12, 0, 0)

# Só as tabelas necessárias: evita o ARRAY de client_groups.email_to, que o SQLite não suporta
_TABELAS = [Base.metadata.tables[n] for n in ("contas", "clients", "nvrs", "nvr_cameras", "notificacoes")]


def _central(status=1, armada=True, disparada=False, cid=3):
    return {"id": cid, "nome": "CENTRAL RIO PRETO", "status": status,
            "particoes": [{"id": 4, "nome": "Setor 1", "armada": armada, "disparada": disparada}]}


def _cenario(db, alarmes=None, erro=None, marcadas=("3",), coletado=AGORA):
    conta = Conta(id=uuid.uuid4(), nome="Conta Teste")
    machine = Machine(id=uuid.uuid4(), conta_id=conta.id, name="Maquina Teste", backup_hour=2, backup_minute=0, active=True)
    nvr = NVR(id=uuid.uuid4(), machine_id=machine.id, tipo="DEFENSE", name="Defense Teste", ip="127.0.0.1",
              username="system", password="x", active=True, alarmes_notificar=list(marcadas))
    nvr.last_alarm_status = {"atualizado_em": coletado.strftime("%Y-%m-%dT%H:%M:%S"), "ip": "127.0.0.1",
                             "erro": erro, "alarmes": alarmes if alarmes is not None else [_central()]}
    db.add_all([conta, machine, nvr])
    db.commit()
    return nvr


def _abertas(db, nvr):
    return {n.referencia for n in db.query(Notificacao).filter(
        Notificacao.tipo == "ALARME", Notificacao.nvr_id == nvr.id, Notificacao.resolvido_em.is_(None))}


def _verificar(db, nvr, agora=AGORA):
    with patch.object(servico, "_enviar_email_alarme", return_value=False):
        servico.verificar_alarmes_equipamento(db, nvr, agora)
    db.commit()


def _db():
    Base.metadata.create_all(bind=engine, tables=_TABELAS)
    return SessionLocal()


def test_central_normal_nao_notifica():
    db = _db()
    try:
        nvr = _cenario(db)
        _verificar(db, nvr)
        assert _abertas(db, nvr) == set()
    finally:
        db.close()


def test_central_nao_marcada_nao_notifica():
    db = _db()
    try:
        nvr = _cenario(db, alarmes=[_central(status=0, armada=False, disparada=True)], marcadas=())
        _verificar(db, nvr)
        assert _abertas(db, nvr) == set()
    finally:
        db.close()


def test_disparo_desconexao_e_desarme_viram_notificacoes_separadas():
    db = _db()
    try:
        nvr = _cenario(db, alarmes=[_central(status=0, armada=False, disparada=True)])
        _verificar(db, nvr)
        assert _abertas(db, nvr) == {"3:DESCONECTADA", "3:4:DISPARO", "3:4:DESARMADA"}
    finally:
        db.close()


def test_situacao_que_passou_e_resolvida_e_as_outras_continuam():
    db = _db()
    try:
        nvr = _cenario(db, alarmes=[_central(armada=False, disparada=True)])
        _verificar(db, nvr)
        assert _abertas(db, nvr) == {"3:4:DISPARO", "3:4:DESARMADA"}

        nvr.last_alarm_status = {**nvr.last_alarm_status, "alarmes": [_central(armada=False, disparada=False)]}
        db.commit()
        _verificar(db, nvr)
        assert _abertas(db, nvr) == {"3:4:DESARMADA"}
    finally:
        db.close()


def test_falha_na_consulta_notifica_e_mantem_o_disparo_aberto():
    db = _db()
    try:
        nvr = _cenario(db, alarmes=[_central(disparada=True)])
        _verificar(db, nvr)
        nvr.last_alarm_status = {**nvr.last_alarm_status, "erro": "login recusado", "alarmes": []}
        db.commit()
        _verificar(db, nvr)
        assert _abertas(db, nvr) == {"3:4:DISPARO", "FALHA"}

        nvr.last_alarm_status = {**nvr.last_alarm_status, "erro": None, "alarmes": [_central()]}
        db.commit()
        _verificar(db, nvr)
        assert _abertas(db, nvr) == set()
    finally:
        db.close()


def test_desmarcar_a_central_resolve_os_alertas():
    db = _db()
    try:
        nvr = _cenario(db, alarmes=[_central(disparada=True)])
        _verificar(db, nvr)
        nvr.alarmes_notificar = []
        db.commit()
        _verificar(db, nvr)
        assert _abertas(db, nvr) == set()
    finally:
        db.close()


def test_status_velho_nao_abre_nem_fecha():
    db = _db()
    try:
        nvr = _cenario(db, alarmes=[_central(disparada=True)], coletado=AGORA - timedelta(hours=2))
        _verificar(db, nvr)
        assert _abertas(db, nvr) == set()
    finally:
        db.close()


if __name__ == "__main__":
    for nome, funcao in list(globals().items()):
        if nome.startswith("test_"):
            funcao()
    print("OK")
