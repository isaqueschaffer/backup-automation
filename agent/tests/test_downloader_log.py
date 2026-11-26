"""AGT-12 (auditoria de 25/11/2026): o log local não pode guardar a `secretkey` da URL de backup Hikvision."""
import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src.backup import downloader  # noqa: E402

URL = "http://10.0.0.5/ISAPI/System/configurationData?secretkey=ABCDEF0123&iv=99887766"


class _Resp:
    def __init__(self, status):
        self.status_code = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Sessao:
    def __init__(self, status=None, erro=None):
        self.status, self.erro = status, erro

    def get(self, url, **k):
        if self.erro:
            raise self.erro
        return _Resp(self.status)


class TestDownloaderSemSegredoNoLog(unittest.TestCase):
    def test_sem_query_tira_a_query_de_urls_no_texto(self):
        texto = f"Max retries exceeded with url: /ISAPI/x?secretkey=AB12&iv=34 (Caused by ...)"
        limpo = downloader.sem_query(texto)
        self.assertNotIn("secretkey", limpo)
        self.assertNotIn("AB12", limpo)
        self.assertIn("/ISAPI/x?…", limpo)

    def _log_de(self, sessao, em_disco=False):
        with self.assertLogs(level="ERROR") as cm:
            if em_disco:
                with tempfile.TemporaryDirectory() as tmp:
                    downloader.baixar_arquivo(sessao, URL, Path(tmp) / "x.bin")
            else:
                downloader.baixar_bytes(sessao, URL)
        return "\n".join(cm.output)

    def test_http_de_erro_nao_loga_a_secretkey(self):
        for em_disco in (False, True):
            log = self._log_de(_Sessao(status=500), em_disco)
            self.assertNotIn("ABCDEF0123", log)
            self.assertIn("HTTP 500", log)

    def test_excecao_com_a_url_nao_loga_a_secretkey(self):
        erro = ConnectionError(f"HTTPConnectionPool(host='10.0.0.5'): Max retries exceeded with url: "
                               f"/ISAPI/System/configurationData?secretkey=ABCDEF0123&iv=99887766")
        for em_disco in (False, True):
            log = self._log_de(_Sessao(erro=erro), em_disco)
            self.assertNotIn("ABCDEF0123", log)
            self.assertNotIn("99887766", log)


if __name__ == "__main__":
    unittest.main()
