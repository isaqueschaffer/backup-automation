"""Notificações de OLT (services/notificacoes.verificar_olt_equipamento): ONU offline (sem energia, fibra desconectada,
offline) e sinal óptico crítico, opt-in por equipamento (NVR.olt_notificar), um alerta por OLT depois de 10 min no
problema, e-mail só quando entram ONUs novas. SQLite em memória, como tests/test_antenas.py."""
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
from models import Conta, Machine, Notificacao, NVR
from services import notificacoes as servico

T0 = datetime(2026, 11, 13, 12, 0, 0)
_TABELAS = [Base.metadata.tables[n] for n in ("contas", "clients", "nvrs", "nvr_cameras", "notificacoes")]


def _db():
    for tabela in _TABELAS:
        for coluna in tabela.columns:
            if isinstance(coluna.type, ARRAY):
                coluna.type = JSON()
    Base.metadata.create_all(bind=engine, tables=_TABELAS)
    return SessionLocal()


def _onu(n, estado="ONLINE", qualidade="BOM", dbm=-20.0, nome=None):
    return {"slot": 1, "pon": 1, "onu": n, "estado": estado, "qualidade": qualidade, "sinal_olt_dbm": dbm,
            "nome": nome or f"Cliente {n}"}


def _status(onus, agora, erro=None, nome="OLT Sede"):
    olt = {"nome": nome, "ip": "10.0.0.1"}
    olt.update({"erro": erro} if erro else {"onus": onus})
    return {"atualizado_em": agora.strftime("%Y-%m-%dT%H:%M:%S"), "olts": [olt]}


def _cenario(db, onus, opcoes=None):
    conta = Conta(id=uuid.uuid4(), nome="Conta Teste", tipo="INTEGRADOR")
    mid = uuid.uuid4()
    machine = Machine(id=mid, conta_id=conta.id, name="Maquina", api_key_hash=mid.hex, api_key_prefix="sk_t",
                      backup_hour=2, backup_minute=0, active=True)
    nvr = NVR(id=uuid.uuid4(), machine_id=mid, tipo="OLT", name="OLT Sede", ip="10.0.0.1", username="u", password="x",
              active=True, olt_notificar=opcoes if opcoes is not None else {"onu_offline": True, "sinal_critico": True})
    nvr.olt_status = _status(onus, T0)
    db.add_all([conta, machine, nvr])
    db.commit()
    return nvr


def _rodar(db, nvr, agora, onus=None, erro=None, email=True):
    if onus is not None or erro:
        nvr.olt_status = _status(onus, agora, erro)
    with patch.object(servico, "_enviar_email_alarme", return_value=email) as envio:
        servico.verificar_olt_equipamento(db, nvr, agora)
    db.commit()
    return envio


def _abertas(db, nvr, tipo):
    return db.query(Notificacao).filter(Notificacao.tipo == tipo, Notificacao.nvr_id == nvr.id,
                                         Notificacao.resolvido_em.is_(None)).all()


def test_so_avisa_depois_de_10_minutos():
    db = _db()
    try:
        onus = [_onu(1, "SEM_ENERGIA"), _onu(2)]
        nvr = _cenario(db, onus)
        envio = _rodar(db, nvr, T0, onus)
        assert _abertas(db, nvr, "ONU_OFFLINE") == [] and envio.call_count == 0
        envio = _rodar(db, nvr, T0 + timedelta(minutes=5), onus)
        assert _abertas(db, nvr, "ONU_OFFLINE") == []
        envio = _rodar(db, nvr, T0 + timedelta(minutes=10), onus)
        (n,) = _abertas(db, nvr, "ONU_OFFLINE")
        assert n.referencia == "OLT Sede" and "1 ONU(s) offline" in n.titulo and "sem energia" in n.mensagem
        assert envio.call_count == 1
    finally:
        db.close()


def test_um_alerta_por_olt_com_contagem_por_causa():
    db = _db()
    try:
        onus = [_onu(1, "SEM_ENERGIA"), _onu(2, "SEM_ENERGIA"), _onu(3, "FALHA"), _onu(4, "OFFLINE"), _onu(5)]
        nvr = _cenario(db, onus)
        _rodar(db, nvr, T0, onus)
        _rodar(db, nvr, T0 + timedelta(minutes=10), onus)
        (n,) = _abertas(db, nvr, "ONU_OFFLINE")
        assert "4 ONU(s) offline" in n.titulo
        assert "2 sem energia" in n.mensagem and "1 fibra desconectada" in n.mensagem and "1 offline" in n.mensagem
        assert "Cliente 5" not in n.mensagem
    finally:
        db.close()


