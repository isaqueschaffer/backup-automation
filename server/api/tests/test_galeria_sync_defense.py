"""Sincronizar da Máquina (DEFENSE): câmeras que o Defense lista e a Galeria não tem viram câmeras da Galeria."""
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.galeria_vms import (cameras_do_relatorio_sem_par, credenciais_dos_gravadores, gravador_do_canal,
                                  marca_pelo_modelo)


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


GRAVADORES = [{"nome": "DVR-CATANDUVA", "ip": "10.0.40.47"}, {"nome": "NVR INTELBRAS", "ip": "192.168.75.6"}]


def test_canal_de_gravador_nasce_com_onvif_e_camera_de_ip_proprio_segue_o_modelo():
    novas = {c["nome"]: c for c in cameras_do_relatorio_sem_par([], RELATORIO)}
    assert novas["DVR - FRENTE"]["modelo"] == "ONVIF" and novas["DVR - LATERAL"]["modelo"] == "ONVIF"
    assert novas["LATERAL TERRENO"]["modelo"] == "Intelbras"  # IP próprio: continua pela marca do modelo


def test_canal_do_gravador_da_planilha_vira_onvif_mesmo_sem_canal_rtsp():
    rel = [{"nome": "DVR-CATANDUVA - FRENTE", "ip": "10.0.40.47", "modelo": "MHDX 1008", "dispositivo": "DVR-CATANDUVA"}]
    (cam,) = cameras_do_relatorio_sem_par([], rel, GRAVADORES)
    assert (cam["modelo"], cam["canal_rtsp"]) == ("ONVIF", None)


def test_ip_do_gravador_da_planilha_vale_quando_o_defense_nao_informa():
    rel = [{"nome": "NVR INTELBRAS - CAM 2", "ip": "N/A", "dispositivo": "NVR INTELBRAS", "canal_rtsp": 2}]
    assert cameras_do_relatorio_sem_par([], rel) == []  # sem a planilha não há IP: descartada
    (cam,) = cameras_do_relatorio_sem_par([], rel, GRAVADORES)
    assert (cam["ip"], cam["modelo"], cam["canal_rtsp"]) == ("192.168.75.6", "ONVIF", 2)


GRAVADORES_COM_ACESSO = [
    {"nome": "DVR-CATANDUVA", "ip": "10.0.40.47", "usuario": "sup", "senha": "S3nha!"},
    {"nome": "NVR INTELBRAS", "ip": "192.168.75.6"},  # sem usuário/senha na planilha
]


def test_canal_novo_de_gravador_nasce_com_o_usuario_e_a_senha_da_planilha():
    rel = [{"nome": "DVR-CATANDUVA - FRENTE", "ip": "10.0.40.47", "dispositivo": "DVR-CATANDUVA", "canal_rtsp": 1},
           {"nome": "NVR INTELBRAS - CAM 2", "ip": "N/A", "dispositivo": "NVR INTELBRAS", "canal_rtsp": 2},
           {"nome": "TERRENO 01", "ip": "192.168.75.10"}]
    novas = {c["nome"]: c for c in cameras_do_relatorio_sem_par([], rel, GRAVADORES_COM_ACESSO)}
    assert (novas["DVR-CATANDUVA - FRENTE"]["username"], novas["DVR-CATANDUVA - FRENTE"]["password"]) == ("sup", "S3nha!")
    assert "username" not in novas["NVR INTELBRAS - CAM 2"] and "password" not in novas["NVR INTELBRAS - CAM 2"]
    assert "username" not in novas["TERRENO 01"]  # câmera de IP próprio não herda acesso de gravador


def test_credenciais_dos_gravadores_atingem_so_canais_de_gravador_ja_na_galeria():
    galeria = [_cam("DVR-CATANDUVA - FRENTE", "10.0.40.47", 1), _cam("TERRENO 01", "192.168.75.10", 2),
               _cam("NVR INTELBRAS - CAM 2", "192.168.75.6", 3)]
    rel = [{"nome": "DVR-CATANDUVA - FRENTE", "ip": "10.0.40.47", "dispositivo": "DVR-CATANDUVA"},
           {"nome": "TERRENO 01", "ip": "192.168.75.10"},
           {"nome": "NVR INTELBRAS - CAM 2", "ip": "192.168.75.6", "dispositivo": "NVR INTELBRAS"}]
    achadas = credenciais_dos_gravadores(galeria, rel, GRAVADORES_COM_ACESSO)
    assert [(c.nome, u, s) for c, u, s in achadas] == [("DVR-CATANDUVA - FRENTE", "sup", "S3nha!")]
    assert credenciais_dos_gravadores(galeria, rel, None) == []
    assert credenciais_dos_gravadores(galeria, None, GRAVADORES_COM_ACESSO) == []


def test_gravador_do_canal_casa_pelo_dispositivo_ou_pelo_prefixo_do_nome():
    assert gravador_do_canal({"dispositivo": "dvr-catanduva", "nome": "FRENTE"}, GRAVADORES)["ip"] == "10.0.40.47"
    assert gravador_do_canal({"nome": "NVR INTELBRAS - CAM 1"}, GRAVADORES)["ip"] == "192.168.75.6"
    assert gravador_do_canal({"dispositivo": "OUTRO", "nome": "NVR INTELBRAS - CAM 1"}, GRAVADORES) is None
    assert gravador_do_canal({"nome": "TERRENO 01"}, GRAVADORES) is None
    assert gravador_do_canal({"nome": "x"}, None) is None
