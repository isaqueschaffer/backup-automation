"""Interpretacao do status das ONTs de uma OLT Huawei (amostra de uma OLT real, MA5800)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.application.status_olt import coletar_status_olts
from src.olt import huawei_status as h

BOARD = """
  -------------------------------------------------------------------------
  SlotID  BoardName  Status          SubType0 SubType1    Online/Offline
  -------------------------------------------------------------------------
  0
  1
  2       H901GPLF   Normal
  3
  4
  5
  6
  7
  8       H902MPLA   Standby_normal
  9       H902MPLA   Active_normal
  10
  11
  12
  13
  14
  15
  16
  17
  18      H901PILA   Normal
  19      H901PILA   Normal
  -------------------------------------------------------------------------
"""

RESUMO_ONT = """
  Command:
          display ont info summary 0
  Command is being executed. Please wait
  ------------------------------------------------------------------------------
  In port 0/2/0, the total of ONTs are: 4, online: 2
  ------------------------------------------------------------------------------
  ONT  Run     Last                Last                Last
  ID   State   UpTime              DownTime            DownCause
  ------------------------------------------------------------------------------
  0    online  2026-11-01 09:46:24 -                   -
  1    online  2026-11-06 17:12:45 2026-11-06 17:11:56 dying-gasp
  9    offline 2026-11-06 14:42:52 2026-11-06 14:45:54 dying-gasp
  11   offline 2026-11-01 09:46:37 2026-11-01 12:54:17 LOSi/LOBi
  ------------------------------------------------------------------------------
  ONT        SN        Type          Distance Rx/Tx power  Description
  ID                                    (m)      (dBm)
  ------------------------------------------------------------------------------
  0   485754436527AF9E HG8546M5         1334  -18.63/2.43  PORTARIA_SERVICO
  1   485754432698BA9E HG8546M5         91    -7.88/2.28   PORTARIA_SOCIAL
  9   485754434043837F 010H             -     -/-          CX LAGO QUADRA FUTSAL
  11  48575443CA6F609D HG8546M5         -     -/-          onu perimetro 11
  ------------------------------------------------------------------------------
