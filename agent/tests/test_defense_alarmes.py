"""Alarmes das centrais Intelbras cadastradas no DEFENSE (painel web de alarmes, /api/alarm-centrals)."""
import base64
import hashlib
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.application.status_alarmes_defense import coletar_status_alarmes
from src.vms import defense_alarmes as d

# Amostra real (CENTRAL RIO PRETO), com as chaves da bridge trocadas por valores falsos
RESPOSTA_API = [
    {
        "id": 3,
        "name": "CENTRAL RIO PRETO",
        "status": 1,
        "Bridge": {"id": 1, "name": "ALARMES", "private_key": "CHAVE_FALSA", "access_key": "ACESSO_FALSO"},
        "Model": {"id": 9, "name": "AMT 8000 LITE"},
        "partitions": [
            {"id": 4, "index": 0, "name": "Zona sem partição", "armed": 0, "alarm": 0},
        ],
        "zones": [],
    }
]


class TestParseAlarmes(unittest.TestCase):
    def test_central_e_particoes(self):
        alarmes = d.parse_alarmes(RESPOSTA_API)
        self.assertEqual(len(alarmes), 1)
        central = alarmes[0]
        self.assertEqual(central["id"], 3)
        self.assertEqual(central["nome"], "CENTRAL RIO PRETO")
        self.assertEqual(central["status"], 1)
        self.assertEqual(central["particoes"],
                         [{"id": 4, "nome": "Zona sem partição", "armada": False, "disparada": False}])

    def test_nao_copia_as_chaves_da_bridge(self):
        self.assertNotIn("CHAVE_FALSA", repr(d.parse_alarmes(RESPOSTA_API)))

    def test_particao_armada_e_disparada(self):
        dados = [{"name": "C1", "status": 1, "partitions": [{"name": "P1", "armed": 1, "alarm": 1}]}]
        particao = d.parse_alarmes(dados)[0]["particoes"][0]
        self.assertTrue(particao["armada"])
        self.assertTrue(particao["disparada"])

    def test_sem_nome_de_particao_usa_indice(self):
        dados = [{"name": "C1", "partitions": [{"index": 2, "armed": 0}]}]
        self.assertEqual(d.parse_alarmes(dados)[0]["particoes"][0]["nome"], "Partição 2")

    def test_lista_vazia_ou_invalida(self):
        self.assertEqual(d.parse_alarmes([]), [])
        self.assertEqual(d.parse_alarmes(None), [])
        self.assertEqual(d.parse_alarmes([{"nao_e_central": True}, "lixo"])[0]["nome"], "Central sem nome")


def _resposta(status=200, json=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json
    r.raise_for_status.return_value = None
    return r


class SessaoFake:
    """Dublê de requests.Session que guarda cookies e chamadas e devolve respostas fixas por rota."""

    def __init__(self, login, centrais=None, incendio=None, comando=None):
        self.cookies = CookiesFake()
        self.chamadas = []
        self._login = login
        self._gets = {"/api/alarm-centrals": centrais, "/api/firestations": incendio or _resposta(200, [])}
        self._comando = comando
        type(self).ultima = self

    def patch(self, url, json=None, timeout=None):
        self.chamadas.append(("PATCH", url, json, dict(self.cookies)))
        return self._comando

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, json=None, timeout=None):
        self.chamadas.append(("POST", url, json, dict(self.cookies)))
        return self._login

    def get(self, url, timeout=None):
        self.chamadas.append(("GET", url, None, dict(self.cookies)))
        resposta = self._gets[url[url.index("/api/"):]]
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


class CookiesFake(dict):
    def set(self, nome, valor):
        self[nome] = valor


class TestTokenCsrf(unittest.TestCase):
    def test_formato_do_pacote_csrf(self):
        token = d.gerar_token_csrf("secret-key")
        sal, assinatura = token.split("-", 1)
        esperado = base64.b64encode(hashlib.sha1(f"{sal}-secret-key".encode()).digest()).decode()
        self.assertEqual(assinatura, esperado.replace("+", "-").replace("/", "_").rstrip("="))
        self.assertEqual(len(sal), 8)


RESPOSTA_INCENDIO = [
    {"id": 7, "name": "INCENDIO BLOCO A", "mac": "AA:BB", "hmac": "HMAC_SECRETO", "status": 1,
     "Model": {"id": 2, "name": "CIE 1125"}, "Bridge": {"private_key": "CHAVE_FALSA"}},
]

LOGIN_OK = _resposta(200, {"desc": "ok", "token": {"token": "TOKEN_SESSAO", "refresh_token": "R"}})


