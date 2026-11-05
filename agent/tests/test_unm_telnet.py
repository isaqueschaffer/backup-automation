"""Interpretacao das respostas do CLI da OLT FiberHome (amostras conferidas numa OLT real) e selecao das OLTs."""
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.application.status_olt import coletar_status_olts
from src.olt import unm_telnet as u

ESTADO = """SLOT  2 PON  1 ONU   1 status : power down.
SLOT  2 PON  1 ONU   2 status :  active.
SLOT  2 PON  1 ONU   8 status : inactive.
SLOT  2 PON  1 ONU  99 status : algo novo.
"""

AUTORIZACAO = """-----  ONU Auth Table, Total ITEM = 150 -----

A: Authorized  P: Preauthorized  R: System Reserved

-----  ONU Auth Table, SLOT = 2, PON = 1, ITEM = 88 -----
Slot Pon Onu OnuType        ST Lic OST PhyId        PhyPwd     LogicId                  LogicPwd
---- --- --- -------------- -- --- --- ------------ ---------- ------------------------ ------------
2    1   1   HG6145E        A  1   dn  FHTTc093e037
2    1   2   HG6145E        A  1   up  FHTTc093e009
"""

OPTICO = """-----  ONU OPTIC MODULE PAR INFO 2.1.2-----
NAME          VALUE	UNIT
---------------------------------------
TYPE         : 20	(KM)
TEMPERATURE  : 39.56	('C)
VOLTAGE      :  3.20	(V)
BIAS CURRENT :  8.43	(mA)
SEND POWER   :  2.36	(Dbm)
RECV POWER   : -18.70	(Dbm)
OLT RECV POWER : -20.55	(Dbm)

RX Laser UP Threshold    : -8.00     (Dbm)
"""


ATIVO = """onu 1 is active.
onu 2 is no power.
onu 3 is inactive.
onu 4 is link loss.
onu 5 is not authorized!
onu 6 is algo novo.
"""

AUTORIZACAO_FOZ = """-----  ONU Auth Table, Total ITEM = 4 -----
-----  ONU Auth Table, SLOT = 1, PON = 1, ITEM = 2 -----
1    1   1   HG6145E        A  0   up  FHTTfe241d33
1    1   2   HG6145E        A  0   dn  FHTTfe241e14
-----  ONU Auth Table, SLOT = 1, PON = 3, ITEM = 2 -----
1    3   1   HG6145E        A  0   up  FHTTfe24aaaa
"""


VERSAO_V104 = """-------------------------------------------------
system device version is:V104R002, hardware version:V1.2
CARD            NAME          HARDVER           SOFEVER    
  1             ----             ----             ----
  2           GCOB    WKE2.201.168S1B           RP1800
  9           HSUB    WKE2.201.341R1C           RP1800
"""

VERSAO_V105 = """-------------------------------------------------
system device version is:V105R002
CARD            NAME          HARDVER           SOFEVER    
  1             GPOA  WKE2.202.802R2A           RP1500
  2             ----             ----             ----
 26             ----             ----             ----
"""


# `show onu optical-info 1` dentro de `interface pon`: tabela na RP1200 (AN6000-7) e lista na RP1100 (AN6001-G16)
OPTICO_TABELA = """			  --------------  ONU OPTIC MODULE PAR INFO  --------------
ID  TYPE(KM)  TEMPERATURE('C)  VOLTAGE(V)  BIASCURRENT(mA)  SEND POWER(Dbm)  RECV POWER(Dbm)  OLT RECV POWER(Dbm)
1   20        42.86             3.25        7.72             2.36            -18.27           -19.78           
"""
OPTICO_LISTA_6001 = """-----  ONU OPTIC MODULE PAR INFO 1.1.1-----
NAME          VALUE	UNIT
TEMPERATURE  : 64.28	('C)
SEND POWER   :  3.21	(Dbm)
RECV POWER   : -22.51	(Dbm)
OLT RECV POWER : -23.76	(Dbm)
"""
CARD_6000 = """---------------------AN6000-7---------------------
CARD   EXIST   CONFIG   DETECT    DETAIL 
  9     YES     HSCA     HSCA     MATCH/S
"""


