"""AGT-02: as chamadas ao servidor da Trilan validam o certificado, com fallback (aviso único) quando a verificação
falha, e as chamadas aos equipamentos da LAN continuam sem validar (certificado autoassinado)."""
import io
import ssl
import sys
import unittest
from pathlib import Path
from unittest import mock

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.application import api_client

CONF = {"server_url": "https://server.exemplo/", "client_id": "cid", "api_key": "chave"}


def _resposta(status=200, corpo=None):
    r = requests.Response()
    r.status_code = status
    r._content = (corpo or b'{"status": "ok", "backup_id": "b1"}')
    return r


def _erro_certificado():
    causa = ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
                                            "self-signed certificate")
    erro = requests.exceptions.SSLError(causa)
    erro.__cause__ = causa
    return erro


class SessaoFalsa:
    def __init__(self, falhas=()):
        self.falhas = list(falhas)
        self.chamadas = []

    def request(self, metodo, url, **kw):
        self.chamadas.append((metodo, url, kw))
        if self.falhas:
            erro = self.falhas.pop(0)
            if erro is not None:
                raise erro
        return _resposta()


class TestTlsServidor(unittest.TestCase):
    def setUp(self):
        api_client._tls_inseguro = False
        api_client._avisos_dados.clear()

    tearDown = setUp

    def _com_sessao(self, sessao):
        return mock.patch.object(api_client, "_obter_sessao", return_value=sessao)

    def test_chamada_ao_servidor_valida_o_certificado_e_leva_a_autenticacao(self):
        sessao = SessaoFalsa()
        with self._com_sessao(sessao), mock.patch.object(api_client, "_get_telemetry", return_value={}):
            self.assertTrue(api_client.send_status_olts(CONF, []))
            api_client.ping_server(CONF)
        metodo, url, kw = sessao.chamadas[0]
        self.assertEqual((metodo, url), ("POST", "https://server.exemplo/api/v1/agent/olt/status"))
        self.assertIs(kw["verify"], True)
        self.assertEqual(kw["headers"], {"X-Client-ID": "cid", "X-API-Key": "chave"})
        self.assertIs(sessao.chamadas[1][2]["verify"], True)

    def test_falha_de_certificado_cai_no_fallback_e_avisa_uma_vez(self):
        sessao = SessaoFalsa(falhas=[_erro_certificado()])
        with self._com_sessao(sessao), self.assertLogs("trilan.api", level="WARNING") as logs:
            self.assertTrue(api_client.send_status_antenas(CONF, []))
            self.assertTrue(api_client.send_status_alarmes(CONF, []))
            self.assertTrue(api_client.corrigir_resultado(CONF, "b1", "NVR", "OK"))
        self.assertEqual([c[2]["verify"] for c in sessao.chamadas], [True, False, False, False])
        self.assertTrue(api_client._tls_inseguro)
        self.assertEqual(len(logs.records), 1)
        self.assertIn("não pôde ser validado", logs.records[0].getMessage())
        self.assertIn("server.exemplo", logs.records[0].getMessage())
        self.assertNotIn("chave", logs.records[0].getMessage())

    def test_outro_erro_de_tls_nao_liga_o_modo_inseguro(self):
        sessao = SessaoFalsa(falhas=[requests.exceptions.SSLError("EOF occurred in violation of protocol")])
        with self._com_sessao(sessao), mock.patch.object(api_client, "_get_telemetry", return_value={}):
            with self.assertRaises(requests.exceptions.SSLError):
                api_client.ping_server(CONF)
        self.assertFalse(api_client._tls_inseguro)
        self.assertEqual(len(sessao.chamadas), 1)

    def test_upload_volta_o_arquivo_ao_inicio_na_segunda_tentativa(self):
        lidos = []

        class SessaoQueLe(SessaoFalsa):
            def request(self, metodo, url, **kw):
                lidos.append(kw["files"]["file"][1].read())
                return super().request(metodo, url, **kw)

        sessao = SessaoQueLe(falhas=[_erro_certificado()])
        arquivo = io.BytesIO(b"conteudo do zip")
        with self._com_sessao(sessao), mock.patch("src.application.api_client.open", create=True, return_value=arquivo), \
                self.assertLogs("trilan.api", level="WARNING"):
            arquivo.close = lambda: None
            self.assertTrue(api_client.upload_zip(CONF, "b1", Path("x.zip")))
        self.assertEqual(lidos, [b"conteudo do zip", b"conteudo do zip"])

    def test_upload_em_fluxo_usa_put_com_content_type(self):
        sessao = SessaoFalsa()
        with self._com_sessao(sessao):
            self.assertTrue(api_client.upload_zip_stream(CONF, "b1", "a.zip", iter([b"x"])))
        metodo, url, kw = sessao.chamadas[0]
        self.assertEqual(metodo, "PUT")
        self.assertEqual(kw["headers"]["Content-Type"], "application/zip")
        self.assertEqual(kw["headers"]["X-API-Key"], "chave")
        self.assertIs(kw["verify"], True)

    def test_url_http_continua_funcionando_e_avisa_uma_vez(self):
        sessao = SessaoFalsa()
        conf = dict(CONF, server_url="http://10.0.0.5:7001")
        with self._com_sessao(sessao), self.assertLogs("trilan.api", level="WARNING") as logs:
            api_client.send_logs(conf, [])
            api_client.send_logs(conf, [])
        self.assertEqual(len(sessao.chamadas), 2)
        self.assertNotIn("verify", sessao.chamadas[0][2])
        self.assertEqual(len(logs.records), 1)
        self.assertIn("http://", logs.records[0].getMessage())

    def test_aviso_dentro_do_envio_de_logs_chega_ao_log_remoto(self):
        from src.application import log_remoto
        manipulador = log_remoto.ManipuladorLogRemoto()
        api_client.log.addHandler(manipulador)
        try:
            sessao = SessaoFalsa(falhas=[_erro_certificado()])
            with self._com_sessao(sessao), log_remoto._marcar_enviando():
                self.assertTrue(api_client.send_logs(CONF, []))
                self.assertTrue(log_remoto._esta_enviando())
        finally:
            api_client.log.removeHandler(manipulador)
        self.assertEqual(len(manipulador.fila), 1)
        self.assertIn("[TLS]", manipulador.fila[0]["mensagem"])

    def test_nenhuma_chamada_ao_servidor_fica_com_verify_false_fixo(self):
        fonte = (BASE_DIR / "src" / "application" / "api_client.py").read_text(encoding="utf-8")
        self.assertEqual(fonte.count("verify=False"), 3)  # comentário + http-inseguro do fallback (2 chamadas)
        self.assertEqual(fonte.count('"X-API-Key"'), 1)


class TestEquipamentosSemValidacao(unittest.TestCase):
    """Os equipamentos da LAN (certificado autoassinado) continuam com verify=False."""

    def test_modulos_de_equipamento_mantem_verify_false(self):
        esperados = {
            "src/utils/http.py": "verify=False",
            "src/application/backup_job.py": "sessao.verify = False",
            "src/backup/tunel_preparo.py": "sessao.verify = False",
            "src/olt/vsol.py": "session.verify = False",
            "src/olt/vsol_status.py": "session.verify = False",
            "src/pabx/issabel.py": "verify=False",
            "src/vms/defense.py": "session.verify = False",
            "src/application/teste_conexao.py": "verify=False",
        }
        for arquivo, trecho in esperados.items():
            with self.subTest(arquivo=arquivo):
                self.assertIn(trecho, (BASE_DIR / arquivo).read_text(encoding="utf-8"))

    def test_fazer_get_do_equipamento_nao_valida(self):
        from src.utils import http
        with mock.patch("src.utils.http.requests.get", return_value=_resposta()) as get:
            http.fazer_get("https://192.168.0.10/ISAPI", "admin", "x")
        self.assertIs(get.call_args.kwargs["verify"], False)


if __name__ == "__main__":
    unittest.main()
