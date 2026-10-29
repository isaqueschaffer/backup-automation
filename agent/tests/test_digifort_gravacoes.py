"""
Testes do calculo de tempo de gravacao do Digifort a partir dos arquivos de indice (.dix).
Os indices sao gerados aqui no formato real (cabecalho de 26 bytes + registros de 69 bytes).
"""
import struct
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.backup.file_manager.manager import _gravacao_digifort
from src.vms import digifort_gravacoes as g

EPOCA = datetime(1899, 12, 30)
EXEMPLOS = Path(r"C:\Users\Helena\OneDrive - Trilan\Downloads\digifort\gravacoes")


def tdatetime(dt: datetime) -> float:
    return (dt - EPOCA).total_seconds() / 86400


def escrever_indice(caminho: Path, instantes, cabecalho=b"DGFDB2" + bytes(20), truncar=0):
    """Grava um .dix com um registro por instante (datetime)."""
    partes = [cabecalho]
    for dt in instantes:
        dias = tdatetime(dt)
        inteiro = float(int(dias))
        partes.append(b"-REG-" + struct.pack("<dd", inteiro, dias - inteiro) + b"0" * 32 + bytes(16))
    dados = b"".join(partes)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(dados[:len(dados) - truncar] if truncar else dados)


def segundos(inicio: datetime, fim: datetime, passo_s=1):
    t = inicio
    while t <= fim:
        yield t
        t += timedelta(seconds=passo_s)


class TestIndice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def total(self, intervalos):
        return sum((fim - ini) * 86400 for ini, fim in intervalos)

    def test_trecho_continuo(self):
        arq = self.dir / "20261028_19.dix"
        escrever_indice(arq, segundos(datetime(2026, 10, 28, 9, 0, 0), datetime(2026, 10, 28, 9, 9, 59)))
        iv = g.intervalos_do_indice(arq, passo=7)
        self.assertEqual(len(iv), 1)
        self.assertAlmostEqual(self.total(iv), 599, delta=0.01)

    def test_interrupcao_maior_que_a_tolerancia_divide_o_trecho(self):
        arq = self.dir / "20261028_19.dix"
        a = list(segundos(datetime(2026, 10, 28, 9, 0, 0), datetime(2026, 10, 28, 9, 4, 59)))
        b = list(segundos(datetime(2026, 10, 28, 9, 6, 30), datetime(2026, 10, 28, 9, 9, 59)))  # 91 s de lacuna
        escrever_indice(arq, a + b)
        for passo in (1, 7, 50, 600):  # amostragem diferente, mesmo resultado
            iv = g.intervalos_do_indice(arq, passo=passo)
            self.assertEqual(len(iv), 2, passo)
            self.assertAlmostEqual(self.total(iv), 299 + 209, delta=0.01)

    def test_lacuna_dentro_da_tolerancia_conta_como_gravado(self):
        arq = self.dir / "20261028_19.dix"
        a = list(segundos(datetime(2026, 10, 28, 9, 0, 0), datetime(2026, 10, 28, 9, 4, 59)))
        b = list(segundos(datetime(2026, 10, 28, 9, 5, 20), datetime(2026, 10, 28, 9, 9, 59)))  # 21 s de lacuna
        escrever_indice(arq, a + b)
        iv = g.intervalos_do_indice(arq, passo=11)
        self.assertEqual(len(iv), 1)
        self.assertAlmostEqual(self.total(iv), 599, delta=0.01)

    def test_quadros_esparsos_sem_lacuna_real(self):
        """Gravacao por movimento (1 quadro a cada 10 s) nao e lacuna."""
        arq = self.dir / "20261028_19.dix"
        escrever_indice(arq, segundos(datetime(2026, 10, 28, 9, 0, 0), datetime(2026, 10, 28, 9, 29, 50), passo_s=10))
        iv = g.intervalos_do_indice(arq, passo=5)
        self.assertEqual(len(iv), 1)

    def test_trecho_que_atravessa_a_meia_noite_e_dividido_por_dia(self):
        arq = self.dir / "20261028_48.dix"
        escrever_indice(arq, segundos(datetime(2026, 10, 28, 23, 55, 0), datetime(2026, 10, 29, 0, 4, 59)))
        por_dia = g.segundos_por_dia(g.intervalos_do_indice(arq, passo=13))
        self.assertAlmostEqual(por_dia[date(2026, 10, 28)], 300, delta=1)
        self.assertAlmostEqual(por_dia[date(2026, 10, 29)], 299, delta=1)

    def test_cabecalho_desconhecido_e_rejeitado(self):
        arq = self.dir / "20261028_19.dix"
        escrever_indice(arq, [datetime(2026, 10, 28, 9, 0, 0)], cabecalho=b"OUTRO!" + bytes(20))
        with self.assertRaises(g.IndiceInvalido):
            g.intervalos_do_indice(arq)

    def test_registro_incompleto_no_fim_e_ignorado(self):
        """O Digifort ainda escreve no arquivo do momento: um registro cortado no fim nao quebra a leitura."""
        arq = self.dir / "20261028_19.dix"
        escrever_indice(arq, segundos(datetime(2026, 10, 28, 9, 0, 0), datetime(2026, 10, 28, 9, 0, 59)), truncar=30)
        iv = g.intervalos_do_indice(arq, passo=4)
        self.assertAlmostEqual(self.total(iv), 58, delta=0.01)

    def test_arquivo_vazio(self):
        arq = self.dir / "20261028_19.dix"
        escrever_indice(arq, [])
        self.assertEqual(g.intervalos_do_indice(arq), [])


