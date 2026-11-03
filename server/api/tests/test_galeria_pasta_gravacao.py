import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

from services.galeria_vms import aprender_pastas, parear_cameras


def _cam(nome, canal, ip=None, pasta=None):
    return SimpleNamespace(id=uuid.uuid4(), nome=nome, canal=canal, ip=ip, pasta_gravacao=pasta)


def test_camera_renomeada_pareia_pela_pasta():
    renomeada = _cam("Entrada principal", 1, "10.0.0.9", pasta="Garagem")
    outra = _cam("Garagem", 2, "10.0.0.8")  # nome igual ao da pasta, mas é outra câmera
    par = parear_cameras([outra, renomeada], [{"nome": "Garagem", "pasta_gravacao": "Garagem"}])
    assert par[0][2] is renomeada


def test_aprende_a_pasta_so_com_nome_igual():
    igual = _cam("Garagem", 1)
    parecida = _cam("Garagem 2 andar", 2)
    relatorio = [
        {"nome": "Garagem", "pasta_gravacao": "Garagem"},
        {"nome": "Garagem 2", "pasta_gravacao": "Garagem 2", "ip": ""},
    ]
    assert aprender_pastas([igual, parecida], relatorio) == 1
    assert igual.pasta_gravacao == "Garagem"
    assert parecida.pasta_gravacao is None


def test_nao_sobrescreve_pasta_ja_gravada():
    cam = _cam("Garagem", 1, pasta="Outra")
    assert aprender_pastas([cam], [{"nome": "Garagem", "pasta_gravacao": "Garagem"}]) == 0
    assert cam.pasta_gravacao == "Outra"
