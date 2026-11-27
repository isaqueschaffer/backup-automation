"""Hikvision com RTSP sempre em tempo esgotado (DS-2CD1101-I do CFTV 01 - Navarro, 12 câmeras de elevador): a captura
pede a foto pela API HTTP (ISAPI), que não depende de quadro-chave. E o tempo esgotado traz a última linha do ffmpeg."""
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

sys.modules.setdefault("imageio_ffmpeg", types.SimpleNamespace(get_ffmpeg_exe=lambda: "ffmpeg"))

from src.camera import rtsp_client as rc

TASK = {"ip": "192.168.5.23", "username": "admin", "password": "s3nh@", "modelo": "Hikvision",
        "canal": None, "stream_principal": True, "direct_camera": True}
JPEG = b"\xff\xd8" + b"x" * 2000
TEMPO = (None, "Tempo esgotado (18s) via TCP")


def _resp(status, conteudo=b""):
    r = MagicMock()
    r.status_code, r.content = status, conteudo
    return r


class TestFotoHikvision(unittest.TestCase):
    def _capturar(self, task, respostas_http):
        with patch.object(rc, "_capturar_frame_ffmpeg", return_value=TEMPO), \
                patch.object(rc.socket, "create_connection"), \
                patch("src.utils.http.fazer_get", side_effect=respostas_http) as get:
            return rc.test_rtsp_camera(dict(task)), get

    def test_rtsp_em_tempo_esgotado_usa_a_foto_http(self):
        res, get = self._capturar(TASK, [_resp(200, JPEG)])
        self.assertTrue(res["success"])
        self.assertIn("/ISAPI/Streaming/channels/101/picture", get.call_args[0][0])
        self.assertEqual(get.call_args[0][1:3], ("admin", "s3nh@"))  # senha pura, não a da URL RTSP

    def test_caminho_antigo_quando_o_isapi_nao_existe(self):
        res, get = self._capturar(TASK, [_resp(404), _resp(200, JPEG)])
        self.assertTrue(res["success"])
        self.assertIn("/Streaming/channels/101/picture", get.call_args[0][0])

    def test_canal_de_gravador_entra_no_caminho(self):
        res, get = self._capturar({**TASK, "canal": 3}, [_resp(200, JPEG)])
        self.assertIn("/channels/301/picture", get.call_args[0][0])

    def test_senha_recusada_no_http_para_sem_nova_tentativa(self):
        res, get = self._capturar(TASK, [_resp(401)])
        self.assertFalse(res["success"])
        self.assertEqual(get.call_count, 1)
        self.assertIn("Foto HTTP: usuário ou senha recusados", res["error_message"])

    def test_401_no_rtsp_nao_tenta_o_http(self):
        with patch.object(rc, "_capturar_frame_ffmpeg", return_value=(None, "401 Unauthorized")), \
                patch.object(rc.socket, "create_connection"), \
                patch("src.utils.http.fazer_get") as get:
            res = rc.test_rtsp_camera(dict(TASK))
        self.assertFalse(res["success"])
        get.assert_not_called()  # outra senha errada poderia bloquear o usuário na câmera

    def test_outras_marcas_nao_usam_a_api_hikvision(self):
        with patch.object(rc, "_capturar_frame_ffmpeg", return_value=TEMPO), \
                patch.object(rc.socket, "create_connection"), \
                patch("src.utils.http.fazer_get") as get:
            rc.test_rtsp_camera({**TASK, "modelo": "Grandstream"})
        get.assert_not_called()


class TestTempoEsgotadoComLogDoFfmpeg(unittest.TestCase):
    def test_ultima_linha_do_ffmpeg_vai_no_motivo_sem_senha(self):
        erro = subprocess.TimeoutExpired(cmd="ffmpeg", timeout=18,
                                         stderr=b"Input #0, rtsp, from 'rtsp://admin:s3nh@@1.2.3.4:554/x':\n"
                                                b"  Stream #0:0: Video: h264, none, 90k tbr\n")
        with patch.object(rc.subprocess, "run", side_effect=erro):
            img, motivo = rc._capturar_frame_ffmpeg("ffmpeg", "rtsp://admin:s3nh@@1.2.3.4:554/x", timeout=18)
        self.assertIsNone(img)
        self.assertTrue(motivo.startswith("Tempo esgotado (18s) via TCP [ffmpeg: Stream #0:0: Video: h264"))
        self.assertNotIn("s3nh", motivo)

    def test_sem_saida_do_ffmpeg_fica_so_o_tempo(self):
        with patch.object(rc.subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=8)):
            _, motivo = rc._capturar_frame_ffmpeg("ffmpeg", "rtsp://x", transport="udp", timeout=8)
        self.assertEqual(motivo, "Tempo esgotado (8s) via UDP")


if __name__ == "__main__":
    unittest.main()