class TestPastasECache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        self.hoje = date(2026, 10, 29)

    def tearDown(self):
        self.tmp.cleanup()

    def indice(self, camera, nome, ini, fim):
        escrever_indice(self.raiz / camera / "Indices" / nome, segundos(ini, fim, passo_s=2))

    def test_estrutura_raiz_com_uma_pasta_por_camera(self):
        self.indice("camera 01", "20261029_19.dix", datetime(2026, 10, 29, 9, 0), datetime(2026, 10, 29, 9, 10))
        (self.raiz / "sem_indices" / "Dados").mkdir(parents=True)
        (self.raiz / "arquivo.txt").write_text("x")
        self.assertEqual(list(g.listar_pastas_cameras(self.raiz)), ["camera 01"])

    def test_estrutura_de_pasta_unica_de_camera(self):
        unica = self.raiz / "Cliente"
        escrever_indice(unica / "Indices" / "20261029_19.dix", segundos(datetime(2026, 10, 29, 9, 0), datetime(2026, 10, 29, 9, 1)))
        self.assertEqual(list(g.listar_pastas_cameras(unica)), ["Cliente"])

    def test_pasta_inexistente(self):
        self.assertEqual(g.listar_pastas_cameras(self.raiz / "nao existe"), {})
        self.assertEqual(g.calcular_gravacoes(self.raiz / "nao existe", self.hoje), {})

    def test_calcula_por_dia_e_ignora_fora_da_janela_e_nomes_estranhos(self):
        self.indice("cam", "20261029_19.dix", datetime(2026, 10, 29, 9, 0), datetime(2026, 10, 29, 9, 10))
        self.indice("cam", "20261028_19.dix", datetime(2026, 10, 28, 9, 0), datetime(2026, 10, 28, 9, 5))
        self.indice("cam", "20260101_19.dix", datetime(2026, 1, 1, 9, 0), datetime(2026, 1, 1, 9, 5))   # fora dos 15 dias
        self.indice("cam", "backup_antigo.dix", datetime(2026, 10, 29, 10, 0), datetime(2026, 10, 29, 10, 5))
        res = g.calcular_gravacoes(self.raiz, self.hoje)
        self.assertEqual(sorted(res["cam"]), [date(2026, 10, 28), date(2026, 10, 29)])
        self.assertAlmostEqual(res["cam"][date(2026, 10, 29)], 600, delta=2)

    def test_cache_nao_rele_arquivo_inalterado_e_relê_se_mudou(self):
        self.indice("cam", "20261029_19.dix", datetime(2026, 10, 29, 9, 0), datetime(2026, 10, 29, 9, 10))
        cache = self.raiz / "cache.json"
        original = g.intervalos_do_indice
        with mock.patch.object(g, "intervalos_do_indice", side_effect=original) as leitura:
            g.calcular_gravacoes(self.raiz, self.hoje, cache=cache)
            self.assertEqual(leitura.call_count, 1)
            r2 = g.calcular_gravacoes(self.raiz, self.hoje, cache=cache)
            self.assertEqual(leitura.call_count, 1)   # veio do cache
            self.assertAlmostEqual(r2["cam"][self.hoje], 600, delta=2)
            self.indice("cam", "20261029_19.dix", datetime(2026, 10, 29, 9, 0), datetime(2026, 10, 29, 9, 20))
            r3 = g.calcular_gravacoes(self.raiz, self.hoje, cache=cache)
            self.assertEqual(leitura.call_count, 2)   # o arquivo cresceu
            self.assertAlmostEqual(r3["cam"][self.hoje], 1200, delta=2)

    def test_tempo_esgotado_devolve_camera_incompleta(self):
        self.indice("cam", "20261029_19.dix", datetime(2026, 10, 29, 9, 0), datetime(2026, 10, 29, 9, 10))
        res = g.calcular_gravacoes(self.raiz, self.hoje, limite_s=-1)
        self.assertIsNone(res["cam"])


