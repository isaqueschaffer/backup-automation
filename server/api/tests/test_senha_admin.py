"""Senha do login legado (só senha) do administrador da plataforma (API-05, auditoria de 25/11/2026): guardada em
bcrypt, valor antigo em texto puro migra no primeiro login, ADMIN_PASSWORD do ambiente continua valendo e o
PUT/GET /settings nunca grava nem devolve o valor cru. Sessão falsa: tabela settings num dicionário."""
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from jose import jwt


class _Consulta:
    def __init__(self, db):
        self._db = db
        self._chave = None

    def filter(self, expr, *a, **k):
        self._chave = expr.right.value  # Setting.key == "<chave>"
        return self

    def first(self):
        return self._db.linhas.get(self._chave)

    def all(self):
        return list(self._db.linhas.values())


class _Db:
    def __init__(self, **valores):
        from models import Setting

        self.linhas = {k: Setting(key=k, value=v) for k, v in valores.items()}
        self.commits = 0

    def query(self, modelo, *a, **k):
        return _Consulta(self)

    def add(self, obj):
        self.linhas[obj.key] = obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def _request():
    # IP diferente a cada chamada: o limitador de tentativas do login é global no processo
    return SimpleNamespace(headers={}, client=SimpleNamespace(host=f"198.51.100.{uuid.uuid4().int % 250}"))


def _login(db, senha):
    from routers.auth_router import login
    from schemas import LoginRequest

    return login(LoginRequest(password=senha), _request(), db)


def test_hash_bcrypt_confere():
    from routers.auth_router import conferir_senha_admin
    from services import senhas

    db = _Db(admin_password_hash=senhas.gerar_hash("SenhaForte-123"))
    assert conferir_senha_admin(db, "SenhaForte-123") is True
    assert conferir_senha_admin(db, "outra") is False
    assert db.commits == 0  # nada a migrar


def test_texto_puro_legado_confere_e_vira_hash():
    from routers.auth_router import conferir_senha_admin
    from services import senhas

    db = _Db(admin_password_hash="senha-antiga")
    assert conferir_senha_admin(db, "senha-errada") is False
    assert db.linhas["admin_password_hash"].value == "senha-antiga"  # errada não migra

    assert conferir_senha_admin(db, "senha-antiga") is True
    guardado = db.linhas["admin_password_hash"].value
    assert guardado != "senha-antiga" and senhas.eh_hash_bcrypt(guardado) and db.commits == 1
    assert conferir_senha_admin(db, "senha-antiga") is True  # depois da migração, pelo bcrypt
    assert db.commits == 1


def test_sem_valor_gravado_usa_variavel_de_ambiente():
    from config import settings
    from routers.auth_router import conferir_senha_admin

    db = _Db()
    assert conferir_senha_admin(db, settings.ADMIN_PASSWORD) is True
    assert conferir_senha_admin(db, settings.ADMIN_PASSWORD + "x") is False
    assert db.linhas == {}  # a senha do ambiente não é copiada para o banco


def test_login_legado_token_igual_e_senha_errada_401():
    from auth import ALGORITHM
    from config import settings
    from services import senhas

    db = _Db(admin_password_hash=senhas.gerar_hash("SenhaForte-123"))
    resp = _login(db, "SenhaForte-123")
    payload = jwt.decode(resp.access_token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "admin"  # formato do token não mudou

    with pytest.raises(HTTPException) as e:
        _login(db, "errada")
    assert e.value.status_code == 401 and e.value.detail == "Wrong password"


def test_put_settings_grava_hash_e_get_nao_devolve():
    from routers.settings_router import get_settings, update_settings
    from services import senhas

    db = _Db(admin_password_hash="senha-antiga")
    resp = update_settings({"admin_password_hash": "NovaSenhaForte-1", "smtp_server": "smtp.x"}, db)
    guardado = db.linhas["admin_password_hash"].value
    assert senhas.eh_hash_bcrypt(guardado) and senhas.conferir("NovaSenhaForte-1", guardado)
    assert db.linhas["smtp_server"].value == "smtp.x"
    for r in (resp, get_settings(db)):
        dados = r.model_dump()
        assert "admin_password_hash" not in dados
        assert guardado not in str(dados) and "NovaSenhaForte-1" not in str(dados)

    assert _login(db, "NovaSenhaForte-1").access_token


def test_put_settings_recusa_hash_e_senha_fraca():
    from routers.settings_router import update_settings
    from services import senhas

    db = _Db(admin_password_hash="senha-antiga")
    with pytest.raises(HTTPException) as e:
        update_settings({"admin_password_hash": senhas.gerar_hash("escolhida-por-mim")}, db)
    assert e.value.status_code == 422
    with pytest.raises(HTTPException) as e:
        update_settings({"admin_password_hash": "curta"}, db)
    assert e.value.status_code == 422
    assert db.linhas["admin_password_hash"].value == "senha-antiga" and db.commits == 0

    update_settings({"admin_password_hash": "", "retention_days": "30"}, db)  # vazio = manter a senha atual
    assert db.linhas["admin_password_hash"].value == "senha-antiga"