class TestConsultarAlarmesDefense(unittest.TestCase):
    def _consultar(self, login, centrais=None, incendio=None):
        with patch("src.vms.defense_alarmes.requests.Session", side_effect=lambda: SessaoFake(login, centrais, incendio)):
            try:
                return d.consultar_alarmes_defense("192.168.75.41", "system", "senha", 3001)
            finally:
                self.sessao = SessaoFake.ultima

    def test_login_com_csrf_e_consulta_com_token_no_cookie(self):
        alarmes = self._consultar(LOGIN_OK, _resposta(200, RESPOSTA_API))["alarmes"]

        self.assertEqual(alarmes[0]["nome"], "CENTRAL RIO PRETO")
        metodo, url, corpo, cookies = self.sessao.chamadas[0]
        self.assertEqual((metodo, url), ("POST", "http://192.168.75.41:3001/api/auth/login"))
        self.assertEqual(corpo, {"username": "system", "password": "senha"})
        self.assertIn("csrfToken", cookies)
        metodo, url, _, cookies = self.sessao.chamadas[1]
        self.assertEqual((metodo, url), ("GET", "http://192.168.75.41:3001/api/alarm-centrals"))
        self.assertEqual(cookies["token"], "TOKEN_SESSAO")

    def test_login_recusado_levanta_erro_sem_consultar(self):
        with self.assertRaises(ValueError):
            self._consultar(_resposta(403, {"error": "Token CSRF ausente"}))
        self.assertEqual(len(self.sessao.chamadas), 1)

    def test_login_sem_token_levanta_erro(self):
        with self.assertRaises(ValueError):
            self._consultar(_resposta(200, {"desc": "erro"}))

    def test_resposta_que_nao_e_lista_levanta_erro(self):
        login = _resposta(200, {"token": {"token": "T"}})
        with self.assertRaises(ValueError):
            self._consultar(login, _resposta(200, {"erro": "nao autorizado"}))

    def test_centrais_de_incendio_sem_segredos(self):
        resultado = self._consultar(LOGIN_OK, _resposta(200, RESPOSTA_API), _resposta(200, RESPOSTA_INCENDIO))
        self.assertEqual(resultado["incendio"], [{"id": 7, "nome": "INCENDIO BLOCO A", "modelo": "CIE 1125", "status": 1}])
        self.assertNotIn("HMAC_SECRETO", repr(resultado))
        self.assertEqual(self.sessao.chamadas[2][3]["token"], "TOKEN_SESSAO")

    def test_falha_so_no_incendio_mantem_as_centrais_de_alarme(self):
        resultado = self._consultar(LOGIN_OK, _resposta(200, RESPOSTA_API), d.requests.ConnectionError("404"))
        self.assertEqual(resultado["incendio"], [])
        self.assertEqual(resultado["alarmes"][0]["nome"], "CENTRAL RIO PRETO")


class TestComandarCentral(unittest.TestCase):
    def _comandar(self, centrais, acao="ARMAR", central_id="3", comando=None):
        comando = comando or _resposta(200, {"message": "Comando enviado"})
        with patch("src.vms.defense_alarmes.requests.Session",
                   side_effect=lambda: SessaoFake(LOGIN_OK, _resposta(200, centrais), comando=comando)):
            try:
                return d.comandar_central("192.168.75.41", "system", "senha", 3001, central_id, acao)
            finally:
                self.sessao = SessaoFake.ultima

    def test_mensagem_real_do_painel_vem_em_objeto(self):
        # Resposta real do PATCH /api/commands/AMT8000/Desarm (CENTRAL RIO PRETO, 12/11/2026)
        centrais = [{"id": 3, "name": "C", "Model": {"name": "AMT 8000 LITE"}}]
        resposta = _resposta(200, {"Code": 200, "message": {"0": "Central Deactivated"}})
        self.assertEqual(self._comandar(centrais, "DESARMAR", comando=resposta), "Central Deactivated")

    def test_amt8000_usa_a_rota_propria(self):
        centrais = [{"id": 3, "name": "C", "Model": {"name": "AMT 8000 LITE"}}]
        self.assertEqual(self._comandar(centrais, "ARMAR"), "Comando enviado")
        metodo, url, corpo, cookies = self.sessao.chamadas[-1]
        self.assertEqual((metodo, url, corpo), ("PATCH", "http://192.168.75.41:3001/api/commands/AMT8000/Arm", {"station_id": 3}))
        self.assertEqual(cookies["token"], "TOKEN_SESSAO")

        self._comandar(centrais, "DESARMAR")
        self.assertTrue(self.sessao.chamadas[-1][1].endswith("/api/commands/AMT8000/Desarm"))

    def test_outros_modelos_usam_arm_disarm_com_particoes(self):
        self._comandar([{"id": 5, "name": "C", "Model": {"name": "AMT 4010 SMART"}}], "DESARMAR", "5")
        _, url, corpo, _ = self.sessao.chamadas[-1]
        self.assertTrue(url.endswith("/api/commands/arm-disarm"))
        self.assertEqual(corpo["command"], 0)
        self.assertTrue(all(corpo["partitionsState"].values()))

        self._comandar([{"id": 5, "name": "C", "Model": {"name": "AMT 2018"}}], "ARMAR", "5")
        corpo = self.sessao.chamadas[-1][2]
        self.assertEqual(corpo["command"], 1)
        self.assertEqual(corpo["partitionsState"],
                         {"partitionA": True, "partitionB": True, "partitionC": False, "partitionD": False})

    def test_central_inexistente_nao_manda_comando(self):
        with self.assertRaises(ValueError):
            self._comandar([{"id": 3, "Model": {"name": "AMT 8000"}}], central_id="99")
        self.assertNotIn("PATCH", [c[0] for c in self.sessao.chamadas])

    def test_painel_recusando_levanta_erro(self):
        with self.assertRaises(ValueError):
            self._comandar([{"id": 3, "Model": {"name": "AMT 8000"}}], comando=_resposta(500, {"error": "x"}))

    def test_acao_invalida(self):
        with self.assertRaises(ValueError):
            d.comandar_central("ip", "u", "s", 3001, "3", "EXPLODIR")