"""


class TestParseBoard(unittest.TestCase):
    def test_so_slots_com_placa(self):
        self.assertEqual(h.parse_board(BOARD), [2, 8, 9, 18, 19])

    def test_vazio_nao_quebra(self):
        self.assertEqual(h.parse_board(""), [])
        self.assertEqual(h.parse_board(None), [])


class TestParseOntSummary(unittest.TestCase):
    def test_cabecalho_e_quantidade(self):
        resumo = h.parse_ont_summary(RESUMO_ONT)
        self.assertEqual((resumo["frame"], resumo["slot"], resumo["porta"]), (0, 2, 0))
        self.assertEqual((resumo["total"], resumo["online"]), (4, 2))
        self.assertEqual(len(resumo["onts"]), 4)

    def test_onu_online_com_sinal_e_identificacao(self):
        onts = h.parse_ont_summary(RESUMO_ONT)["onts"]
        self.assertEqual(onts[0]["estado"], "ONLINE")
        self.assertEqual(onts[0]["serial"], "485754436527AF9E")
        self.assertEqual(onts[0]["tipo"], "HG8546M5")
        self.assertEqual(onts[0]["distancia_m"], 1334)
        self.assertEqual(onts[0]["sinal_onu_dbm"], -18.63)
        self.assertEqual(onts[0]["tx_onu_dbm"], 2.43)
        self.assertEqual(onts[0]["nome"], "PORTARIA_SERVICO")

    def test_offline_por_dying_gasp_e_sem_energia(self):
        onts = h.parse_ont_summary(RESUMO_ONT)["onts"]
        self.assertEqual(onts[9]["estado"], "SEM_ENERGIA")

    def test_offline_por_losi_e_falha(self):
        onts = h.parse_ont_summary(RESUMO_ONT)["onts"]
        self.assertEqual(onts[11]["estado"], "FALHA")

    def test_online_ignora_causa_do_historico(self):
        # ONT 1 esta online mas tem uma causa de queda antiga (dying-gasp) no historico; deve ficar ONLINE.
        onts = h.parse_ont_summary(RESUMO_ONT)["onts"]
        self.assertEqual(onts[1]["estado"], "ONLINE")

    def test_sem_sinal_nao_populado(self):
        onts = h.parse_ont_summary(RESUMO_ONT)["onts"]
        self.assertNotIn("sinal_onu_dbm", onts[9])
        self.assertNotIn("distancia_m", onts[9])

    def test_resposta_sem_cabecalho_devolve_vazio(self):
        self.assertEqual(h.parse_ont_summary("porta sem ONT configurada"), {})
        self.assertEqual(h.parse_ont_summary(""), {})


class TestColetarHuawei(unittest.TestCase):
    def test_monta_indice_e_qualidade(self):
        # Respostas canonicas por comando enviado (a 1a. leitura, do banner de login, nao tem comando associado).
        # Slot 8 (H902MPLA, controladora) rejeita o `interface gpon`: o prompt nao muda, fica em (config)#.
        por_comando = [
            ("enable", "RECANTOREAL#"),
            ("undo smart", "RECANTOREAL#"),
            ("display board 0", BOARD + "\nRECANTOREAL#"),
            ("config", "RECANTOREAL(config)#"),
            ("interface gpon 0/8", "Error: Wrong parameter found.\nRECANTOREAL(config)#"),
            ("interface gpon 0/2", "RECANTOREAL(config-if-gpon-0/2)#"),
            ("display ont info summary 0", RESUMO_ONT + "\nRECANTOREAL(config-if-gpon-0/2)#"),
            ("quit", "RECANTOREAL(config)#"),
        ]

        class FakeShell:
            def __init__(self):
                self._pendente = "RECANTOREAL>"  # banner inicial, ja disponivel

            def send(self, texto, *_a, **_k):
                cmd = texto.strip()
                if cmd:  # ignora o "\n" de wait inicial, se houver
                    for prefixo, resposta in por_comando:
                        if cmd.startswith(prefixo):
                            self._pendente = resposta
                            break

            def settimeout(self, *_a):
                pass

            def recv_ready(self):
                return self._pendente is not None

            def recv(self, *_a):
                texto, self._pendente = self._pendente, None
                return texto.encode()

        class FakeSSH:
            def set_missing_host_key_policy(self, *_a):
                pass

            def connect(self, *_a, **_k):
                pass

            def invoke_shell(self):
                return FakeShell()

            def close(self):
                pass

        with patch.object(h.paramiko, "SSHClient", return_value=FakeSSH()):
            with patch.object(h, "parse_board", return_value=[2, 8]), \
                 patch.object(h, "MAX_PORTA", 1):
                resultado = h.coletar_huawei("10.11.104.2", "root", "senha")

        self.assertNotIn("erro", resultado)
        onus = {o["indice"]: o for o in resultado["onus"]}
        self.assertIn("0/2/0:0", onus)
        self.assertEqual(onus["0/2/0:0"]["qualidade"], "BOM")
        # Slot 8 nao entrou no modo GPON (prompt nao mudou): nenhuma ONU vem de la.
        self.assertFalse(any(o["slot"] == 8 for o in resultado["onus"]))

    def test_falha_de_conexao_nao_levanta_erro(self):
        with patch.object(h.paramiko, "SSHClient", side_effect=OSError("sem rota")):
            resultado = h.coletar_huawei("10.11.104.2", "root", "senha")
        self.assertIn("erro", resultado)


class TestColetarStatusOltsHuawei(unittest.TestCase):
    def test_usa_coletor_huawei_injetado(self):
        equipamento = {
            "name": "OLT_HUAWEI_01", "tipo": "OLT", "active": True,
            "fabricante": "HUAWEI", "ip": "10.11.104.2", "username": "root", "password": "senha",
        }
        chamadas = []

        def coletar_huawei_fake(ip, usuario, senha, porta):
            chamadas.append((ip, usuario, senha, porta))
            return {"ip": ip, "onus": []}

        resultado = coletar_status_olts([equipamento], coletar_huawei=coletar_huawei_fake)

        self.assertEqual(chamadas, [("10.11.104.2", "root", "senha", 22)])
        self.assertEqual(resultado[0]["olts"][0]["ip"], "10.11.104.2")

    def test_sem_credenciais_nao_chama_coletor(self):
        equipamento = {"name": "OLT_HUAWEI_01", "tipo": "OLT", "active": True, "fabricante": "HUAWEI", "ip": "10.11.104.2"}
        chamado = []
        resultado = coletar_status_olts([equipamento], coletar_huawei=lambda *a: chamado.append(a))
        self.assertEqual(chamado, [])
        self.assertIn("erro", resultado[0]["olts"][0])


if __name__ == "__main__":
    unittest.main()
