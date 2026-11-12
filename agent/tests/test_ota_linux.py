"""OTA do agente Linux (Mikrotik, 1.1.52): updater_linux.py e launcher_linux.py, sem rede."""
import hashlib
import importlib
import io
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src.application import updater_linux  # noqa: E402
import launcher_linux  # noqa: E402


def _pacote(versao, extra=None, requisitos="requests>=2.31,<3\n"):
    buf = io.BytesIO()
    arquivos = {
        "service_linux.py": "print('ok')\n",
        "requirements-linux.txt": requisitos,
        "src/application/updater.py": f'CURRENT_VERSION = "{versao}"\n',
    }
    arquivos.update(extra or {})
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for nome, texto in arquivos.items():
            dados = texto.encode()
            info = tarfile.TarInfo(nome)
            info.size = len(dados)
            tar.addfile(info, io.BytesIO(dados))
    return buf.getvalue()


class _Resp:
    def __init__(self, json_data=None, conteudo=b""):
        self._json, self._conteudo = json_data, conteudo

    def raise_for_status(self):
        pass

    def json(self):
        return self._json

    def iter_content(self, _n):
        yield self._conteudo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TesteUpdaterLinux(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.codigo = self.tmp / "code"
        self.imagem = self.tmp / "app"
        (self.imagem).mkdir()
        (self.imagem / "requirements-linux.txt").write_text("requests>=2.31,<3\n")
        for nome in ("DIR_CODIGO", "ATUAL", "ANTERIOR", "NOVO", "PENDENTE", "FALHOU"):
            sub = {"DIR_CODIGO": ""}.get(nome, nome.lower())
            mock.patch.object(updater_linux, nome, self.codigo / sub if sub else self.codigo).start()
        mock.patch.dict(os.environ, {"TRILAN_AGENT_DIR": str(self.imagem)}).start()
        self.addCleanup(mock.patch.stopall)

    def _rodar(self, pacote, versao="9.9.9", sha=None):
        oferta = {"has_update": True, "version": versao, "url_linux": "https://x/TrilanAgentLinux.tar.gz",
                  "sha256_linux": sha or hashlib.sha256(pacote).hexdigest()}
        with mock.patch.object(updater_linux.requests, "get",
                               side_effect=lambda url, **k: _Resp(oferta) if "update-check" in url else _Resp(conteudo=pacote)):
            return updater_linux.verificar_e_instalar({"server_url": "https://s", "client_id": "c", "api_key": "k"})

    def test_instala_e_marca_pendente(self):
        self.assertTrue(self._rodar(_pacote("9.9.9")))
        self.assertTrue((self.codigo / "atual" / "service_linux.py").is_file())
        self.assertEqual((self.codigo / "pendente").read_text(), "0")
        self.assertFalse((self.codigo / "novo").exists())

    def test_hash_errado_recusa(self):
        self.assertFalse(self._rodar(_pacote("9.9.9"), sha="0" * 64))
        self.assertFalse((self.codigo / "atual").exists())

    def test_versao_do_pacote_diferente_recusa(self):
        self.assertFalse(self._rodar(_pacote("9.9.8")))
        self.assertFalse((self.codigo / "atual").exists())

    def test_requisitos_diferentes_recusa(self):
        self.assertFalse(self._rodar(_pacote("9.9.9", requisitos="requests\nnova-lib\n")))

    def test_sintaxe_errada_recusa(self):
        self.assertFalse(self._rodar(_pacote("9.9.9", extra={"src/x.py": "def (:\n"})))

    def test_caminho_malicioso_recusa(self):
        self.assertFalse(self._rodar(_pacote("9.9.9", extra={"../fora.py": "x = 1\n"})))
        self.assertFalse((self.tmp / "fora.py").exists())

    def test_versao_bloqueada_apos_falha(self):
        self.codigo.mkdir()
        (self.codigo / "falhou").write_text("9.9.9")
        self.assertFalse(self._rodar(_pacote("9.9.9")))

    def test_atual_vira_anterior(self):
        self.assertTrue(self._rodar(_pacote("9.9.8"), versao="9.9.8"))
        self.assertTrue(self._rodar(_pacote("9.9.9")))
        self.assertIn("9.9.8", (self.codigo / "anterior" / "src/application/updater.py").read_text())
        self.assertIn("9.9.9", (self.codigo / "atual" / "src/application/updater.py").read_text())


class TesteLauncher(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.imagem = self.tmp / "app"
        self._codigo(self.imagem, "1.1.52")
        c = self.tmp / "code"
        for nome, valor in {"IMAGEM": self.imagem, "DIR_CODIGO": c, "ATUAL": c / "atual", "ANTERIOR": c / "anterior",
                            "PENDENTE": c / "pendente", "FALHOU": c / "falhou"}.items():
            mock.patch.object(launcher_linux, nome, valor).start()
        self.addCleanup(mock.patch.stopall)
        self.c = c

    def _codigo(self, pasta, versao):
        (pasta / "src/application").mkdir(parents=True)
        (pasta / "service_linux.py").write_text("")
        (pasta / "src/application/updater.py").write_text(f'CURRENT_VERSION = "{versao}"\n')

    def test_sem_ota_usa_imagem(self):
        self.assertEqual(launcher_linux.escolher(), self.imagem)

    def test_ota_mais_nova_usa_atual(self):
        self._codigo(self.c / "atual", "1.1.53")
        self.assertEqual(launcher_linux.escolher(), self.c / "atual")

    def test_imagem_mais_nova_descarta_ota(self):
        self._codigo(self.c / "atual", "1.1.51")
        self.assertEqual(launcher_linux.escolher(), self.imagem)
        self.assertFalse((self.c / "atual").exists())

    def test_tres_falhas_voltam_para_anterior(self):
        self._codigo(self.c / "anterior", "1.1.53")
        self._codigo(self.c / "atual", "1.1.54")
        (self.c / "pendente").write_text("0")
        for _ in range(3):
            self.assertEqual(launcher_linux.escolher(), self.c / "atual")
        self.assertEqual(launcher_linux.escolher(), self.c / "atual")   # 4ª: desfez e restaurou a anterior
        self.assertIn("1.1.53", (self.c / "atual/src/application/updater.py").read_text())
        self.assertEqual((self.c / "falhou").read_text(), "1.1.54")
        self.assertFalse((self.c / "pendente").exists())

    def test_tres_falhas_sem_anterior_voltam_para_imagem(self):
        self._codigo(self.c / "atual", "1.1.54")
        (self.c / "pendente").write_text("3")
        self.assertEqual(launcher_linux.escolher(), self.imagem)
        self.assertFalse((self.c / "atual").exists())


if __name__ == "__main__":
    unittest.main()
