"""Túnel do Mikrotik com origem SFTP e memória: conversão de caminho, somente leitura/raiz, TOFU da chave do host,
chave privada, leitura em blocos, ZIP em fluxo (AES) com origens SFTP + memória + HTTP, planilhas e nenhum arquivo
criado fora do known_hosts. Usa um servidor SSH/SFTP de verdade em 127.0.0.1 (paramiko), com pasta temporária só
de teste (leitura)."""
import builtins
import io
import io as _io
import os
import socket
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import paramiko
import pyzipper

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backup import sftp_origem, tunel  # noqa: E402
from src.backup.file_manager.models import BackupFile  # noqa: E402
from src.backup.sftp_origem import ErroChaveHost, ErroSftp, PastaSftp, para_sftp  # noqa: E402

SENHA_ZIP = "senha-da-maquina"


# ─── servidor SSH/SFTP de teste (somente leitura) ────────────────────────────

class _Handle(paramiko.SFTPHandle):
    def __init__(self, arq, flags=0):
        super().__init__(flags)
        self.readfile = arq


class _SftpFS(paramiko.SFTPServerInterface):
    raiz = ""

    def _real(self, path):
        return self.raiz + path

    def list_folder(self, path):
        out = []
        for nome in os.listdir(self._real(path)):
            a = paramiko.SFTPAttributes.from_stat(os.stat(os.path.join(self._real(path), nome)), nome)
            out.append(a)
        return out

    def stat(self, path):
        try:
            return paramiko.SFTPAttributes.from_stat(os.stat(self._real(path)))
        except OSError as e:
            return paramiko.SFTPServer.convert_errno(e.errno)

    lstat = stat

    def open(self, path, flags, attr):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            return paramiko.SFTP_PERMISSION_DENIED
        try:
            return _Handle(open(self._real(path), "rb"))
        except OSError as e:
            return paramiko.SFTPServer.convert_errno(e.errno)


class _Auth(paramiko.ServerInterface):
    def __init__(self, servidor):
        self.s = servidor

    def get_allowed_auths(self, username):
        return "password,publickey"

    def check_auth_password(self, username, password):
        ok = username == "leitor" and password == "segredo"
        return paramiko.AUTH_SUCCESSFUL if ok else paramiko.AUTH_FAILED

    def check_auth_publickey(self, username, key):
        ok = username == "leitor" and self.s.chave_autorizada is not None and key == self.s.chave_autorizada
        return paramiko.AUTH_SUCCESSFUL if ok else paramiko.AUTH_FAILED

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED


class ServidorSftp:
    def __init__(self, raiz):
        self.host_key = paramiko.RSAKey.generate(2048)
        self.chave_autorizada = None
        _SftpFS.raiz = raiz
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.porta = self.sock.getsockname()[1]
        self._parar = False
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while not self._parar:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            t = paramiko.Transport(c)
            t.add_server_key(self.host_key)
            t.set_subsystem_handler("sftp", paramiko.SFTPServer, _SftpFS)
            try:
                t.start_server(server=_Auth(self))
            except Exception:
                pass

    def fechar(self):
        self._parar = True
        self.sock.close()


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = os.path.join(self.tmp.name, "srv")
        os.makedirs(os.path.join(self.raiz, "backups", "20260101"))
        self.grande = os.urandom(3 * 1024 * 1024 + 17)
        for rel, dados in {"backups/unm.zip": self.grande, "backups/20260101/a.txt": b"aaa" * 100,
                           "backups/vazio.bin": b"", "segredo.txt": b"fora da pasta"}.items():
            with open(os.path.join(self.raiz, rel), "wb") as f:
                f.write(dados)
        self.kh = Path(self.tmp.name) / "known_hosts_trilan"
        env = mock.patch.dict(os.environ, {"TRILAN_KNOWN_HOSTS": str(self.kh)})
        env.start()
        self.addCleanup(env.stop)
        self.srv = ServidorSftp(self.raiz)
        self.addCleanup(self.srv.fechar)
        self.addCleanup(sftp_origem.fechar_todas)

    def con(self, **kw):
        base = dict(host="127.0.0.1", porta=self.srv.porta, usuario="leitor", senha="segredo")
        base.update(kw)
        return sftp_origem.obter_conexao(base["host"], base["porta"], base["usuario"], base.get("senha"),
                                         base.get("chave"), base.get("fingerprint"))


# ─── caminhos ────────────────────────────────────────────────────────────────