PON_OPTICO = """ -----  PON OPTIC MODULE PAR INFO  -----
NAME                VALUE	UNIT
---------------------------------------
TYPE              : 20	(KM)
TEMPERATURE       : 24.39	('C)
VOLTAGE           :  3.27	(V)
BIAS CURRENT      : 10.92	(mA)
SEND POWER        :  5.04	(Dbm)

ONU_NO	RECV_POWER , ITEM=3
1	-19.82	(Dbm)
2	-24.55	(Dbm)
10	-26.02	(Dbm)
"""


class TestUnmTelnet(unittest.TestCase):
    def test_modulo_optico_da_pon_e_sinal_de_todas_as_onus(self):
        r = u.parse_pon_optico(PON_OPTICO)
        self.assertEqual((r["tx_dbm"], r["temperatura"]), (5.04, 24.39))
        self.assertEqual(r["sinal_onus"], {1: -19.82, 2: -24.55, 10: -26.02})
        self.assertEqual(u.parse_pon_optico("% Unknown command."), {})
        self.assertEqual(u.parse_pon_optico("ONU OPTIC MODULE PAR INFO RECV POWER : -20.0"), {})
    def test_optico_da_serie_6000_nos_dois_formatos(self):
        esperado = {"sinal_olt_dbm": -19.78, "sinal_onu_dbm": -18.27, "tx_onu_dbm": 2.36, "temperatura_onu": 42.86}
        self.assertEqual(u.parse_optico(OPTICO_TABELA), esperado)
        self.assertEqual(u.parse_optico(OPTICO_LISTA_6001),
                         {"sinal_olt_dbm": -23.76, "sinal_onu_dbm": -22.51, "tx_onu_dbm": 3.21, "temperatura_onu": 64.28})
        self.assertEqual(u.parse_optico("[ ERR -4 ] onuNo error!\nCommand executes failed."), {})

    def test_modelo_e_controladora_do_slot_9(self):
        self.assertEqual(u.parse_modelo(CARD_6000), "AN6000-7")
        self.assertIsNone(u.parse_modelo("% Command incomplete."))
        placas = [{"slot": 1, "tipo": "GPOA", "software": "RP1500"}, {"slot": 9, "tipo": "HSCA", "software": "RP1200"}]
        self.assertEqual(u.parse_controladora(placas), {"slot": 9, "tipo": "HSCA", "software": "RP1200"})
        self.assertIsNone(u.parse_controladora(placas[:1]))

    def test_parse_version(self):
        v = u.parse_version(VERSAO_V104)
        self.assertEqual((v["firmware"], v["maior"], v["hardware"]), ("V104R002", 104, "V1.2"))
        self.assertEqual(v["placas"], [{"slot": 2, "tipo": "GCOB", "hardware": "WKE2.201.168S1B", "software": "RP1800"},
                                       {"slot": 9, "tipo": "HSUB", "hardware": "WKE2.201.341R1C", "software": "RP1800"}])
        v = u.parse_version(VERSAO_V105)
        self.assertEqual((v["firmware"], v["maior"], v["hardware"]), ("V105R002", 105, None))
        self.assertEqual(len(v["placas"]), 1)
        self.assertEqual(u.parse_version("% Unknown command."), {})

    def test_familia_pelo_firmware(self):
        self.assertEqual(u.FAMILIA_POR_VERSAO[104], "classico")
        self.assertEqual(u.FAMILIA_POR_VERSAO[105], "config")

    def test_parse_active_state_do_modo_config(self):
        r = u.parse_active_state(ATIVO, 1, 4)
        self.assertEqual([(o["onu"], o["estado"]) for o in r],
                         [(1, "ONLINE"), (2, "SEM_ENERGIA"), (3, "OFFLINE"), (4, "FALHA")])
        self.assertTrue(all(o["slot"] == 1 and o["pon"] == 4 for o in r))

    def test_pons_da_autorizacao(self):
        self.assertEqual(u.pons_da_autorizacao(AUTORIZACAO_FOZ), [(1, 1), (1, 3)])
        self.assertEqual(u.parse_authorization(AUTORIZACAO_FOZ)[(1, 3, 1)]["serial"], "FHTTfe24aaaa")

    def test_prompt_de_todos_os_modos(self):
        for prompt in ("Admin# ", "Admin\\onu# ", "Admin(config)# ", "Admin(config-if-pon-1/1/1)#"):
            self.assertTrue(u._RE_PROMPT.search("resposta\n" + prompt), prompt)
        self.assertIsNone(u._RE_PROMPT.search("linha com # no meio e mais texto"))

    def test_parse_hosts(self):
        r = u.parse_hosts("10.0.0.1\nOLT Centro=10.0.0.2, 10.0.0.1;  \n!!!")
        self.assertEqual(r, [{"nome": "10.0.0.1", "ip": "10.0.0.1"}, {"nome": "OLT Centro", "ip": "10.0.0.2"}])
        self.assertEqual(u.parse_hosts(None), [])

    def test_parse_onu_state(self):
        r = u.parse_onu_state(ESTADO)
        self.assertEqual([(o["onu"], o["estado"]) for o in r],
                         [(1, "SEM_ENERGIA"), (2, "ONLINE"), (8, "OFFLINE"), (99, "DESCONHECIDO")])
        self.assertEqual(u.parse_onu_state("Admin\\onu# "), [])

    def test_parse_authorization(self):
        r = u.parse_authorization(AUTORIZACAO)
        self.assertEqual(r[(2, 1, 2)], {"tipo": "HG6145E", "serial": "FHTTc093e009"})
        self.assertEqual(len(r), 2)

    def test_parse_optico(self):
        r = u.parse_optico(OPTICO)
        self.assertEqual(r["sinal_olt_dbm"], -20.55)
        self.assertEqual(r["sinal_onu_dbm"], -18.70)
        self.assertEqual(r["tx_onu_dbm"], 2.36)
        self.assertEqual(r["temperatura_onu"], 39.56)
        self.assertEqual(u.parse_optico("[ ERR -553 ] onu is in unactive!\nCommand executes failed."), {})

    def test_qualidade_do_sinal_tres_niveis(self):
        self.assertEqual(u.qualidade_sinal(-25.0), "BOM")
        self.assertEqual(u.qualidade_sinal(-25.4), "BOM")
        self.assertEqual(u.qualidade_sinal(-25.5), "ATENCAO")   # limite: amarelo comeca em -25,5
        self.assertEqual(u.qualidade_sinal(-26.0), "ATENCAO")
        self.assertEqual(u.qualidade_sinal(-26.9), "ATENCAO")
        self.assertEqual(u.qualidade_sinal(-27.0), "RUIM")      # limite: vermelho comeca em -27
        self.assertEqual(u.qualidade_sinal(-30.0), "RUIM")
        self.assertIsNone(u.qualidade_sinal(None))

    def test_resumir_onus(self):
        onus = [
            {"slot": 2, "pon": 1, "estado": "ONLINE", "qualidade": "RUIM"}, {"slot": 2, "pon": 1, "estado": "OFFLINE"},
            {"slot": 2, "pon": 1, "estado": "SEM_ENERGIA"}, {"slot": 1, "pon": 3, "estado": "DESCONHECIDO"},
        ]
        totais, por_pon = u.resumir_onus(onus)
        self.assertEqual(totais, {"total": 4, "online": 1, "offline": 1, "falha": 0, "sem_energia": 1, "sinal_ruim": 1})
        self.assertEqual([(p["slot"], p["pon"], p["total"], p["sinal_ruim"]) for p in por_pon], [(1, 3, 1, 0), (2, 1, 3, 1)])

    def test_remove_negociacao_telnet(self):
        self.assertEqual(u._limpar_telnet(b"\xff\xfd\x18Login: \xff\xfa\x18\x01\xff\xf0ok"), "Login: ok")


