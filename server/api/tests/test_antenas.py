"""Equipamento ANTENA: validação do cadastro (MAC, porta, prefixos), mescla do status enviado pelo agente (queda, último IP)
e notificação ANTENA_OFFLINE (services/antenas.py e services/notificacoes.py). Roda com SQLite em memória, como
tests/test_alarmes_notificacao.py."""
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
os.environ["FERNET_KEY"] = "dGVzdF9mZXJuZXRfa2V5XzMyX2J5dGVzX2xvbmdfISE="  # 32 bytes válidos (a chave dos outros testes tem 31)
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("ADMIN_PASSWORD", "senha_de_teste")

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import ARRAY

from database import Base, engine, SessionLocal
from models import Conta, Machine, Notificacao, NVR
from services import antenas as servico_antenas
from services import notificacoes as servico

AGORA = datetime(2026, 11, 13, 12, 0, 0)
_TABELAS = [Base.metadata.tables[n] for n in ("contas", "clients", "nvrs", "nvr_cameras", "notificacoes")]


def _txt(d):
    return d.strftime("%Y-%m-%dT%H:%M:%S")


# ── cadastro ──────────────────────────────────────────────────────────────

def test_normaliza_mac_e_tolerancia_de_32():
    assert servico_antenas.normalizar_mac("9c2b.a671.6acf") == "9C:2B:A6:71:6A:CF"
    assert servico_antenas.normalizar_mac("9c-2b-a6-71-6a-cf") == "9C:2B:A6:71:6A:CF"
    assert servico_antenas.normalizar_mac("9c2b.a671") is None
    assert servico_antenas.normalizar_mac("zz:2b:a6:71:6a:cf") is None
    assert servico_antenas.macs_proximos("9C:2B:A6:71:6A:CF", "9C:2B:A6:71:6A:D0")
    assert servico_antenas.macs_proximos("9C:2B:A6:71:6A:CF", "9C:2B:A6:71:6A:EF")      # +32
    assert not servico_antenas.macs_proximos("9C:2B:A6:71:6A:CF", "9C:2B:A6:71:6A:F0")  # +33
    assert not servico_antenas.macs_proximos("9C:2B:A6:71:6A:CF", "9D:2B:A6:71:6A:D0")  # outro fabricante


def test_config_valida_e_normalizada():
    cfg = servico_antenas.normalizar_config({
        "porta_ssh": "22", "prefixos_mac": "9c:2b:a6, 54-16-51, lixo",
        "antenas": [{"nome": "  Sala  ", "mac": "9c2b.a671.6acf", "ip": "192.168.75.123"}, {"nome": "", "mac": "AA:BB:CC:00:00:01", "notificar": False}],
    })
    assert cfg["porta_ssh"] == 22
    assert cfg["prefixos_mac"] == "9C:2B:A6, 54:16:51"
    assert cfg["antenas"][0] == {"nome": "Sala", "mac": "9C:2B:A6:71:6A:CF", "ip": "192.168.75.123", "notificar": True}
    assert cfg["antenas"][1]["nome"] == "Antena 00:01" and cfg["antenas"][1]["notificar"] is False and "ip" not in cfg["antenas"][1]


def test_marca_da_antena_e_normalizada_e_opcional():
    cfg = servico_antenas.normalizar_config({"antenas": [
        {"nome": "A", "mac": "AA:BB:CC:00:00:01", "marca": "  Ruijie   Reyee "},
        {"nome": "B", "mac": "AA:BB:CC:00:00:99", "marca": "   "},
        {"nome": "C", "mac": "AA:BB:CC:00:01:99", "marca": "x" * 80},
    ]})
    a, b, c = cfg["antenas"]
    assert a["marca"] == "Ruijie Reyee" and "marca" not in b and len(c["marca"]) == 40


def test_config_rejeita_mac_ip_porta_e_repeticao():
    erros = []
    for cfg in (
        {"antenas": [{"nome": "x", "mac": "123"}]},
        {"antenas": [{"nome": "x", "mac": "AA:BB:CC:00:00:01", "ip": "abc"}]},
        {"antenas": [{"mac": "AA:BB:CC:00:00:01"}, {"mac": "aabb.cc00.0001"}]},
        {"porta_ssh": 70000},
        {"porta_ssh": "abc"},
        {"antenas": "não é lista"},
        {"antenas": [{"mac": "AA:BB:CC:00:%02X:01" % (i % 256)} for i in range(201)]},
    ):
        try:
            servico_antenas.normalizar_config(cfg)
        except ValueError as e:
            erros.append(str(e))
    assert len(erros) == 7