class TestCaminho(unittest.TestCase):
    def test_formatos_do_cadastro_viram_caminho_sftp_do_openssh_windows(self):
        for entrada in ("D:UNM2000/emsback", "D:\\UNM2000\\emsback", "d:\\UNM2000\\emsback\\", "D:/UNM2000/emsback/",
                        "192.168.75.27:D:\\UNM2000\\emsback"):
            self.assertEqual(para_sftp(entrada), "/D:/UNM2000/emsback", entrada)
        self.assertEqual(para_sftp("D:\\"), "/D:/")
        self.assertEqual(para_sftp("/var/backups"), "/var/backups")
        self.assertEqual(para_sftp("/var//backups/./x/"), "/var/backups/x")

    def test_recusa_dotdot_relativo_e_unc(self):
        for ruim in ("D:\\a\\..\\b", "/var/../etc", "relativo/pasta", "\\\\srv\\share\\x", "", "D:/x/../../y"):
            with self.assertRaises(ErroSftp, msg=ruim):
                para_sftp(ruim)


class TestRaizSomenteLeitura(unittest.TestCase):
    def _pasta(self, raiz):
        con = mock.Mock()
        con.sftp.return_value.stat.return_value = SimpleNamespace(st_mode=0o100644, st_size=1, st_mtime=0)
        return PastaSftp(con, raiz)

    def test_recusa_fora_da_pasta_e_dotdot(self):
        p = self._pasta("D:\\UNM2000\\emsback")
        for ruim in ("/D:/UNM2000", "/D:/UNM2000/emsback2/x", "/etc/passwd", "/D:/UNM2000/emsback/../segredo",
                     "/D:/UNM2000/emsback/../../x"):
            with self.assertRaises(ErroSftp, msg=ruim):
                p.stat(ruim)
            with self.assertRaises(ErroSftp, msg=ruim):
                p.abrir(ruim)
            with self.assertRaises(ErroSftp, msg=ruim):
                p.listar(ruim)

    def test_aceita_dentro_da_pasta_sem_diferenciar_caixa_no_drive(self):
        p = self._pasta("D:\\UNM2000\\emsback")
        p.stat("/d:/unm2000/EMSBACK/x.zip")
        p.stat("/D:/UNM2000/emsback")

    def test_nao_existe_metodo_de_escrita(self):
        for nome in ("remove", "rename", "put", "mkdir", "write", "unlink", "rmdir", "chmod", "open_escrita"):
            self.assertFalse(hasattr(PastaSftp, nome), nome)

    def test_modo_relativo_so_aceita_nome_simples(self):
        con = mock.Mock()
        con.sftp.return_value.stat.return_value = SimpleNamespace(st_mode=0o100644, st_size=1, st_mtime=0)
        p = PastaSftp(con, "", relativo=True)
        p.stat("backup_x.rsc")
        for ruim in ("../x", "a/b", "/etc/passwd", ".."):
            with self.assertRaises(ErroSftp, msg=ruim):
                p.stat(ruim)


# ─── conexão real (servidor local) ───────────────────────────────────────────

class TestTofu(_Base):
    def test_primeira_grava_segunda_igual_passa_diferente_recusa(self):
        self.assertFalse(self.kh.exists())
        self.con()
        self.assertTrue(self.kh.exists())
        linhas = self.kh.read_text().strip().splitlines()
        self.assertEqual(len(linhas), 1)
        self.assertIn(f"[127.0.0.1]:{self.srv.porta}", linhas[0])
        sftp_origem.fechar_todas()

        self.con()                              # mesma chave: passa, sem acrescentar linha
        self.assertEqual(len(self.kh.read_text().strip().splitlines()), 1)
        sftp_origem.fechar_todas()

        self.srv.host_key = paramiko.RSAKey.generate(2048)     # servidor "trocou" de chave
        with self.assertRaises(ErroChaveHost) as cm:
            self.con()
        self.assertIn("a chave SSH de 127.0.0.1 mudou", str(cm.exception))

    def test_fingerprint_cadastrada_prevalece(self):
        fp = sftp_origem.impressao_digital(self.srv.host_key)
        self.con(fingerprint=fp)
        self.assertFalse(self.kh.exists())        # com fingerprint não grava nada
        sftp_origem.fechar_todas()
        with self.assertRaises(ErroChaveHost):
            self.con(fingerprint="SHA256:" + "A" * 43)

    def test_senha_errada_nao_vaza_a_senha(self):
        with self.assertRaises(ErroSftp) as cm:
            self.con(senha="errada-123")
        self.assertNotIn("errada-123", str(cm.exception))

    def test_autenticacao_por_chave_privada_em_memoria(self):
        chave = paramiko.RSAKey.generate(2048)
        self.srv.chave_autorizada = chave
        buf = io.StringIO()
        chave.write_private_key(buf)
        self.con(senha=None, chave=buf.getvalue())

    def test_chave_invalida(self):
        with self.assertRaises(ErroSftp):
            sftp_origem.carregar_chave("isto não é uma chave")


