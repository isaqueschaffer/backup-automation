"""Busca de gravação que falha em um dia antigo não pode virar "sem gravação" (NVR 03 da Horizontes, 27/11/2026:
PLACAS VISITANTES e CASA ZANON apareciam sem gravação em dias que o NVR tinha gravado)."""
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.nvr import factory  # noqa: E402

HOJE = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
CAMERAS = {"9": {"nome": "PLACAS VISITANTES", "ip": "x", "online": True},
           "10": {"nome": "CASA ZANON", "ip": "y", "online": True}}


def _rodar(tem_no_dia, tem_entre=None):
    with mock.patch.object(factory, "buscar_cameras", return_value=(CAMERAS, "NVR", None)), \
            mock.patch.object(factory, "tem_gravacao_no_dia", side_effect=tem_no_dia), \
            mock.patch.object(factory, "tem_gravacao_entre", side_effect=tem_entre or (lambda *a: True)), \
            mock.patch("src.nvr.factory.time.sleep") as dormir:
        resultados, _ = factory.verificar_gravacao_nvr("10.0.0.1", "u", "p", "HIKVISION")
    return {r["nome"]: r for r in resultados}, dormir


class TestDiasNaoVerificados(unittest.TestCase):
    def test_dia_antigo_que_falha_uma_vez_e_refeito_e_fica_gravado(self):
        chamadas = []

        def tem_no_dia(ip, u, p, canal, dia):
            chamadas.append((canal, dia))
            if canal == "9" and dia < HOJE - timedelta(days=2) and chamadas.count((canal, dia)) == 1:
                return None  # o NVR não respondeu na 1a passada
            return True

        r, dormir = _rodar(tem_no_dia)
        self.assertEqual(r["PLACAS VISITANTES"]["mapa"], "█" * 15)
        self.assertEqual(r["PLACAS VISITANTES"]["total_dias"], 15)
        self.assertEqual(r["PLACAS VISITANTES"]["dias_nao_verificados"], [])
        self.assertEqual(r["PLACAS VISITANTES"]["status_gravacao"], "COM_GRAVACAO")
        dormir.assert_called_once()
        # a nova verificação refaz só os 12 dias que falharam, não os 15 nem o outro canal
        self.assertEqual(len([c for c in chamadas if c[0] == "9"]), 15 + 12)
        self.assertEqual(len([c for c in chamadas if c[0] == "10"]), 15)

    def test_dia_que_nunca_responde_fica_como_nao_verificado_e_nao_como_sem_gravacao(self):
        def tem_no_dia(ip, u, p, canal, dia):
            if canal == "10" and dia <= HOJE - timedelta(days=11):
                return None
            if canal == "10" and dia == HOJE - timedelta(days=5):
                return False  # o NVR respondeu: não gravou
            return True

        r, dormir = _rodar(tem_no_dia)
        zanon = r["CASA ZANON"]
        self.assertEqual(zanon["mapa"], "????" + "█" * 5 + "░" + "█" * 5)
        self.assertEqual(len(zanon["dias_nao_verificados"]), 4)
        self.assertEqual(zanon["status_gravacao"], "COM_GRAVACAO")  # hoje respondeu
        self.assertEqual(dormir.call_count, factory.NOVAS_VERIFICACOES)

    def test_hoje_sem_resposta_continua_nao_verificado(self):
        def tem_no_dia(ip, u, p, canal, dia):
            return None if (canal == "10" and dia == HOJE) else True

        r, _ = _rodar(tem_no_dia)
        self.assertEqual(r["CASA ZANON"]["status_gravacao"], "NAO_VERIFICADO")
        self.assertTrue(r["CASA ZANON"]["mapa"].endswith("?"))

    def test_dias_gravados_que_falham_sao_refeitos(self):
        falhas = {"n": 0}

        def tem_entre(ip, u, p, canal, inicio, fim):
            if canal == "9" and falhas["n"] < 1:
                falhas["n"] += 1
                return None
            return True

        r, dormir = _rodar(lambda *a: True, tem_entre)
        self.assertEqual(r["PLACAS VISITANTES"]["dias_gravados"], factory.DIAS_MAX_RETENCAO)
        dormir.assert_called_once()

    def test_nvr_mudo_encerra_a_rodada_sem_consultar_todos_os_canais(self):
        cams = {str(c): {"nome": f"C{c}", "ip": "x", "online": True} for c in range(1, 7)}
        consultas_na_rodada = []

        def tem_no_dia(ip, u, p, canal, dia):
            consultas_na_rodada.append(canal)
            return None

        with mock.patch.object(factory, "buscar_cameras", return_value=(cams, "NVR", None)), \
                mock.patch.object(factory, "tem_gravacao_no_dia", side_effect=tem_no_dia), \
                mock.patch.object(factory, "tem_gravacao_entre", return_value=None), \
                mock.patch("src.nvr.factory.time.sleep"):
            resultados, _ = factory.verificar_gravacao_nvr("10.0.0.1", "u", "p", "HIKVISION")
        # 1a passada: 6 canais x 15 dias; cada rodada para depois de 2 canais sem resposta
        self.assertEqual(len(consultas_na_rodada), 6 * 15 + factory.NOVAS_VERIFICACOES * 2 * 15)
        self.assertTrue(all(r["mapa"] == "?" * 15 for r in resultados))
        self.assertTrue(all(r["status_gravacao"] == "NAO_VERIFICADO" for r in resultados))

    def test_mapa_mantem_o_formato_antigo_sem_falhas(self):
        self.assertEqual(factory.gerar_mapa_dias([HOJE]), "░" * 14 + "█")


if __name__ == "__main__":
    unittest.main()
