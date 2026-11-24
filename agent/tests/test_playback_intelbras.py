"""Captura da gravação (modos "noite" e "referência") em NVR Intelbras/Dahua: antes caía no playback Hikvision
(/Streaming/tracks), o NVR respondia 404 e o painel mostrava "NVR não entregou o trecho gravado"."""
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

sys.modules.setdefault("imageio_ffmpeg", types.SimpleNamespace(get_ffmpeg_exe=lambda: "ffmpeg"))

from src.camera import rtsp_client as rc
from src.nvr.intelbras import recordings as ir


class _Resp:
    def __init__(self, text, status_code=200):
        self.text, self.status_code = text, status_code


FIND_NEXT = (
    "found=2\r\n"
    "items[0].Channel=0\r\nitems[0].StartTime=2026-11-22 00:00:00\r\nitems[0].EndTime=2026-11-22 01:00:00\r\n"
    "items[1].Channel=0\r\nitems[1].StartTime=2026-11-22 01:00:00\r\nitems[1].EndTime=2026-11-22 03:10:00\r\n"
)


def _cgi(found_text=FIND_NEXT, find_ok=True):
    def get(url, params=None, **_):
        acao = (params or {}).get("action") or url.split("action=")[1].split("&")[0]
        return {"factory.create": _Resp("result=77\r\n"), "findFile": _Resp("OK\r\n" if find_ok else "Error\r\n"),
                "findNextFile": _Resp(found_text), "destroy": _Resp("OK\r\n")}[acao]
    return get


class TestBuscaTrechos(unittest.TestCase):
    def test_le_inicio_e_fim_dos_itens(self):
        with patch.object(ir.requests, "get", _cgi()):
            t = ir.buscar_trechos_intelbras("10.0.0.1", "u", "p", 1, datetime(2026, 11, 22), datetime(2026, 11, 22, 6))
        self.assertEqual(t, [(datetime(2026, 11, 22, 0), datetime(2026, 11, 22, 1)),
                             (datetime(2026, 11, 22, 1), datetime(2026, 11, 22, 3, 10))])

    def test_sem_arquivo_e_lista_vazia(self):
        with patch.object(ir.requests, "get", _cgi("found=0\r\n")):
            self.assertEqual(ir.buscar_trechos_intelbras("10.0.0.1", "u", "p", 1, datetime(2026, 11, 22),
                                                         datetime(2026, 11, 22, 6)), [])

    def test_busca_recusada_e_none(self):
        with patch.object(ir.requests, "get", _cgi(find_ok=False)):
            self.assertIsNone(ir.buscar_trechos_intelbras("10.0.0.1", "u", "p", 1, datetime(2026, 11, 22),
                                                          datetime(2026, 11, 22, 6)))


class TestNoiteIntelbras(unittest.TestCase):
    def test_usa_02h_dentro_do_trecho(self):
        alvos = []

        def frame(_ff, _ip, _u, _s, _c, alvo, _fim, timeout=25):
            alvos.append(alvo)
            return (b"x" * 2000, "") if alvo.hour == 2 else (None, "404 Not Found")

        with patch.object(ir.requests, "get", _cgi()), patch.object(rc, "_frame_intelbras", frame), \
                patch.object(rc, "_ffmpeg_exe", lambda: "ffmpeg"):
            r = rc.capture_night_image_intelbras("10.0.0.1", "u", "p", 1, "2026-11-22")
        self.assertEqual(r["status"], "OK")
        self.assertEqual(r["horario"], "2026-11-22T02:00:00")

    def test_url_de_playback_dahua(self):
        class _Run:
            returncode, stdout, stderr = 0, b"x" * 2000, b""
        with patch.object(rc.subprocess, "run", return_value=_Run()) as run:
            rc._frame_intelbras("ffmpeg", "10.0.0.1", "admin", "s%40", 3, datetime(2026, 11, 22, 2),
                                datetime(2026, 11, 22, 3))
        url = run.call_args[0][0][run.call_args[0][0].index("-i") + 1]
        self.assertEqual(url, "rtsp://admin:s%40@10.0.0.1:554/cam/playback?channel=3&subtype=0"
                              "&starttime=2026_11_22_02_00_00&endtime=2026_11_22_02_00_10")


class TestRoteamento(unittest.TestCase):
    def test_marca_cadastrada_decide_sem_consultar(self):
        with patch.object(ir, "eh_nvr_intelbras", side_effect=AssertionError("não devia sondar")):
            self.assertTrue(rc._eh_intelbras({"marca": "Intelbras"}))
            self.assertFalse(rc._eh_intelbras({"marca": "Motorola"}))
            self.assertFalse(rc._eh_intelbras({"marca": "", "modelo": "", "direct_camera": True}))

    def test_sem_marca_sonda_uma_vez(self):
        task = {"ip": "10.0.0.1", "marca": "", "modelo": ""}
        with patch.object(ir, "eh_nvr_intelbras", return_value=True) as sonda:
            self.assertTrue(rc._eh_intelbras(task))
            self.assertTrue(rc._eh_intelbras(task))
        sonda.assert_called_once()

    def test_noite_em_nvr_intelbras_nao_usa_hikvision(self):
        task = {"ip": "10.0.0.1", "marca": "Intelbras", "modelo": "", "canal": 2, "modo": "noite",
                "username": "admin", "password": "p"}
        ok = {"image": "aW1n", "horario": "2026-11-22T02:00:00", "status": "OK", "motivo": None}
        with patch.object(rc, "capture_night_image_intelbras", return_value=ok) as intel, \
                patch.object(rc, "capture_night_image", side_effect=AssertionError("caminho Hikvision")):
            res = rc.executar_tarefa_rtsp(task)
        self.assertTrue(res["success"])
        intel.assert_called_once()


if __name__ == "__main__":
    unittest.main()