class TestLeituraSftp(_Base):
    def _pasta(self):
        return PastaSftp(self.con(), "/backups")

    def test_listar_stat_tamanho(self):
        p = self._pasta()
        nomes = {e.name: e for e in p.listar()}
        self.assertEqual(set(nomes), {"unm.zip", "20260101", "vazio.bin"})
        self.assertTrue(nomes["20260101"].is_dir)
        self.assertEqual(p.stat("/backups/unm.zip").size, len(self.grande))
        self.assertEqual(p.tamanho("/backups/20260101"), 300)

    def test_fora_da_pasta_no_servidor_real_e_recusado(self):
        p = self._pasta()
        with self.assertRaises(ErroSftp):
            p.abrir("/segredo.txt")
        with self.assertRaises(ErroSftp):
            p.abrir("/backups/../segredo.txt")

    def test_leitura_em_blocos_confere_byte_a_byte(self):
        p = self._pasta()
        with p.abrir("/backups/unm.zip") as f:
            dados = b"".join(tunel._blocos_de(f, 1024 * 1024))
        self.assertEqual(dados, self.grande)
        with p.abrir("/backups/vazio.bin") as f:
            self.assertEqual(f.read(10), b"")

    def test_read_tamanhos_irregulares(self):
        p = self._pasta()
        with p.abrir("/backups/unm.zip") as f:
            saida = bytearray()
            for n in (1, 7, 32768, 100000, 1):
                saida += f.read(n)
            saida += f.read()
        self.assertEqual(bytes(saida), self.grande)

    def test_servidor_nao_aceita_escrita(self):
        con = self.con()
        with self.assertRaises(Exception):
            con.sftp().open("/backups/novo.txt", "wb")
        self.assertFalse(os.path.exists(os.path.join(self.raiz, "backups", "novo.txt")))


# ─── ZIP em fluxo ────────────────────────────────────────────────────────────

def _montar(prontos, senha=SENHA_ZIP, extras=None):
    fila = tunel.FilaSaida()
    falha = {}
    t = threading.Thread(target=tunel._produtor, args=(fila, prontos, senha, falha, extras), daemon=True)
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


def _pronto(nome, itens, tipo="OLT"):
    return {"nome": nome, "tipo": tipo, "status": "OK", "pasta_zip": f"{tipo}/backup_{tipo.lower()}_{nome}",
            "arquivos_origem": itens}


def _abrir_zip(corpo, caminho):
    with pyzipper.AESZipFile(io.BytesIO(corpo)) as ext:
        ext.setpassword(SENHA_ZIP.encode())
        return ext.read(caminho)


