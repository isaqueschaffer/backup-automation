import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.backup import smb_ssh_provisioner as prov


class TestProvisionadorSsh(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.arq = Path(self.tmp.name) / "smb_leitura.json"
        self.p = patch.object(prov, "_arquivo_cache", return_value=self.arq)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_caminho_local(self):
        self.assertEqual(prov.caminho_local_windows("D:UNM2000/emsback", "10.0.0.5"), r"D:\UNM2000\emsback")
        self.assertEqual(prov.caminho_local_windows("10.0.0.5:D:/x", "10.0.0.5"), r"D:\x")
        self.assertIsNone(prov.caminho_local_windows("\\10.0.0.5\emsback", "10.0.0.5"))

    def test_senha_complexa(self):
        s = prov.gerar_senha()
        self.assertEqual(len(s), 24)
        self.assertTrue(s.isalnum() and any(c.isupper() for c in s) and any(c.isdigit() for c in s))

    def test_script_escapa_aspas_e_somente_leitura(self):
        sc = prov.montar_script("trilan_leitura", "Abc123", {r"D:\o'brien": "trilan_ro_1$"})
        self.assertIn(r"'D:\o''brien'", sc)
        self.assertIn("RX", sc)
        self.assertIn("-ReadAccess", sc)
        self.assertNotIn("FullAccess", sc)
        with self.assertRaises(prov.ProvisionamentoErro):
            prov.montar_script("u", "p", {"D:\\a\nb": "s"})

    def test_provisiona_e_reaproveita_cache(self):
        def fake(host, porta, u, s, script, timeout=60):
            return r"OK|trilan_ro_x$|D:\UNM2000\emsback"+"\n"
        with patch.object(prov, "_executar_ssh", side_effect=fake) as ex:
            alvo, msg = prov.obter_alvo_leitura("D:UNM2000/emsback", "10.0.0.5", {}, "adm", "pw")
            self.assertEqual(alvo.unc_path, r"\\10.0.0.5\trilan_ro_x$")
            self.assertEqual(alvo.username, "trilan_leitura")
            self.assertEqual(ex.call_count, 1)
            alvo2, _ = prov.obter_alvo_leitura("D:UNM2000/emsback", "10.0.0.5", {}, None, None)
            self.assertEqual(alvo2.password, alvo.password)
            self.assertEqual(ex.call_count, 1)

    def test_sem_credencial_admin(self):
        alvo, msg = prov.obter_alvo_leitura("D:x", "10.0.0.5", {}, None, None)
        self.assertIsNone(alvo)
        self.assertIn("SSH", msg)

    def test_pasta_inexistente(self):
        with patch.object(prov, "_executar_ssh", return_value=r"ERRO|D:\x|pasta nao existe"+"\n"):
            alvo, msg = prov.obter_alvo_leitura("D:x", "10.0.0.5", {}, "adm", "pw")
        self.assertIsNone(alvo)
        self.assertIn("pasta nao existe", msg)

    def test_gatilho(self):
        self.assertTrue(prov.usa_provisionamento_ssh({"ssh_usuario": "adm"}))
        self.assertFalse(prov.usa_provisionamento_ssh({"ssh_usuario": "adm", "smb_usuario": "x"}))


if __name__ == "__main__":
    unittest.main()
