"""Backup em túnel (agente do Mikrotik): o ZIP global (AES) com um backup.zip por equipamento é montado em fluxo a
partir do SMB (aqui, um SMB falso em memória) e entregue em pedaços, sem criar nenhum arquivo; tamanho divergente ou
falha de leitura derrubam o envio; o orquestrador refaz o ZIP sem o equipamento que falhou e corrige o relatório."""
import io
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pyzipper
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backup import tunel  # noqa: E402

SENHA = "senha-da-maquina"


class SmbFalso:
    """Imita o que o tunel usa de smbclient: stat, open_file e scandir."""

    def __init__(self, arquivos: dict, extra_tamanho: int = 0, quebra_em: str = ""):
        self.arquivos = arquivos
        self.extra = extra_tamanho
        self.quebra_em = quebra_em

    def stat(self, caminho):
        return SimpleNamespace(st_size=len(self.arquivos[caminho]) + self.extra)

    def open_file(self, caminho, mode="rb"):
        if self.quebra_em and self.quebra_em in caminho:
            raise OSError("conexão SMB caiu")
        return io.BytesIO(self.arquivos[caminho])

    def scandir(self, caminho):
        prefixo = caminho.rstrip("\\") + "\\"
        vistos = {}
        for k in self.arquivos:
            if k.startswith(prefixo):
                nome, _, resto = k[len(prefixo):].partition("\\")
                vistos[nome] = bool(resto)
        return [SimpleNamespace(name=n, is_dir=(lambda d=d: d)) for n, d in vistos.items()]


def _origem(remoto, tipo="UNM2000"):
    return SimpleNamespace(remote_path=remoto, path=Path(remoto), is_smb=True, file_type=tipo)


def _pronto(nome, itens, tipo="OLT"):
    return {"nome": nome, "tipo": tipo, "status": "OK", "pasta_zip": f"{tipo}/backup_{tipo.lower()}_{nome}",
            "arquivos_origem": itens}


def _coletar(prontos, smb, senha=SENHA):
    """Roda o montador e junta os pedaços como o corpo do PUT faria; devolve (bytes, erro_do_montador)."""
    fila = tunel.FilaSaida()
    falha = {}
    t = threading.Thread(target=tunel._produtor, args=(fila, prontos, senha, falha), daemon=True)
    with mock.patch.object(tunel, "_smbclient", return_value=smb):
        t.start()
        corpo = bytearray()
        try:
            for pedaco in fila.pedacos():
                corpo += pedaco
            erro = None
        except BaseException as e:
            erro = e
        t.join(10)
    return bytes(corpo), erro