class TestSelecaoDeOlts(unittest.TestCase):
    def test_coleta_so_unm2000_ativa_com_olts_e_acesso(self):
        chamadas = []

        def falso(ip, usuario, senha, enable, porta):
            chamadas.append((ip, usuario, senha, enable, porta))
            return {"ip": ip, "totais": {"total": 1}}

        acesso = {"telnet_usuario": "GEPON", "telnet_senha": "s1", "telnet_enable": "e1"}
        equipamentos = [
            {"tipo": "OLT", "name": "UNM", "active": True,
             "config_extra": {"fabricante_olt": "UNM2000", "olts": "OLT A=10.0.0.1\n10.0.0.2", **acesso}},
            {"tipo": "OLT", "name": "Porta", "active": True,
             "config_extra": {"olts": "10.0.0.3", "telnet_usuario": "u", "telnet_senha": "p", "telnet_porta": "2323"}},
            {"tipo": "OLT", "name": "Sem OLTs", "active": True, "config_extra": {"fabricante_olt": "UNM2000", **acesso}},
            {"tipo": "OLT", "name": "Sem usuario", "active": True, "config_extra": {"olts": "10.0.0.4"}},
            {"tipo": "OLT", "name": "Huawei", "active": True, "config_extra": {"fabricante_olt": "HUAWEI", "olts": "10.0.0.9", **acesso}},
            {"tipo": "OLT", "name": "Inativa", "active": False, "config_extra": {"olts": "10.0.0.8", **acesso}},
            {"tipo": "NVR", "name": "NVR", "active": True, "config_extra": {"olts": "10.0.0.7", **acesso}},
        ]
        r = coletar_status_olts(equipamentos, coletar=falso)
        self.assertEqual(chamadas, [("10.0.0.1", "GEPON", "s1", "e1", 23), ("10.0.0.2", "GEPON", "s1", "e1", 23),
                                    ("10.0.0.3", "u", "p", "p", 2323)])
        self.assertEqual([e["nome"] for e in r], ["UNM", "Porta"])
        self.assertEqual([o["nome"] for o in r[0]["olts"]], ["OLT A", "10.0.0.2"])


