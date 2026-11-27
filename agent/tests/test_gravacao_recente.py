"""Captura da gravação no modo "referência" com a câmera offline (NVR 02 do Horizontes, canal 24, 27/11/2026): os
2 trechos mais recentes estouravam o tempo e o agente desistia com "Tempo esgotado ao ler o vídeo (25s)"."""
import subprocess
import sys
import time
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

sys.modules.setdefault("imageio_ffmpeg", types.SimpleNamespace(get_ffmpeg_exe=lambda: "ffmpeg"))

from src.camera import rtsp_client as rc

TASK = {"canal": 24}


def _trechos_recentes():
    agora = datetime.now().replace(microsecond=0)
    return [(agora - timedelta(hours=1, minutes=10), agora - timedelta(hours=1)),       # curto, mais recente
            (agora - timedelta(hours=4), agora - timedelta(hours=2))]                   # longo


class TestGravacaoRecente(unittest.TestCase):
    def test_tenta_outros_pontos_quando_o_fim_do_trecho_nao_vem(self):
        trechos = _trechos_recentes()
        lidos = []

        def ler(alvo, _en):
            lidos.append(alvo)
            if len(lidos) < 3:
                raise subprocess.TimeoutExpired("ffmpeg", 15)
            return b"x" * 2000, ""

        r = rc._gravacao_recente(TASK, time.monotonic() + 100, lambda i, f: trechos, ler, "teste")
        self.assertEqual(r["status"], "OK")
        self.assertEqual(len(lidos), 3)
        self.assertEqual(len(set(lidos)), 3)  # pontos diferentes, não o mesmo fim de trecho de novo

    def test_so_tempo_esgotado_explica_que_ha_gravacao(self):
        trechos = _trechos_recentes()

        def ler(_a, _e):
            raise subprocess.TimeoutExpired("ffmpeg", 15)

        r = rc._gravacao_recente(TASK, time.monotonic() + 100, lambda i, f: trechos, ler, "teste")
        self.assertEqual(r["status"], "FALHA")
        self.assertIn("tem gravação", r["motivo"])
        self.assertIn("tentativas", r["motivo"])

    def test_limita_as_tentativas(self):
        agora = datetime.now().replace(microsecond=0)
        trechos = [(agora - timedelta(hours=h, minutes=30), agora - timedelta(hours=h)) for h in range(1, 6)]
        chamadas = []

        def ler(alvo, _e):
            chamadas.append(alvo)
            raise subprocess.TimeoutExpired("ffmpeg", 15)

        rc._gravacao_recente(TASK, time.monotonic() + 100, lambda i, f: trechos, ler, "teste")
        self.assertEqual(len(chamadas), rc.TENTATIVAS_GRAVACAO)

    def test_senha_recusada_para_na_hora(self):
        chamadas = []

        def ler(alvo, _e):
            chamadas.append(alvo)
            return None, "method DESCRIBE failed: 401 Unauthorized"

        r = rc._gravacao_recente(TASK, time.monotonic() + 100, lambda i, f: _trechos_recentes(), ler, "teste")
        self.assertEqual(len(chamadas), 1)
        self.assertIn("senha", r["motivo"])

    def test_sem_trechos_e_sem_gravacao(self):
        r = rc._gravacao_recente(TASK, time.monotonic() + 100, lambda i, f: [], lambda a, e: (None, ""), "teste")
        self.assertEqual(r["status"], "SEM_GRAVACAO")

    def test_busca_recusada(self):
        r = rc._gravacao_recente(TASK, time.monotonic() + 100, lambda i, f: None, lambda a, e: (None, ""), "teste")
        self.assertEqual(r["motivo"], "NVR não respondeu à busca de gravações")

    def test_trecho_longo_rende_ponto_no_meio(self):
        agora = datetime.now().replace(microsecond=0)
        alvos = rc._alvos_trechos([(agora - timedelta(hours=2), agora)], agora)
        self.assertEqual(len(alvos), 2)
        self.assertEqual(alvos[0][0], agora - timedelta(seconds=rc.JANELA_GRAVACAO_S + 10))
        self.assertEqual(alvos[1][0], agora - timedelta(hours=1))


if __name__ == "__main__":
    unittest.main()
