"""Antenas pelo MikroTik: leitura (`print terse`), MACs com tolerância de 32, status e descoberta automática."""
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.application.status_antena import coletar_antena, coletar_status_antenas
from src.mikrotik.antenas import (
    ErroMikrotik, _COMANDOS, avaliar_antena, consolidar_dispositivos, descobrir_antenas, interpretar_terse, mac_int,
    macs_proximos, marca_do_texto, normalizar_mac, prefixos_validos,
)

ARP = """ 0 D  address=192.168.75.12 mac-address=52:AE:1B:BE:2C:61 interface=bridge_cftv published=no status=failed vrf=main

 1 DC address=192.168.75.123 mac-address=9C:2B:A6:71:6A:D0 interface=bridge_cftv published=no status=reachable vrf=main

 2 DC address=192.168.75.14 mac-address=E0:CA:3C:AC:53:2D interface=bridge_cftv published=no status=stale vrf=main
"""
LEASES = """ 0   comment=CAMERA TERRENO INT address=192.168.75.14 mac-address=E0:CA:3C:AC:53:2D status=bound last-seen=14m59s

25 D address=192.168.75.123 mac-address=9C:2B:A6:71:6A:D0 host-name=TESTE status=bound last-seen=1m29s
"""
HOSTS = """ 35 D   mac-address=9C:2B:A6:71:6A:D0 interface=vlan_cftv02 bridge=bridge_cftv on-interface=vlan_cftv02
"""
VIZINHOS = """0  interface=ether2,bridge_juan address=186.225.133.111 mac-address=78:45:58:F3:FE:43 identity=DreamMachinePro platform=Debian system-caps=bridge,wlan-ap,router,station-only discovered-by=lldp
1  interface=vlan_cftv02,bridge_cftv address=192.168.75.54 mac-address=48:A9:8A:BC:AA:F2 identity=RB4011iGS platform=MikroTik system-caps="" discovered-by=mndp
"""


def leitura(arp=ARP, leases=LEASES, hosts=HOSTS, vizinhos=VIZINHOS):
    return {
        "identity": "MikroTik-TRLN-RP",
        "arp": interpretar_terse(arp, _COMANDOS["arp"][1]),
        "lease": interpretar_terse(leases, _COMANDOS["lease"][1]),
        "host": interpretar_terse(hosts, _COMANDOS["host"][1]),
        "neighbor": interpretar_terse(vizinhos, _COMANDOS["neighbor"][1]),
    }


class TestMac(unittest.TestCase):
    def test_normaliza_formatos(self):
        self.assertEqual(normalizar_mac("9c2b.a671.6acf"), "9C:2B:A6:71:6A:CF")
        self.assertEqual(normalizar_mac("9c-2b-a6-71-6a-cf"), "9C:2B:A6:71:6A:CF")
        self.assertEqual(normalizar_mac("9C2BA6716ACF"), "9C:2B:A6:71:6A:CF")
        self.assertIsNone(normalizar_mac("9c2b.a671"))
        self.assertIsNone(normalizar_mac("zz:2b:a6:71:6a:cf"))
        self.assertIsNone(normalizar_mac(None))

    def test_tolerancia_de_32(self):
        base = "9C:2B:A6:71:6A:CF"
        self.assertTrue(macs_proximos(base, "9C:2B:A6:71:6A:D0"))          # +1
        self.assertTrue(macs_proximos(base, "9C:2B:A6:71:6A:EF"))          # +32 exatos
        self.assertFalse(macs_proximos(base, "9C:2B:A6:71:6A:F0"))         # +33
        self.assertTrue(macs_proximos(base, "9C:2B:A6:71:6A:AF"))          # -32 exatos
        self.assertTrue(macs_proximos("9C:2B:A6:71:6B:00", "9C:2B:A6:71:6A:EF"))  # atravessa o byte
        self.assertFalse(macs_proximos(base, "9D:2B:A6:71:6A:D0"))         # outro fabricante
        self.assertEqual(mac_int("00:00:00:00:01:00"), 256)

    def test_prefixos(self):
        self.assertEqual(prefixos_validos("9c:2b:a6, 54-16-51\n9C2BA6, xx, 1234"), ["9C:2B:A6", "54:16:51"])
        self.assertEqual(prefixos_validos(None), [])


