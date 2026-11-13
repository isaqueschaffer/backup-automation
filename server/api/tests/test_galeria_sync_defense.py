"""Sincronizar da Máquina (DEFENSE): câmeras que o Defense lista e a Galeria não tem viram câmeras da Galeria."""
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.galeria_vms import cameras_do_relatorio_sem_par, marca_pelo_modelo


def _cam(nome, ip, canal):
    return NS(id=uuid.uuid4(), nome=nome, ip=ip, canal=canal, pasta_gravacao=None)


RELATORIO = [
    {"canal": 1, "nome": "TERRENO 01", "ip": "192.168.75.10"},
    {"canal": 8, "nome": "DVR - FRENTE", "ip": "10.0.40.47", "modelo": "MHDX 1008", "canal_rtsp": 1},
    {"canal": 9, "nome": "DVR - LATERAL", "ip": "10.0.40.47", "modelo": "MHDX 1008", "canal_rtsp": 2},
    {"canal": 18, "nome": "LATERAL TERRENO", "ip": "192.168.75.66", "modelo": "VIP-3230-D-SC-IA"},
    {"canal": 19, "nome": "SEM IP", "ip": "N/A"},
]


def test_so_vem_o_que_a_galeria_nao_tem_e_tem_ip():
    novas = cameras_do_relatorio_sem_par([_cam("TERRENO 01", "192.168.75.10", 1)], RELATORIO)
    assert [(c["nome"], c["canal_rtsp"]) for c in novas] == [("DVR - FRENTE", 1), ("DVR - LATERAL", 2), ("LATERAL TERRENO", None)]
    assert all(c["ip"] != "N/A" for c in novas)


def test_galeria_completa_nao_traz_nada():
    galeria = [_cam("TERRENO 01", "192.168.75.10", 1), _cam("DVR - FRENTE", "10.0.40.47", 2),
               _cam("DVR - LATERAL", "10.0.40.47", 3), _cam("LATERAL TERRENO", "192.168.75.66", 4)]
    assert cameras_do_relatorio_sem_par(galeria, RELATORIO) == []


def test_relatorio_vazio_ou_ruim_nao_quebra():
    assert cameras_do_relatorio_sem_par([], None) == []
    assert cameras_do_relatorio_sem_par([], ["lixo", None, {"nome": "", "ip": "1.1.1.1"}]) == []


def test_canal_rtsp_fora_da_faixa_e_descartado():
    rel = [{"nome": "A", "ip": "1.1.1.1", "canal_rtsp": 0}, {"nome": "B", "ip": "1.1.1.2", "canal_rtsp": 9999}]
    assert [c["canal_rtsp"] for c in cameras_do_relatorio_sem_par([], rel)] == [None, None]


def test_marca_pelo_modelo():
    assert marca_pelo_modelo("DS-2CD2021G1-I") == "Hikvision"
    assert marca_pelo_modelo("MTIBM052713") == "ONVIF"
    assert marca_pelo_modelo("DIH33001-D/A(POE)") == "ONVIF"
    assert marca_pelo_modelo("MHDX 1008") == "Intelbras"
    assert marca_pelo_modelo("iNVD 3016") == "Intelbras"
    assert marca_pelo_modelo("VIPC-1230-D-G2") == "Intelbras"
    assert marca_pelo_modelo(None) == "Hikvision"
