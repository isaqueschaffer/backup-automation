"""Rotas `async def` não podem tocar o banco (nem rodar bcrypt) no laço de eventos (API-01, auditoria de 25/11/2026):
com o pool cheio o laço parava esperando conexão e todos os pings travavam (API fora do ar em 23/11/2026).

Sessão falsa (sem banco real): cada chamada ao banco anota se rodou com um laço de eventos ativo na thread. Dentro de
asyncio.to_thread não há laço na thread, então a lista `no_laco` precisa terminar vazia."""
import asyncio
import uuid
from types import SimpleNamespace

import pytest


def _no_laco() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


class _Vigia:
    def __init__(self):
        self.no_laco = []
        self.chamadas = []

    def marcar(self, nome):
        self.chamadas.append(nome)
        if _no_laco():
            self.no_laco.append(nome)


class _Consulta:
    def __init__(self, vigia, resultado):
        self._v, self._r = vigia, resultado

    def filter(self, *a, **k):
        self._v.marcar("filter")
        return self

    def first(self):
        self._v.marcar("first")
        return self._r

    def all(self):
        self._v.marcar("all")
        return [self._r] if self._r is not None else []

    def delete(self, *a, **k):
        self._v.marcar("delete")
        return 0


class _Db:
    """Sessão falsa: `query(Modelo)` devolve o objeto cadastrado para o modelo; todo método anota a thread."""

    def __init__(self, vigia, por_modelo=None):
        self._v = vigia
        self._por_modelo = por_modelo or {}

    def query(self, modelo, *a, **k):
        self._v.marcar("query")
        return _Consulta(self._v, self._por_modelo.get(modelo))

    def __getattr__(self, nome):  # add, commit, close, refresh, rollback, delete, get...
        def metodo(*a, **k):
            self._v.marcar(nome)
        return metodo


def _ctx():
    return SimpleNamespace(somente_leitura=False, feito_por="admin@teste.com")


async def _responder_agente(pendentes: dict, chave: str, resultado, tarefa_rota):
    """Faz o papel do agente: espera a tarefa aparecer, entrega o resultado e devolve a resposta da rota."""
    for _ in range(500):
        entry = pendentes.get(chave)
        if entry is not None or tarefa_rota.done():
            break
        await asyncio.sleep(0.01)
    if tarefa_rota.done():
        return await tarefa_rota
    entry["result"] = resultado
    entry["event"].set()
    return await tarefa_rota


# ─── test-rtsp ────────────────────────────────────────────────────────────
def _nvr(eid):
    return SimpleNamespace(id=eid, tipo="NVR", ip=" 10.0.0.5 ", password=None, config_extra={}, last_recording_status=[],
                           username="admin", name="NVR 1")


@pytest.fixture()
def rotas_equip(monkeypatch):
    from routers import equipamentos

    vigia = _Vigia()
    monkeypatch.setattr(equipamentos, "_get_machine_or_404", lambda mid, db, ctx: vigia.marcar("obter_maquina"))
    monkeypatch.setattr(equipamentos, "registrar_alteracao", lambda db, *a, **k: vigia.marcar("registrar_alteracao"))
    monkeypatch.setattr(equipamentos, "_marcar_imagem_noite", lambda db, *a, **k: vigia.marcar("marcar_noite"))
    return equipamentos, vigia


def test_rtsp_ao_vivo_banco_fora_do_laco(rotas_equip):
    from models import NVR
    from routers.agent import pending_rtsp_tasks
    from schemas import RTSPTestResponse

    equipamentos, vigia = rotas_equip
    mid, eid = uuid.uuid4(), uuid.uuid4()
    db = _Db(vigia, {NVR: _nvr(eid)})

    async def cenario():
        rota = asyncio.create_task(equipamentos.test_equipamento_rtsp(
            machine_id=mid, equipamento_id=eid, canal=1, modo="ao_vivo", nome=None, db=db, ctx=_ctx()))
        return await _responder_agente(pending_rtsp_tasks, str(mid), RTSPTestResponse(success=True, image_base64="x"), rota)

    resp = asyncio.run(cenario())
    assert resp.success is True and resp.image_base64 == "x"
    assert "registrar_alteracao" in vigia.chamadas and "commit" in vigia.chamadas and "close" in vigia.chamadas
    assert vigia.no_laco == []
    assert str(mid) not in pending_rtsp_tasks