class TestMontarZip(_Base):
    def test_sftp_arquivo_pasta_e_memoria_no_mesmo_zip_com_senha(self):
        p = PastaSftp(self.con(), "/backups")
        arq = BackupFile(path=Path("unm.zip"), file_type="ZIP", remote_path="/backups/unm.zip", is_sftp=True, sftp=p)
        pasta = BackupFile(path=Path("20260101"), file_type="DIGIFORT_DIR", remote_path="/backups/20260101",
                           is_sftp=True, sftp=p)
        mem = BackupFile(path=Path("CONFIG.bin"), file_type="NVR_CONFIG", dados=b"config-nvr" * 50)
        corpo, erro = _montar([_pronto("UNM_A", [(arq, "unm.zip")]),
                               _pronto("DIG", [(pasta, "20260101")], tipo="DIGIFORT"),
                               _pronto("NVR_1", [(mem, "CONFIG.bin")], tipo="NVR")],
                              extras=[("NVR/PLANILHA/x.xlsx", b"planilha")])
        self.assertIsNone(erro)
        with pyzipper.AESZipFile(io.BytesIO(corpo)) as ext:
            ext.setpassword(SENHA_ZIP.encode())
            self.assertIsNone(ext.testzip())
            self.assertEqual(sorted(ext.namelist()), ["DIGIFORT/backup_digifort_DIG/backup.zip",
                                                      "NVR/PLANILHA/x.xlsx", "NVR/backup_nvr_NVR_1/backup.zip",
                                                      "OLT/backup_olt_UNM_A/backup.zip"])
            self.assertEqual(ext.read("NVR/PLANILHA/x.xlsx"), b"planilha")
        with zipfile.ZipFile(io.BytesIO(_abrir_zip(corpo, "OLT/backup_olt_UNM_A/backup.zip"))) as z:
            self.assertEqual(z.read("unm.zip"), self.grande)
        with zipfile.ZipFile(io.BytesIO(_abrir_zip(corpo, "DIGIFORT/backup_digifort_DIG/backup.zip"))) as z:
            self.assertEqual(z.namelist(), ["20260101/a.txt"])
        with zipfile.ZipFile(io.BytesIO(_abrir_zip(corpo, "NVR/backup_nvr_NVR_1/backup.zip"))) as z:
            self.assertEqual(z.read("CONFIG.bin"), b"config-nvr" * 50)

    def test_sftp_tamanho_divergente_vira_corrompido(self):
        p = PastaSftp(self.con(), "/backups")
        falso = mock.Mock(wraps=p)
        falso.stat.return_value = SimpleNamespace(size=len(self.grande) + 5)
        falso.abrir.side_effect = p.abrir
        arq = SimpleNamespace(remote_path="/backups/unm.zip", path=Path("unm.zip"), is_smb=False, is_sftp=True,
                              sftp=falso, file_type="ZIP")
        _, erro = _montar([_pronto("UNM_A", [(arq, "unm.zip")])])
        self.assertIsInstance(erro, tunel._Divergente)
        self.assertEqual(tunel._status_da_falha(erro), "CORROMPIDO")

    def test_sftp_falha_de_leitura_vira_erro(self):
        p = PastaSftp(self.con(), "/backups")
        arq = BackupFile(path=Path("nao.zip"), file_type="ZIP", remote_path="/backups/nao.zip", is_sftp=True, sftp=p)
        _, erro = _montar([_pronto("UNM_A", [(arq, "nao.zip")])])
        self.assertIsInstance(erro, tunel._FalhaLeitura)
        self.assertEqual(tunel._status_da_falha(erro), "ERRO")

    def test_http_com_e_sem_content_length(self):
        dados = os.urandom(300_000)

        def fluxo(tam):
            return lambda: (iter([dados[:100_000], dados[100_000:]]), tam)

        ok = BackupFile(path=Path("x.tar"), file_type="PABX_TAR", abrir_fluxo=fluxo(len(dados)))
        corpo, erro = _montar([_pronto("PABX", [(ok, "x.tar")], tipo="PABX")])
        self.assertIsNone(erro)
        with zipfile.ZipFile(io.BytesIO(_abrir_zip(corpo, "PABX/backup_pabx_PABX/backup.zip"))) as z:
            self.assertEqual(z.read("x.tar"), dados)
        sem = BackupFile(path=Path("x.tar"), file_type="PABX_TAR", abrir_fluxo=fluxo(None))
        corpo, erro = _montar([_pronto("PABX", [(sem, "x.tar")], tipo="PABX")])
        self.assertIsNone(erro)                    # sem Content-Length: sem conferência, mas termina sem erro
        errado = BackupFile(path=Path("x.tar"), file_type="PABX_TAR", abrir_fluxo=fluxo(len(dados) + 1))
        _, erro = _montar([_pronto("PABX", [(errado, "x.tar")], tipo="PABX")])
        self.assertIsInstance(erro, tunel._Divergente)

    def test_http_que_cai_no_meio_derruba_o_fluxo(self):
        def quebra():
            def it():
                yield b"abc"
                raise ConnectionError("caiu")
            return it(), None
        bf = BackupFile(path=Path("x.tar"), file_type="PABX_TAR", abrir_fluxo=quebra)
        _, erro = _montar([_pronto("PABX", [(bf, "x.tar")], tipo="PABX")])
        self.assertIsInstance(erro, tunel._FalhaLeitura)

    def test_nada_e_criado_fora_do_known_hosts_durante_o_tunel(self):
        escritas = []
        original_open, original_io_open = builtins.open, _io.open

        def vigia(orig):
            def _open(arq, mode="r", *a, **kw):
                if isinstance(arq, (str, bytes, os.PathLike)) and any(c in mode for c in "wax+"):
                    escritas.append(str(arq))
                return orig(arq, mode, *a, **kw)
            return _open

        cwd = os.getcwd()
        vazio = tempfile.mkdtemp()
        os.chdir(vazio)
        try:
            with mock.patch.object(builtins, "open", vigia(original_open)), \
                    mock.patch.object(_io, "open", vigia(original_io_open)), \
                    mock.patch.object(Path, "write_bytes", side_effect=AssertionError("write_bytes")), \
                    mock.patch.object(Path, "write_text", side_effect=AssertionError("write_text")), \
                    mock.patch("tempfile.mkstemp", side_effect=AssertionError("mkstemp")), \
                    mock.patch("tempfile.NamedTemporaryFile", side_effect=AssertionError("tmp")):
                sftp_origem.fechar_todas()
                p = PastaSftp(self.con(), "/backups")        # 1ª conexão grava o known_hosts
                arq = BackupFile(path=Path("unm.zip"), file_type="ZIP", remote_path="/backups/unm.zip",
                                 is_sftp=True, sftp=p)
                mem = BackupFile(path=Path("c.bin"), file_type="NVR_CONFIG", dados=b"x" * 1000)
                corpo, erro = _montar([_pronto("A", [(arq, "unm.zip"), (mem, "c.bin")])])
            self.assertIsNone(erro)
            self.assertTrue(corpo)
            self.assertEqual({str(Path(e)) for e in escritas}, {str(self.kh)})
            self.assertEqual(os.listdir(vazio), [])
        finally:
            os.chdir(cwd)
            os.rmdir(vazio)