class TestLeitura(unittest.TestCase):
    def test_terse_com_comentario_de_varias_palavras(self):
        itens = interpretar_terse(LEASES, _COMANDOS["lease"][1])
        self.assertEqual(itens[0]["comment"], "CAMERA TERRENO INT")
        self.assertEqual(itens[0]["address"], "192.168.75.14")
        self.assertEqual(itens[0]["mac-address"], "E0:CA:3C:AC:53:2D")
        self.assertEqual(itens[1]["host-name"], "TESTE")
        self.assertNotIn("comment", itens[1])

    def test_terse_separa_mac_address_de_address(self):
        item = interpretar_terse(ARP, _COMANDOS["arp"][1])[1]
        self.assertEqual(item["address"], "192.168.75.123")
        self.assertEqual(item["mac-address"], "9C:2B:A6:71:6A:D0")
        self.assertEqual(item["status"], "reachable")

    def test_ignora_linhas_sem_chave(self):
        self.assertEqual(interpretar_terse("\n\nFlags: X - DISABLED\n", ["address"]), [])

    def test_consolida_por_mac(self):
        disp = consolidar_dispositivos(leitura())
        d = disp["9C:2B:A6:71:6A:D0"]
        self.assertEqual(d["ip"], "192.168.75.123")
        self.assertEqual(d["hostname"], "TESTE")
        self.assertEqual(sorted(d["fontes"]), ["arp", "bridge", "dhcp"])
        self.assertEqual(d["arp_status"], "reachable")
        self.assertEqual(disp["78:45:58:F3:FE:43"]["capacidades"], "bridge,wlan-ap,router,station-only")


class TestStatus(unittest.TestCase):
    ANTENA = {"nome": "Antena Ruijie", "mac": "9c2b.a671.6acf"}

    def test_online_com_mac_vizinho_e_ping(self):
        r = avaliar_antena(self.ANTENA, consolidar_dispositivos(leitura()), ping=lambda ip: 3)
        self.assertEqual((r["status"], r["ip"], r["mac_visto"], r["ping_ms"]), ("ONLINE", "192.168.75.123", "9C:2B:A6:71:6A:D0", 3))
        self.assertEqual(r["hostname"], "TESTE")

    def test_sem_ping_mas_arp_reachable_continua_online(self):
        r = avaliar_antena(self.ANTENA, consolidar_dispositivos(leitura()), ping=lambda ip: None)
        self.assertEqual(r["status"], "ONLINE")

    def test_offline_quando_ip_conhecido_nao_responde(self):
        arp = ARP.replace("status=reachable", "status=stale")
        r = avaliar_antena(self.ANTENA, consolidar_dispositivos(leitura(arp=arp)), ping=lambda ip: None)
        self.assertEqual((r["status"], r["ip"]), ("OFFLINE", "192.168.75.123"))

    def test_sem_registro_quando_o_mikrotik_nao_ve_o_mac(self):
        r = avaliar_antena({"nome": "Outra", "mac": "AA:BB:CC:00:00:01"}, consolidar_dispositivos(leitura()), ping=lambda ip: 1)
        self.assertEqual((r["status"], r["ip"], r["mac_visto"]), ("SEM_REGISTRO", "", ""))

    def test_ip_do_cadastro_e_usado_quando_o_mac_sumiu(self):
        r = avaliar_antena({"nome": "X", "mac": "AA:BB:CC:00:00:01", "ip": "192.168.75.200"},
                           consolidar_dispositivos(leitura()), ping=lambda ip: 2 if ip == "192.168.75.200" else None)
        self.assertEqual((r["status"], r["ip"]), ("ONLINE", "192.168.75.200"))

    def test_mac_invalido_vira_erro_sem_derrubar_a_coleta(self):
        r = avaliar_antena({"nome": "Ruim", "mac": "123"}, {}, ping=lambda ip: 1)
        self.assertEqual(r["status"], "ERRO")

    def test_notificar_padrao_e_ligado(self):
        self.assertTrue(avaliar_antena(self.ANTENA, {}, ping=lambda ip: None)["notificar"])
        self.assertFalse(avaliar_antena({**self.ANTENA, "notificar": False}, {}, ping=lambda ip: None)["notificar"])