def test_config_vazia_ganha_padroes():
    cfg = servico_antenas.normalizar_config({})
    assert cfg == {"porta_ssh": 22, "prefixos_mac": "", "antenas": []}
    assert servico_antenas.normalizar_config(None) is None


# ── mescla do status ──────────────────────────────────────────────────────

def _antena(status="ONLINE", mac="9C:2B:A6:71:6A:CF", ip="192.168.75.123", **extra):
    return {"nome": "Sala", "mac": mac, "ip": ip, "hostname": "TESTE", "status": status, "notificar": True, **extra}


def test_mescla_online_marca_ultimo_online_e_limpa_queda():
    anterior = {"antenas": [_antena("OFFLINE", ultimo_online="2026-11-13T10:00:00", offline_desde="2026-11-13T11:00:00")]}
    novo = servico_antenas.mesclar_status(anterior, {"antenas": [_antena("ONLINE")]}, AGORA)["antenas"][0]
    assert novo["ultimo_online"] == _txt(AGORA) and novo["offline_desde"] is None


def test_mescla_primeira_queda_guarda_o_momento_e_depois_mantem():
    primeira = servico_antenas.mesclar_status({"antenas": [_antena("ONLINE", ultimo_online="2026-11-13T11:55:00")]},
                                             {"antenas": [_antena("OFFLINE")]}, AGORA)
    a = primeira["antenas"][0]
    assert a["offline_desde"] == _txt(AGORA) and a["ultimo_online"] == "2026-11-13T11:55:00"
    depois = servico_antenas.mesclar_status(primeira, {"antenas": [_antena("OFFLINE")]}, AGORA + timedelta(minutes=9))
    assert depois["antenas"][0]["offline_desde"] == _txt(AGORA)  # não recomeça a contagem


def test_mescla_guarda_o_ultimo_ip_quando_a_antena_some():
    anterior = {"antenas": [_antena("ONLINE")]}
    sumida = _antena("SEM_REGISTRO", ip="", hostname="")
    a = servico_antenas.mesclar_status(anterior, {"antenas": [sumida]}, AGORA)["antenas"][0]
    assert (a["ip"], a["hostname"], a["ip_ultimo"]) == ("192.168.75.123", "TESTE", True)


def test_mescla_com_erro_mantem_o_estado_anterior():
    anterior = {"antenas": [_antena("ONLINE")], "descobertas": [{"mac": "AA:BB:CC:00:00:09"}], "mikrotik": {"identidade": "MK"}}
    s = servico_antenas.mesclar_status(anterior, {"erro": "SSH recusado", "antenas": []}, AGORA)
    assert s["erro"] == "SSH recusado" and len(s["antenas"]) == 1 and s["mikrotik"] == {"identidade": "MK"}
    assert s["atualizado_em"] == _txt(AGORA)


def test_mescla_situacao_desconhecida_vira_erro():
    a = servico_antenas.mesclar_status({}, {"antenas": [_antena("???")]}, AGORA)["antenas"][0]
    assert a["status"] == "ERRO"


# ── notificação ───────────────────────────────────────────────────────────

def _db():
    # O SQLite não tem ARRAY (clients.email_to): nestes testes a coluna vira JSON
    for tabela in _TABELAS:
        for coluna in tabela.columns:
            if isinstance(coluna.type, ARRAY):
                coluna.type = JSON()
    Base.metadata.create_all(bind=engine, tables=_TABELAS)
    return SessionLocal()


def _cenario(db, antenas, erro=None, coletado=AGORA):
    conta = Conta(id=uuid.uuid4(), nome="Conta Teste", tipo="INTEGRADOR")
    mid = uuid.uuid4()
    machine = Machine(id=mid, conta_id=conta.id, name="Maquina Teste", api_key_hash=mid.hex, api_key_prefix="sk_test", backup_hour=2, backup_minute=0, active=True)
    nvr = NVR(id=uuid.uuid4(), machine_id=machine.id, tipo="ANTENA", name="Antenas Sede", ip="192.168.75.1",
              username="u", password="x", active=True)
    nvr.antena_status = {"atualizado_em": _txt(coletado), "erro": erro, "mikrotik": {}, "antenas": antenas, "descobertas": []}
    db.add_all([conta, machine, nvr])
    db.commit()
    return nvr


