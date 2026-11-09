import base64
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

import pytest

# Add server/api to path
API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
os.environ["FERNET_KEY"] = "dGVzdF9mZXJuZXRfa2V5XzMyX2J5dGVzX2xvbmdfIQ=="
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("ADMIN_PASSWORD", "test")

from models import NVR, NVRCamera
from services import whatsapp_relatorios, whatsapp_service
from whatsapp_numero import normalizar_lista, normalizar_numero

CFG = {"url": "http://whatsapp:3000", "instance": "trilan", "apikey": "chave"}
JPEG = b"\xff\xd8\xff\xe0fake-jpeg"
B64 = base64.b64encode(JPEG).decode()


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


# ─── Normalização de números ────────────────────────────────────────────────

def test_normaliza_numero_brasileiro_sem_ddi():
    assert normalizar_numero("(11) 99999-8888") == "5511999998888"
    assert normalizar_numero("11 3333-4444") == "551133334444"


def test_normaliza_numero_com_ddi_e_prefixo_internacional():
    assert normalizar_numero("+55 11 99999-8888") == "5511999998888"
    assert normalizar_numero("0055 11 99999-8888") == "5511999998888"
    assert normalizar_numero("+1 415 555 2671") == "14155552671"


def test_numero_vazio_vira_none_e_invalido_levanta():
    assert normalizar_numero("") is None
    assert normalizar_numero(None) is None
    assert normalizar_numero("   ") is None
    with pytest.raises(ValueError):
        normalizar_numero("12345")
    with pytest.raises(ValueError):
        normalizar_numero("1234567890123456789")


def test_normaliza_lista_remove_vazios_e_repetidos_e_aceita_varios_por_entrada():
    assert normalizar_lista(None) is None
    assert normalizar_lista(["11 99999-8888", "", "5511999998888", "21 98888-7777, 31 97777-6666"]) == [
        "5511999998888", "5521988887777", "5531977776666",
    ]


# ─── Configuração ───────────────────────────────────────────────────────────

def test_sem_chave_o_whatsapp_fica_desligado(monkeypatch):
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_BRIDGE_KEY", None)
    assert whatsapp_service.whatsapp_config() is None
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_BRIDGE_KEY", "   ")
    assert whatsapp_service.whatsapp_config() is None


def test_config_padrao_aponta_para_o_container(monkeypatch):
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_BRIDGE_KEY", "k" * 20)
    assert whatsapp_service.whatsapp_config() == {"url": "http://whatsapp:3000", "instance": "trilan", "apikey": "k" * 20}


def test_config_tira_barra_final_da_url(monkeypatch):
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_BRIDGE_KEY", "k" * 20)
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_BRIDGE_URL", "http://ponte:3000/ ")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_INSTANCE", "outra")
    assert whatsapp_service.whatsapp_config() == {"url": "http://ponte:3000", "instance": "outra", "apikey": "k" * 20}


# ─── Envio (rotas da ponte do WhatsApp) ─────────────────────────────────────

class _Resp:
    def __init__(self, status=201, text="ok"):
        self.status_code, self.text = status, text


@pytest.fixture
def chamadas(monkeypatch):
    """Captura os POSTs e zera as pausas."""
    registro = []
    monkeypatch.setattr(whatsapp_service.time, "sleep", lambda s: None)
    monkeypatch.setattr(whatsapp_service, "whatsapp_config", lambda: CFG)

    def _post(url, json=None, headers=None, timeout=None):
        registro.append({"url": url, "json": json, "headers": headers})
        return _Resp()

    monkeypatch.setattr(whatsapp_service.requests, "post", _post)
    return registro


def test_envia_texto_e_imagens_para_cada_numero(chamadas):
    ok = whatsapp_service.enviar_whatsapp(
        None, ["5511999998888", "5521988887777"], "Olá", [("Cam 1.jpg", JPEG)], contexto="teste",
    )
    assert ok
    urls = [c["url"] for c in chamadas]
    assert urls == [
        "http://whatsapp:3000/message/sendText/trilan",
        "http://whatsapp:3000/message/sendMedia/trilan",
        "http://whatsapp:3000/message/sendText/trilan",
        "http://whatsapp:3000/message/sendMedia/trilan",
    ]
    assert all(c["headers"] == {"apikey": "chave"} for c in chamadas)
    assert chamadas[0]["json"] == {"number": "5511999998888", "text": "Olá"}
    media = chamadas[1]["json"]
    assert media["mediatype"] == "image" and media["mimetype"] == "image/jpeg"
    assert media["fileName"] == "Cam 1.jpg" and media["caption"] == "📷 Cam 1"
    assert base64.b64decode(media["media"]) == JPEG


