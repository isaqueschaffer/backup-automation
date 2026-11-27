"""Backup da configuracao dos NVR Motorola sem plugin (src/nvr/motorola/backup.py).

Um NVR falso local fala os dois protocolos reproduzidos a partir da captura do plugin (24/11/2026):
o binario da porta de servico (pacotes "1111", firmware com plugin v2/v3) e o WebSocket do modo H5 (plugin v5)."""
import base64
import hashlib
import json
import os
import socket
import struct
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.backup.downloader import LimiteMemoriaExcedido  # noqa: E402
from src.nvr.motorola import backup as mb  # noqa: E402

USUARIO, SENHA = "admin", "senha-de-teste"
ARQUIVO = os.urandom(4096 * 3 + 1234)  # 3 blocos cheios + 1 parcial
SESSAO_GUID, CLIENTE_GUID = os.urandom(16), os.urandom(16)


def _ler(c, n):
    buf = b""
    while len(buf) < n:
        parte = c.recv(n - len(buf))
        if not parte:
            raise ConnectionError
        buf += parte
    return buf


def _fechar(servidor):
    for s in (getattr(servidor, "conexao", None), servidor.srv):
        if s is not None:
            s.close()


def _pacote(f0, cmd, seq, dados=b"", cab_extra=b""):
    corpo = struct.pack("<IIII", f0, cmd, seq, len(dados)) + cab_extra + dados
    return b"1111" + struct.pack("<I", len(corpo)) + corpo


class NvrBinarioFalso(threading.Thread):
    """Porta de servico NVMS-9000: login, info, abertura, blocos com ACK, fim e fechamento."""

    def __init__(self, arquivo=ARQUIVO):
        super().__init__(daemon=True)
        self.arquivo = arquivo
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(2)
        self.porta = self.srv.getsockname()[1]
        self.acks, self.logins_recusados, self.erro = 0, 0, None

    def _ler_pacote(self, c):
        ini = _ler(c, 8)
        assert ini[:4] == b"1111", ini
        p = _ler(c, struct.unpack("<I", ini[4:])[0])
        return struct.unpack("<IIII", p[:16]) + (p,)

    def run(self):
        try:
            c, _ = self.srv.accept()
            self.conexao = c
            c.settimeout(10)
            c.sendall(b"head" + b"\0" * 60)
            c.sendall(b"1111" + struct.pack("<I", 0))  # keepalive
            while True:
                try:
                    _, cmd, seq, _, p = self._ler_pacote(c)
                except ConnectionError:
                    return
                if cmd == 0x0101:
                    usuario = p[0x34:0x74].rstrip(b"\0").decode()
                    senha = p[0x74:0xB4].rstrip(b"\0").decode()
                    if (usuario, senha) != (USUARIO, SENHA):
                        self.logins_recusados += 1
                        c.sendall(_pacote(0x01000006, 0x20000101, seq, b"\0" * 500))
                        continue
                    resp = bytearray(500)
                    resp[0:16] = SESSAO_GUID
                    resp[0x54:0x64] = CLIENTE_GUID  # p[0x64:0x74] do pacote = dados[0x54:0x64]
                    c.sendall(_pacote(0x01000006, 0x10000101, seq, bytes(resp)))
                    # notificacao no meio do fluxo (deve ser ignorada)
                    c.sendall(_pacote(0x00000006, 0x0A01, 0, b"\0" * 92))
                elif cmd == 0x0102:
                    c.sendall(_pacote(0x01000006, 0x10000102, seq, b"<info/>".ljust(64, b"\0")))
                elif cmd == 0x0C01:
                    assert p[0x58:0x58 + 18] == b"EXPORT_CONFIG_FILE"
                    assert p[0x20:0x30] == CLIENTE_GUID and p[0x30:0x40] == SESSAO_GUID
                    cab = p[16:88]
                    info = bytearray(4292)
                    struct.pack_into("<I", info, 0xD8 - 88, len(self.arquivo))
                    c.sendall(_pacote(0x01020006, 0x10000C01, seq, bytes(info), cab))
                    num = 0x5FB8E
                    for i in range(0, len(self.arquivo), 4096):
                        bloco = self.arquivo[i:i + 4096]
                        c.sendall(_pacote(0x01020006, 0x0C02, num, bloco, os.urandom(16) + SESSAO_GUID + CLIENTE_GUID
                                          + struct.pack("<I", 2) + os.urandom(16) + struct.pack("<I", 5)))
                        _, acmd, aseq, aln, _ = self._ler_pacote(c)
                        assert (acmd, aseq, aln) == (0x10000C02, num, 0), (hex(acmd), aseq, aln)
                        self.acks += 1
                        num += 1
                    c.sendall(_pacote(0x00020006, 0x0C03, 0, b"\0" * 4, b"\0" * 72))
                elif cmd == 0x0C04:
                    c.sendall(_pacote(0x01020006, 0x10000C04, seq, b"", p[16:88]))
        except Exception as e:  # pragma: no cover - aparece no teste
            self.erro = e
        finally:
            _fechar(self)


