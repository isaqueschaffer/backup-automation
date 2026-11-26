"""OLT Huawei: uma sessao SSH por vez do agente e nova tentativa so quando a OLT fecha o login (sem avaliar a senha)."""
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import paramiko

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.olt import huawei_sessao as hs
from src.olt import huawei_status

EOF = paramiko.AuthenticationException("Authentication failed: transport shut down or saw EOF")
SENHA_ERRADA = paramiko.AuthenticationException("Authentication failed.")


class TestNovasTentativas(unittest.TestCase):
    def test_fechado_no_login_tenta_de_novo(self):
        respostas = iter([EOF, EOF, "cliente"])

        def abrir():
            r = next(respostas)
            if isinstance(r, Exception):
                raise r
            return r

        with mock.patch("src.olt.huawei_sessao.time.sleep") as dormir:
            self.assertEqual(hs.conectar_com_novas_tentativas(abrir, "x", tentativas=3, pausa_s=7), "cliente")
        self.assertEqual(dormir.call_args_list, [mock.call(7), mock.call(7)])

    def test_senha_errada_nao_repete(self):
        chamadas = []

        def abrir():
            chamadas.append(1)
            raise SENHA_ERRADA

        with mock.patch("src.olt.huawei_sessao.time.sleep") as dormir, self.assertRaises(paramiko.AuthenticationException):
            hs.conectar_com_novas_tentativas(abrir, "x", tentativas=3)
        self.assertEqual(len(chamadas), 1)
        dormir.assert_not_called()

    def test_esgota_as_tentativas_e_sobe_o_erro(self):
        def abrir():
            raise EOF

        with mock.patch("src.olt.huawei_sessao.time.sleep"), self.assertRaises(paramiko.AuthenticationException):
            hs.conectar_com_novas_tentativas(abrir, "x", tentativas=2)

    def test_reconhece_o_fechamento(self):
        self.assertTrue(hs.login_fechado_pela_olt(EOF))
        self.assertTrue(hs.login_fechado_pela_olt(EOFError()))
        self.assertTrue(hs.login_fechado_pela_olt(Exception("x fechou a conexão durante o login (Authentication failed: "
                                                            "transport shut down or saw EOF)")))
        self.assertFalse(hs.login_fechado_pela_olt(SENHA_ERRADA))
        self.assertFalse(hs.login_fechado_pela_olt(TimeoutError("timed out")))


class TestSessaoExclusiva(unittest.TestCase):
    def test_segunda_sessao_espera_a_primeira(self):
        ordem = []
        dentro = threading.Event()

        def primeira():
            with hs.sessao_exclusiva("10.9.9.1"):
                ordem.append("1-entra")
                dentro.set()
                time.sleep(0.3)
                ordem.append("1-sai")

        t = threading.Thread(target=primeira)
        t.start()
        dentro.wait(2)
        with hs.sessao_exclusiva("10.9.9.1", espera_s=5):
            ordem.append("2-entra")
        t.join()
        self.assertEqual(ordem, ["1-entra", "1-sai", "2-entra"])

    def test_ips_diferentes_nao_se_esperam(self):
        with hs.sessao_exclusiva("10.9.9.2"):
            with hs.sessao_exclusiva("10.9.9.3", espera_s=0.1):
                pass

    def test_espera_demais_vira_olt_ocupada(self):
        with hs.sessao_exclusiva("10.9.9.4"):
            erro = []
            t = threading.Thread(target=lambda: self._tentar("10.9.9.4", erro))
            t.start()
            t.join()
        self.assertIsInstance(erro[0], hs.OltOcupada)
        self.assertIn("sessão aberta", huawei_status.explicar_erro_ssh(erro[0], "10.9.9.4"))

    def _tentar(self, ip, erro):
        try:
            with hs.sessao_exclusiva(ip, espera_s=0.1):
                pass
        except Exception as e:
            erro.append(e)

    def test_libera_mesmo_com_erro(self):
        with self.assertRaises(RuntimeError):
            with hs.sessao_exclusiva("10.9.9.5"):
                raise RuntimeError("falhou")
        with hs.sessao_exclusiva("10.9.9.5", espera_s=0.1):
            pass