class TestAtenderComandoAlarme(unittest.TestCase):
    TASK = {"equipamento": "DEFENSE_01", "ip": "192.168.75.41", "porta": 3001, "username": "system",
            "password": "senha", "central_id": "3", "acao": "ARMAR"}

    def _atender(self, comandar):
        self.resultados, self.status = [], []
        from src.application.status_alarmes_defense import atender_comando_alarme
        return atender_comando_alarme(
            self.TASK, {"server_url": "x"}, comandar=comandar,
            coletar=lambda eq: {"ip": eq["ip"], "alarmes": [{"id": 3}], "incendio": []},
            enviar_resultado=lambda conf, ok, msg: self.resultados.append((ok, msg)),
            enviar_status=lambda conf, lista: self.status.append(lista),
            esperar=lambda s: None,
        )

    def test_sucesso_devolve_resultado_e_reenvia_o_status(self):
        chamadas = []
        ok = self._atender(lambda *a: chamadas.append(a) or "Central armada.")
        self.assertTrue(ok)
        self.assertEqual(chamadas, [("192.168.75.41", "system", "senha", 3001, "3", "ARMAR")])
        self.assertEqual(self.resultados, [(True, "Central armada.")])
        self.assertEqual(self.status[0][0]["nome"], "DEFENSE_01")

    def test_falha_devolve_erro_e_nao_reenvia_status(self):
        def falhar(*a):
            raise ValueError("login recusado")
        self.assertFalse(self._atender(falhar))
        self.assertEqual(self.resultados, [(False, "login recusado")])
        self.assertEqual(self.status, [])


class TestColetarAlarmesEquipamento(unittest.TestCase):
    def test_usa_porta_do_config_extra(self):
        chamadas = []

        def consultar_fake(ip, usuario, senha, porta):
            chamadas.append((ip, usuario, senha, porta))
            return {"alarmes": [{"nome": "C1", "status": 1, "particoes": []}], "incendio": []}

        equipamento = {
            "name": "DEFENSE_01", "ip": "192.168.75.41", "username": "admin", "password": "senha",
            "config_extra": {"porta_alarme": 3005},
        }
        resultado = d.coletar_alarmes_equipamento(equipamento, consultar=consultar_fake)

        self.assertEqual(chamadas, [("192.168.75.41", "admin", "senha", 3005)])
        self.assertEqual(resultado["ip"], "192.168.75.41")
        self.assertEqual(resultado["alarmes"][0]["nome"], "C1")

    def test_sem_senha_nao_consulta(self):
        chamado = []
        resultado = d.coletar_alarmes_equipamento(
            {"name": "DEFENSE_01", "ip": "192.168.75.41"}, consultar=lambda *a: chamado.append(a))
        self.assertEqual(chamado, [])
        self.assertIn("erro", resultado)

    def test_falha_na_consulta_nao_levanta_erro(self):
        def consultar_com_falha(*a):
            raise TimeoutError("sem resposta")

        equipamento = {"name": "DEFENSE_01", "ip": "192.168.75.41", "username": "admin", "password": "senha"}
        resultado = d.coletar_alarmes_equipamento(equipamento, consultar=consultar_com_falha)
        self.assertIn("erro", resultado)


class TestColetarStatusAlarmes(unittest.TestCase):
    def test_so_considera_defense_ativos(self):
        equipamentos = [
            {"name": "DEFENSE_01", "tipo": "DEFENSE", "active": True},
            {"name": "DEFENSE_02", "tipo": "DEFENSE", "active": False},
            {"name": "NVR_01", "tipo": "NVR", "active": True},
        ]
        chamadas = []

        def coletar_fake(eq):
            chamadas.append(eq["name"])
            return {"ip": eq.get("ip"), "alarmes": []}

        resultado = coletar_status_alarmes(equipamentos, coletar=coletar_fake)

        self.assertEqual(chamadas, ["DEFENSE_01"])
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["nome"], "DEFENSE_01")


if __name__ == "__main__":
    unittest.main()
