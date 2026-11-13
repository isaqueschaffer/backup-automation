"""Isolamento por máquina (services/escopo.py): VISUALIZADOR/LEITURA com máquinas marcadas pelo admin só veem essas
máquinas, os clientes delas e os alertas delas; o que junta o cliente inteiro (ZIP, rodadas, dashboard) exige todas."""
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
os.environ["FERNET_KEY"] = "dGVzdF9mZXJuZXRfa2V5XzMyX2J5dGVzX2xvbmdfISE="  # 32 bytes válidos
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("ADMIN_PASSWORD", "senha_de_teste")

from auth import Contexto
from services import escopo

M1, M2, M3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def _ctx(permitidas=None, papel="VISUALIZADOR"):
    return Contexto(usuario_id=uuid.uuid4(), nome="x", email="x@x", papel=papel, conta_id=uuid.uuid4(), conta=None,
                    somente_leitura=True, maquinas_permitidas=frozenset(permitidas) if permitidas else None)


def _cliente(*ids):
    return SimpleNamespace(machines=[SimpleNamespace(id=i) for i in ids])


def test_sem_restricao_ve_tudo():
    ctx = _ctx()
    assert escopo.maquina_permitida(ctx, M1) and escopo.maquina_permitida(ctx, M3)
    assert escopo.ve_cliente_inteiro(ctx, _cliente(M1, M2))
    escopo.exigir_cliente_inteiro(ctx, _cliente(M1, M2))


def test_com_restricao_so_as_marcadas():
    ctx = _ctx({M1})
    assert escopo.maquina_permitida(ctx, M1)
    assert not escopo.maquina_permitida(ctx, M2)
    assert [m.id for m in escopo.maquinas_visiveis(ctx, _cliente(M1, M2).machines)] == [M1]


def test_cliente_inteiro_exige_todas_as_maquinas():
    ctx = _ctx({M1})
    assert escopo.ve_cliente_inteiro(ctx, _cliente(M1))
    assert not escopo.ve_cliente_inteiro(ctx, _cliente(M1, M2))
    with pytest.raises(HTTPException) as e:
        escopo.exigir_cliente_inteiro(ctx, _cliente(M1, M2))
    assert e.value.status_code == 403


class _Consulta:
    """Consulta falsa: guarda os filtros aplicados e devolve o primeiro objeto."""
    def __init__(self, obj):
        self.obj, self.filtros = obj, []

    def filter(self, *f):
        self.filtros.extend(f)
        return self

    def first(self):
        return self.obj


def test_obter_maquina_de_fora_da_lista_e_404():
    ctx = _ctx({M1})
    assert escopo.obter_maquina(None, ctx, M1, _Consulta(SimpleNamespace(id=M1))).id == M1
    with pytest.raises(HTTPException) as e:
        escopo.obter_maquina(None, ctx, M2, _Consulta(SimpleNamespace(id=M2)))
    assert e.value.status_code == 404


def test_obter_cliente_sem_nenhuma_maquina_liberada_e_404():
    ctx = _ctx({M3})
    with pytest.raises(HTTPException) as e:
        escopo.obter_cliente(None, ctx, uuid.uuid4(), _Consulta(_cliente(M1, M2)))
    assert e.value.status_code == 404
    assert escopo.obter_cliente(None, _ctx({M1}), uuid.uuid4(), _Consulta(_cliente(M1, M2))) is not None


def test_filtrar_maquinas_so_filtra_quem_tem_restricao():
    from models import Machine
    sem = _Consulta(None)
    assert escopo.filtrar_maquinas(sem, Machine.id, _ctx()) is sem and sem.filtros == []
    com = escopo.filtrar_maquinas(_Consulta(None), Machine.id, _ctx({M1, M2}))
    assert len(com.filtros) == 1