def test_rtsp_noite_falha_grava_motivo_fora_do_laco(rotas_equip):
    from models import NVR
    from routers.agent import pending_rtsp_tasks
    from schemas import RTSPTestResponse

    equipamentos, vigia = rotas_equip
    mid, eid = uuid.uuid4(), uuid.uuid4()
    db = _Db(vigia, {NVR: _nvr(eid)})

    async def cenario():
        rota = asyncio.create_task(equipamentos.test_equipamento_rtsp(
            machine_id=mid, equipamento_id=eid, canal=2, modo="noite", nome="Portão", db=db, ctx=_ctx()))
        return await _responder_agente(pending_rtsp_tasks, str(mid),
                                       RTSPTestResponse(success=False, error_message="sem gravação"), rota)

    resp = asyncio.run(cenario())
    assert resp.success is False and resp.error_message == "sem gravação"
    assert "marcar_noite" in vigia.chamadas and "registrar_alteracao" not in vigia.chamadas
    assert vigia.no_laco == []


def test_rtsp_noite_agente_antigo_sem_horario(rotas_equip):
    from models import NVR
    from routers.agent import pending_rtsp_tasks
    from schemas import RTSPTestResponse

    equipamentos, vigia = rotas_equip
    mid, eid = uuid.uuid4(), uuid.uuid4()
    db = _Db(vigia, {NVR: _nvr(eid)})

    async def cenario():
        rota = asyncio.create_task(equipamentos.test_equipamento_rtsp(
            machine_id=mid, equipamento_id=eid, canal=2, modo="noite", nome=None, db=db, ctx=_ctx()))
        return await _responder_agente(pending_rtsp_tasks, str(mid), RTSPTestResponse(success=True, image_base64="x"), rota)

    resp = asyncio.run(cenario())
    assert resp.success is False and "1.1.6" in resp.error_message
    assert "marcar_noite" not in vigia.chamadas and vigia.no_laco == []


def test_rtsp_equipamento_inexistente_404(rotas_equip):
    from fastapi import HTTPException

    equipamentos, vigia = rotas_equip
    with pytest.raises(HTTPException) as e:
        asyncio.run(equipamentos.test_equipamento_rtsp(
            machine_id=uuid.uuid4(), equipamento_id=uuid.uuid4(), canal=1, modo="ao_vivo", nome=None,
            db=_Db(vigia), ctx=_ctx()))
    assert e.value.status_code == 404 and vigia.no_laco == []


# ─── comando de alarme (DEFENSE) ──────────────────────────────────────────
def test_comando_alarme_banco_fora_do_laco(monkeypatch):
    from models import NVR
    from routers import equipamentos
    from routers.agent import pending_alarme_tasks
    from schemas import ComandoAlarmeRequest, ComandoAlarmeResultado

    vigia = _Vigia()
    logs = []
    monkeypatch.setattr(equipamentos, "_get_machine_or_404", lambda mid, db, ctx: SimpleNamespace(id=mid))
    monkeypatch.setattr(equipamentos, "check_machine_online", lambda m: (vigia.marcar("online"), True)[1])

    def registrar(machine_id, nvr_nome, mensagem, nivel, usuario=None):
        vigia.marcar("registrar_comando")
        logs.append((nvr_nome, mensagem, nivel, usuario))

    monkeypatch.setattr(equipamentos, "_registrar_comando_alarme", registrar)
    mid, nid = uuid.uuid4(), uuid.uuid4()
    nvr = SimpleNamespace(id=nid, tipo="DEFENSE", ip="10.0.0.9", password=None, config_extra={}, username=None,
                          name="Defense", last_alarm_status={"alarmes": [{"id": "7", "nome": "Galpão"}]})
    db = _Db(vigia, {NVR: nvr})

    async def cenario():
        rota = asyncio.create_task(equipamentos.comandar_central_alarme(
            machine_id=mid, id=nid, body=ComandoAlarmeRequest(central_id="7", acao="ARMAR"), db=db, ctx=_ctx()))
        return await _responder_agente(pending_alarme_tasks, str(mid),
                                       ComandoAlarmeResultado(sucesso=True, mensagem="Armada"), rota)

    resp = asyncio.run(cenario())
    assert resp.sucesso is True
    assert logs[0] == ("Defense", "admin@teste.com pediu para armar a central 'Galpão'.", "INFO", "admin@teste.com")
    assert logs[1] == ("Defense", "Comando para armar a central 'Galpão' concluído: Armada", "INFO", None)
    assert "online" in vigia.chamadas and "close" in vigia.chamadas
    assert vigia.no_laco == []
    assert str(mid) not in pending_alarme_tasks