class TestResumo(unittest.TestCase):
    HOJE = date(2026, 10, 29)
    AGORA = datetime(2026, 10, 29, 12, 0)   # 43200 s decorridos hoje

    def dia(self, dias_atras):
        return self.HOJE - timedelta(days=dias_atras)

    def test_mapa_com_todos_os_estados(self):
        por_dia = {
            self.dia(3): 86400 * 0.95,   # gravou
            self.dia(2): 3600,           # parcial
            self.dia(0): 43200 * 0.95,   # hoje: 95% do que ja passou
        }                                # dia(1) sem nada
        r = g.resumir_camera(por_dia, self.HOJE, self.AGORA)
        self.assertEqual(len(r["mapa"]), 15)
        self.assertEqual(r["mapa"], "·" * 11 + "█▒░█")
        self.assertEqual(r["total_dias"], 3)
        self.assertEqual(r["status_gravacao"], "COM_GRAVACAO")
        self.assertEqual(r["dias_com_gravacao"], [self.dia(3).isoformat(), self.dia(2).isoformat(), self.HOJE.isoformat()])

    def test_hoje_e_medido_contra_o_tempo_decorrido(self):
        # 1 h gravada as 02:00: 50% do que passou = parcial; as 12:00 seria so 8% = parcial tambem
        r = g.resumir_camera({self.HOJE: 3600}, self.HOJE, datetime(2026, 10, 29, 1, 0))
        self.assertTrue(r["mapa"].endswith("█"))
        r = g.resumir_camera({self.HOJE: 3600}, self.HOJE, datetime(2026, 10, 29, 12, 0))
        self.assertTrue(r["mapa"].endswith("▒"))

    def test_sem_nenhuma_gravacao_nao_marca_sem_historico(self):
        r = g.resumir_camera({}, self.HOJE, self.AGORA)
        self.assertEqual(r["mapa"], "░" * 15)
        self.assertEqual(r["total_dias"], 0)
        self.assertEqual(r["status_gravacao"], "SEM_GRAVACAO")

    def test_parou_de_gravar_aparece_como_falha(self):
        por_dia = {self.dia(i): 86400 for i in range(14, 3, -1)}   # gravou ate 4 dias atras
        r = g.resumir_camera(por_dia, self.HOJE, self.AGORA)
        self.assertEqual(r["mapa"], "█" * 11 + "░" * 4)
        self.assertEqual(r["status_gravacao"], "SEM_GRAVACAO")

    def test_casar_pasta_ignora_acento_caixa_e_pontuacao(self):
        pastas = {"camera 01": 1, "Garagem_Norte": 2}
        self.assertEqual(g.casar_pasta("Câmera 01", pastas), "camera 01")
        self.assertEqual(g.casar_pasta("GARAGEM NORTE", pastas), "Garagem_Norte")
        self.assertIsNone(g.casar_pasta("camera 03", pastas))
        self.assertIsNone(g.casar_pasta("", pastas))

    def test_casar_pasta_ignora_espacos_so_se_for_unica(self):
        self.assertEqual(g.casar_pasta("One Drive - Trilan", {"OneDrive - Trilan": 1, "Cliente": 2}), "OneDrive - Trilan")
        self.assertEqual(g.casar_pasta("Camera01", {"camera 01": 1}), "camera 01")
        # duas pastas so diferem pelos espacos: nao arrisca (a exata, se existir, ainda vence)
        ambiguas = {"camera 01": 1, "cam era 01": 2}
        self.assertIsNone(g.casar_pasta("camera0 1", ambiguas))
        self.assertEqual(g.casar_pasta("camera 01", ambiguas), "camera 01")


class TestIntegracaoManager(unittest.TestCase):
    def test_sem_pasta_configurada_mantem_o_comportamento_do_ping(self):
        total, mapa, dias, status, pasta = _gravacao_digifort("Qualquer", True, None, set())
        self.assertEqual((total, mapa, status, pasta), (15, "█" * 15, "COM_GRAVACAO", None))
        total, mapa, dias, status, pasta = _gravacao_digifort("Qualquer", False, None, set())
        self.assertEqual((total, mapa, dias, status), (0, "░" * 15, [], "SEM_GRAVACAO"))

    def test_com_pasta_usa_os_arquivos_e_nao_o_ping(self):
        resumos = {"camera 01": {"total_dias": 2, "mapa": "·" * 13 + "█▒", "dias_com_gravacao": ["a", "b"],
                                 "status_gravacao": "COM_GRAVACAO"}}
        usadas = set()
        total, mapa, dias, status, pasta = _gravacao_digifort("Camera 01", False, resumos, usadas)   # offline no ping
        self.assertEqual((total, status, pasta), (2, "COM_GRAVACAO", "camera 01"))
        self.assertEqual(usadas, {"camera 01"})

    def test_camera_sem_pasta_ou_incompleta_fica_nao_verificado(self):
        resumos = {"camera 01": None}
        # leitura incompleta: a pasta e conhecida; sem pasta com o nome: pasta None
        self.assertEqual(_gravacao_digifort("camera 01", True, resumos, set()), (0, "", [], "NAO_VERIFICADO", "camera 01"))
        self.assertEqual(_gravacao_digifort("camera 99", True, resumos, set()), (0, "", [], "NAO_VERIFICADO", None))
        self.assertEqual(_gravacao_digifort("x", True, {}, set())[3], "NAO_VERIFICADO")


