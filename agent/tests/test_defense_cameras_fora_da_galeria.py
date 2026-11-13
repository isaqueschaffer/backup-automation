"""Câmeras que o Defense lista e a Galeria não tem (canais de DVR/NVR) entram no relatório, com modelo e canal RTSP
do gravador, para o painel mostrar estado/gravação e o "Sincronizar da Máquina" criá-las na Galeria."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.vms.defense import (
    _casar_cameras_defense,
    _montar_status_cameras_defense,
    canal_rtsp_do_codigo,
    extrair_cameras_defense_tree,
)

ARVORE = [
    {"name": "TERRENO 01", "type": 2, "deviceIp": "192.168.75.10", "deviceModelStr": "DS-2CD2021G1-I",
     "units": [{"encoder": True, "unitType": "1", "channels": [
         {"channelName": "Canal 1", "channelCode": "1000001$1$0$0", "channelType": "1", "status": "1"}]}]},
    {"name": "DVR-CATANDUVA", "type": 1, "deviceIp": "10.0.40.47", "deviceModelStr": "MHDX 1008",
     "units": [{"encoder": True, "unitType": "1", "channels": [
         {"channelName": "FRENTE", "channelCode": "1000079$1$0$0", "channelType": "1", "status": "1"},
         {"channelName": "CORREDOR", "channelCode": "1000079$1$0$4", "channelType": "1", "status": "0"}]}]},
]


class TestCanalRtspDoCodigo(unittest.TestCase):
    def test_gravador_usa_o_ultimo_numero_mais_um(self):
        self.assertEqual(canal_rtsp_do_codigo("1000079$1$0$3", True), 4)
        self.assertEqual(canal_rtsp_do_codigo("1000092$1$0$7", True), 8)

    def test_camera_de_ip_proprio_e_codigo_estranho_nao_tem_canal(self):
        self.assertIsNone(canal_rtsp_do_codigo("1000001$1$0$0", False))
        self.assertIsNone(canal_rtsp_do_codigo("sem-padrao", True))
        self.assertIsNone(canal_rtsp_do_codigo("", True))

    def test_arvore_traz_canal_so_nos_canais_do_gravador(self):
        por_nome = {c["nome"]: c for c in extrair_cameras_defense_tree(ARVORE)}
        self.assertIsNone(por_nome["TERRENO 01"]["canal_rtsp"])
        self.assertEqual(por_nome["DVR-CATANDUVA - FRENTE"]["canal_rtsp"], 1)
        self.assertEqual(por_nome["DVR-CATANDUVA - CORREDOR"]["canal_rtsp"], 5)


class TestCamerasSoNoDefense(unittest.TestCase):
    def setUp(self):
        self.cameras_api = extrair_cameras_defense_tree(ARVORE)
        self.status = {"TERRENO 01": True, "terreno 01": True}
        for c in self.cameras_api:
            for chave in (c["nome"], c["canal_nome_original"]):
                self.status[chave] = self.status[chave.lower()] = c["online"]

    def test_galeria_so_com_ipcs_recebe_os_canais_do_dvr(self):
        galeria = [{"canal": 1, "nome": "TERRENO 01", "ip": "192.168.75.10"}]
        casadas = _casar_cameras_defense(galeria, self.status, self.cameras_api)
        nomes = [c["nome"] for c in casadas]
        self.assertEqual(nomes, ["TERRENO 01", "DVR-CATANDUVA - FRENTE", "DVR-CATANDUVA - CORREDOR"])
        self.assertTrue(casadas[1]["so_na_api"])
        self.assertNotIn("so_na_api", casadas[0])
        self.assertEqual(casadas[2]["online"], False)

    def test_camera_ja_na_galeria_nao_duplica_nem_pelo_nome_do_canal_nem_pelo_ip(self):
        galeria = [
            {"canal": 1, "nome": "terreno 01", "ip": "192.168.75.10"},
            {"canal": 2, "nome": "FRENTE", "ip": "10.0.40.47"},  # nome do canal do DVR
        ]
        nomes = [c["nome"] for c in _casar_cameras_defense(galeria, self.status, self.cameras_api)]
        self.assertEqual(nomes, ["terreno 01", "FRENTE", "DVR-CATANDUVA - CORREDOR"])

    def test_galeria_igual_ao_defense_nao_acrescenta_nada(self):
        galeria = [{"canal": 1, "nome": "TERRENO 01", "ip": "192.168.75.10"},
                   {"canal": 2, "nome": "DVR-CATANDUVA - FRENTE", "ip": "10.0.40.47"},
                   {"canal": 3, "nome": "DVR-CATANDUVA - CORREDOR", "ip": "10.0.40.47"}]
        self.assertEqual(len(_casar_cameras_defense(galeria, self.status, self.cameras_api)), 3)

    @patch("src.vms.defense.consultar_status_cameras_defense_api")
    def test_relatorio_leva_modelo_e_canal_rtsp_so_das_camera_fora_da_galeria(self, mock_api):
        mock_api.return_value = (self.status, self.cameras_api, {})
        equipamento = {"name": "Defense", "ip": "10.0.0.1", "username": "system", "password": "x",
                       "cameras_config": [{"canal": 1, "nome": "TERRENO 01", "ip": "192.168.75.10"}]}
        res = _montar_status_cameras_defense(equipamento)
        self.assertEqual(len(res), 3)
        self.assertNotIn("modelo", res[0])
        self.assertNotIn("canal_rtsp", res[0])
        self.assertEqual((res[1]["modelo"], res[1]["canal_rtsp"], res[1]["ip"]), ("MHDX 1008", 1, "10.0.40.47"))
        self.assertEqual(res[2]["canal_rtsp"], 5)
        self.assertEqual(res[2]["status_comunicacao"], "OFFLINE")


if __name__ == "__main__":
    unittest.main()
