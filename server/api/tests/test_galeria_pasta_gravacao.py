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


def test_painel_mostra_o_nome_da_galeria_no_lugar_da_pasta():
    from datetime import datetime
    from schemas import NVRResponse
    renomeada = _cam("Entrada principal", 1, "10.0.0.9", pasta="Garagem")
    sem_pasta = _cam("Teto", 2, "10.0.0.7")
    relatorio = [
        {"nome": "Garagem", "pasta_gravacao": "Garagem", "status_gravacao": "COM_GRAVACAO"},
        {"nome": "Teto", "pasta_gravacao": None, "ip": "10.0.0.7"},
    ]
    eq = SimpleNamespace(id=uuid.uuid4(), machine_id=uuid.uuid4(), tipo="DIGIFORT", name="D", ip="1.1.1.1",
                         username="u", config_extra=None, active=True, last_recording_status=relatorio,
                         last_telemetry_status=None, updated_at=datetime.utcnow(),
                         cameras_status=[renomeada, sem_pasta])
    cams = NVRResponse.model_validate(eq).last_recording_status
    assert cams[0]["nome"] == "Entrada principal" and cams[0]["pasta_gravacao"] == "Entrada principal"
    assert cams[1]["pasta_gravacao"] is None
    assert relatorio[0]["nome"] == "Garagem"  # o relatório gravado não muda

    eq.tipo = "NVR"
    assert NVRResponse.model_validate(eq).last_recording_status[0]["nome"] == "Garagem"


def test_caminho_completo_da_planilha_pareia_e_aparece_como_esta():
    from services.galeria_vms import com_nomes_da_galeria
    caminho = r"D:\44"
    cam = _cam("4° ANDAR A FUNDO CORREDOR", 1, "192.168.5.57", pasta=caminho)
    outra = _cam("Outra", 2, "192.168.5.58", pasta=r"E:\GRAVACAO\45")
    relatorio = [{"nome": "4 ANDAR A FUNDO CORREDOR", "pasta_gravacao": caminho, "status_gravacao": "SEM_GRAVACAO"}]
    assert parear_cameras([outra, cam], relatorio)[0][2] is cam
    exibido = com_nomes_da_galeria(relatorio, [outra, cam])
    assert exibido[0]["nome"] == "4° ANDAR A FUNDO CORREDOR"
    assert exibido[0]["pasta_gravacao"] == caminho


def test_pasta_gravacao_aceita_caminho_ate_255():
    from pydantic import ValidationError
    from schemas import NVRCameraConfigItem
    assert NVRCameraConfigItem(nome="a", ip="1.1.1.1", pasta_gravacao=r"D:\17").pasta_gravacao == r"D:\17"
    try:
        NVRCameraConfigItem(nome="a", ip="1.1.1.1", pasta_gravacao="D:\\" + "x" * 300)
    except ValidationError:
        pass
    else:
        raise AssertionError("caminho acima de 255 caracteres deveria ser recusado")
