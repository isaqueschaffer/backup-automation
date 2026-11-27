import sys
import threading
import time
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.application import estado
from src.application.backup_job import _executar_com_limite


class TestBackupTravado(unittest.TestCase):
    def test_equipamento_travado_estoura_o_limite_sem_prender_o_backup(self):
        parar = threading.Event()
        inicio = time.monotonic()
        with self.assertRaises(TimeoutError):
            _executar_com_limite(lambda: parar.wait(30), 0.2)
        self.assertLess(time.monotonic() - inicio, 2)
        parar.set()

    def test_devolve_o_valor_e_repassa_o_erro(self):
        self.assertEqual(_executar_com_limite(lambda a, b: a + b, 5, 1, 2), 3)
        with self.assertRaises(ValueError):
            _executar_com_limite(lambda: (_ for _ in ()).throw(ValueError("x")), 5)

    def test_backup_ha_min(self):
        estado.backup_em_andamento, estado.backup_inicio = False, None
        self.assertIsNone(estado.backup_ha_min())
        estado.backup_em_andamento, estado.backup_inicio = True, time.monotonic() - 125 * 60
        self.assertEqual(estado.backup_ha_min(), 125)
        estado.backup_em_andamento, estado.backup_inicio = False, None


if __name__ == "__main__":
    unittest.main()
