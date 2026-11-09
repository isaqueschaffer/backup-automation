"""Interpretacao e juncao das paginas de status/diagnostico optico das ONUs da OLT VSOL
(amostras de uma OLT real)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.application.status_olt import coletar_status_olts
from src.olt import vsol_status as v

PAGINA_STATUS = """<html><body><form name=form method=post action="onustatusinfo.html">
<table border="1" cellpadding="4" cellspacing="0">
<tr><td class='hd'>ONU ID</td><td><font data-i18N-text='Status'>Status</font></td><td><font data-i18N-text='MACAddress'>MAC Address</font></td><td><font data-i18N-text='Description'>Description</font></td></tr>
<tr><td class='hd'>EPON0/1:1</td><td><font color=#008040><font data-i18N-text='Online'>Online</font></font></td><td>00:6D:61:AD:B7:99</td><td>PERIMETRO_04</td></tr>
<tr><td class='hd'>EPON0/1:6</td><td><font color=#ff0000><font data-i18N-text='Offline'>Offline</font></font></td><td>00:6D:61:AD:B7:36</td><td>PERIMETRO_06</td></tr>
<tr><td class='hd'>EPON0/1:15</td><td><font color=#ff0000><font data-i18N-text='Offline'>Offline</font></font></td><td>00:6D:61:B0:19:D0</td><td></td></tr>
</table></form></body></html>"""

PAGINA_OPM = """<html><body><form name=form method=post action="onuopmdiag.html">
<table border="1" cellpadding="4" cellspacing="0">
<tr><td class='hd'>ONU ID</td><td class='hd'>MAC</td><td class='hd'>Description</td><td class='hd'>Distance</td><td class='hd'>Temperature</td><td class='hd'>SupplyVoltage</td><td class='hd'>TXBiasCurrent</td><td class='hd'>TXPower</td><td class='hd'>RXPower</td></tr>
<tr><td class='hd'>EPON0/1:1</td><td>00:6D:61:AD:B7:99</td><td>PERIMETRO_04</td><td>141</td><td>33.75</td><td>3.35</td><td>14.25</td><td>2.62</td><td>-16.35</td></tr>
</table></form></body></html>"""


class TestParseOnuStatus(unittest.TestCase):
    def test_le_onus_online_e_offline(self):
        onus = v.parse_onu_status(PAGINA_STATUS)
        self.assertEqual(len(onus), 3)
        self.assertEqual([o["estado"] for o in onus], ["ONLINE", "OFFLINE", "OFFLINE"])

    def test_campos_da_primeira_onu(self):
        onu = v.parse_onu_status(PAGINA_STATUS)[0]
        self.assertEqual(onu["indice"], "EPON0/1:1")
        self.assertEqual((onu["slot"], onu["pon"], onu["onu"]), (0, 1, 1))
        self.assertEqual(onu["mac"], "00:6D:61:AD:B7:99")
        self.assertEqual(onu["nome"], "PERIMETRO_04")

    def test_offline_sem_descricao(self):
        onu = v.parse_onu_status(PAGINA_STATUS)[2]
        self.assertIsNone(onu["nome"])

    def test_texto_vazio_nao_quebra(self):
        self.assertEqual(v.parse_onu_status(""), [])
        self.assertEqual(v.parse_onu_status(None), [])


class TestParseOnuOpm(unittest.TestCase):
    def test_so_tem_entrada_para_quem_respondeu(self):
        opticos = v.parse_onu_opm(PAGINA_OPM)
        self.assertEqual(list(opticos.keys()), ["EPON0/1:1"])
        self.assertEqual(opticos["EPON0/1:1"]["temperatura_onu"], 33.75)
        self.assertEqual(opticos["EPON0/1:1"]["sinal_onu_dbm"], -16.35)

    def test_texto_vazio_nao_quebra(self):
        self.assertEqual(v.parse_onu_opm(""), {})
        self.assertEqual(v.parse_onu_opm(None), {})


class TestColetarVsol(unittest.TestCase):
    def test_junta_status_e_opm_por_indice(self):
        equipamento = {
            "name": "OLT_VSOL_01", "tipo": "OLT", "active": True,
            "fabricante": "VSOL", "ip": "192.168.9.100",
            "username": "admin", "password": "admin",
        }
        with patch.object(v, "_fazer_login", return_value=True), \
             patch.object(v, "_pedir", side_effect=[PAGINA_STATUS, PAGINA_OPM]):
            resultado = v.coletar_vsol(equipamento)

        self.assertNotIn("erro", resultado)
        onus = {o["indice"]: o for o in resultado["onus"]}
        self.assertEqual(len(onus), 3)
        # Online e com leitura optica.
        self.assertEqual(onus["EPON0/1:1"]["estado"], "ONLINE")
        self.assertEqual(onus["EPON0/1:1"]["temperatura_onu"], 33.75)
        self.assertEqual(onus["EPON0/1:1"]["sinal_onu_dbm"], -16.35)
        # Offline: sem leitura optica, mas com MAC/descricao do status.
        self.assertEqual(onus["EPON0/1:6"]["estado"], "OFFLINE")
        self.assertNotIn("temperatura_onu", onus["EPON0/1:6"])
        self.assertEqual(onus["EPON0/1:6"]["mac"], "00:6D:61:AD:B7:36")
        self.assertEqual(resultado["totais"]["total"], 3)
        self.assertEqual(resultado["totais"]["online"], 1)
        self.assertEqual(resultado["totais"]["offline"], 2)

    def test_falha_de_login_nao_levanta_erro(self):
        equipamento = {"name": "OLT_VSOL_01", "ip": "192.168.9.100", "username": "admin", "password": "errada"}
        with patch.object(v, "_fazer_login", return_value=False):
            resultado = v.coletar_vsol(equipamento)
        self.assertIn("erro", resultado)

    def test_sem_credenciais_nao_levanta_erro(self):
        resultado = v.coletar_vsol({"name": "OLT_VSOL_01", "ip": "192.168.9.100"})
        self.assertIn("erro", resultado)


class TestColetarStatusOltsVsol(unittest.TestCase):
    def test_usa_coletor_vsol_injetado_para_fabricante_vsol(self):
        equipamento = {
            "name": "OLT_VSOL_01", "tipo": "OLT", "active": True,
            "fabricante": "VSOL", "ip": "192.168.9.100",
            "username": "admin", "password": "admin",
        }
        chamadas = []

        def coletar_vsol_fake(eq):
            chamadas.append(eq["name"])
            return {"ip": eq["ip"], "onus": []}

        resultado = coletar_status_olts([equipamento], coletar_vsol=coletar_vsol_fake)

        self.assertEqual(chamadas, ["OLT_VSOL_01"])
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["nome"], "OLT_VSOL_01")
        self.assertEqual(resultado[0]["olts"][0]["ip"], "192.168.9.100")

    def test_nao_chama_vsol_para_unm2000(self):
        equipamento = {
            "name": "OLT_UNM", "tipo": "OLT", "active": True,
            "fabricante": "UNM2000", "config_extra": {"olts": "", "telnet_usuario": ""},
        }
        chamado = []
        resultado = coletar_status_olts([equipamento], coletar_vsol=lambda eq: chamado.append(eq))
        self.assertEqual(chamado, [])
        self.assertEqual(resultado, [])


if __name__ == "__main__":
    unittest.main()
