"""Cameras do Digifort lidas das pastas de gravacao (nome da pasta = nome da camera), sem export/CSV."""
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.backup.file_manager.manager import _cameras_pelas_pastas
from src.vms.digifort_gravacoes import vincular_cameras_as_pastas

GRAVOU = {"total_dias": 15, "mapa": "█" * 15, "dias_com_gravacao": ["2026-11-03"], "status_gravacao": "COM_GRAVACAO"}
SEM = {"total_dias": 0, "mapa": "░" * 15, "dias_com_gravacao": [], "status_gravacao": "SEM_GRAVACAO"}


def _por_nome(lista):
    return {c["nome"]: c for c in lista}


class TestCamerasPelasPastas(unittest.TestCase):
    def test_sem_galeria_usa_o_nome_da_pasta_e_nao_verifica_comunicacao(self):
        resumos = {"Garagem": GRAVOU, "Portao": SEM}
        status, captura = _cameras_pelas_pastas(resumos, [], lambda ip: True)
        cams = _por_nome(status)
        self.assertEqual(set(cams), {"Garagem", "Portao"})
        self.assertEqual(cams["Garagem"]["status_comunicacao"], "NAO_VERIFICADO")
        self.assertIsNone(cams["Garagem"]["online"])
        self.assertEqual(cams["Garagem"]["status_gravacao"], "COM_GRAVACAO")
        self.assertEqual(cams["Portao"]["status_gravacao"], "SEM_GRAVACAO")
        self.assertEqual(cams["Garagem"]["pasta_gravacao"], "Garagem")
        self.assertEqual(captura, [])

    def test_camera_da_galeria_com_o_mesmo_nome_da_ip_para_o_ping(self):
        galeria = [{"canal": 7, "nome": "garagem", "ip": "10.0.0.5"}]
        status, captura = _cameras_pelas_pastas({"Garagem": GRAVOU}, galeria, lambda ip: ip == "10.0.0.5")
        self.assertEqual(len(status), 1)
        self.assertEqual(status[0]["nome"], "garagem")
        self.assertEqual(status[0]["ip"], "10.0.0.5")
        self.assertEqual(status[0]["status_comunicacao"], "ONLINE")
        self.assertEqual(captura, galeria)

    def test_camera_renomeada_continua_ligada_a_pasta(self):
        galeria = [{"canal": 1, "nome": "Entrada principal", "ip": "10.0.0.9", "pasta_gravacao": "Garagem"}]
        status, _ = _cameras_pelas_pastas({"Garagem": GRAVOU}, galeria, lambda ip: False)
        self.assertEqual(len(status), 1)
        self.assertEqual(status[0]["nome"], "Entrada principal")
        self.assertEqual(status[0]["pasta_gravacao"], "Garagem")
        self.assertEqual(status[0]["status_comunicacao"], "OFFLINE")
        self.assertEqual(status[0]["status_gravacao"], "COM_GRAVACAO")

    def test_camera_da_galeria_sem_pasta_entra_como_nao_verificada(self):
        galeria = [{"canal": 2, "nome": "Teto", "ip": "10.0.0.7"}]
        status, _ = _cameras_pelas_pastas({"Garagem": GRAVOU}, galeria, lambda ip: True)
        cams = _por_nome(status)
        self.assertEqual(cams["Teto"]["status_gravacao"], "NAO_VERIFICADO")
        self.assertIsNone(cams["Teto"]["pasta_gravacao"])
        self.assertEqual(cams["Teto"]["status_comunicacao"], "ONLINE")

    def test_pasta_com_leitura_incompleta_nao_afirma_nada(self):
        status, _ = _cameras_pelas_pastas({"Garagem": None}, [], lambda ip: True)
        self.assertEqual(status[0]["status_gravacao"], "NAO_VERIFICADO")

    def test_vinculo_explicito_ganha_do_nome(self):
        pastas = {"A": 1, "B": 2}
        explicita = {"nome": "B", "pasta_gravacao": "A"}
        por_nome = {"nome": "A"}
        r = vincular_cameras_as_pastas([por_nome, explicita], pastas)
        self.assertEqual(list(r), ["A"])
        self.assertIs(r["A"], explicita)


if __name__ == "__main__":
    unittest.main()
