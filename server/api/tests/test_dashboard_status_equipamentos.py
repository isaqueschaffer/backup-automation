"""Widgets do Dashboard por Cliente para ANTENA, OLT e DEFENSE: lista branca (nada sensível sai), níveis de cor,
filtro por tipo/equipamento e o que o link público esconde (partição armada/desarmada)."""
import json
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.dashboards.layout import DashboardLayout, ids_referenciados
from services.dashboards.widgets import (
    ConfigAlarmesDefense,
    ConfigAntenas,
    ConfigStatusOlt,
    ContextoDados,
    construir_alarmes_defense,
    construir_antenas,
    construir_status_olt,
)

AGORA = datetime(2026, 11, 13, 15, 0, 0)
FMT = "%Y-%m-%dT%H:%M:%S"


def _t(minutos_atras: int) -> str:
    return (AGORA - timedelta(minutes=minutos_atras)).strftime(FMT)


def _eq(tipo, nome, **colunas):
    base = dict(id=uuid.uuid4(), tipo=tipo, name=nome, active=True, config_extra=None,
                antena_status=None, olt_status=None, last_alarm_status=None)
    base.update(colunas)
    return SimpleNamespace(**base)


def _ctx(equipamentos, publico=False):
    maquina = SimpleNamespace(id=uuid.uuid4(), name="Servidor", equipamentos=equipamentos)
    return ContextoDados(db=None, customer=None, maquinas=[maquina], periodo="7d", agora=AGORA, publico=publico)