class NvrWebSocketFalso(threading.Thread):
    """/requestWebsocketConnection do firmware H5: autentica pelo sessionID e envia o arquivo em blocos."""

    def __init__(self, sid, arquivo=ARQUIVO, bloco=32768):
        super().__init__(daemon=True)
        self.sid, self.arquivo, self.bloco = sid, arquivo, bloco
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(2)
        self.porta = self.srv.getsockname()[1]
        self.passos, self.parou, self.erro = 0, False, None

    @staticmethod
    def _quadro(dados, op):
        n = len(dados)
        cab = bytes([0x80 | op, n]) if n < 126 else (bytes([0x80 | op, 126]) + struct.pack(">H", n) if n < 65536
                                                     else bytes([0x80 | op, 127]) + struct.pack(">Q", n))
        return cab + dados

    @staticmethod
    def _receber(c):
        b0, b1 = _ler(c, 2)
        n = b1 & 0x7F
        if n == 126:
            n = struct.unpack(">H", _ler(c, 2))[0]
        elif n == 127:
            n = struct.unpack(">Q", _ler(c, 8))[0]
        m = _ler(c, 4)
        return b0 & 0x0F, bytes(b ^ m[i % 4] for i, b in enumerate(_ler(c, n)))

    def run(self):
        try:
            c, _ = self.srv.accept()
            self.conexao = c
            c.settimeout(10)
            req = b""
            while b"\r\n\r\n" not in req:
                req += c.recv(4096)
            linha = req.split(b"\r\n")[0].decode()
            chave = [ln.split(b": ")[1] for ln in req.split(b"\r\n") if ln.lower().startswith(b"sec-websocket-key")][0]
            aceite = base64.b64encode(hashlib.sha1(chave + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
            c.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      b"Sec-WebSocket-Accept: " + aceite + b"\r\n\r\n")
            codigo = 0 if f"sessionID={self.sid}" in linha else 536870947
            c.sendall(self._quadro(json.dumps({"url": "/device/create_connection#response",
                                               "data": {"code": codigo}}).encode(), 1))
            op, d = self._receber(c)
            msg = json.loads(d)
            assert msg["url"] == "/device/file/download/start" and msg["data"] == {"file_id": "config_file"}
            c.sendall(self._quadro(b"", 9))  # ping (o cliente responde pong)
            assert self._receber(c)[0] == 10
            for i in range(0, len(self.arquivo), self.bloco):
                c.sendall(self._quadro(struct.pack("<II", 0, 0) + self.arquivo[i:i + self.bloco], 2))
                op, d = self._receber(c)
                msg = json.loads(d)
                assert msg["url"] == "/device/file/download/step#response", msg
                self.passos += 1
                assert msg["data"]["index"] == self.passos
            c.sendall(self._quadro(json.dumps({"url": "/device/file/download/step",
                                               "data": {"code": 536870961}}).encode(), 1))
            op, d = self._receber(c)
            self.parou = json.loads(d)["url"] == "/device/file/download/stop"
        except Exception as e:  # pragma: no cover
            self.erro = e
        finally:
            _fechar(self)


class _Resp:
    def __init__(self, status_code=200, content=b""):
        self.status_code, self.content = status_code, content
        self.text = content.decode(errors="replace")


class SessaoFalsa:
    """Dublê do requests.Session devolvido por abrir_sessao_motorola."""

    def __init__(self, porta_servico, h5=False, sid="ABCD-1234"):
        self.porta_servico, self.h5 = porta_servico, h5
        self.tvt_token, self.tvt_session_id = "tok", sid
        self.comandos = []

    def post(self, url, data=None, **kw):
        nome = url.rsplit("/", 1)[1]
        self.comandos.append(nome)
        if nome == "queryUPnPCfg":
            return _Resp(content=f"<response><status>success</status><content><item><portType>SERVICE</portType>"
                                 f"<localPort>{self.porta_servico}</localPort></item></content></response>".encode())
        if nome == "exportConfig":
            assert b"<networkConfigSwitch>true</networkConfigSwitch>" in data
            return _Resp(content=b"<response><status>success</status></response>")
        return _Resp(404)

    def get(self, url, **kw):
        if url.endswith("/js/lib/websocket.download.js") and self.h5:
            return _Resp(content=b"define(['websocket.base'],function(){/* download */})")
        return _Resp(404)


class TestBackupMotorola(unittest.TestCase):
    def setUp(self):
        p = patch.object(mb, "PAUSA_NOVA_TENTATIVA_S", 0)
        p.start()
        self.addCleanup(p.stop)

    def _rodar(self, sessoes, ip="127.0.0.1", senha=SENHA, **kw):
        with patch.object(mb, "abrir_sessao_motorola", side_effect=sessoes) as abrir:
            dados = mb.baixar_configuracao_motorola_memoria(ip, USUARIO, senha, **kw)
        return dados, abrir

    def test_protocolo_binario_baixa_o_arquivo_inteiro_com_ack_por_bloco(self):
        nvr = NvrBinarioFalso()
        nvr.start()
        sessao = SessaoFalsa(nvr.porta)
        dados, _ = self._rodar([sessao])
        nvr.join(5)
        self.assertIsNone(nvr.erro)
        self.assertEqual(dados, ARQUIVO)
        self.assertEqual(nvr.acks, 4)
        self.assertIn("exportConfig", sessao.comandos)

    def test_firmware_h5_usa_websocket_com_session_id(self):
        ws = NvrWebSocketFalso("ABCD-1234")
        ws.start()
        sessao = SessaoFalsa(porta_servico=1, h5=True)
        dados, _ = self._rodar([sessao], ip=f"127.0.0.1:{ws.porta}")
        ws.join(5)
        self.assertIsNone(ws.erro)
        self.assertEqual(dados, ARQUIVO)
        self.assertEqual(ws.passos, 1)
        self.assertTrue(ws.parou)

    def test_h5_sem_session_id_cai_para_o_binario(self):
        nvr = NvrBinarioFalso()
        nvr.start()
        dados, _ = self._rodar([SessaoFalsa(nvr.porta, h5=True, sid="")])
        self.assertEqual(dados, ARQUIVO)

    def test_login_recusado_na_porta_de_servico_tenta_de_novo_e_devolve_none(self):
        nvrs = [NvrBinarioFalso(), NvrBinarioFalso()]
        for n in nvrs:
            n.start()
        dados, abrir = self._rodar([SessaoFalsa(nvrs[0].porta, sid=""), SessaoFalsa(nvrs[1].porta, sid="")],
                                   senha="errada")
        self.assertIsNone(dados)
        self.assertEqual(abrir.call_count, 2)
        self.assertEqual([n.logins_recusados for n in nvrs], [1, 1])

    def test_login_http_falho_nao_insiste(self):
        dados, abrir = self._rodar([None, None])
        self.assertIsNone(dados)
        self.assertEqual(abrir.call_count, 1)

    def test_limite_de_memoria_sobe_para_o_tunel(self):
        nvr = NvrBinarioFalso()
        nvr.start()
        with self.assertRaises(LimiteMemoriaExcedido):
            self._rodar([SessaoFalsa(nvr.porta)], limite=4096)

    def test_grava_em_disco(self):
        import tempfile
        nvr = NvrBinarioFalso()
        nvr.start()
        with tempfile.TemporaryDirectory() as d, \
                patch.object(mb, "abrir_sessao_motorola", return_value=SessaoFalsa(nvr.porta)):
            destino = Path(d) / "CONFIG_MOTOROLA.bin"
            self.assertTrue(mb.baixar_configuracao_motorola("127.0.0.1", USUARIO, SENHA, destino))
            self.assertEqual(destino.read_bytes(), ARQUIVO)

    def test_separar_host(self):
        self.assertEqual(mb._separar_host("10.0.0.5"), ("10.0.0.5", 80))
        self.assertEqual(mb._separar_host("10.0.0.5:8080"), ("10.0.0.5", 8080))


if __name__ == "__main__":
    unittest.main()
