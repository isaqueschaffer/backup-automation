"""1.1.69 (NVR 03 da Horizontes, PARCIAL em 23, 25 e 26/11/2026): o NVR Hikvision mais fraco trava o serviço web
durante a verificação de gravação. (1) A configuração é baixada ANTES da verificação; (2) as câmeras que ficarem
NAO_VERIFICADO são verificadas de novo depois de uma pausa; (3) o resultado diz o motivo quando não fica OK."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from src.application import backup_job
from src.backup import downloader
from src.nvr import factory
from src.nvr.hikvision import backup as backup_hikvision

EQ = {"name": "NVR 03", "ip": "192.168.5.4", "username": "admin", "password": "x", "config_extra": None}
BIN, XLS = b"B" * 150_000, b"X" * 500


def _baixar(bin_=BIN, xls=XLS):
    def baixar(sessao, url, **kw):
        if "configurationData" in url:
            return bin_() if callable(bin_) else bin_
        return xls() if callable(xls) else xls
    return baixar


class TestConfigAntesDaGravacao(unittest.TestCase):
    def _processar(self, verificar, baixar=None, isapi=True, telemetria=None):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(backup_job, "verificar_gravacao_nvr", side_effect=verificar), \
                mock.patch.object(backup_job, "coletar_telemetria_nvr", return_value=telemetria), \
                mock.patch.object(downloader, "isapi_responde", return_value=isapi), \
                mock.patch.object(downloader, "baixar_bytes", side_effect=baixar or _baixar()), \
                mock.patch("src.backup.downloader.time.sleep"), \
                mock.patch.dict(backup_job.PLANILHAS_NVR, {}, clear=True):
            res = backup_job.processar_nvr(dict(EQ), "senha-zip", Path(tmp))
            arquivos = sorted(p.name.split("_")[1] for p in Path(tmp).iterdir())
        return res, arquivos

    def test_configuracao_vem_antes_da_verificacao_de_gravacao(self):
        ordem = []

        def baixar(sessao, url, **kw):
            ordem.append("config")
            return BIN if "configurationData" in url else XLS

        def verificar(*a, **k):
            ordem.append("gravacao")
            return [{"nome": "c1", "status_gravacao": "COM_GRAVACAO"}], "NVR"

        res, arquivos = self._processar(verificar, baixar, telemetria={"cpu": 1})
        self.assertEqual(ordem, ["config", "config", "gravacao"])
        self.assertEqual(res["status"], "OK")
        self.assertNotIn("motivo", res)
        self.assertEqual(arquivos, ["IPCAM", "NVR"])

    def test_nvr_que_trava_na_verificacao_fica_parcial_com_a_configuracao_salva(self):
        """Antes: verificação sem resposta = ERRO "NVR INACESSIVEL" e nenhum arquivo. Agora a config já veio."""
        res, arquivos = self._processar(lambda *a, **k: ([], "DESCONHECIDO"))
        self.assertEqual(res["status"], "PARCIAL")
        self.assertIn("parou de responder", res["motivo"])
        self.assertEqual(arquivos, ["IPCAM", "NVR"])

    def test_nvr_inacessivel_desde_o_inicio_continua_erro(self):
        res, arquivos = self._processar(lambda *a, **k: ([], "DESCONHECIDO"), isapi=False)
        self.assertEqual(res["status"], "ERRO")
        self.assertEqual(arquivos, [])

    def test_falha_no_xls_vira_parcial_com_motivo(self):
        def xls():
            downloader._registrar_falha("HTTP 503")
            return None

        res, arquivos = self._processar(lambda *a, **k: ([{"nome": "c1", "status_gravacao": "COM_GRAVACAO"}], "NVR"),
                                        baixar=_baixar(xls=xls), telemetria={"cpu": 1})
        self.assertEqual(res["status"], "PARCIAL")
        self.assertIn("configuração das IPCAM (.xls) não baixada: HTTP 503", res["motivo"])
        self.assertEqual(arquivos, ["NVR"])

    def test_marca_intelbras_nao_tenta_o_isapi_antes(self):
        eq = dict(EQ, config_extra={"marca": "INTELBRAS"})
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(backup_job, "verificar_gravacao_nvr", return_value=([{"nome": "c"}], "INTELBRAS")), \
                mock.patch.object(backup_job, "coletar_telemetria_nvr", return_value=None), \
                mock.patch.object(backup_job, "baixar_configuracao_intelbras", return_value=True), \
                mock.patch.object(backup_hikvision, "baixar_antes_da_gravacao") as antes, \
                mock.patch.dict(backup_job.PLANILHAS_NVR, {}, clear=True):
            res = backup_job.processar_nvr(eq, "s", Path(tmp))
        antes.assert_not_called()
        self.assertEqual(res["status"], "OK")


class TestDescreverFalhas(unittest.TestCase):
    def test_junta_config_cameras_e_telemetria(self):
        cfg = {"bin": BIN, "xls": None, "motivos": {"xls": "ReadTimeout: Read timed out"}}
        cams = [{"nome": "MURO 01", "status_gravacao": "NAO_VERIFICADO"}, {"nome": "OK", "status_gravacao": "COM_GRAVACAO"}]
        texto = backup_hikvision.descrever_falhas(cfg, cams, None)
        self.assertIn("configuração das IPCAM (.xls) não baixada: ReadTimeout", texto)
        self.assertIn("1 câmera(s) com a gravação não verificada (MURO 01)", texto)
        self.assertIn("telemetria indisponível", texto)

    def test_tudo_ok_e_vazio(self):
        cfg = {"bin": BIN, "xls": XLS, "motivos": {}}
        self.assertEqual(backup_hikvision.descrever_falhas(cfg, [{"status_gravacao": "COM_GRAVACAO"}], {"cpu": 1}), "")

    def test_motivo_da_falha_sem_segredo(self):
        downloader._registrar_falha("Max retries exceeded with url: /ISAPI/x?secretkey=ABC123&iv=9")
        self.assertNotIn("ABC123", downloader.motivo_da_falha())


class TestNovaVerificacaoDasCamerasNaoVerificadas(unittest.TestCase):
    def test_camera_que_falhou_e_verificada_de_novo_depois_da_pausa(self):
        cameras = {"1": {"nome": "MURO 01", "ip": "x", "online": True}, "2": {"nome": "PORTARIA", "ip": "y", "online": True}}
        hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        chamadas = {"1": 0}

        def tem_no_dia(ip, u, p, canal, dia):
            if canal == "1" and dia == hoje:
                chamadas["1"] += 1
                return None if chamadas["1"] == 1 else True  # 1a vez o NVR não responde; na nova verificação responde
            return True

        with mock.patch.object(factory, "buscar_cameras", return_value=(cameras, "NVR", None)), \
                mock.patch.object(factory, "tem_gravacao_no_dia", side_effect=tem_no_dia), \
                mock.patch.object(factory, "tem_gravacao_entre", return_value=True), \
                mock.patch.object(factory, "PAUSA_NOVA_VERIFICACAO_S", 0), \
                mock.patch("src.nvr.factory.time.sleep") as dormir:
            resultados, tipo = factory.verificar_gravacao_nvr("10.0.0.1", "u", "p", "HIKVISION")
        por_nome = {r["nome"]: r["status_gravacao"] for r in resultados}
        self.assertEqual(por_nome, {"MURO 01": "COM_GRAVACAO", "PORTARIA": "COM_GRAVACAO"})
        self.assertEqual(chamadas["1"], 2)
        dormir.assert_called_once()
        self.assertEqual([r["nome"] for r in resultados], ["MURO 01", "PORTARIA"])  # a ordem dos canais se mantém

    def test_sem_camera_pendente_nao_pausa(self):
        cameras = {"1": {"nome": "A", "ip": "x", "online": True}}
        with mock.patch.object(factory, "buscar_cameras", return_value=(cameras, "NVR", None)), \
                mock.patch.object(factory, "tem_gravacao_no_dia", return_value=True), \
                mock.patch.object(factory, "tem_gravacao_entre", return_value=True), \
                mock.patch("src.nvr.factory.time.sleep") as dormir:
            factory.verificar_gravacao_nvr("10.0.0.1", "u", "p", "HIKVISION")
        dormir.assert_not_called()


class TestMotivoNoRelatorio(unittest.TestCase):
    def test_post_report_leva_o_motivo_so_quando_existe(self):
        from src.application import api_client
        enviado = {}

        def falso(conf, caminho, **k):
            enviado.update(k.get("json") or {})
            return mock.Mock(raise_for_status=lambda: None, json=lambda: {"backup_id": "b1"})

        resultados = [{"nome": "NVR 03", "status": "PARCIAL", "motivo": "configuração das IPCAM (.xls) não baixada"},
                      {"nome": "NVR 01", "status": "OK"}]
        with mock.patch.object(api_client, "_post", side_effect=falso):
            api_client.post_report({"server_url": "https://s"}, datetime.now() - timedelta(minutes=1), datetime.now(),
                                   resultados, "scheduled")
        itens = {r["nome"]: r for r in enviado["nvr_results"]}
        self.assertEqual(itens["NVR 03"]["motivo"], "configuração das IPCAM (.xls) não baixada")
        self.assertNotIn("motivo", itens["NVR 01"])


if __name__ == "__main__":
    unittest.main()
