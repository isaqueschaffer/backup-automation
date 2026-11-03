import hashlib
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.vms.defense import (
    calcular_assinatura_defense,
    extrair_cameras_defense_tree,
    consultar_gravacoes_defense_api,
    consultar_status_cameras_defense_api,
    _montar_status_cameras_defense,
)


class TestDefenseAPI(unittest.TestCase):

    def test_calcular_assinatura_defense(self):
        username = "system"
        password = "AdminPassword123"
        realm = "Defense_Realm_4433"
        random_key = "rnd_key_987654321"

        # Cálculo de conferência passo a passo
        t1 = hashlib.md5(password.encode('utf-8')).hexdigest()
        t2 = hashlib.md5((username + t1).encode('utf-8')).hexdigest()
        t3 = hashlib.md5(t2.encode('utf-8')).hexdigest()
        t4 = hashlib.md5(f"{username}:{realm}:{t3}".encode('utf-8')).hexdigest()
        esperado = hashlib.md5(f"{t4}:{random_key}".encode('utf-8')).hexdigest()

        resultado = calcular_assinatura_defense(username, password, realm, random_key)
        self.assertEqual(resultado, esperado)
        self.assertEqual(len(resultado), 32)

    def test_extrair_cameras_defense_tree(self):
        devices = [
            {
                "name": "LATERAL TERRENO",
                "deviceIp": "192.168.75.66",
                "deviceModelStr": "VIP-3230",
                "units": [
                    {
                        "unitType": "1",
                        "encoder": True,
                        "channels": [
                            {
                                "channelName": "VIP Intelbras",
                                "channelCode": "1000096$1$0$0",
                                "status": "0",
                                "deviceIp": "192.168.75.66"
                            }
                        ]
                    }
                ]
            },
            {
                "name": "DVR-CATANDUVA",
                "deviceIp": "10.0.40.47",
                "deviceModelStr": "MHDX 1116",
                "units": [
                    {
                        "unitType": "1",
                        "encoder": True,
                        "channels": [
                            {
                                "channelName": "Portaria 01",
                                "channelCode": "CH01",
                                "status": "1",
                                "deviceIp": "10.0.40.47"
                            },
                            {
                                "channelName": "Estacionamento",
                                "channelCode": "CH02",
                                "status": "0",
                                "deviceIp": "10.0.40.47"
                            }
                        ]
                    },
                    {
                        "unitType": "2",  # Não encoder
                        "channels": [
                            {"channelName": "Sensor Alarme", "status": "1"}
                        ]
                    }
                ]
            }
        ]

        cameras = extrair_cameras_defense_tree(devices)
        self.assertEqual(len(cameras), 3)

        # Canal 1 - LATERAL TERRENO (substitui 'VIP Intelbras' pelo nome do dispositivo)
        self.assertEqual(cameras[0]["canal"], 1)
        self.assertEqual(cameras[0]["nome"], "LATERAL TERRENO")
        self.assertEqual(cameras[0]["codigo"], "1000096$1$0$0")
        self.assertEqual(cameras[0]["ip"], "192.168.75.66")
        self.assertFalse(cameras[0]["online"])
        self.assertEqual(cameras[0]["status_comunicacao"], "OFFLINE")

        # Canal 2 - DVR-CATANDUVA - Portaria 01
        self.assertEqual(cameras[1]["canal"], 2)
        self.assertEqual(cameras[1]["nome"], "DVR-CATANDUVA - Portaria 01")
        self.assertTrue(cameras[1]["online"])
        self.assertEqual(cameras[1]["status_comunicacao"], "ONLINE")

        # Canal 3 - DVR-CATANDUVA - Estacionamento
        self.assertEqual(cameras[2]["canal"], 3)
        self.assertEqual(cameras[2]["nome"], "DVR-CATANDUVA - Estacionamento")
        self.assertFalse(cameras[2]["online"])
        self.assertEqual(cameras[2]["status_comunicacao"], "OFFLINE")

    @patch("requests.Session")
    def test_consultar_gravacoes_defense_api(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        agora_ts = int(datetime.now().timestamp())
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Simula registros dinâmicos nos últimos 2 dias
        mock_resp.json.return_value = {
            "code": 1000,
            "data": {
                "records": [
                    {"startTime": agora_ts - 86400 * 2, "endTime": agora_ts - 86400 * 2 + 3600},
                    {"startTime": str(agora_ts - 86400), "endTime": agora_ts - 86400 + 3600},
                ]
            }
        }
        mock_session.post.return_value = mock_resp

        lista_cameras = [
            {
                "canal": 1,
                "nome": "LATERAL TERRENO",
                "codigo": "1000096$1$0$0",
                "ip": "192.168.75.66",
                "dev_name": "LATERAL TERRENO",
                "canal_nome_original": "VIP Intelbras",
                "is_single_channel": True
            }
        ]

        res = consultar_gravacoes_defense_api("https://192.168.75.41:4433", "token123", lista_cameras, dias_historico=15)
        self.assertIn("1000096$1$0$0", res)
        self.assertIn("LATERAL TERRENO", res)
        self.assertIn("192.168.75.66", res)
        info = res["LATERAL TERRENO"]
        self.assertGreater(info["total_dias"], 0)
        self.assertEqual(info["status_gravacao"], "COM_GRAVACAO")
        self.assertIn("█", info["mapa"])

    @patch("requests.Session")
    def test_consultar_status_cameras_defense_api_sucesso(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        # Mock resposta 1: Handshake
        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.text = '{"realm": "test_realm", "randomKey": "test_key"}'
        resp1.json.return_value = {"realm": "test_realm", "randomKey": "test_key"}

        # Mock resposta 2: Autorização com token
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.text = '{"token": "auth_token_xyz"}'
        resp2.headers = {"X-Subject-Token": "auth_token_xyz"}
        resp2.json.return_value = {"token": "auth_token_xyz"}

        # Mock resposta 3: Tree devices
        resp3 = MagicMock()
        resp3.status_code = 200
        mock_tree = [
            {
                "deviceIp": "192.168.1.100",
                "units": [
                    {
                        "unitType": "1",
                        "channels": [
                            {"channelName": "Camera Teste", "status": "1", "deviceIp": "192.168.1.101", "channelCode": "C01"}
                        ]
                    }
                ]
            }
        ]
        resp3.text = "ok"
        resp3.json.return_value = mock_tree

        # Mock resposta 4: QueryRecords
        resp4 = MagicMock()
        resp4.status_code = 200
        resp4.json.return_value = {"data": {"records": []}}

        mock_session.post.side_effect = [resp1, resp2, resp3, resp4]

        status_dict, cameras, gravacoes_map = consultar_status_cameras_defense_api(
            ip="192.168.1.10",
            username="system",
            password="secret_password",
            porta_api=4433,
            timeout=5
        )

        self.assertEqual(len(cameras), 1)
        self.assertTrue(status_dict.get("Camera Teste"))
        self.assertTrue(status_dict.get("camera teste"))
        self.assertTrue(status_dict.get("192.168.1.101"))
        self.assertIsInstance(gravacoes_map, dict)

    @patch("requests.Session")
    def test_consultar_status_cameras_defense_api_falha_conexao(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        import requests
        mock_session.post.side_effect = requests.exceptions.ConnectTimeout("Conexão expirada")

        status_dict, cameras, gravacoes_map = consultar_status_cameras_defense_api(
            ip="192.168.1.10",
            username="system",
            password="secret_password"
        )
        self.assertEqual(status_dict, {})
        self.assertEqual(cameras, [])
        self.assertEqual(gravacoes_map, {})

    @patch("src.vms.defense.consultar_status_cameras_defense_api")
    def test_montar_status_cameras_defense_com_api_e_gravacoes(self, mock_api):
        mock_api.return_value = (
            {"Camera 1": True, "camera 1": True, "Camera 2": False, "camera 2": False},
            [
                {"canal": 1, "nome": "Camera 1", "codigo": "C01", "online": True},
                {"canal": 2, "nome": "Camera 2", "codigo": "C02", "online": False},
            ],
            {
                "Camera 2": {
                    "total_dias": 8,
                    "mapa": "░░░░░░░████████",
                    "dias_com_gravacao": ["2026-10-22", "2026-10-23"],
                    "status_gravacao": "COM_GRAVACAO"
                }
            }
        )

        equipamento = {
            "name": "Defense IA Teste",
            "ip": "192.168.1.10",
            "username": "system",
            "password": "pass",
            "cameras_config": [
                {"canal": 1, "nome": "Camera 1", "ip": "10.0.0.1"},
                {"canal": 2, "nome": "Camera 2", "ip": "10.0.0.2"}
            ]
        }

        res = _montar_status_cameras_defense(equipamento, conf=None)
        self.assertEqual(len(res), 2)
        # Câmera 1 - Online
        self.assertTrue(res[0]["online"])
        self.assertEqual(res[0]["status_comunicacao"], "ONLINE")
        self.assertEqual(res[0]["total_dias"], 15)

        # Câmera 2 - Offline MAS com histórico de gravação real
        self.assertFalse(res[1]["online"])
        self.assertEqual(res[1]["status_comunicacao"], "OFFLINE")
        self.assertEqual(res[1]["status_gravacao"], "COM_GRAVACAO")
        self.assertEqual(res[1]["total_dias"], 8)
        self.assertEqual(res[1]["mapa"], "░░░░░░░████████")
        self.assertEqual(res[1]["dias_com_gravacao"], ["2026-10-22", "2026-10-23"])


if __name__ == "__main__":
    unittest.main()
