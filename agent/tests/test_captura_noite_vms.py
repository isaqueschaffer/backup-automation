import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.application import captura_noite_vms as cn


def _equipamentos():
    return [{
        "tipo": "DIGIFORT", "name": "Digifort A", "active": True,
        "cameras_config": [
            {"canal": 1, "nome": "Cam 1", "ip": "10.0.0.1"},
            {"canal": 2, "nome": "Cam 2", "ip": "10.0.0.2"},
            {"canal": 3, "nome": "Sem IP", "ip": ""},
        ],
    }, {"tipo": "NVR", "name": "NVR", "active": True, "cameras_config": [{"canal": 1, "ip": "10.0.0.9"}]}]


def _captura_falsa(falham=()):
    def _f(nome, cameras, conf, prazo=None):
        for cam in cameras:
            ok = cam["nome"] not in falham
            cam["imagem_noite"] = {"status": "OK" if ok else "FALHA", "motivo": None if ok else "sem vídeo"}
    return _f


class TestCapturaNoiteVms(unittest.TestCase):
    def setUp(self):
        cn._noite_atual = None
        cn._capturadas.clear()
        cn._ultima_tentativa.clear()

    def test_janela_da_noite(self):
        self.assertTrue(cn.na_janela_noite(datetime(2026, 10, 30, 19, 30)))
        self.assertTrue(cn.na_janela_noite(datetime(2026, 10, 31, 3, 59)))
        self.assertFalse(cn.na_janela_noite(datetime(2026, 10, 31, 4, 0)))
        self.assertFalse(cn.na_janela_noite(datetime(2026, 10, 30, 19, 29)))
        self.assertFalse(cn.na_janela_noite(datetime(2026, 10, 30, 12, 0)))

    def test_fora_da_janela_nao_captura(self):
        with patch("src.camera.rtsp_client.capturar_imagens_noite_vms") as cap:
            self.assertEqual(cn.capturar_noite_vms(_equipamentos(), {}, datetime(2026, 10, 30, 12, 0)), 0)
            cap.assert_not_called()

    def test_captura_so_cameras_vms_com_ip_e_uma_vez_por_noite(self):
        with patch("src.camera.rtsp_client.capturar_imagens_noite_vms", side_effect=_captura_falsa()) as cap:
            self.assertEqual(cn.capturar_noite_vms(_equipamentos(), {}, datetime(2026, 10, 30, 20, 0)), 2)
            self.assertEqual(cap.call_count, 1)
            self.assertEqual([c["nome"] for c in cap.call_args[0][1]], ["Cam 1", "Cam 2"])
            # Mesma noite, de madrugada: nada pendente
            self.assertEqual(cn.capturar_noite_vms(_equipamentos(), {}, datetime(2026, 10, 31, 2, 0)), 0)
            self.assertEqual(cap.call_count, 1)

    def test_repete_so_a_que_falhou_depois_do_intervalo(self):
        with patch("src.camera.rtsp_client.capturar_imagens_noite_vms", side_effect=_captura_falsa(falham=("Cam 2",))) as cap:
            self.assertEqual(cn.capturar_noite_vms(_equipamentos(), {}, datetime(2026, 10, 30, 20, 0)), 1)
            # Antes de 30 min a que falhou não é repetida
            self.assertEqual(cn.capturar_noite_vms(_equipamentos(), {}, datetime(2026, 10, 30, 20, 10)), 0)
            self.assertEqual(cap.call_count, 1)
            for chave in cn._ultima_tentativa:
                cn._ultima_tentativa[chave] -= cn.REPETIR_FALHA_S + 1
            cn.capturar_noite_vms(_equipamentos(), {}, datetime(2026, 10, 30, 20, 45))
            self.assertEqual(cap.call_count, 2)
            self.assertEqual([c["nome"] for c in cap.call_args[0][1]], ["Cam 2"])

    def test_nova_noite_captura_de_novo(self):
        with patch("src.camera.rtsp_client.capturar_imagens_noite_vms", side_effect=_captura_falsa()) as cap:
            cn.capturar_noite_vms(_equipamentos(), {}, datetime(2026, 10, 30, 20, 0))
            cn.capturar_noite_vms(_equipamentos(), {}, datetime(2026, 10, 31, 20, 0))
            self.assertEqual(cap.call_count, 2)


if __name__ == "__main__":
    unittest.main()
