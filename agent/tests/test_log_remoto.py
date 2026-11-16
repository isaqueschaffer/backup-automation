"""Log completo: o ManipuladorLogRemoto enfileira todas as linhas INFO para cima (as comuns com detalhe=True),
menos as marcadas com enviar_servidor=False, e o envio leva o campo detalhe ao servidor."""
import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.application import log_remoto


class TestLogRemoto(unittest.TestCase):
    def setUp(self):
        self.manipulador = log_remoto.ManipuladorLogRemoto()
        self.logger = logging.getLogger("teste.log_remoto")
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        self.logger.addHandler(self.manipulador)

    def tearDown(self):
        self.logger.removeHandler(self.manipulador)
        log_remoto._instancia = None

    def _fila(self):
        return [(i["nivel"], i["mensagem"], i["detalhe"]) for i in self.manipulador.fila]

    def test_envia_todas_as_linhas_e_marca_as_comuns_como_detalhe(self):
        self.logger.debug("debug fica de fora")
        self.logger.info("Conectando ao NVR")
        self.logger.info("BACKUP FINALIZADO.", extra={"enviar_servidor": True})
        self.logger.warning("Aviso")
        self.logger.error("Erro")
        self.logger.info("Ping recebido", extra={"enviar_servidor": False})
        self.logger.error("erro local", extra={"enviar_servidor": False})
        self.assertEqual(self._fila(), [
            ("INFO", "Conectando ao NVR", True),
            ("INFO", "BACKUP FINALIZADO.", False),
            ("WARNING", "Aviso", False),
            ("ERROR", "Erro", False),
        ])

    def test_linha_comum_repetida_e_deduplicada_e_senha_mascarada(self):
        self.logger.info("Conectando rtsp://admin:segredo@10.0.0.1")
        self.logger.info("Conectando rtsp://admin:segredo@10.0.0.1")
        self.assertEqual(self._fila(), [("INFO", "Conectando rtsp://admin:***@10.0.0.1", True)])

    def test_envio_leva_o_campo_detalhe(self):
        log_remoto._instancia = self.manipulador
        self.logger.info("linha comum")
        self.logger.warning("aviso")
        with patch("src.application.api_client.send_logs", return_value=True) as envio:
            self.assertEqual(log_remoto.enviar_pendentes({}), 2)
        enviados = envio.call_args[0][1]
        self.assertEqual([(l["mensagem"], l["detalhe"]) for l in enviados], [("linha comum", True), ("aviso", False)])
        self.assertEqual(len(self.manipulador.fila), 0)


if __name__ == "__main__":
    unittest.main()
