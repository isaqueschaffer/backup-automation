"""Nova tentativa do download da configuracao do NVR (Hikvision que trava o servico web por alguns minutos)."""
import unittest
from unittest import mock

from src.backup import downloader
from src.backup.downloader import com_novas_tentativas, isapi_responde


class TestComNovasTentativas(unittest.TestCase):
    def test_primeira_tentativa_ok_nao_espera(self):
        with mock.patch("src.backup.downloader.time.sleep") as dormir:
            self.assertTrue(com_novas_tentativas(lambda: True, "x"))
        dormir.assert_not_called()

    def test_tenta_de_novo_ate_dar_certo(self):
        respostas = iter([None, None, b"dados"])
        with mock.patch("src.backup.downloader.time.sleep") as dormir:
            self.assertEqual(com_novas_tentativas(lambda: next(respostas), "x", tentativas=3, pausa=7), b"dados")
        self.assertEqual(dormir.call_args_list, [mock.call(7), mock.call(7)])

    def test_todas_falham_devolve_falso_sem_esperar_depois_da_ultima(self):
        chamadas = []
        with mock.patch("src.backup.downloader.time.sleep") as dormir:
            r = com_novas_tentativas(lambda: chamadas.append(1) or False, "x", tentativas=3, pausa=1)
        self.assertFalse(r)
        self.assertEqual(len(chamadas), 3)
        self.assertEqual(dormir.call_count, 2)

    def test_padrao_usa_constantes(self):
        respostas = iter([False, True])
        with mock.patch("src.backup.downloader.time.sleep") as dormir:
            self.assertTrue(com_novas_tentativas(lambda: next(respostas), "x"))
        dormir.assert_called_once_with(downloader.PAUSA_NOVA_TENTATIVA_NVR_S)

    def test_isapi_responde(self):
        ok = mock.Mock()
        ok.get.return_value = mock.Mock(raise_for_status=lambda: None)
        self.assertTrue(isapi_responde(ok, "1.2.3.4"))
        travado = mock.Mock()
        travado.get.side_effect = TimeoutError("Read timed out")
        self.assertFalse(isapi_responde(travado, "1.2.3.4"))


class TestBackupHikvisionComNovaTentativa(unittest.TestCase):
    def test_config_baixa_na_segunda_tentativa_fica_ok(self):
        import tempfile
        from pathlib import Path
        from src.application import backup_job

        eq = {"name": "NVR 03", "ip": "192.168.5.4", "username": "admin", "password": "x", "config_extra": None}
        cams = [{"canal": "1"}]
        tentativas_bin = iter([False, True])

        def baixar(sessao, url, destino, **kw):
            return next(tentativas_bin) if "configurationData" in url else True

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(backup_job, "verificar_gravacao_nvr", return_value=(cams, "NVR")), \
                mock.patch.object(backup_job, "coletar_telemetria_nvr", return_value=None), \
                mock.patch.object(backup_job, "isapi_responde", return_value=True), \
                mock.patch.object(backup_job, "baixar_arquivo", side_effect=baixar), \
                mock.patch("src.backup.downloader.time.sleep") as dormir, \
                mock.patch.dict(backup_job.PLANILHAS_NVR, {}, clear=True):
            res = backup_job.processar_nvr(eq, "senha-zip", Path(tmp))
        self.assertEqual(res["status"], "OK")
        dormir.assert_called_once()


if __name__ == "__main__":
    unittest.main()
