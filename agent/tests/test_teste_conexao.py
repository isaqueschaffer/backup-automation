"""Teste de conexão pedido pelo painel (src/application/teste_conexao.py)."""
import socket
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.application import teste_conexao as tc  # noqa: E402


def _servidor_tcp():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(5)

    def aceitar():
        while True:
            try:
                c, _ = s.accept()
                c.close()
            except OSError:
                return

    threading.Thread(target=aceitar, daemon=True).start()
    return s


class HostPorta(unittest.TestCase):
    def test_formatos(self):
        self.assertEqual(tc.host_porta("10.0.0.1", 80), ("10.0.0.1", 80))
        self.assertEqual(tc.host_porta("10.0.0.1:8080", 80), ("10.0.0.1", 8080))
        self.assertEqual(tc.host_porta("https://pabx.local/x", 80), ("pabx.local", 443))
        self.assertEqual(tc.host_porta("http://1.2.3.4:81", 80), ("1.2.3.4", 81))


class Execucao(unittest.TestCase):
    def setUp(self):
        self.estados = []

    def _rodar(self, task):
        return tc.executar_teste_conexao({"task_id": "t1", **task}, {}, lambda e: self.estados.append(e))

    def test_generico_ok_envia_progresso_e_final(self):
        srv = _servidor_tcp()
        try:
            porta = srv.getsockname()[1]
            r = self._rodar({"tipo": "ONU", "name": "x", "ip": f"127.0.0.1:{porta}", "password": "segredo"})
        finally:
            srv.close()
        self.assertTrue(r["ok"])
        final = self.estados[-1]
        self.assertTrue(final["concluido"] and final["ok"])
        self.assertEqual(final["etapas"][0]["estado"], "ok")
        self.assertEqual(final["task_id"], "t1")

    def test_porta_fechada_falha_e_marca_etapas(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
        s.close()
        r = self._rodar({"tipo": "PABX", "name": "p", "ip": f"http://127.0.0.1:{porta}", "password": "segredo"})
        self.assertFalse(r["ok"])
        final = self.estados[-1]
        self.assertEqual([e["estado"] for e in final["etapas"]], ["erro", "pulado"])

    def test_senha_nunca_sai_na_mensagem(self):
        with mock.patch.object(tc, "_testar_generico", side_effect=RuntimeError("falhou com senha segredo123")):
            r = self._rodar({"tipo": "ONU", "name": "x", "ip": "1.1.1.1", "password": "segredo123"})
        self.assertNotIn("segredo123", r["mensagem"])
        self.assertNotIn("segredo123", str(self.estados))

    def test_olt_sem_fabricante(self):
        r = self._rodar({"tipo": "OLT", "name": "o", "ip": "1.1.1.1", "password": "x", "config_extra": {}})
        self.assertFalse(r["ok"])
        self.assertIn("fabricante", r["mensagem"])

    def test_olt_vsol_coleta_e_envia_status(self):
        srv = _servidor_tcp()
        porta = srv.getsockname()[1]
        enviados = []
        lista = [{"nome": "o", "olts": [{"nome": "o", "ip": "127.0.0.1", "onus": [{}, {}, {}]}]}]
        try:
            with mock.patch("src.application.status_olt.coletar_status_olts", return_value=lista), \
                 mock.patch("src.application.api_client.send_status_olts", side_effect=lambda c, l: enviados.append(l) or True):
                r = self._rodar({"tipo": "OLT", "name": "o", "ip": "127.0.0.1", "password": "x", "username": "u",
                                 "config_extra": {"fabricante_olt": "VSOL", "porta": porta}})
        finally:
            srv.close()
        self.assertTrue(r["ok"], r)
        self.assertIn("3 ONU", r["mensagem"])
        self.assertEqual(enviados, [lista])


if __name__ == "__main__":
    unittest.main()