class TestDescoberta(unittest.TestCase):
    def test_acha_por_prefixo_e_por_wlan_ap(self):
        achadas = descobrir_antenas(consolidar_dispositivos(leitura()), [], ["9C:2B:A6"])
        macs = {a["mac"] for a in achadas}
        self.assertEqual(macs, {"9C:2B:A6:71:6A:D0", "78:45:58:F3:FE:43"})
        ruijie = next(a for a in achadas if a["mac"] == "9C:2B:A6:71:6A:D0")
        self.assertEqual((ruijie["ip"], ruijie["hostname"]), ("192.168.75.123", "TESTE"))

    def test_sem_prefixo_so_os_vizinhos_ap(self):
        achadas = descobrir_antenas(consolidar_dispositivos(leitura()), [], [])
        self.assertEqual([a["mac"] for a in achadas], ["78:45:58:F3:FE:43"])

    def test_antena_ja_cadastrada_nao_volta_na_busca(self):
        achadas = descobrir_antenas(consolidar_dispositivos(leitura()), [{"mac": "9C:2B:A6:71:6A:CF"}], ["9C:2B:A6"])
        self.assertNotIn("9C:2B:A6:71:6A:D0", {a["mac"] for a in achadas})

    def test_macs_proximos_viram_uma_antena_so(self):
        arp = ARP + " 3 DC address=192.168.75.130 mac-address=9C:2B:A6:71:6A:D2 interface=bridge_cftv status=stale\n"
        hosts = HOSTS + " 36 D   mac-address=9C:2B:A6:71:6A:D1 on-interface=vlan_cftv02 bridge=bridge_cftv\n"
        achadas = descobrir_antenas(consolidar_dispositivos(leitura(arp=arp, hosts=hosts)), [], ["9C:2B:A6"])
        grupo = [a for a in achadas if a["mac"].startswith("9C:2B:A6")]
        self.assertEqual(len(grupo), 1)
        self.assertEqual(sorted(grupo[0]["macs"]), ["9C:2B:A6:71:6A:D0", "9C:2B:A6:71:6A:D1", "9C:2B:A6:71:6A:D2"])


