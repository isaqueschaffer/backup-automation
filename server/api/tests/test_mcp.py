"""MCP: regras sem banco (redirect OAuth, PKCE, montagem do pedido da ferramenta, marca na Auditoria)."""
import base64
import hashlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "teste-mcp")
os.environ.setdefault("FERNET_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
os.environ.setdefault("ADMIN_PASSWORD", "teste")

import pytest


def test_redirect_aceito():
    from mcp_server.oauth import _redirect_aceito, _redirect_confere

    assert _redirect_aceito("https://claude.ai/api/mcp/auth_callback")
    assert _redirect_aceito("https://chatgpt.com/connector_platform_oauth_redirect")
    assert _redirect_aceito("http://127.0.0.1:7777/callback")  # Gemini CLI / Antigravity
    assert not _redirect_aceito("http://exemplo.com/callback")
    assert not _redirect_aceito("javascript:alert(1)")
    assert not _redirect_aceito("https://x.com/cb#frag")
    assert _redirect_confere("http://localhost:5555/cb", ["http://localhost:7777/cb"])  # porta de loopback varia
    assert not _redirect_confere("https://outro.com/cb", ["https://claude.ai/cb"])


def test_pkce():
    from mcp_server.oauth import _pkce_ok

    verif = "a" * 60
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verif.encode()).digest()).decode().rstrip("=")
    assert _pkce_ok(verif, desafio)
    assert not _pkce_ok("b" * 60, desafio)
    assert not _pkce_ok("curto", desafio)


def test_montar_pedido():
    from mcp_server.ferramentas import CAMPO_CONTA, Ferramenta

    f = Ferramenta(nome="x", metodo="PUT", caminho="/api/v1/machines/{machine_id}", descricao="d", esquema={},
                   params_caminho=["machine_id"], params_query=["forcar"], campos_corpo=["name"], tem_corpo=True)
    caminho, query, corpo, conta = f.montar_pedido(
        {"machine_id": "a/b", "forcar": True, "name": "N", "extra": 1, CAMPO_CONTA: "c1"})
    assert caminho == "/api/v1/machines/a%2Fb"
    assert query == {"forcar": True} and corpo == {"name": "N"} and conta == "c1"
    with pytest.raises(ValueError):
        f.montar_pedido({})


def test_auditoria_marca_mcp():
    from auth import Contexto

    base = dict(usuario_id=None, nome="n", email="a@b.com", papel="ADMIN", conta_id=None, conta=None,
                somente_leitura=False)
    assert Contexto(**base).feito_por == "a@b.com"
    assert Contexto(**base, via="mcp").feito_por == "a@b.com (IA via MCP)"
