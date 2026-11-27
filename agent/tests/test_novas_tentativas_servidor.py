"""Relatório e ZIP do backup com novas tentativas quando o pedido não chegou ao servidor (queda de DNS na Horizontes,
26/11/2026: a rodada inteira foi descartada por um erro de menos de 1 minuto)."""
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

import requests
from urllib3.exceptions import MaxRetryError, NewConnectionError, ReadTimeoutError

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.application import api_client

CONF = {"server_url": "https://server.exemplo/", "client_id": "cid", "api_key": "chave"}
INICIO = api_client.datetime(2026, 11, 26, 15, 10)
FIM = api_client.datetime(2026, 11, 26, 15, 16)


def _resposta(status=200, corpo=b'{"backup_id": "b1"}'):
    r = requests.Response()
    r.status_code = status
    r._content = corpo
    return r


def _erro_dns():
    """Como o requests entrega a falha de DNS: ConnectionError(MaxRetryError(reason=NameResolutionError))."""
    try:
        from urllib3.exceptions import NameResolutionError
        causa = NameResolutionError("server.exemplo", None, OSError("getaddrinfo failed"))
    except ImportError:  # urllib3 1.x
        causa = NewConnectionError(None, "Failed to resolve 'server.exemplo'")
    return requests.exceptions.ConnectionError(MaxRetryError(None, "/api/v1/agent/backup/report", reason=causa))


def _erro_conexao_recusada():
    causa = NewConnectionError(None, "[WinError 10061] conexão recusada")
    return requests.exceptions.ConnectionError(MaxRetryError(None, "/x", reason=causa))


def _erro_leitura():
    causa = ReadTimeoutError(None, "/x", "Read timed out.")
    return requests.exceptions.ReadTimeout(MaxRetryError(None, "/x", reason=causa))


class SessaoFalsa:
    """Cada item de `roteiro` é uma exceção (levantada) ou um status HTTP (respondido)."""

    def __init__(self, roteiro=()):
        self.roteiro = list(roteiro)
        self.chamadas = 0

    def request(self, metodo, url, **kw):
        self.chamadas += 1
        if "files" in kw:
            kw["files"]["file"][1].read()
        passo = self.roteiro.pop(0) if self.roteiro else 200
        if isinstance(passo, BaseException):
            raise passo
        return _resposta(passo)


class TestNovasTentativasServidor(unittest.TestCase):
    def setUp(self):
        api_client._tls_inseguro = False
        api_client._avisos_dados.clear()
        self.dormir = mock.patch("time.sleep").start()
        self.addCleanup(mock.patch.stopall)

    def _sessao(self, roteiro):
        sessao = SessaoFalsa(roteiro)
        mock.patch.object(api_client, "_obter_sessao", return_value=sessao).start()
        return sessao

    def _relatorio(self):
        return api_client.post_report(CONF, INICIO, FIM, [{"nome": "NVR 01", "status": "OK"}], "manual_dashboard")

    def test_queda_de_dns_no_relatorio_tenta_de_novo_e_entrega(self):
        sessao = self._sessao([_erro_dns(), _erro_dns()])
        with self.assertLogs(level="WARNING") as logs:
            self.assertEqual(self._relatorio(), "b1")
        self.assertEqual(sessao.chamadas, 3)
        self.assertEqual([c.args[0] for c in self.dormir.call_args_list], [30, 60])
        self.assertTrue(any("Nova tentativa em 30s (2/5)" in r.getMessage() for r in logs.records))

    def test_conexao_recusada_e_502_503_tambem_repetem(self):
        sessao = self._sessao([_erro_conexao_recusada(), 502, 503])
        self.assertEqual(self._relatorio(), "b1")
        self.assertEqual(sessao.chamadas, 4)

    def test_tempo_de_leitura_esgotado_nao_repete_para_nao_duplicar(self):
        # O servidor pode ter gravado o relatório: repetir criaria um backup duplicado e avançaria a fila 2 vezes
        sessao = self._sessao([_erro_leitura()])
        self.assertIsNone(self._relatorio())
        self.assertEqual(sessao.chamadas, 1)
        self.dormir.assert_not_called()

    def test_erro_do_servidor_nao_repete(self):
        for status in (500, 504, 403, 422):
            with self.subTest(status=status):
                sessao = self._sessao([status])
                self.assertIsNone(self._relatorio())
                self.assertEqual(sessao.chamadas, 1)
        self.dormir.assert_not_called()

    def test_esgotadas_as_tentativas_desiste_como_antes(self):
        sessao = self._sessao([_erro_dns()] * 10)
        self.assertIsNone(self._relatorio())
        self.assertEqual(sessao.chamadas, 5)
        self.assertEqual([c.args[0] for c in self.dormir.call_args_list], [30, 60, 120, 240])

    def test_upload_do_zip_repete_lendo_o_arquivo_do_inicio(self):
        lidos = []
        sessao = self._sessao([_erro_dns()])
        original = sessao.request

        def request(metodo, url, **kw):
            arquivo = kw["files"]["file"][1]
            lidos.append(arquivo.read())
            arquivo.seek(0)
            return original(metodo, url, **kw)

        sessao.request = request
        abrir = mock.patch("src.application.api_client.open", create=True,
                           side_effect=lambda *a, **k: io.BytesIO(b"zip")).start()
        self.assertTrue(api_client.upload_zip(CONF, "b1", Path("x.zip"), device_type="MIXED"))
        self.assertEqual(lidos, [b"zip", b"zip"])
        self.assertEqual(abrir.call_count, 2)

    def test_classificacao_dos_erros(self):
        self.assertTrue(api_client._nao_chegou_ao_servidor(_erro_dns()))
        self.assertTrue(api_client._nao_chegou_ao_servidor(_erro_conexao_recusada()))
        self.assertTrue(api_client._nao_chegou_ao_servidor(requests.exceptions.ConnectTimeout("connect timeout")))
        self.assertFalse(api_client._nao_chegou_ao_servidor(_erro_leitura()))
        self.assertFalse(api_client._nao_chegou_ao_servidor(
            requests.exceptions.ConnectionError("('Connection aborted.', RemoteDisconnected())")))
        self.assertFalse(api_client._nao_chegou_ao_servidor(requests.exceptions.SSLError("EOF")))
        self.assertFalse(api_client._nao_chegou_ao_servidor(ValueError("x")))


if __name__ == "__main__":
    unittest.main()
