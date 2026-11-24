"""POST /auth/renovar: troca um token válido por um novo, sem banco real (sessão falsa)."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "teste-renovar")
os.environ.setdefault("FERNET_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
os.environ.setdefault("ADMIN_PASSWORD", "teste")

import pytest
from fastapi import HTTPException
from jose import jwt


class _Consulta:
    def __init__(self, resultado):
        self._r = resultado

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._r


class _Db:
    def __init__(self, usuario):
        self._u = usuario

    def query(self, *a, **k):
        return _Consulta(self._u)


def _ctx(usuario_id):
    return SimpleNamespace(usuario_id=usuario_id)


def test_renova_usuario_com_email():
    from auth import ALGORITHM
    from config import settings
    from routers.auth_router import renovar

    usuario = SimpleNamespace(id=uuid4(), token_versao=3)
    resp = renovar(ctx=_ctx(usuario.id), db=_Db(usuario))
    payload = jwt.decode(resp.access_token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == str(usuario.id)
    assert payload["tv"] == 3  # mantém a versão: trocar a senha continua derrubando a sessão
    assert "exp" in payload


def test_login_legado_nao_renova():
    from routers.auth_router import renovar

    with pytest.raises(HTTPException) as e:
        renovar(ctx=_ctx(None), db=_Db(None))
    assert e.value.status_code == 400
