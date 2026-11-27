"""Defense no túnel do Mikrotik: o relatório leva as câmeras (online e gravações pela API do Defense), como no
Windows. Antes ia `cameras: None` e a Galeria/Gravação do equipamento ficavam vazias, embora o teste de conexão
listasse as câmeras."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.backup import tunel_preparo as prep
from src.vms import defense

EQ = {"name": "Defense MK", "tipo": "DEFENSE", "ip": "10.0.0.5", "username": "system", "password": "x",
      "config_extra": {}}
CAMS = [{"canal": 1, "nome": "Portaria", "ip": "10.0.0.20", "online": True, "status_comunicacao": "ONLINE",
         "status_gravacao": "COM_GRAVACAO", "total_dias": 15, "mapa": "█" * 15, "dias_com_gravacao": []}]


class TestDefenseCamerasNoTunel(unittest.TestCase):
    def test_cameras_vao_com_backup_pronto(self):
        pronto = {"nome": "Defense MK", "status": "PRONTO", "arquivos_origem": [], "cameras": None}
        with patch.object(prep, "_preparar_arquivo_defense", return_value=pronto), \
                patch.object(defense, "_montar_status_cameras_defense", return_value=CAMS):
            res = prep.preparar_defense(dict(EQ))
        self.assertEqual(res["status"], "PRONTO")
        self.assertEqual(res["cameras"], CAMS)

    def test_cameras_vao_mesmo_sem_pasta_de_backup(self):
        # Sem pasta_origem o arquivo dá ERRO, mas a Galeria/Gravação continuam recebendo as câmeras
        with patch.object(defense, "_montar_status_cameras_defense", return_value=CAMS):
            res = prep.preparar_defense(dict(EQ))
        self.assertEqual(res["status"], "ERRO")
        self.assertEqual(res["cameras"], CAMS)

    def test_falha_na_api_nao_derruba_o_backup(self):
        pronto = {"nome": "Defense MK", "status": "PRONTO", "arquivos_origem": [], "cameras": None}
        with patch.object(prep, "_preparar_arquivo_defense", return_value=pronto), \
                patch.object(defense, "_montar_status_cameras_defense", side_effect=RuntimeError("api fora")):
            res = prep.preparar_defense(dict(EQ))
        self.assertEqual(res["status"], "PRONTO")
        self.assertIsNone(res["cameras"])


if __name__ == "__main__":
    unittest.main()