def test_sem_numeros_ou_sem_config_nao_envia(chamadas, monkeypatch):
    assert whatsapp_service.enviar_whatsapp(None, [], "x") is False
    assert whatsapp_service.enviar_whatsapp(None, None, "x") is False
    monkeypatch.setattr(whatsapp_service, "whatsapp_config", lambda: None)
    assert whatsapp_service.enviar_whatsapp(None, ["5511999998888"], "x") is False
    assert chamadas == []


def test_erro_4xx_nao_repete_e_5xx_repete(monkeypatch):
    monkeypatch.setattr(whatsapp_service.time, "sleep", lambda s: None)
    monkeypatch.setattr(whatsapp_service, "whatsapp_config", lambda: CFG)
    tentativas = {"n": 0}

    def _post_400(*a, **k):
        tentativas["n"] += 1
        return _Resp(400, "bad")

    monkeypatch.setattr(whatsapp_service.requests, "post", _post_400)
    assert whatsapp_service.enviar_whatsapp(None, ["5511999998888"], "x") is False
    assert tentativas["n"] == 1

    tentativas["n"] = 0

    def _post_500_depois_ok(*a, **k):
        tentativas["n"] += 1
        return _Resp(500) if tentativas["n"] < 3 else _Resp(201)

    monkeypatch.setattr(whatsapp_service.requests, "post", _post_500_depois_ok)
    assert whatsapp_service.enviar_whatsapp(None, ["5511999998888"], "x") is True
    assert tentativas["n"] == 3


def test_excecao_de_rede_nao_vaza(monkeypatch):
    monkeypatch.setattr(whatsapp_service.time, "sleep", lambda s: None)
    monkeypatch.setattr(whatsapp_service, "whatsapp_config", lambda: CFG)

    def _boom(*a, **k):
        raise whatsapp_service.requests.ConnectionError("sem rede")

    monkeypatch.setattr(whatsapp_service.requests, "post", _boom)
    assert whatsapp_service.enviar_whatsapp(None, ["5511999998888"], "x") is False


def test_falha_na_imagem_nao_derruba_o_envio(monkeypatch):
    monkeypatch.setattr(whatsapp_service.time, "sleep", lambda s: None)
    monkeypatch.setattr(whatsapp_service, "whatsapp_config", lambda: CFG)
    monkeypatch.setattr(whatsapp_service.requests, "post",
                        lambda url, **k: _Resp(201) if "sendText" in url else _Resp(400))
    assert whatsapp_service.enviar_whatsapp(None, ["5511999998888"], "x", [("a.jpg", JPEG)]) is True


# ─── Mensagens dos relatórios ───────────────────────────────────────────────

class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *criteria):
        rows = self.rows
        for c in criteria:
            col = c.left.key if hasattr(c.left, "key") else c.left.name
            val = c.right.value
            attr = {"client_id": "machine_id"}.get(col, col)
            rows = [r for r in rows if getattr(r, attr) == val]
        return _FakeQuery(rows)

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)


class _FakeDB:
    def __init__(self, nvrs, cams):
        self.data = {NVR: nvrs, NVRCamera: cams}

    def query(self, model):
        return _FakeQuery(self.data.get(model, []))


def _setup(n_offline=2):
    machine_id = uuid.uuid4()
    nvr = _Obj(id=uuid.uuid4(), machine_id=machine_id, name="NVR Portaria", tipo="NVR", active=True)
    cams_db = [_Obj(nvr_id=nvr.id, canal=ch, perfect_image_base64=B64) for ch in range(1, n_offline + 1)]
    results = [
        {
            "nome": "NVR Portaria", "tipo": "NVR", "status": "OK",
            "cameras": [{"canal": ch, "nome": f"Cam {ch}", "status_comunicacao": "OFFLINE"} for ch in range(1, n_offline + 1)]
            + [{"canal": 99, "nome": "Online", "status_comunicacao": "ONLINE"}],
        },
        {"nome": "OLT Centro", "tipo": "OLT", "status": "ERRO"},
    ]
    return machine_id, _FakeDB([nvr], cams_db), results