# ─── seleção do backup por SFTP (mesmas regras do SMB) ──────────────────────

class TestSelecaoUnm(_Base):
    def test_parser_sftp_acha_data_e_digifort_e_ignora_o_resto(self):
        from src.backup.file_manager.parsers import UNM2000Parser
        for nome in ("20260102_030000_allback.zip", "20260103_030000_allback.zip", "sem_data.zip", "20260104_030000.txt"):
            with open(os.path.join(self.raiz, "backups", nome), "wb") as f:
                f.write(b"x" * 10)
        grupos = UNM2000Parser().find_backups(PastaSftp(self.con(), "/backups"))
        self.assertEqual([g.group_id for g in grupos], ["20260103_030000", "20260102_030000", "20260101"])
        self.assertTrue(all(f.is_sftp for g in grupos for f in g.files))
        self.assertEqual(grupos[2].files[0].file_type, "DIGIFORT_DIR")

    def test_manager_usa_sftp_so_no_tunel_e_com_acesso_remoto_sftp(self):
        from datetime import datetime
        from src.backup.file_manager.manager import FileManager
        hoje = datetime.now().strftime("%Y%m%d")
        with open(os.path.join(self.raiz, "backups", f"{hoje}_030000_allback.zip"), "wb") as f:
            f.write(b"y" * 5000)
        eq = {"name": "UNM Teste", "tipo": "OLT", "ip": "127.0.0.1", "config_extra": {
            "pasta_origem": "/backups", "acesso_remoto": "sftp", "smb_host": "127.0.0.1", "ssh_usuario": "leitor",
            "ssh_senha": "segredo", "ssh_porta": self.srv.porta}}
        with mock.patch("src.backup.file_manager.validators.time.sleep"):
            res = FileManager(check_hash=False).process_equipment(eq, Path(os.devnull), "UNM2000", None,
                                                                   somente_preparar=True)
        self.assertEqual(res["status"], "PRONTO", res)
        origem, nome_zip = res["arquivos_origem"][0]
        self.assertTrue(origem.is_sftp)
        self.assertTrue(nome_zip.endswith(".zip"))
        self.assertEqual(origem.size_bytes, 5000)

    def test_data_antiga_vira_backup_antigo_como_no_windows(self):
        from src.backup.file_manager.manager import FileManager
        eq = {"name": "UNM", "tipo": "OLT", "ip": "127.0.0.1", "config_extra": {
            "pasta_origem": "/backups", "acesso_remoto": "sftp", "smb_host": "127.0.0.1", "ssh_usuario": "leitor",
            "ssh_senha": "segredo", "ssh_porta": self.srv.porta}}
        with open(os.path.join(self.raiz, "backups", "20200101_030000_allback.zip"), "wb") as f:
            f.write(b"z")
        res = FileManager(check_hash=False).process_equipment(eq, Path(os.devnull), "UNM2000", None,
                                                               somente_preparar=True)
        self.assertEqual(res["status"], "BACKUP_ANTIGO")

    def test_sftp_com_chave_do_host_trocada_vira_erro(self):
        from src.backup.file_manager.manager import FileManager
        eq = {"name": "UNM", "tipo": "OLT", "ip": "127.0.0.1", "config_extra": {
            "pasta_origem": "/backups", "acesso_remoto": "sftp", "smb_host": "127.0.0.1", "ssh_usuario": "leitor",
            "ssh_senha": "segredo", "ssh_porta": self.srv.porta}}
        FileManager(check_hash=False).process_equipment(eq, Path(os.devnull), "UNM2000", None, somente_preparar=True)
        sftp_origem.fechar_todas()
        self.srv.host_key = paramiko.RSAKey.generate(2048)
        res = FileManager(check_hash=False).process_equipment(eq, Path(os.devnull), "UNM2000", None,
                                                               somente_preparar=True)
        self.assertEqual(res["status"], "ERRO")


