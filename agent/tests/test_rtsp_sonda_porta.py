"""A porta RTSP só é conferida depois que a 1ª captura falha: a conexão vazia de antes do ffmpeg deixava
Hikvision antigas (DS-2CD2012-I) ~18s sem atender e a captura estourava o tempo."""
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# O ffmpeg real não é usado: _capturar_frame_ffmpeg é substituído em cada teste
sys.modules.setdefault("imageio_ffmpeg", types.SimpleNamespace(get_ffmpeg_exe=lambda: "ffmpeg"))

from src.camera import rtsp_client as rc

TASK = {"ip": "192.168.5.23", "username": "admin", "password": "navarro@123", "modelo": "Hikvision",
        "canal": None, "stream_principal": True, "direct_camera": True}


class TestSondaPortaRtsp(unittest.TestCase):
    def test_sucesso_nao_abre_conexao_antes_do_ffmpeg(self):
        with patch.object(rc, "_capturar_frame_ffmpeg", return_value=(b"x" * 2000, "")), \
                patch.object(rc.socket, "create_connection") as conexao:
            res = rc.test_rtsp_camera(dict(TASK))
        self.assertTrue(res["success"])
        conexao.assert_not_called()

    def test_porta_fechada_para_na_primeira_falha(self):
        with patch.object(rc, "_capturar_frame_ffmpeg", return_value=(None, "Connection refused")) as ffmpeg, \
                patch.object(rc.socket, "create_connection", side_effect=OSError("recusada")):
            res = rc.test_rtsp_camera(dict(TASK))
        self.assertFalse(res["success"])
        self.assertIn("Porta RTSP 554 inacessível em 192.168.5.23", res["error_message"])
        self.assertEqual(ffmpeg.call_count, 1)

    def test_porta_aberta_continua_nas_outras_urls(self):
        respostas = [(None, "Tempo esgotado (18s) via TCP"), (None, "Tempo esgotado (8s) via UDP"),
                     (b"x" * 2000, "")]
        with patch.object(rc, "_capturar_frame_ffmpeg", side_effect=respostas) as ffmpeg, \
                patch.object(rc.socket, "create_connection") as conexao:
            res = rc.test_rtsp_camera(dict(TASK))
        self.assertTrue(res["success"])
        self.assertEqual(ffmpeg.call_count, 3)
        conexao.assert_called_once_with(("192.168.5.23", 554), timeout=5)

    def test_401_nao_sonda_a_porta(self):
        with patch.object(rc, "_capturar_frame_ffmpeg", return_value=(None, "401 Unauthorized")), \
                patch.object(rc.socket, "create_connection") as conexao:
            res = rc.test_rtsp_camera(dict(TASK))
        self.assertFalse(res["success"])
        self.assertIn("recusados", res["error_message"])
        conexao.assert_not_called()


if __name__ == "__main__":
    unittest.main()
