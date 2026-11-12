"""Login HTTP da OLT VSOL (src/olt/vsol.py): o bug real era a OLT da Horizontes, cuja tela de login so
tem texto em ingles ("login"/"password", sem "senha"), passando pelo filtro antigo (que exigia as tres
palavras juntas) e sendo tratada como "login aceito" mesmo sem autenticar — por isso nao aparecia nenhuma
ONU (as paginas de status so devolviam o redirect JS pra login, consumido como 0 linhas pelo parser)."""
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.olt import vsol as v

# Tela de login real (so em ingles) de uma OLT VSOL: form que posta para main.html, nao para login.html.
PAGINA_LOGIN_INGLES = (
    '<html><body id="body_login"><form id=form name=lgform method=post action="main.html">'
    '<td>Username</td><td><input type="text" name="user" id="user"></td>'
    '<td>Password</td><td><input type="password" name="pass" id="pass"></td>'
    '</form></body></html>'
)

# Resposta quando a sessao expira/nao autentica, ao pedir uma pagina de dados.
REDIRECT_SESSAO_INVALIDA = (
    '<html><body><script type="text/javascript">window.top.location.href="login.html";</script></body></html>'
)

PAGINA_PRINCIPAL_AUTENTICADA = '<html><body><frameset><frame src="menu.html"></frameset></body></html>'


class FakeResponse:
    def __init__(self, status_code=200, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


class FakeSession:
    """Dublê de requests.Session: devolve uma resposta fixa por URL chamada, nessa ordem."""

    def __init__(self, respostas_por_url):
        self._respostas = respostas_por_url
        self.cookies = type("Cookies", (), {"get_dict": staticmethod(lambda: {})})()
        self.chamadas = []

    def post(self, url, data=None, timeout=None, allow_redirects=None):
        self.chamadas.append(url)
        return self._respostas[url]


class TestParecerTelaLogin(unittest.TestCase):
    def test_reconhece_tela_de_login_so_em_ingles(self):
        self.assertTrue(v._parece_tela_login(PAGINA_LOGIN_INGLES))

    def test_reconhece_redirect_de_sessao_invalida(self):
        self.assertTrue(v._parece_tela_login(REDIRECT_SESSAO_INVALIDA))

    def test_nao_reconhece_pagina_autenticada(self):
        self.assertFalse(v._parece_tela_login(PAGINA_PRINCIPAL_AUTENTICADA))

    def test_texto_vazio(self):
        self.assertFalse(v._parece_tela_login(""))
        self.assertFalse(v._parece_tela_login(None))


class TestFazerLoginEndpointErrado(unittest.TestCase):
    def test_nao_aceita_login_quando_primeiro_endpoint_so_devolve_a_tela_de_login(self):
        # /action/login.html devolve a propria tela de login (o form real posta para main.html);
        # /action/main.html (segundo endpoint tentado) e quem autentica de verdade.
        session = FakeSession({
            "https://olt/action/login.html": FakeResponse(200, PAGINA_LOGIN_INGLES),
            "https://olt/action/main.html": FakeResponse(200, PAGINA_PRINCIPAL_AUTENTICADA),
        })
        sucesso = v._fazer_login(session, "https://olt", "admin", "admin")
        self.assertTrue(sucesso)
        self.assertEqual(session.chamadas, ["https://olt/action/login.html", "https://olt/action/main.html"])


if __name__ == "__main__":
    unittest.main()