class TestNomesDasOnus(unittest.TestCase):
    def test_nome_ligado_ao_serial_sem_diferenciar_maiusculas(self):
        from src.olt.unm_nomes import aplicar_nomes
        onus = [{"serial": "FHTTc093e037"}, {"serial": "FHTTzzzz"}, {"serial": None}]
        self.assertEqual(aplicar_nomes(onus, {"fhttc093e037": "QUARTO 229"}), (1, 1))
        self.assertEqual(onus[0]["nome"], "QUARTO 229")
        self.assertNotIn("nome", onus[1])

    def test_nome_automatico_da_unm_conta_como_sem_nome(self):
        from src.olt.unm_nomes import aplicar_nomes, nome_automatico
        self.assertTrue(nome_automatico("PON[1]-HG6145E[3]"))
        self.assertTrue(nome_automatico("PON[4]-AN5506-04-B2[20]"))
        self.assertFalse(nome_automatico("PON 1 - SALA 609"))
        onus = [{"serial": "FHTT1"}, {"serial": "FHTT2"}]
        self.assertEqual(aplicar_nomes(onus, {"fhtt1": "PON[1]-HG6145E[1]", "fhtt2": "SALA 2"}), (1, 1))
        self.assertNotIn("nome", onus[0])

    def test_varios_servidores_e_nome_real_vence_o_automatico(self):
        from src.olt.unm_nomes import consultar_nomes, hosts_do_banco
        self.assertEqual(hosts_do_banco({"nomes_db_host": "10.0.0.1, 10.0.0.2;10.0.0.1 10.0.0.3"}), ["10.0.0.1", "10.0.0.2", "10.0.0.3"])
        bancos = {"10.0.0.1": {"a": "PON[1]-X[1]", "b": "SALA B"}, "10.0.0.2": {"a": "SALA A", "b": "PON[2]-X[2]"}}

        def buscar(host, *_):
            if host not in bancos:
                raise OSError("sem rota")
            return bancos[host]

        nomes, erros = consultar_nomes({"nomes_db_host": "10.0.0.1 10.0.0.2 10.0.0.9", "nomes_db_usuario": "u"}, buscar)
        self.assertEqual(nomes, {"a": "SALA A", "b": "SALA B"})
        self.assertEqual(len(erros), 1)
        self.assertIn("10.0.0.9", erros[0])
        self.assertIn("porta 3306", erros[0])

    def test_mensagem_de_acesso_negado_ao_banco(self):
        from src.olt.unm_nomes import explicar_erro
        self.assertIn("GRANT SELECT", explicar_erro(Exception(1045, "Access denied"), "h"))

    def test_coleta_informa_nomes_e_erro_do_banco(self):
        eq = {"tipo": "OLT", "name": "UNM", "active": True,
              "config_extra": {"olts": "10.0.0.1", "telnet_usuario": "g", "telnet_senha": "p",
                               "nomes_db_host": "h", "nomes_db_usuario": "u"}}

        def sem_banco(*a):
            raise OSError("sem rota")

        r = coletar_status_olts([eq], coletar=lambda *a: {"ip": a[0], "onus": [{"serial": "FHTT1"}]}, buscar_nomes=sem_banco)
        info = r[0]["olts"][0]["nomes"]
        self.assertEqual((info["com_nome"], info["sem_nome"]), (0, 1))
        self.assertIn("porta 3306", info["erro"])

    def test_sem_host_usa_o_localhost_do_proprio_servidor(self):
        from src.olt import unm_nomes
        chamadas = []
        unm_nomes.nomes_das_onus({}, lambda *a: chamadas.append(a[0]) or {})
        self.assertEqual(chamadas, [unm_nomes.HOST_LOCAL])

    def test_cria_usuario_de_leitura_quando_o_padrao_e_recusado(self):
        from src.olt import unm_nomes
        estado = {"criado": False}
        criadas = []

        def buscar(host, usuario, senha, banco, porta):
            if not estado["criado"]:
                raise Exception(1045, "Access denied")
            return {"fhtt1": "SALA 1"}

        def provisionar(usuario, senha, banco, porta):
            criadas.append((usuario, senha))
            estado["criado"] = True

        nomes, erros = unm_nomes.consultar_nomes({"nomes_db_host": "127.0.0.1"}, buscar, provisionar)
        self.assertEqual(nomes, {"fhtt1": "SALA 1"})
        self.assertEqual(erros, [])
        self.assertEqual(criadas, [(unm_nomes.USUARIO_PADRAO, unm_nomes.SENHA_PADRAO)])

    def test_nao_cria_usuario_quando_a_credencial_e_do_cadastro(self):
        from src.olt import unm_nomes

        def buscar(*a):
            raise Exception(1045, "Access denied")

        def provisionar(*a):
            raise AssertionError("nao deveria criar usuario com credencial do cadastro")

        nomes, erros = unm_nomes.consultar_nomes(
            {"nomes_db_host": "127.0.0.1", "nomes_db_usuario": "u", "nomes_db_senha": "s"}, buscar, provisionar)
        self.assertEqual(nomes, {})
        self.assertTrue(erros)

    def test_host_sem_usuario_usa_a_credencial_padrao(self):
        from src.olt import unm_nomes
        chamadas = []
        unm_nomes.nomes_das_onus({"nomes_db_host": "10.0.0.1"}, lambda *a: chamadas.append(a) or {})
        self.assertEqual(chamadas, [("10.0.0.1", unm_nomes.USUARIO_PADRAO, unm_nomes.SENHA_PADRAO, None, 3306)])

    def test_mesma_credencial_padrao_para_todos_os_hosts(self):
        from src.olt import unm_nomes
        chamadas = []
        unm_nomes.nomes_das_onus({"nomes_db_host": "10.0.0.1, 10.0.0.2"}, lambda *a: chamadas.append(a[:3]) or {})
        self.assertEqual(chamadas, [("10.0.0.1", unm_nomes.USUARIO_PADRAO, unm_nomes.SENHA_PADRAO),
                                    ("10.0.0.2", unm_nomes.USUARIO_PADRAO, unm_nomes.SENHA_PADRAO)])

    def test_usuario_e_senha_do_cadastro_tem_prioridade(self):
        from src.olt.unm_nomes import nomes_das_onus
        chamadas = []
        r = nomes_das_onus({"nomes_db_host": " 10.0.0.1 ", "nomes_db_usuario": "u", "nomes_db_senha": "s", "nomes_db_porta": "x"},
                           lambda *a: chamadas.append(a) or {"a": "B"})
        self.assertEqual((r, chamadas), ({"a": "B"}, [("10.0.0.1", "u", "s", None, 3306)]))

    def test_falha_do_banco_nao_derruba_a_coleta(self):
        from src.olt.unm_nomes import nomes_das_onus

        def falha(*a):
            raise OSError("sem rota")

        self.assertEqual(nomes_das_onus({"nomes_db_host": "h", "nomes_db_usuario": "u"}, falha), {})

    def test_coleta_aplica_os_nomes(self):
        eq = {"tipo": "OLT", "name": "UNM", "active": True,
              "config_extra": {"olts": "10.0.0.1", "telnet_usuario": "g", "telnet_senha": "p",
                               "nomes_db_host": "h", "nomes_db_usuario": "u"}}
        r = coletar_status_olts([eq], coletar=lambda *a: {"ip": a[0], "onus": [{"serial": "FHTT1"}]},
                                buscar_nomes=lambda *a: {"fhtt1": "SALA 1"})
        self.assertEqual(r[0]["olts"][0]["onus"][0]["nome"], "SALA 1")


if __name__ == "__main__":
    unittest.main()