class TestMarca(unittest.TestCase):
    def test_reconhece_marca_pelo_que_o_vizinho_anuncia(self):
        self.assertEqual(marca_do_texto("RG-RAP2260", "Ruijie Networks AP"), "Ruijie")
        self.assertEqual(marca_do_texto("ArubaOS AP-515"), "Aruba")
        self.assertEqual(marca_do_texto("XIXIAN-AP01"), "Xixian")
        self.assertEqual(marca_do_texto("DreamMachinePro", "Debian"), "")  # outras marcas ficam sem detecção por enquanto
        self.assertEqual(marca_do_texto("RB4011iGS", "MikroTik"), "")
        self.assertEqual(marca_do_texto("TESTE", "", ""), "")
        self.assertEqual(marca_do_texto(None, None), "")

    VIZINHO_REYEE = ("0 interface=ether2 address=192.168.75.50 mac-address=9C:2B:A6:71:6A:D0 identity=Reyee-AP "
                     "platform=Linux system-caps=wlan-ap discovered-by=lldp")

    def test_marca_detectada_pelo_vizinho_quando_nao_foi_digitada(self):
        viz = self.VIZINHO_REYEE
        disp = consolidar_dispositivos(leitura(vizinhos=viz))
        r = avaliar_antena({"nome": "A", "mac": "9C:2B:A6:71:6A:CF"}, disp, ping=lambda ip: 1)
        self.assertEqual((r["marca"], r["marca_detectada"]), ("Ruijie", "Ruijie"))

    def test_marca_digitada_vale_sobre_a_detectada(self):
        viz = self.VIZINHO_REYEE
        r = avaliar_antena({"nome": "A", "mac": "9C:2B:A6:71:6A:CF", "marca": "Intelbras"}, consolidar_dispositivos(leitura(vizinhos=viz)), ping=lambda ip: 1)
        self.assertEqual((r["marca"], r["marca_detectada"]), ("Intelbras", "Ruijie"))

    def test_sem_lldp_a_marca_fica_vazia_ate_o_usuario_informar(self):
        r = avaliar_antena(TestStatus.ANTENA, consolidar_dispositivos(leitura()), ping=lambda ip: 1)
        self.assertEqual((r["marca"], r["marca_detectada"]), ("", ""))
        r2 = avaliar_antena({**TestStatus.ANTENA, "marca": "Ruijie"}, consolidar_dispositivos(leitura()), ping=lambda ip: 1)
        self.assertEqual((r2["marca"], r2["marca_detectada"]), ("Ruijie", ""))

    def test_descoberta_traz_a_marca_quando_o_vizinho_a_anuncia(self):
        achadas = descobrir_antenas(consolidar_dispositivos(leitura()), [], [])
        self.assertEqual(achadas[0]["marca"], "")  # o UniFi não está entre as marcas (Ruijie, Aruba, Xixian)
        sem_lldp = descobrir_antenas(consolidar_dispositivos(leitura()), [], ["9C:2B:A6"])
        self.assertEqual(next(a for a in sem_lldp if a["mac"].startswith("9C:2B:A6"))["marca"], "")


class TestColeta(unittest.TestCase):
    EQ = {"tipo": "ANTENA", "name": "Antenas Sede", "ip": "192.168.75.1", "username": "trilan", "password": "segredo123",
          "active": True, "config_extra": {"porta_ssh": 22, "prefixos_mac": "9C:2B:A6",
                                             "antenas": [{"nome": "Ruijie sala", "mac": "9C:2B:A6:71:6A:CF"}]}}

    def test_coleta_completa(self):
        chamado = []
        res = coletar_antena(self.EQ, ler=lambda *a: chamado.append(a) or leitura(), ping=lambda ip: 2)
        self.assertEqual(chamado, [("192.168.75.1", "trilan", "segredo123", 22)])
        self.assertEqual(res["nome"], "Antenas Sede")
        self.assertEqual(res["antenas"][0]["status"], "ONLINE")
        self.assertEqual(res["mikrotik"]["identidade"], "MikroTik-TRLN-RP")
        self.assertEqual([d["mac"] for d in res["descobertas"]], ["78:45:58:F3:FE:43"])

    def test_erro_de_ssh_nao_vaza_a_senha_e_nao_traz_antenas(self):
        def falha(*a):
            raise ErroMikrotik("falhou com segredo123 dentro")
        res = coletar_antena(self.EQ, ler=falha)
        self.assertNotIn("segredo123", res["erro"])
        self.assertEqual((res["antenas"], res["descobertas"]), ([], []))

    def test_sem_credenciais_nem_tenta_conectar(self):
        res = coletar_antena({**self.EQ, "password": ""}, ler=lambda *a: self.fail("não deveria conectar"))
        self.assertIn("não informados", res["erro"])

    def test_so_equipamentos_antena_ativos(self):
        eqs = [self.EQ, {**self.EQ, "name": "pausada", "active": False}, {**self.EQ, "name": "olt", "tipo": "OLT"}]
        lista = coletar_status_antenas(eqs, ler=lambda *a: leitura(), ping=lambda ip: 1)
        self.assertEqual([i["nome"] for i in lista], ["Antenas Sede"])


if __name__ == "__main__":
    unittest.main()