class TestColetaUsaTravaETentativas(unittest.TestCase):
    def test_coleta_tenta_de_novo_e_explica(self):
        with mock.patch.object(huawei_status, "abrir_ssh_huawei", side_effect=EOF) as abrir, \
                mock.patch("src.olt.huawei_sessao.time.sleep"):
            r = huawei_status.coletar_huawei("10.9.9.6", "root", "x")
        self.assertEqual(abrir.call_count, huawei_status.TENTATIVAS_LOGIN_STATUS)
        self.assertIn("a senha não foi avaliada", r["erro"])


try:
    import pyftpdlib  # noqa: F401  (dependencia so do agente Windows)
    TEM_PYFTPDLIB = True
except ImportError:
    TEM_PYFTPDLIB = False


@unittest.skipUnless(TEM_PYFTPDLIB, "pyftpdlib nao instalado (dependencia do agente Windows)")
class TestBackupAtivoMensagem(unittest.TestCase):
    def _backup(self, erro):
        from src.olt import huawei_active
        servidor = mock.Mock()
        with mock.patch.object(huawei_active, "FTPServer", return_value=servidor), \
                mock.patch.object(huawei_active.threading, "Thread"), \
                mock.patch.object(huawei_active, "abrir_ssh_huawei", side_effect=erro) as abrir, \
                mock.patch("src.olt.huawei_sessao.time.sleep"), \
                self.assertLogs(level="ERROR") as logs:
            r = huawei_active.realizar_backup_huawei_ativo(
                {"ip": "10.9.9.7", "username": "root", "password": "x", "name": "HUAWEII"}, Path("."))
        return r, abrir.call_count, "\n".join(logs.output)

    def test_olt_fechou_o_login_nao_vira_senha_incorreta(self):
        r, chamadas, log = self._backup(EOF)
        self.assertEqual(r["status"], "ERRO")
        self.assertEqual(chamadas, hs.TENTATIVAS_LOGIN)
        self.assertIn("a senha não foi avaliada", log)
        self.assertNotIn("Usuario ou senha incorretos", log)

    def test_senha_errada_uma_tentativa_so(self):
        r, chamadas, log = self._backup(SENHA_ERRADA)
        self.assertEqual(chamadas, 1)
        self.assertIn("recusou o usuário ou a senha", log)


if __name__ == "__main__":
    unittest.main()


class TestSairDaOlt(unittest.TestCase):
    """1.1.70: logout limpo antes de fechar o SSH, para a sessão não ficar contando na OLT até o idle-timeout."""

    class _ShellFalso:
        def __init__(self, respostas, falhar=False):
            self.enviados, self.respostas, self.falhar = [], list(respostas), falhar
            self.closed = False

        def send(self, texto):
            if self.falhar:
                raise OSError("canal fechado")
            self.enviados.append(texto)

        def recv_ready(self):
            return bool(self.respostas)

        def recv(self, n):
            return self.respostas.pop(0)

        def exit_status_ready(self):
            return False

    def test_confirma_o_logout_quando_a_olt_pergunta(self):
        from src.olt.huawei_sessao import sair_da_olt
        shell = self._ShellFalso([b"OLT#", b"Are you sure to log out? (y/n)[n]:"])
        with mock.patch("src.olt.huawei_sessao.time.sleep"):
            sair_da_olt(shell, espera_s=1)
        self.assertEqual(shell.enviados, ["return\n", "quit\n", "y\n"])

    def test_nunca_levanta_erro(self):
        from src.olt.huawei_sessao import sair_da_olt
        with mock.patch("src.olt.huawei_sessao.time.sleep"):
            sair_da_olt(self._ShellFalso([], falhar=True), espera_s=0.1)