def test_email_so_para_onus_novas_e_resolve_quando_voltam():
    db = _db()
    try:
        um = [_onu(1, "OFFLINE"), _onu(2)]
        nvr = _cenario(db, um)
        _rodar(db, nvr, T0, um)
        assert _rodar(db, nvr, T0 + timedelta(minutes=10), um).call_count == 1
        assert _rodar(db, nvr, T0 + timedelta(minutes=15), um).call_count == 0  # nada novo: não repete
        dois = [_onu(1, "OFFLINE"), _onu(2, "OFFLINE")]
        _rodar(db, nvr, T0 + timedelta(minutes=20), dois)  # a 2 entrou agora: ainda não venceu os 10 min
        envio = _rodar(db, nvr, T0 + timedelta(minutes=30), dois)
        assert envio.call_count == 1 and "2 ONU(s) offline" in _abertas(db, nvr, "ONU_OFFLINE")[0].titulo
        _rodar(db, nvr, T0 + timedelta(minutes=35), [_onu(1), _onu(2)])
        assert _abertas(db, nvr, "ONU_OFFLINE") == []
    finally:
        db.close()


def test_email_que_falhou_e_tentado_de_novo():
    db = _db()
    try:
        um = [_onu(1, "OFFLINE")]
        nvr = _cenario(db, um)
        _rodar(db, nvr, T0, um)
        _rodar(db, nvr, T0 + timedelta(minutes=10), um, email=False)
        assert _rodar(db, nvr, T0 + timedelta(minutes=15), um).call_count == 1
    finally:
        db.close()


def test_sinal_critico_separado_e_so_em_onu_online():
    db = _db()
    try:
        onus = [_onu(1, qualidade="RUIM", dbm=-28.4), _onu(2, "OFFLINE", qualidade="RUIM"), _onu(3, qualidade="ATENCAO")]
        nvr = _cenario(db, onus, {"sinal_critico": True})
        _rodar(db, nvr, T0, onus)
        _rodar(db, nvr, T0 + timedelta(minutes=10), onus)
        (n,) = _abertas(db, nvr, "SINAL_OPTICO")
        assert "1 ONU(s) com sinal óptico crítico" in n.titulo and "-28,4 dBm" in n.mensagem
        assert _abertas(db, nvr, "ONU_OFFLINE") == []  # aviso de ONU offline está desligado
    finally:
        db.close()


def test_olt_sem_resposta_mantem_o_alerta_e_a_contagem():
    db = _db()
    try:
        um = [_onu(1, "OFFLINE")]
        nvr = _cenario(db, um)
        _rodar(db, nvr, T0, um)
        _rodar(db, nvr, T0 + timedelta(minutes=10), um)
        _rodar(db, nvr, T0 + timedelta(minutes=15), erro="Telnet sem resposta")
        assert len(_abertas(db, nvr, "ONU_OFFLINE")) == 1
        # voltou a responder com a ONU ainda offline: não reavisa (já avisada) e o tempo não recomeça
        assert _rodar(db, nvr, T0 + timedelta(minutes=20), um).call_count == 0
        assert len(_abertas(db, nvr, "ONU_OFFLINE")) == 1
    finally:
        db.close()


def test_desligar_o_aviso_resolve_e_status_velho_nao_mexe():
    db = _db()
    try:
        um = [_onu(1, "OFFLINE")]
        nvr = _cenario(db, um)
        _rodar(db, nvr, T0, um)
        _rodar(db, nvr, T0 + timedelta(minutes=10), um)
        # status de 30 min atrás: não abre nem fecha
        nvr.olt_notificar = {"onu_offline": False}
        with patch.object(servico, "_enviar_email_alarme", return_value=True):
            servico.verificar_olt_equipamento(db, nvr, T0 + timedelta(minutes=40))
        db.commit()
        assert len(_abertas(db, nvr, "ONU_OFFLINE")) == 1
        _rodar(db, nvr, T0 + timedelta(minutes=41), um)
        assert _abertas(db, nvr, "ONU_OFFLINE") == []
    finally:
        db.close()
