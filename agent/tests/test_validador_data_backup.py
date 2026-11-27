"""Regra de data do backup de pasta (UNM2000/Huawei/Digifort): o do dia ou um de ate 24 h atras."""
import sys
import unittest
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.backup.file_manager.models import BackupFile, BackupGroup, BackupStatus
from src.backup.file_manager.validators import Validator


def grupo(data):
    return BackupGroup(date=data, files=[BackupFile(path=Path("x.zip"), file_type="ZIP")])


class TestDataDoBackup(unittest.TestCase):
    def test_mesmo_dia_vale(self):
        self.assertTrue(Validator.is_expected_date(grupo(datetime(2026, 11, 26, 3, 0)), datetime(2026, 11, 26, 23, 0)))

    def test_madrugada_antes_da_exportacao_aceita_o_de_ontem(self):
        # agenda das 02:00 (teste-mk): o UNM so exporta as 03:00, o ultimo e o de 25/11 03:00
        ok, status = Validator.validate_group_for_copy(grupo(datetime(2026, 11, 25, 3, 0, 10)), datetime(2026, 11, 26, 2, 0))
        self.assertEqual((ok, status), (True, BackupStatus.OK))
        # backup manual de 00:58 (Chiquinho)
        self.assertTrue(Validator.is_expected_date(grupo(datetime(2026, 11, 25, 3, 0, 10)), datetime(2026, 11, 26, 0, 58)))

    def test_mais_de_24h_continua_antigo(self):
        ok, status = Validator.validate_group_for_copy(grupo(datetime(2026, 11, 25, 3, 0)), datetime(2026, 11, 26, 3, 30))
        self.assertEqual((ok, status), (False, BackupStatus.ANTIGO))
        # Hot Beach Resort: ultimo backup de 15/11
        self.assertFalse(Validator.is_expected_date(grupo(datetime(2026, 11, 15, 3, 0)), datetime(2026, 11, 25, 23, 0)))

    def test_data_futura_de_outro_dia_nao_vale(self):
        self.assertFalse(Validator.is_expected_date(grupo(datetime(2026, 11, 27, 3, 0)), datetime(2026, 11, 26, 23, 0)))


if __name__ == "__main__":
    unittest.main()