class TestTunel(unittest.TestCase):
    def test_zip_montado_em_fluxo_abre_com_a_senha_e_confere_o_conteudo(self):
        dados = {"\\\\h\\s\\unm.zip": os.urandom(3 * 1024 * 1024 + 17),
                 "\\\\h\\s\\dig\\a.txt": b"aaa" * 1000,
                 "\\\\h\\s\\dig\\sub\\b.txt": b"bbb"}
        smb = SmbFalso(dados)
        prontos = [
            _pronto("UNM_A", [(_origem("\\\\h\\s\\unm.zip"), "OLT_UNM2000_UNM_A_20261118.zip")]),
            _pronto("DIG_B", [(_origem("\\\\h\\s\\dig", "DIGIFORT_DIR"), "dig")], tipo="DIGIFORT"),
        ]
        with tempfile.TemporaryDirectory() as d, mock.patch.dict("os.environ", {"TMPDIR": d, "TEMP": d, "TMP": d}):
            cwd = os.getcwd()
            os.chdir(d)
            try:
                corpo, erro = _coletar(prontos, smb)
                self.assertEqual(os.listdir(d), [])      # nada foi gravado em disco
            finally:
                os.chdir(cwd)
        self.assertIsNone(erro)
        with pyzipper.AESZipFile(io.BytesIO(corpo)) as ext:
            ext.setpassword(SENHA.encode())
            self.assertIsNone(ext.testzip())
            self.assertEqual(sorted(i.filename for i in ext.infolist()),
                             ["DIGIFORT/backup_digifort_DIG_B/backup.zip", "OLT/backup_olt_UNM_A/backup.zip"])
            interno_a = ext.read("OLT/backup_olt_UNM_A/backup.zip")
            interno_b = ext.read("DIGIFORT/backup_digifort_DIG_B/backup.zip")
        with zipfile.ZipFile(io.BytesIO(interno_a)) as z:
            self.assertEqual(z.read("OLT_UNM2000_UNM_A_20261118.zip"), dados["\\\\h\\s\\unm.zip"])
        with zipfile.ZipFile(io.BytesIO(interno_b)) as z:
            self.assertEqual(sorted(z.namelist()), ["dig/a.txt", "dig/sub/b.txt"])
            self.assertEqual(z.read("dig/sub/b.txt"), b"bbb")

    def test_sem_senha_gera_zip_comum(self):
        smb = SmbFalso({"\\\\h\\s\\x.zip": b"conteudo"})
        corpo, erro = _coletar([_pronto("A", [(_origem("\\\\h\\s\\x.zip"), "x.zip")])], smb, senha=None)
        self.assertIsNone(erro)
        with zipfile.ZipFile(io.BytesIO(corpo)) as ext:
            self.assertIsNone(ext.testzip())
            self.assertEqual(ext.namelist(), ["OLT/backup_olt_A/backup.zip"])

    def test_tamanho_divergente_derruba_o_fluxo_e_aponta_o_equipamento(self):
        smb = SmbFalso({"\\\\h\\s\\x.zip": b"abc"}, extra_tamanho=5)   # o cliente diz 5 bytes a mais
        _, erro = _coletar([_pronto("UNM_A", [(_origem("\\\\h\\s\\x.zip"), "x.zip")])], smb)
        self.assertIsInstance(erro, tunel._Divergente)
        self.assertEqual(erro.item, "UNM_A")
        self.assertEqual(tunel._status_da_falha(erro), "CORROMPIDO")

    def test_falha_de_leitura_smb_derruba_o_fluxo(self):
        smb = SmbFalso({"\\\\h\\s\\x.zip": b"abc"}, quebra_em="x.zip")
        _, erro = _coletar([_pronto("UNM_A", [(_origem("\\\\h\\s\\x.zip"), "x.zip")])], smb)
        self.assertIsInstance(erro, tunel._FalhaLeitura)
        self.assertEqual(tunel._status_da_falha(erro), "ERRO")

    def test_origem_local_nao_existe_no_mikrotik(self):
        local = SimpleNamespace(remote_path=None, path=Path("/pasta/local"), is_smb=False, file_type="UNM2000")
        _, erro = _coletar([_pronto("A", [(local, "x.zip")])], SmbFalso({}))
        self.assertIsInstance(erro, tunel._FalhaLeitura)

    def test_envio_lento_nao_acumula_na_memoria(self):
        """O montador bloqueia quando a fila enche: com 40 MB e um consumidor lento, a fila nunca passa do limite."""
        dados = {"\\\\h\\s\\grande.bin": os.urandom(40 * 1024 * 1024)}
        fila = tunel.FilaSaida()
        maior = 0
        falha = {}
        with mock.patch.object(tunel, "_smbclient", return_value=SmbFalso(dados)):
            t = threading.Thread(target=tunel._produtor, daemon=True, args=(
                fila, [_pronto("G", [(_origem("\\\\h\\s\\grande.bin"), "grande.bin")])], SENHA, falha))
            t.start()
            total = 0
            for pedaco in fila.pedacos():
                maior = max(maior, fila._fila.qsize())
                total += len(pedaco)
            t.join(10)
        self.assertIsNone(falha.get("erro"))
        self.assertGreater(total, 40 * 1024 * 1024)
        self.assertLessEqual(maior, tunel.FILA_PEDACOS)

    def test_envio_que_falha_na_rede_libera_o_montador(self):
        """Se o servidor/rede falhar, o montador não fica preso para sempre numa fila cheia."""
        dados = {"\\\\h\\s\\grande.bin": os.urandom(20 * 1024 * 1024)}

        def upload_que_desiste(conf, backup_id, nome, pedacos, device_type="MIXED"):
            next(pedacos)           # lê um pedaço e desiste (conexão caiu)
            return False

        with mock.patch.object(tunel, "_smbclient", return_value=SmbFalso(dados)), \
                mock.patch("src.application.api_client.upload_zip_stream", side_effect=upload_que_desiste):
            ok, erro = tunel.enviar_em_tunel({}, "bid", "z.zip",
                                             [_pronto("G", [(_origem("\\\\h\\s\\grande.bin"), "grande.bin")])], SENHA)
        self.assertFalse(ok)
        self.assertIsNone(erro)     # falha de rede, não de leitura
        self.assertEqual([t.name for t in threading.enumerate() if t.name == "tunel-zip"], [])