class TestCamerasEmQualquerDesfechoDoBackup(unittest.TestCase):
    """Regressao: com BACKUP_ANTIGO / NAO_ENCONTRADO o agente nao calculava as cameras, e o servidor
    recebia lista vazia e apagava o status de gravacao ('o campo de gravacoes nao aparece')."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        hoje = date.today()
        self.raiz = self.dir / "gravacoes"
        escrever_indice(self.raiz / "Cliente" / "Indices" / f"{hoje:%Y%m%d}_01.dix",
                        segundos(datetime.combine(hoje, datetime.min.time()), datetime.combine(hoje, datetime.min.time()) + timedelta(minutes=10)))
        self.backup = self.dir / "bk"
        self.backup.mkdir()
        # o cache de leituras vai para a pasta temporaria, nao para a pasta do agente
        patcher = mock.patch("src.core.config.DIR_AGENT", self.dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.eq = {
            "name": "DIGIFORT 01", "tipo": "DIGIFORT",
            "config_extra": {"pasta_origem": str(self.backup), "pasta_gravacoes": str(self.raiz)},
            "cameras_config": [{"nome": "Cliente", "ip": "192.168.75.45", "canal": 1},
                               {"nome": "Sem Pasta", "ip": "192.168.75.46", "canal": 2}],
        }

    def tearDown(self):
        self.tmp.cleanup()

    def processar(self):
        from src.backup.file_manager.manager import FileManager
        with mock.patch("src.application.webhook_digifort.ping_camera", return_value=True),              mock.patch("src.application.webhook_digifort.get_status_cameras", return_value={}),              mock.patch("src.application.webhook_digifort.get_detalhes_cameras", return_value=[]):
            return FileManager().process_equipment(self.eq, self.dir / "destino", "UNM2000", None)

    def confere(self, resultado, status_backup):
        self.assertEqual(resultado["status"], status_backup)
        por_nome = {c["nome"]: c for c in resultado["cameras"]}
        cliente = por_nome["Cliente"]
        self.assertEqual(cliente["status_comunicacao"], "ONLINE")
        self.assertEqual(cliente["status_gravacao"], "COM_GRAVACAO")
        self.assertEqual(cliente["pasta_gravacao"], "Cliente")
        self.assertEqual(cliente["total_dias"], 1)
        self.assertEqual(por_nome["Sem Pasta"]["status_gravacao"], "NAO_VERIFICADO")
        self.assertIsNone(por_nome["Sem Pasta"]["pasta_gravacao"])

    def test_backup_antigo(self):
        (self.backup / "20200101").mkdir()
        (self.backup / "20200101" / "dados.bak").write_bytes(b"x" * 10)
        self.confere(self.processar(), "BACKUP_ANTIGO")

    def test_backup_nao_encontrado(self):
        self.confere(self.processar(), "BACKUP_NAO_ENCONTRADO")

    def test_outros_tipos_nao_ganham_cameras(self):
        from src.backup.file_manager.manager import FileManager
        eq = {"name": "UNM", "tipo": "OLT", "config_extra": {"pasta_origem": str(self.backup)}}
        resultado = FileManager().process_equipment(eq, self.dir / "d2", "UNM2000", None)
        self.assertIsNone(resultado["cameras"])


@unittest.skipUnless(EXEMPLOS.is_dir(), "arquivos de exemplo do Digifort nao encontrados nesta maquina")
class TestArquivosReais(unittest.TestCase):
    def test_exemplos_reais(self):
        res = g.calcular_gravacoes(EXEMPLOS, date(2026, 10, 29))
        self.assertEqual(sorted(res), ["camera 01", "camera 02"])
        self.assertAlmostEqual(res["camera 02"][date(2026, 10, 27)] / 60, 73.0, delta=0.1)
        self.assertAlmostEqual(res["camera 02"][date(2026, 10, 28)] / 60, 148.9, delta=0.1)
        self.assertAlmostEqual(res["camera 01"][date(2026, 10, 29)] / 60, 1.6, delta=0.1)


if __name__ == "__main__":
    unittest.main()