def _abertas(db, nvr):
    return {n.referencia for n in db.query(Notificacao).filter(
        Notificacao.tipo == "ANTENA_OFFLINE", Notificacao.nvr_id == nvr.id, Notificacao.resolvido_em.is_(None))}


def _verificar(db, nvr, agora=AGORA, email=False):
    with patch.object(servico, "_enviar_email_antena", return_value=email) as envio:
        servico.verificar_antenas_equipamento(db, nvr, agora)
    db.commit()
    return envio


def _fora(minutos, **extra):
    return _antena("OFFLINE", offline_desde=_txt(AGORA - timedelta(minutes=minutos)), **extra)


def test_antena_online_nao_notifica():
    db = _db()
    try:
        nvr = _cenario(db, [_antena("ONLINE")])
        _verificar(db, nvr)
        assert _abertas(db, nvr) == set()
    finally:
        db.close()


def test_queda_recente_ainda_nao_notifica_e_a_antiga_sim():
    db = _db()
    try:
        nvr = _cenario(db, [_fora(5)])
        _verificar(db, nvr)
        assert _abertas(db, nvr) == set()
        nvr.antena_status = {**nvr.antena_status, "antenas": [_fora(11)]}
        _verificar(db, nvr)
        assert _abertas(db, nvr) == {"9C:2B:A6:71:6A:CF"}
        n = db.query(Notificacao).filter_by(nvr_id=nvr.id).one()
        assert "Sala" in n.titulo and "Antenas Sede" in n.titulo and "9C:2B:A6:71:6A:CF" in n.mensagem and "192.168.75.123" in n.mensagem
    finally:
        db.close()


def test_sem_registro_tambem_notifica():
    db = _db()
    try:
        nvr = _cenario(db, [{**_fora(30), "status": "SEM_REGISTRO", "ip": ""}])
        _verificar(db, nvr)
        assert _abertas(db, nvr) == {"9C:2B:A6:71:6A:CF"}
    finally:
        db.close()


def test_antena_com_notificar_desligado_nao_notifica():
    db = _db()
    try:
        nvr = _cenario(db, [_fora(60, notificar=False)])
        _verificar(db, nvr)
        assert _abertas(db, nvr) == set()
    finally:
        db.close()


def test_volta_resolve_e_avisa_so_se_o_alerta_tinha_email():
    db = _db()
    try:
        nvr = _cenario(db, [_fora(20)])
        _verificar(db, nvr, email=True)  # e-mail de queda enviado
        notif = db.query(Notificacao).filter_by(nvr_id=nvr.id).one()
        assert notif.ultimo_email_em == AGORA.date()
        nvr.antena_status = {**nvr.antena_status, "antenas": [_antena("ONLINE")]}
        envio = _verificar(db, nvr, email=True)
        assert _abertas(db, nvr) == set()
        assert envio.call_count == 1 and "voltou" in envio.call_args.args[2]
    finally:
        db.close()


def test_antena_removida_do_cadastro_fecha_sem_avisar_que_voltou():
    db = _db()
    try:
        nvr = _cenario(db, [_fora(20)])
        _verificar(db, nvr, email=True)
        nvr.antena_status = {**nvr.antena_status, "antenas": []}
        envio = _verificar(db, nvr, email=True)
        assert _abertas(db, nvr) == set() and envio.call_count == 0
    finally:
        db.close()


def test_falha_do_mikrotik_abre_um_alerta_e_nao_mexe_nas_antenas():
    db = _db()
    try:
        nvr = _cenario(db, [_fora(20)])
        _verificar(db, nvr)
        assert _abertas(db, nvr) == {"9C:2B:A6:71:6A:CF"}
        nvr.antena_status = {**nvr.antena_status, "erro": "SSH recusado"}
        _verificar(db, nvr)
        assert _abertas(db, nvr) == {"9C:2B:A6:71:6A:CF", "FALHA"}  # a queda segue aberta: não dá para saber se voltou
        nvr.antena_status = {**nvr.antena_status, "erro": None, "antenas": [_antena("ONLINE")]}
        _verificar(db, nvr)
        assert _abertas(db, nvr) == set()
    finally:
        db.close()


def test_relatorio_velho_nao_abre_nem_fecha():
    db = _db()
    try:
        nvr = _cenario(db, [_fora(60)], coletado=AGORA - timedelta(minutes=30))
        _verificar(db, nvr)
        assert _abertas(db, nvr) == set()
    finally:
        db.close()
