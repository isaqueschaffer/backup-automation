"""Perfil VISUALIZADOR: vê tudo como o LEITURA, mas pode rodar os testes (captura ao vivo sem salvar, "Testar conexão")
pelas rotas que usam `get_contexto_teste`; qualquer outra escrita continua bloqueada (auth.py)."""
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
os.environ["FERNET_KEY"] = "dGVzdF9mZXJuZXRfa2V5XzMyX2J5dGVzX2xvbmdfISE="  # 32 bytes válidos
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("ADMIN_PASSWORD", "senha_de_teste")

import auth
from auth import Contexto
from schemas import _validar_papel_usuario
from services.contas import PAPEIS


def _ctx(papel, bloqueada=False):
    conta = SimpleNamespace(nome="Conta", bloqueada=bloqueada)
    return Contexto(usuario_id=None, nome="x", email="x@x", papel=papel, conta_id="c", conta=conta,
                    somente_leitura=papel in ("LEITURA", "VISUALIZADOR") or bloqueada)


def _req(metodo):
    return SimpleNamespace(method=metodo)


def _chamar(dep, ctx, metodo):
    with patch.object(auth, "_montar_contexto", return_value=ctx), \
         patch.object(auth, "conta_bloqueada", side_effect=lambda c: bool(getattr(c, "bloqueada", False))):
        return dep(_req(metodo), SimpleNamespace(credentials="t"), None, None)


def test_papel_valido_e_na_lista():
    assert _validar_papel_usuario("visualizador") == "VISUALIZADOR"
    assert "VISUALIZADOR" in PAPEIS
    with pytest.raises(ValueError):
        _validar_papel_usuario("OPERADOR")


def test_quem_pode_testar():
    with patch.object(auth, "conta_bloqueada", side_effect=lambda c: bool(getattr(c, "bloqueada", False))):
        assert _ctx("ADMIN").pode_testar and _ctx("VISUALIZADOR").pode_testar and _ctx("SUPER_ADMIN").pode_testar
        assert not _ctx("LEITURA").pode_testar
        assert not _ctx("VISUALIZADOR", bloqueada=True).pode_testar  # conta vencida: ninguém testa


def test_visualizador_testa_mas_nao_altera():
    ctx = _ctx("VISUALIZADOR")
    assert _chamar(auth.get_contexto_teste, ctx, "POST") is ctx
    for metodo in ("POST", "PUT", "DELETE"):
        with pytest.raises(HTTPException) as e:
            _chamar(auth.get_contexto, ctx, metodo)
        assert e.value.status_code == 403
    assert _chamar(auth.get_contexto, ctx, "GET") is ctx


def test_leitura_e_conta_vencida_nao_testam():
    for ctx in (_ctx("LEITURA"), _ctx("VISUALIZADOR", bloqueada=True), _ctx("ADMIN", bloqueada=True)):
        with pytest.raises(HTTPException) as e:
            _chamar(auth.get_contexto_teste, ctx, "POST")
        assert e.value.status_code == 403


def test_admin_segue_testando():
    ctx = _ctx("ADMIN")
    assert _chamar(auth.get_contexto_teste, ctx, "POST") is ctx


def test_visualizador_so_captura_ao_vivo():
    from routers.equipamentos import test_equipamento_rtsp
    ctx = _ctx("VISUALIZADOR")
    for modo in ("referencia", "noite"):
        with pytest.raises(HTTPException) as e:
            asyncio.run(test_equipamento_rtsp(machine_id="m", equipamento_id="e", canal=1, modo=modo, nome=None,
                                              db=None, ctx=ctx))
        assert e.value.status_code == 403
