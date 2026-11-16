"""Agente Linux (Mikrotik, 1.1.56): manda o log ao servidor pela mesma rotina do Windows (log_remoto)."""
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import service_linux  # noqa: E402


class TestLogLinux(unittest.TestCase):
    def tearDown(self):
        service_linux.STOP.clear()

    def test_laco_envia_os_logs_e_para_com_o_stop(self):
        chamadas = []

        def enviar(conf):
            chamadas.append(conf)
            service_linux.STOP.set()
            return 0

        with mock.patch.object(service_linux.log_remoto, "enviar_pendentes", side_effect=enviar):
            t = threading.Thread(target=service_linux.logs_loop, args=({"x": 1},))
            t.start()
            t.join(5)
        self.assertFalse(t.is_alive())
        self.assertEqual(chamadas, [{"x": 1}])

    def test_envio_final_nao_derruba_o_agente(self):
        with mock.patch.object(service_linux.log_remoto, "enviar_pendentes", side_effect=RuntimeError("rede")):
            service_linux.enviar_logs_restantes({})

    def test_backup_desativado_vai_ao_servidor(self):
        with mock.patch.dict("os.environ", {"TRILAN_ENABLE_BACKUPS": "false"}), \
                self.assertLogs("trilan.linux", level="WARNING") as cap:
            service_linux.run_backup("manual_dashboard")
        self.assertIn("Backup desativado", cap.output[0])


if __name__ == "__main__":
    unittest.main()