# ─── NVR / planilhas / Huawei / PABX em memória ──────────────────────────────

class TestEmMemoria(unittest.TestCase):
    def test_nomes_das_planilhas_como_no_windows(self):
        from src.backup.tunel_preparo import nomear_planilhas
        from src.backup.archiver import data_hoje
        um = nomear_planilhas({"NVR 1": b"a"}, "Cliente X", "Maq Y")
        self.assertEqual(um, [(f"NVR/PLANILHA/Cliente_X_Maq_Y_{data_hoje()}.xlsx", b"a")])
        dois = nomear_planilhas({"NVR 1": b"a", "NVR 2": b"b"}, None, "Maq")
        self.assertEqual([c for c, _ in dois], [f"NVR/PLANILHA/Maq_NVR_1_{data_hoje()}.xlsx",
                                                 f"NVR/PLANILHA/Maq_NVR_2_{data_hoje()}.xlsx"])

    def _nvr(self, tipo, **patches):
        from src.backup import tunel_preparo
        eq = {"name": "NVR 1", "ip": "10.0.0.9", "username": "admin", "password": "p", "tipo": "NVR",
              "config_extra": {"marca": tipo}}
        cams = [{"canal": 1, "nome": "c1"}]
        return eq, cams, tunel_preparo

    def test_nvr_intelbras_em_memoria_com_cameras_telemetria_e_planilha(self):
        eq, cams, prep = self._nvr("INTELBRAS")
        from src.application import backup_job

        def planilha(ip, u, p, destino):
            destino.write(b"XLSX")
            return True
        with mock.patch("src.nvr.factory.verificar_gravacao_nvr", return_value=(cams, "INTELBRAS")), \
                mock.patch("src.nvr.factory.coletar_telemetria_nvr", return_value={"cpu": 1}), \
                mock.patch("src.nvr.intelbras.backup.baixar_configuracao_intelbras_memoria", return_value=b"cfg" * 500), \
                mock.patch.dict(backup_job.PLANILHAS_NVR, {"INTELBRAS": planilha}):
            res = prep.preparar_nvr(eq, "senha")
        self.assertEqual(res["status"], "PRONTO")
        self.assertEqual(res["status_final"], "OK")
        self.assertEqual(res["cameras"], cams)
        self.assertEqual(res["telemetria"], {"cpu": 1})
        self.assertEqual(res["_planilha"], b"XLSX")
        bf, nome = res["arquivos_origem"][0]
        self.assertEqual(bf.origem, "memoria")
        self.assertEqual(bf.dados, b"cfg" * 500)
        self.assertTrue(nome.startswith("CONFIG_INTELBRAS_"))

    def test_nvr_planilha_que_falha_nao_muda_o_status(self):
        eq, cams, prep = self._nvr("INTELBRAS")
        from src.application import backup_job
        with mock.patch("src.nvr.factory.verificar_gravacao_nvr", return_value=(cams, "INTELBRAS")), \
                mock.patch("src.nvr.factory.coletar_telemetria_nvr", return_value=None), \
                mock.patch("src.nvr.intelbras.backup.baixar_configuracao_intelbras_memoria", return_value=b"c" * 2000), \
                mock.patch.dict(backup_job.PLANILHAS_NVR, {"INTELBRAS": lambda *a: False}):
            res = prep.preparar_nvr(eq, "s")
        self.assertEqual(res["status"], "PRONTO")
        self.assertNotIn("_planilha", res)

    def test_nvr_motorola_config_em_memoria_e_intelbras_sem_download_parcial(self):
        eq, cams, prep = self._nvr("MOTOROLA")
        from src.application import backup_job
        with mock.patch("src.nvr.factory.verificar_gravacao_nvr", return_value=(cams, "MOTOROLA")), \
                mock.patch("src.nvr.factory.coletar_telemetria_nvr", return_value=None), \
                mock.patch("src.nvr.motorola.backup.baixar_configuracao_motorola_memoria",
                           return_value=b"m" * 3000) as baixar, \
                mock.patch.dict(backup_job.PLANILHAS_NVR, {}, clear=True):
            res = prep.preparar_nvr(eq, "s")
        self.assertEqual((res["status"], res["status_final"], res["cameras"]), ("PRONTO", "OK", cams))
        bf, nome = res["arquivos_origem"][0]
        self.assertEqual(bf.dados, b"m" * 3000)
        self.assertTrue(nome.startswith("CONFIG_MOTOROLA_") and nome.endswith(".bin"))
        self.assertIsNotNone(baixar.call_args.kwargs.get("limite"))
        with mock.patch("src.nvr.factory.verificar_gravacao_nvr", return_value=(cams, "MOTOROLA")), \
                mock.patch("src.nvr.factory.coletar_telemetria_nvr", return_value=None), \
                mock.patch("src.nvr.motorola.backup.baixar_configuracao_motorola_memoria", return_value=None), \
                mock.patch.dict(backup_job.PLANILHAS_NVR, {}, clear=True):
            res = prep.preparar_nvr(eq, "s")
        self.assertEqual((res["status"], res["cameras"]), ("PARCIAL", cams))
        eq2, _, _ = self._nvr("INTELBRAS")
        with mock.patch("src.nvr.factory.verificar_gravacao_nvr", return_value=(cams, "INTELBRAS")), \
                mock.patch("src.nvr.factory.coletar_telemetria_nvr", return_value=None), \
                mock.patch("src.nvr.intelbras.backup.baixar_configuracao_intelbras_memoria", return_value=None), \
                mock.patch.dict(backup_job.PLANILHAS_NVR, {}, clear=True):
            res = prep.preparar_nvr(eq2, "s")
        self.assertEqual(res["status"], "PARCIAL")

    def test_nvr_inacessivel_vira_erro(self):
        eq, _, prep = self._nvr("INTELBRAS")
        with mock.patch("src.nvr.factory.verificar_gravacao_nvr", return_value=([], "DESCONHECIDO")):
            self.assertEqual(prep.preparar_nvr(eq, "s")["status"], "ERRO")

    def test_nvr_hikvision_bin_e_xls_em_memoria(self):
        eq, cams, prep = self._nvr("HIKVISION")
        from src.application import backup_job
        respostas = [b"B" * 150_000, b"X" * 500]
        with mock.patch("src.nvr.factory.verificar_gravacao_nvr", return_value=(cams, "NVR")), \
                mock.patch("src.nvr.factory.coletar_telemetria_nvr", return_value=None), \
                mock.patch("requests.Session.get", return_value=mock.Mock(raise_for_status=lambda: None)), \
                mock.patch("src.backup.downloader.baixar_bytes", side_effect=respostas), \
                mock.patch.dict(backup_job.PLANILHAS_NVR, {}, clear=True):
            res = prep.preparar_nvr(eq, "senha-zip")
        self.assertEqual(res["status_final"], "OK")
        self.assertEqual([n.split("_")[1] for _, n in res["arquivos_origem"]], ["NVR", "IPCAM"])
        self.assertEqual([bf.dados for bf, _ in res["arquivos_origem"]], respostas)

    def test_baixar_bytes_respeita_limite_de_memoria(self):
        from src.backup.downloader import LimiteMemoriaExcedido, baixar_bytes

        class R:
            status_code = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def iter_content(self, n):
                for _ in range(5):
                    yield b"x" * 1024

        sessao = SimpleNamespace(get=lambda *a, **k: R())
        self.assertEqual(len(baixar_bytes(sessao, "http://x/y?z=1", limite=10_000)), 5120)
        with self.assertRaises(LimiteMemoriaExcedido):
            baixar_bytes(sessao, "http://x/y", limite=2000)

    def test_huawei_texto_limpa_paginacao_e_valida(self):
        from src.olt.huawei_texto import config_valida, limpar_saida
        corpo = "\n".join(f"interface gpon 0/{i}\n  port 1 ont-auto-find enable" for i in range(40))
        bruto = ("display current-configuration\r\n[MA5800-X7]\r\n" + corpo[:600] +
                 "\r\n---- More ( Press 'Q' to break ) ----\x1b[37D                                     \x1b[37D" +
                 corpo[600:] + "\r\n#\r\nreturn\r\nhuawei#")
        txt = limpar_saida(bruto, "display current-configuration")
        self.assertNotIn("More", txt)
        self.assertNotIn("\x1b", txt)
        self.assertTrue(txt.rstrip().endswith("return"))
        self.assertTrue(config_valida(txt)[0])
        self.assertFalse(config_valida("Error: Unknown command")[0])
        self.assertFalse(config_valida(txt.replace("return", ""))[0])

    def test_huawei_le_pelo_shell_respondendo_a_paginacao(self):
        from src.olt import huawei_texto

        class ShellFalso:
            def __init__(self):
                self.fila = [b"display current-configuration\r\n" + b"a" * 300 + b"\r\n---- More ( Press 'Q' ) ----",
                             b"\x08" * 5 + b"b" * 300 + b"\r\nreturn\r\nhuawei#"]
                self.enviado = []

            def send(self, t):
                self.enviado.append(t)

            def recv_ready(self):
                return bool(self.fila)

            def recv(self, n):
                return self.fila.pop(0)

        sh = ShellFalso()
        bruto = huawei_texto.ler_config_por_shell(sh, 10 ** 6, timeout_total=5, silencio=0.5)
        self.assertEqual(sh.enviado, ["display current-configuration\n", " "])
        self.assertIn("return", bruto)

    def test_pabx_com_content_length_pequeno_fica_em_memoria_e_grande_vira_fluxo(self):
        from src.pabx import issabel

        class Resp:
            def __init__(self, dados, tam):
                self.dados, self.headers = dados, ({"Content-Length": str(tam)} if tam is not None else {})
                self.fechada = False

            def iter_content(self, chunk_size=0):
                yield self.dados[:10]
                yield self.dados[10:]

            def close(self):
                self.fechada = True

        dados = b"T" * 5000
        eq = {"name": "PABX", "ip": "10.0.0.5", "username": "u", "password": "p", "tipo": "PABX"}
        with mock.patch.object(issabel, "login", return_value=True), \
                mock.patch.object(issabel, "disparar_backup", return_value="issabelbackup-1.tar"), \
                mock.patch.object(issabel, "_abrir_download", side_effect=lambda *a: Resp(dados, len(dados))):
            res = issabel.preparar_backup_issabel_tunel(eq, limite_memoria=10_000)
            bf, nome = res["arquivos_origem"][0]
            self.assertEqual((bf.origem, bf.dados, nome), ("memoria", dados, "issabelbackup-1.tar"))
            res = issabel.preparar_backup_issabel_tunel(eq, limite_memoria=1000)
            bf, _ = res["arquivos_origem"][0]
            self.assertEqual(bf.origem, "http")
            blocos, tam = bf.abrir_fluxo()
            self.assertEqual((b"".join(blocos), tam), (dados, len(dados)))
        with mock.patch.object(issabel, "login", return_value=True), \
                mock.patch.object(issabel, "disparar_backup", return_value="issabelbackup-1.tar"), \
                mock.patch.object(issabel, "_abrir_download", side_effect=lambda *a: Resp(dados, None)):
            res = issabel.preparar_backup_issabel_tunel(eq, limite_memoria=10_000_000)
            bf, _ = res["arquivos_origem"][0]
            self.assertEqual(bf.origem, "http")           # sem Content-Length: fluxo, sem conferência
            self.assertIsNone(bf.abrir_fluxo()[1])

    def test_defense_sem_pasta_origem_e_erro_com_mensagem(self):
        from src.backup import tunel_preparo
        with self.assertLogs(level="ERROR") as logs:
            res = tunel_preparo.preparar_defense({"name": "Def", "tipo": "DEFENSE", "config_extra": {}})
        self.assertEqual(res["status"], "ERRO")
        self.assertIn("configure a pasta de backup do Defense", logs.output[0])


if __name__ == "__main__":
    unittest.main()