class TestOrquestracao(unittest.TestCase):
    def _rodar(self, resultados, envios):
        cfg = {"client_name": "Maquina MK", "zip_password": SENHA, "equipamentos": [{"name": "x", "tipo": "OLT"}]}
        corrigidos = []
        with mock.patch("src.core.config.load_conf", return_value={"client_id": "c", "api_key": "k"}), \
                mock.patch("src.application.api_client.fetch_server_config", return_value=cfg), \
                mock.patch.object(tunel, "preparar_equipamentos", return_value=resultados), \
                mock.patch("src.application.api_client.post_report", return_value="bid") as relatorio, \
                mock.patch("src.application.api_client.corrigir_resultado",
                           side_effect=lambda conf, bid, nome, st: corrigidos.append((nome, st)) or True), \
                mock.patch.object(tunel, "enviar_em_tunel", side_effect=envios) as envio:
            tunel.executar_backup_tunel("manual_dashboard")
        return relatorio, envio, corrigidos

    @staticmethod
    def _res(nome, status="PRONTO"):
        return {"nome": nome, "tipo": "OLT", "status": status, "cameras": None, "pasta_zip": f"OLT/{nome}",
                "arquivos_origem": []}

    def test_envio_ok_manda_so_os_prontos_e_nao_corrige_nada(self):
        res = [self._res("A"), self._res("B", "BACKUP_ANTIGO")]
        relatorio, envio, corrigidos = self._rodar(res, [(True, None)])
        enviados = envio.call_args.args[3]
        self.assertEqual([r["nome"] for r in enviados], ["A"])
        self.assertEqual(relatorio.call_args.args[3][0]["status"], "OK")   # provisório
        self.assertEqual(corrigidos, [])

    def test_equipamento_que_falha_sai_do_zip_e_o_relatorio_e_corrigido(self):
        res = [self._res("A"), self._res("B")]
        envios = [(False, tunel._Divergente("B", "tamanho")), (True, None)]
        _, envio, corrigidos = self._rodar(res, envios)
        self.assertEqual(corrigidos, [("B", "CORROMPIDO")])
        self.assertEqual([r["nome"] for r in envio.call_args_list[0].args[3]], ["A", "B"])
        self.assertEqual([r["nome"] for r in envio.call_args_list[1].args[3]], ["A"])

    def test_rede_falha_duas_vezes_marca_tudo_como_erro(self):
        res = [self._res("A"), self._res("B")]
        _, envio, corrigidos = self._rodar(res, [(False, None), (False, None)])
        self.assertEqual(envio.call_count, tunel.TENTATIVAS_ENVIO)
        self.assertEqual(sorted(corrigidos), [("A", "ERRO"), ("B", "ERRO")])

    def test_sem_nenhum_pronto_nao_transmite(self):
        _, envio, _ = self._rodar([self._res("A", "BACKUP_ANTIGO")], [])
        envio.assert_not_called()


if __name__ == "__main__":
    unittest.main()