@pytest.fixture
def enviados(monkeypatch):
    registro = []

    def _enviar(db, numeros, texto, imagens=None, contexto=""):
        registro.append({"numeros": list(numeros), "texto": texto, "imagens": list(imagens or [])})
        return True

    monkeypatch.setattr(whatsapp_relatorios, "enviar_whatsapp", _enviar)
    return registro


def test_relatorio_da_maquina_resumido_com_imagens(enviados):
    machine_id, db, results = _setup(2)
    assert whatsapp_relatorios.enviar_relatorio_maquina(
        db, "POP Centro", results, ["5511999998888"], machine_id=machine_id,
        backup_id="abc", public_url="https://painel.x", base_url="http://local",
    )
    msg = enviados[0]
    assert msg["numeros"] == ["5511999998888"]
    t = msg["texto"]
    assert "*POP Centro POP" in t and "COM ERROS" in t
    assert "Equipamentos: 2 (1 OK, 1 com falha)" in t
    assert "📹 Câmeras: 1 online, 2 offline" in t
    assert "❌ OLT Centro: ERRO" in t and "NVR Portaria:" not in t.split("Com falha:")[1]
    assert "https://painel.x/api/v1/backups/public-download/abc" in t
    assert "2 a seguir" in t
    assert [n for n, _ in msg["imagens"]] == ["Cam 1.jpg", "Cam 2.jpg"]


def test_relatorio_da_maquina_sem_numero_nao_envia(enviados):
    machine_id, db, results = _setup(1)
    assert whatsapp_relatorios.enviar_relatorio_maquina(db, "POP", results, [], machine_id=machine_id) is False
    assert enviados == []


def test_relatorio_limita_imagens_e_avisa(enviados):
    machine_id, db, results = _setup(12)
    whatsapp_relatorios.enviar_relatorio_maquina(db, "POP", results, ["5511999998888"], machine_id=machine_id)
    msg = enviados[0]
    assert len(msg["imagens"]) == whatsapp_relatorios.MAX_OFFLINE_IMAGES == 10
    assert "10 a seguir (de 12; as demais vão no e-mail)" in msg["texto"]


def test_relatorio_do_cliente_resume_maquinas_e_falhas(enviados):
    machine_id, db, results = _setup(1)
    entries = [
        {"machine_id": machine_id, "name": "Maq A", "status": "PARTIAL", "nvr_results": results},
        {"machine_id": None, "name": "Maq B", "status": None, "nvr_results": []},
    ]
    assert whatsapp_relatorios.enviar_relatorio_cliente(
        db, "Cliente X", "run-1", "scheduled", datetime(2026, 11, 9, 5, 0), entries, ["5511999998888"],
        has_zip=True, public_url="https://painel.x",
    )
    t = enviados[0]["texto"]
    assert "*Cliente X" in t and "09/11/2026 – 02:00" in t and "Agendado" in t  # BRT = UTC-3
    assert "Resumo (1/2 máquina(s) reportaram)" in t
    assert "Maq B: não executou" in t
    assert "❌ Maq A › OLT Centro: ERRO" in t
    assert "https://painel.x/api/v1/backups/public-run-download/run-1" in t
    assert len(enviados[0]["imagens"]) == 1


def test_montagem_com_erro_nao_vaza(monkeypatch):
    monkeypatch.setattr(whatsapp_relatorios, "_tipos_cadastrados", lambda db, ids: (_ for _ in ()).throw(RuntimeError("x")))
    assert whatsapp_relatorios.enviar_relatorio_maquina(None, "POP", [], ["5511999998888"]) is False


def test_aviso_curto(enviados):
    assert whatsapp_relatorios.enviar_aviso_whatsapp(None, ["5511999998888"], "Licença vencida", "Renove.")
    assert enviados[0]["texto"].startswith("*Licença vencida*\n\nRenove.")
    assert whatsapp_relatorios.enviar_aviso_whatsapp(None, [], "x", "y") is False
