"""Alarmes das centrais Intelbras cadastradas no DEFENSE (API HTTP /api/alarm-centrals)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.application.status_alarmes_defense import coletar_status_alarmes
from src.vms import defense_alarmes as d

RESPOSTA_API = [
    {
        "id": 3,
        "name": "CENTRAL RIO PRETO",
        "status": 1,
        "partitions": [
            {"id": 4, "index": 0, "name": "Zona sem partição", "armed": 0, "alarm": 0},
        ],
        "zones": [],
    }
]


class TestParseAlarmes(unittest.TestCase):
    def test_central_e_particoes(self):
        alarmes = d.parse_alarmes(RESPOSTA_API)
        self.assertEqual(len(alarmes), 1)
        central = alarmes[0]
        self.assertEqual(central["nome"], "CENTRAL RIO PRETO")
        self.assertEqual(central["status"], 1)
        self.assertEqual(central["particoes"], [{"nome": "Zona sem partição", "armada": False}])

    def test_particao_armada(self):
        dados = [{"name": "C1", "status": 1, "partitions": [{"name": "P1", "armed": 1}]}]
        self.assertTrue(d.parse_alarmes(dados)[0]["particoes"][0]["armada"])

    def test_sem_nome_de_particao_usa_indice(self):
        dados = [{"name": "C1", "partitions": [{"index": 2, "armed": 0}]}]
        self.assertEqual(d.parse_alarmes(dados)[0]["particoes"][0]["nome"], "Partição 2")

    def test_lista_vazia_ou_invalida(self):
        self.assertEqual(d.parse_alarmes([]), [])
        self.assertEqual(d.parse_alarmes(None), [])
        self.assertEqual(d.parse_alarmes([{"nao_e_central": True}, "lixo"])[0]["nome"], "Central sem nome")


class TestConsultarAlarmesDefense(unittest.TestCase):
    @patch("src.vms.defense_alarmes.requests.get")
    def test_sucesso_usa_basic_auth_e_porta(self, get_mock):
        resposta = MagicMock()
        resposta.json.return_value = RESPOSTA_API
        resposta.raise_for_status.return_value = None
        get_mock.return_value = resposta

        alarmes = d.consultar_alarmes_defense("192.168.75.41", "admin", "senha", 3001)

        self.assertEqual(len(alarmes), 1)
        url = get_mock.call_args.args[0]
        self.assertEqual(url, "http://192.168.75.41:3001/api/alarm-centrals")
        auth = get_mock.call_args.kwargs["auth"]
        self.assertEqual((auth.username, auth.password), ("admin", "senha"))

    @patch("src.vms.defense_alarmes.requests.get")
    def test_resposta_que_nao_e_lista_levanta_erro(self, get_mock):
        resposta = MagicMock()
        resposta.json.return_value = {"erro": "nao autorizado"}
        resposta.raise_for_status.return_value = None
        get_mock.return_value = resposta

        with self.assertRaises(ValueError):
            d.consultar_alarmes_defense("192.168.75.41", "admin", "senha")


class TestColetarAlarmesEquipamento(unittest.TestCase):
    def test_usa_porta_do_config_extra(self):
        chamadas = []

        def consultar_fake(ip, usuario, senha, porta):
            chamadas.append((ip, usuario, senha, porta))
            return [{"nome": "C1", "status": 1, "particoes": []}]

        equipamento = {
            "name": "DEFENSE_01", "ip": "192.168.75.41", "username": "admin", "password": "senha",
            "config_extra": {"porta_alarme": 3005},
        }
        resultado = d.coletar_alarmes_equipamento(equipamento, consultar=consultar_fake)

        self.assertEqual(chamadas, [("192.168.75.41", "admin", "senha", 3005)])
        self.assertEqual(resultado["ip"], "192.168.75.41")
        self.assertEqual(resultado["alarmes"][0]["nome"], "C1")

    def test_sem_senha_nao_consulta(self):
        chamado = []
        resultado = d.coletar_alarmes_equipamento(
            {"name": "DEFENSE_01", "ip": "192.168.75.41"}, consultar=lambda *a: chamado.append(a))
        self.assertEqual(chamado, [])
        self.assertIn("erro", resultado)

    def test_falha_na_consulta_nao_levanta_erro(self):
        def consultar_com_falha(*a):
            raise TimeoutError("sem resposta")

        equipamento = {"name": "DEFENSE_01", "ip": "192.168.75.41", "username": "admin", "password": "senha"}
        resultado = d.coletar_alarmes_equipamento(equipamento, consultar=consultar_com_falha)
        self.assertIn("erro", resultado)


class TestColetarStatusAlarmes(unittest.TestCase):
    def test_so_considera_defense_ativos(self):
        equipamentos = [
            {"name": "DEFENSE_01", "tipo": "DEFENSE", "active": True},
            {"name": "DEFENSE_02", "tipo": "DEFENSE", "active": False},
            {"name": "NVR_01", "tipo": "NVR", "active": True},
        ]
        chamadas = []

        def coletar_fake(eq):
            chamadas.append(eq["name"])
            return {"ip": eq.get("ip"), "alarmes": []}

        resultado = coletar_status_alarmes(equipamentos, coletar=coletar_fake)

        self.assertEqual(chamadas, ["DEFENSE_01"])
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["nome"], "DEFENSE_01")


if __name__ == "__main__":
    unittest.main()