# ─── OAuth do MCP ─────────────────────────────────────────────────────────
class _Form(dict):
    pass


def _pedido(form=None, corpo_json=None):
    async def ler_form():
        return _Form(form or {})

    async def ler_json():
        return corpo_json

    return SimpleNamespace(form=ler_form, json=ler_json, headers={}, client=SimpleNamespace(host="203.0.113.9"),
                           query_params={})


def _cliente_oauth():
    return SimpleNamespace(client_id="trilan-abc", nome="App", redirect_uris=["https://claude.ai/cb"], secret_hash=None)


def test_oauth_login_banco_e_bcrypt_fora_do_laco(monkeypatch):
    from mcp_server import oauth
    from models import McpOauthCliente, Usuario
    from services import senhas

    vigia = _Vigia()
    conferir_real = senhas.conferir

    def conferir(senha, h):
        vigia.marcar("bcrypt")
        return conferir_real(senha, h)

    monkeypatch.setattr(oauth.senhas, "conferir", conferir)
    usuario = SimpleNamespace(id=uuid.uuid4(), email="a@b.com", senha_hash=senhas.gerar_hash("SenhaCorreta123"),
                              ativo=True, papel="ADMIN")
    db = _Db(vigia, {McpOauthCliente: _cliente_oauth(), Usuario: usuario})
    form = {"client_id": "trilan-abc", "redirect_uri": "https://claude.ai/cb", "state": "s1",
            "code_challenge": "x" * 43, "code_challenge_method": "S256", "email": "a@b.com", "senha": "SenhaCorreta123"}

    resp = asyncio.run(oauth.autorizar_login(_pedido(form), db))
    assert resp.status_code == 303 and resp.headers["location"].startswith("https://claude.ai/cb?code=")
    assert "bcrypt" in vigia.chamadas and "commit" in vigia.chamadas
    assert vigia.no_laco == []

    form["senha"] = "errada"
    resp = asyncio.run(oauth.autorizar_login(_pedido(form), db))
    assert resp.status_code == 200 and "E-mail ou senha incorretos" in resp.body.decode()
    assert vigia.no_laco == []


def test_oauth_token_revoke_registro_fora_do_laco():
    from mcp_server import oauth
    from models import McpOauthCliente

    vigia = _Vigia()
    db = _Db(vigia, {McpOauthCliente: _cliente_oauth()})

    resp = asyncio.run(oauth.token(_pedido({"client_id": "trilan-abc", "grant_type": "password"}), db))
    assert resp.status_code == 400 and b"unsupported_grant_type" in resp.body

    resp = asyncio.run(oauth.revogar(_pedido({"token": "qualquer"}), db))
    assert resp.status_code == 200

    resp = asyncio.run(oauth.registrar_cliente(
        _pedido(corpo_json={"redirect_uris": ["https://claude.ai/cb"], "client_name": "Claude"}), db))
    assert resp.status_code == 201 and b'"client_name":"Claude"' in resp.body
    assert "commit" in vigia.chamadas
    assert vigia.no_laco == []
