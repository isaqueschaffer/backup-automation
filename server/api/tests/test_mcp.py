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


def _jpeg_b64(tamanho=400_000):
    import base64 as b
    return b.b64encode(b"\xff\xd8\xff\xe0" + b"x" * tamanho).decode()


def test_imagem_sai_do_json_e_vai_como_imagem():
    from mcp_server import imagens

    foto = _jpeg_b64()
    dados, achadas = imagens.separar({"success": True, "image_base64": foto, "error_message": None})
    assert dados["image_base64"] == "[IMAGEM 1]" and len(achadas) == 1 and achadas[0]["mime"] == "image/jpeg"
    blocos, aviso = imagens.anexar(achadas)
    assert blocos == [{"type": "image", "mimeType": "image/jpeg", "data": foto}] and "anexada" in aviso
    # data URL e texto comum não são confundidos
    _, a2 = imagens.separar({"perfect_image_base64": "data:image/png;base64," + _jpeg_b64(1000), "nome": "x" * 600})
    assert len(a2) == 1 and a2[0]["mime"] == "image/jpeg"


def test_galeria_grande_nao_anexa_tudo():
    from mcp_server import imagens

    cams = [{"canal": i, "nome": f"CAM {i}", "night_image_base64": _jpeg_b64(1000), "perfect_image_base64": None}
            for i in range(1, 11)]
    _, achadas = imagens.separar(cams)
    blocos, aviso = imagens.anexar(achadas)
    assert len(blocos) == imagens.MAX_IMAGENS and "ver_imagem_camera" in aviso
    escolhidas, info = imagens.escolher_da_galeria(cams, 7, "noite")
    assert len(escolhidas) == 1 and "CAM 7" in escolhidas[0]["rotulo"]
    vazio, info = imagens.escolher_da_galeria(cams, 99, "noite")
    assert not vazio and "não encontrado" in info