ANTENA_STATUS = {
    "atualizado_em": _t(2), "erro": None,
    "mikrotik": {"identidade": "RB-Portaria", "ip": "10.0.0.1", "dispositivos": 42},
    "antenas": [
        {"nome": "Bloco A", "mac": "9C:2B:A6:71:6A:CF", "ip": "10.0.0.21", "status": "ONLINE", "ping_ms": 3,
         "marca": "Ubiquiti", "ultimo_online": _t(2), "offline_desde": None, "interface": "ether2"},
        {"nome": "Bloco C", "mac": "9C:2B:A6:71:6A:D0", "ip": "10.0.0.22", "status": "OFFLINE",
         "ultimo_online": _t(120), "offline_desde": _t(120)},
        {"nome": "Portaria", "mac": "9C:2B:A6:71:6A:D1", "status": "OFFLINE", "offline_desde": _t(5)},
        {"nome": "Garagem", "mac": "9C:2B:A6:71:6A:D2", "status": "SEM_REGISTRO", "offline_desde": _t(300)},
    ],
    "descobertas": [{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.0.0.99"}],
}


def test_antenas_niveis_ordem_e_lista_branca():
    eq = _eq("ANTENA", "Antenas Condomínio", antena_status=ANTENA_STATUS,
             config_extra={"porta_ssh": 2222, "antenas": [{"mac": "9C:2B:A6:71:6A:CF"}]})
    dados = construir_antenas(_ctx([eq, _eq("NVR", "NVR 1")]), ConfigAntenas())
    assert dados["total"] == {"total": 4, "online": 1, "offline": 2, "sem_registro": 1, "erro": 0}
    item = dados["equipamentos"][0]
    assert len(dados["equipamentos"]) == 1 and item["nivel"] == "critico" and not item["desatualizado"]
    nomes = [(a["nome"], a["nivel"]) for a in item["antenas"]]
    # vermelha: fora há mais de 10 min; amarela: fora há pouco ou sem registro; verde por último
    assert nomes[0] == ("Bloco C", "critico")
    assert ("Portaria", "atencao") in nomes and ("Garagem", "atencao") in nomes
    assert nomes[-1] == ("Bloco A", "ok")
    texto = json.dumps(dados)
    for proibido in ("10.0.0", "9C:2B", "RB-Portaria", "ether2", "2222", "AA:BB"):
        assert proibido not in texto


def test_antenas_sem_latencia_e_status_velho():
    velho = dict(ANTENA_STATUS, atualizado_em=_t(30))
    eq = _eq("ANTENA", "Antenas", antena_status=velho)
    dados = construir_antenas(_ctx([eq]), ConfigAntenas(mostrar_latencia=False))
    item = dados["equipamentos"][0]
    assert item["desatualizado"] and all("ping_ms" not in a for a in item["antenas"])
    vazio = construir_antenas(_ctx([_eq("ANTENA", "Nova")]), ConfigAntenas())["equipamentos"][0]
    assert vazio["sem_status"] and vazio["nivel"] == "atencao" and vazio["antenas"] == []


def test_filtro_por_equipamento_ignora_ids_de_fora():
    a1 = _eq("ANTENA", "A1", antena_status=ANTENA_STATUS)
    a2 = _eq("ANTENA", "A2", antena_status=ANTENA_STATUS)
    dados = construir_antenas(_ctx([a1, a2]), ConfigAntenas(equipamentos=[a2.id, uuid.uuid4()]))
    assert [e["nome"] for e in dados["equipamentos"]] == ["A2"]


OLT_STATUS = {
    "atualizado_em": _t(3),
    "olts": [
        {"nome": "OLT Centro", "ip": "192.168.5.1", "fabricante": "UNM2000", "modelo": "AN5516", "firmware": "x",
         "temperatura": 41,
         "totais": {"total": 100, "online": 90, "offline": 6, "falha": 2, "sem_energia": 2, "sinal_ruim": 4},
         "por_pon": [
             {"slot": 1, "pon": 3, "total": 40, "online": 39, "offline": 1, "falha": 0, "sem_energia": 0, "sinal_ruim": 1},
             {"slot": 2, "pon": 1, "total": 48, "online": 43, "offline": 5, "falha": 0, "sem_energia": 0, "sinal_ruim": 0},
             {"slot": 3, "pon": 1, "total": 12, "online": 12, "offline": 0, "falha": 0, "sem_energia": 0, "sinal_ruim": 0},
         ],
         "onus": [{"nome": "João da Silva", "serial": "FHTT1234", "mac": "00:11:22:33:44:55", "estado": "OFFLINE"}]},
        {"nome": "OLT Bairro", "ip": "192.168.5.2", "totais": {"total": 50, "online": 49, "offline": 1}},
        {"nome": "OLT Morro", "ip": "192.168.5.3", "erro": "Telnet recusado em 192.168.5.3"},
    ],
}


def test_olt_niveis_pons_licenca_e_sem_dado_de_assinante():
    eq = _eq("OLT", "UNM Matriz", olt_status=OLT_STATUS,
             config_extra={"licenca_fim": (AGORA + timedelta(days=5)).strftime("%Y-%m-%d"), "senha": "segredo"})
    dados = construir_status_olt(_ctx([eq]), ConfigStatusOlt())
    item = dados["equipamentos"][0]
    olts = {o["nome"]: o for o in item["olts"]}
    assert olts["OLT Centro"]["nivel"] == "critico" and olts["OLT Centro"]["percentual_fora"] == 10.0
    assert olts["OLT Bairro"]["nivel"] == "atencao"
    assert olts["OLT Morro"]["nivel"] == "critico" and olts["OLT Morro"]["falha_leitura"]
    assert [(p["slot"], p["pon"]) for p in olts["OLT Centro"]["pons"]] == [(2, 1), (1, 3)]
    assert item["licenca"]["nivel"] == "atencao" and item["nivel"] == "critico"
    assert dados["total"]["total"] == 150 and dados["total"]["online"] == 139
    texto = json.dumps(dados)
    for proibido in ("192.168", "João", "FHTT", "00:11:22", "segredo", "Telnet"):
        assert proibido not in texto


def test_olt_sem_pons_e_sem_licenca():
    eq = _eq("OLT", "OLT", olt_status=OLT_STATUS, config_extra={"licenca_fim": "2030-01-01"})
    dados = construir_status_olt(_ctx([eq]), ConfigStatusOlt(mostrar_pons=False, mostrar_licenca=False))
    item = dados["equipamentos"][0]
    assert item["licenca"] is None and all(o["pons"] == [] for o in item["olts"])


DEFENSE_STATUS = {
    "atualizado_em": _t(4), "ip": "172.16.0.9", "erro": None,
    "alarmes": [
        {"id": 12, "nome": "Central Galpão", "modelo": "AMT 4010", "status": 1,
         "particoes": [{"id": 1, "nome": "Depósito", "armada": True, "disparada": True},
                       {"id": 2, "nome": "Doca", "armada": False, "disparada": False}]},
        {"id": 13, "nome": "Central Loja", "modelo": "AMT 2018", "status": 0, "particoes": []},
        {"id": 14, "nome": "Central Escritório", "status": 1,
         "particoes": [{"id": 1, "nome": "Recepção", "armada": True, "disparada": False}]},
    ],
    "incendio": [{"id": 3, "nome": "Incêndio Bloco A", "modelo": "CIE 1125", "status": 1}],
}


def test_alarmes_niveis_e_armada_no_painel():
    eq = _eq("DEFENSE", "Defense", last_alarm_status=DEFENSE_STATUS)
    dados = construir_alarmes_defense(_ctx([eq]), ConfigAlarmesDefense())
    item = dados["equipamentos"][0]
    assert dados["mostra_armada"] and dados["total"] == {"centrais": 3, "desconectadas": 1, "disparos": 1}
    assert [(c["nome"], c["nivel"]) for c in item["centrais"]] == [
        ("Central Galpão", "critico"), ("Central Loja", "atencao"), ("Central Escritório", "ok")]
    assert item["centrais"][0]["particoes"][0] == {"nome": "Depósito", "disparada": True, "armada": True}
    assert item["incendio"] == [{"nome": "Incêndio Bloco A", "modelo": "CIE 1125"}]
    assert "172.16" not in json.dumps(dados)


def test_alarmes_link_publico_nao_mostra_armada():
    eq = _eq("DEFENSE", "Defense", last_alarm_status=DEFENSE_STATUS)
    dados = construir_alarmes_defense(_ctx([eq], publico=True), ConfigAlarmesDefense())
    assert not dados["mostra_armada"]
    texto = json.dumps(dados, ensure_ascii=False)
    assert '"armada"' not in texto and '"armadas"' not in texto and "Depósito" in texto


def test_ids_de_equipamento_dos_widgets_novos_entram_no_isolamento():
    e1, e2, e3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    layout = DashboardLayout.model_validate({"widgets": [
        {"id": "a", "tipo": "antenas", "config": {"equipamentos": [str(e1)]}},
        {"id": "o", "tipo": "status_olt", "config": {"equipamentos": [str(e2)]}},
        {"id": "d", "tipo": "alarmes_defense", "config": {"equipamentos": [str(e3)]}},
    ]})
    _, eqs = ids_referenciados(layout)
    assert eqs == {e1, e2, e3}
