"""Backup restauravel da configuracao dos NVR Motorola (OEM TVT, NVMS-9000), sem o plugin do navegador.

A tela "Backup e restauracao" do NVR pede o `exportConfig` (HTTP) e depois baixa o arquivo por um de dois caminhos,
conforme o firmware; os dois foram reproduzidos aqui em Python puro (Windows e Linux, sem dependencias novas):

- Protocolo binario na porta de servico (6036 por padrao; `queryUPnPCfg`, item SERVICE), que o plugin v2/v3 usa.
  Pacotes "1111" + tamanho; login com usuario e senha, abertura da transferencia EXPORT_CONFIG_FILE, blocos de
  4 KB com ACK e fechamento. O plugin nao cifra nada: o arquivo ja sai cifrado do NVR e e gravado como veio.
- Modo H5 (firmware 1.4.x, plugin v5): WebSocket em /requestWebsocketConnection?sessionID=<sessionId do reqLogin>,
  comandos JSON /device/file/download/start|step|stop e blocos binarios.

O caminho e escolhido sem tentar login: o firmware H5 serve js/lib/websocket.download.js. Se o escolhido falhar por
protocolo, o outro e tentado uma vez. Validado em 24/11/2026 com TD-3116B2 e TD-3316B2-A1 (plugin v2),
TD-2008NS-HL e TD-2116NS-HL (plugin v3) e TD-3316B2-A1 firmware 1.4.8 (plugin v5, H5).
"""
import base64
import hashlib
import json
import logging
import os
import random
import socket
import struct
import time
import uuid
from pathlib import Path
from typing import Optional

from src.backup.downloader import LimiteMemoriaExcedido
from src.nvr.motorola.cameras import abrir_sessao_motorola
from src.utils.xml_parser import parse_xml_seguro

TIMEOUT_S = 30
PRAZO_TOTAL_S = 300
TENTATIVAS = 2  # o NVR as vezes fecha a conexao no meio (visto no TD-3316B2-A1); a 2a rodada costuma passar
PAUSA_NOVA_TENTATIVA_S = 10
PORTA_SERVICO_PADRAO = 6036
CHAVE_ARQUIVO = "EXPORT_CONFIG_FILE"
_XML = '<?xml version="1.0" encoding="utf-8" ?>'

# Protocolo binario
_MAGIC = b"1111"
_F0_CLI_LOGIN, _F0_CLI_ARQ, _F0_SRV_ARQ = 0x01000004, 0x01020004, 0x01020006
_CMD_LOGIN, _CMD_INFO = 0x0101, 0x0102
_CMD_ABRIR, _CMD_DADOS, _CMD_FIM, _CMD_FECHAR = 0x0C01, 0x0C02, 0x0C03, 0x0C04
_RESP_OK, _RESP_ERRO = 0x10000000, 0x20000000
_CAB_ARQ = 88  # cabecalho dos pacotes de transferencia: base(16) + 3 GUIDs + u32 + GUID + u32

# Modo H5
_WS_FIM_DOWNLOAD = 536870961


class ErroExportacao(Exception):
    """Falha de protocolo/transferencia (o outro caminho ainda pode funcionar)."""


def _separar_host(ip: str):
    """'1.2.3.4' ou '1.2.3.4:8080' -> (host, porta_http)."""
    if ip.count(":") == 1:
        host, porta = ip.split(":")
        if porta.isdigit():
            return host, int(porta)
    return ip, 80


def _comando_http(sessao, ip: str, nome: str, extra: str = ""):
    token = getattr(sessao, "tvt_token", "") or ""
    corpo = (f'{_XML}<request version="1.0" systemType="NVMS-9000" clientType="WEB">'
             f'{"<token>%s</token>" % token if token else ""}{extra}</request>')
    r = sessao.post(f"http://{ip}/{nome}", data=corpo.encode("utf-8"),
                    headers={"Content-Type": "application/xml"}, timeout=TIMEOUT_S, verify=False)
    return parse_xml_seguro(r.content)


def _porta_servico(sessao, ip: str) -> int:
    try:
        for item in _comando_http(sessao, ip, "queryUPnPCfg").iter("item"):
            if (item.findtext("portType") or "") == "SERVICE" and (item.findtext("localPort") or "").isdigit():
                return int(item.findtext("localPort"))
    except Exception:
        logging.debug("  queryUPnPCfg falhou; usando a porta de servico padrao.", exc_info=True)
    return PORTA_SERVICO_PADRAO


def _pedir_exportacao(sessao, ip: str) -> None:
    """Pede ao NVR que gere o arquivo (inclui a configuracao de rede, como a opcao da tela)."""
    r = _comando_http(sessao, ip, "exportConfig", "<networkConfigSwitch>true</networkConfigSwitch>"
                      "<encryptionConfigSwitch>false</encryptionConfigSwitch>")
    if (r.findtext("status") or "") != "success":
        raise ErroExportacao(f"exportConfig recusado (errorCode {r.findtext('errorCode') or '?'})")


def _verificar_limite(tamanho: int, limite: Optional[int]) -> None:
    if limite is not None and tamanho > limite:
        raise LimiteMemoriaExcedido(f"a config do NVR passou de {limite // (1024 * 1024)} MB")


# ─── Protocolo binario (plugin v2/v3) ────────────────────────────────────────

class _ConexaoBinaria:
    def __init__(self, host: str, porta: int):
        self.s = socket.create_connection((host, porta), timeout=TIMEOUT_S)
        self.seq = 0x100
        self.sessao = self.cliente = b""

    def _ler(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            parte = self.s.recv(n - len(buf))
            if not parte:
                raise ErroExportacao("conexao fechada pelo NVR")
            buf += parte
        return buf

    def ler_pacote(self):
        """(cmd, seq, ln, pacote) do proximo pacote util; ignora saudacao, keepalive e notificacoes 0x0Axx."""
        while True:
            ini = self._ler(8)
            if ini[:4] == b"head":
                self._ler(56)
                continue
            if ini[:4] != _MAGIC:
                raise ErroExportacao("resposta fora do protocolo NVMS")
            n = struct.unpack("<I", ini[4:])[0]
            p = self._ler(n) if n else b""
            if len(p) < 16:
                continue
            _, cmd, seq, ln = struct.unpack("<IIII", p[:16])
            if cmd & 0xFFFFFF00 == 0x0A00:
                continue
            return cmd, seq, ln, p

    def enviar(self, corpo: bytes) -> None:
        self.s.sendall(_MAGIC + struct.pack("<I", len(corpo)) + corpo)

    def requisitar(self, f0: int, cmd: int, dados: bytes, cab_extra: bytes = b"") -> int:
        self.seq += 1
        self.enviar(struct.pack("<IIII", f0, cmd, self.seq, len(dados)) + cab_extra + dados)
        return self.seq

    def esperar(self, cmd: int, seq: int) -> bytes:
        while True:
            c, s, _, p = self.ler_pacote()
            if s == seq and c & 0xFFFF == cmd:
                if c & _RESP_ERRO:
                    raise ErroExportacao(f"NVR recusou o comando {cmd:#06x}")
                return p

    def login(self, usuario: str, senha: str) -> None:
        ip_local, porta_local = self.s.getsockname()[:2]
        endereco = struct.pack("<H", 2) + struct.pack(">H", porta_local) + socket.inet_aton(ip_local) + b"\0" * 8
        dados = (struct.pack("<I", 3) + b"\0" * 32 + usuario.encode("utf-8")[:63].ljust(64, b"\0")
                 + senha.encode("utf-8")[:63].ljust(64, b"\0") + endereco).ljust(236, b"\0")
        p = self.esperar(_CMD_LOGIN, self.requisitar(_F0_CLI_LOGIN, _CMD_LOGIN, dados))
        self.sessao, self.cliente = p[16:32], p[0x64:0x74]
        if self.sessao == b"\0" * 16:
            raise ErroExportacao("login na porta de servico recusado")
        self.esperar(_CMD_INFO, self.requisitar(_F0_CLI_LOGIN, _CMD_INFO, b"\0" * 20))

    def baixar(self, limite: Optional[int], prazo: float) -> bytes:
        tarefa, transf = uuid.uuid4().bytes, uuid.uuid4().bytes
        base = tarefa + self.cliente + self.sessao + struct.pack("<I", 2) + transf
        p = self.esperar(_CMD_ABRIR, self.requisitar(_F0_CLI_ARQ, _CMD_ABRIR, CHAVE_ARQUIVO.encode().ljust(388, b"\0"),
                                                     base + struct.pack("<I", 1)))
        tamanho = struct.unpack("<I", p[0xD8:0xDC])[0] if len(p) >= 0xDC else 0
        _verificar_limite(tamanho, limite)
        arquivo = bytearray()
        while True:
            if time.monotonic() > prazo:
                raise ErroExportacao("tempo esgotado na transferencia")
            cmd, seq, ln, p = self.ler_pacote()
            if cmd == _CMD_DADOS:
                arquivo += p[_CAB_ARQ:_CAB_ARQ + ln]
                _verificar_limite(len(arquivo), limite)
                ack = bytearray(p[:_CAB_ARQ])
                struct.pack_into("<IIII", ack, 0, _F0_SRV_ARQ, _CMD_DADOS | _RESP_OK, seq, 0)
                struct.pack_into("<I", ack, 0x40, 1)
                struct.pack_into("<I", ack, 0x54, 3)
                self.enviar(bytes(ack))
            elif cmd == _CMD_FIM:
                break
        try:
            self.esperar(_CMD_FECHAR, self.requisitar(_F0_CLI_ARQ, _CMD_FECHAR, b"\0" * 388, base + struct.pack("<I", 2)))
        except (ErroExportacao, OSError):
            pass  # o arquivo ja chegou inteiro; o fechamento e cortesia
        if tamanho and len(arquivo) != tamanho:
            raise ErroExportacao(f"arquivo incompleto: {len(arquivo)} de {tamanho} bytes")
        return bytes(arquivo)

    def fechar(self) -> None:
        try:
            self.s.close()
        except OSError:
            pass


def _exportar_binario(sessao, ip: str, usuario: str, senha: str, limite: Optional[int], prazo: float) -> bytes:
    host, _ = _separar_host(ip)
    porta = _porta_servico(sessao, ip)
    con = _ConexaoBinaria(host, porta)
    try:
        con.login(usuario, senha)
        _pedir_exportacao(sessao, ip)
        return con.baixar(limite, prazo)
    finally:
        con.fechar()


# ─── Modo H5 / WebSocket (plugin v5) ─────────────────────────────────────────

class _WebSocket:
    """Cliente WebSocket minimo (RFC 6455, sem TLS) suficiente para o download do NVR."""

    def __init__(self, host: str, porta: int, caminho: str):
        self.s = socket.create_connection((host, porta), timeout=TIMEOUT_S)
        chave = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET {caminho} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {chave}\r\nSec-WebSocket-Version: 13\r\n"
                        f"Origin: http://{host}\r\n\r\n").encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            parte = self.s.recv(4096)
            if not parte or len(resp) > 65536:
                raise ErroExportacao("WebSocket fechado no handshake")
            resp += parte
        cab, self.buf = resp.split(b"\r\n\r\n", 1)
        if b" 101 " not in cab.split(b"\r\n")[0]:
            raise ErroExportacao("WebSocket recusado pelo NVR")
        aceite = base64.b64encode(hashlib.sha1((chave + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        if aceite not in cab:
            raise ErroExportacao("resposta do WebSocket invalida")

    def _ler(self, n: int) -> bytes:
        while len(self.buf) < n:
            parte = self.s.recv(65536)
            if not parte:
                raise ErroExportacao("WebSocket fechado")
            self.buf += parte
        dados, self.buf = self.buf[:n], self.buf[n:]
        return dados

    def enviar(self, dados, opcode: int = 1) -> None:
        if isinstance(dados, str):
            dados = dados.encode("utf-8")
        mascara, n = os.urandom(4), len(dados)
        if n < 126:
            cab = bytes([0x80 | opcode, 0x80 | n])
        elif n < 65536:
            cab = bytes([0x80 | opcode, 0x80 | 126]) + struct.pack(">H", n)
        else:
            cab = bytes([0x80 | opcode, 0x80 | 127]) + struct.pack(">Q", n)
        self.s.sendall(cab + mascara + bytes(b ^ mascara[i % 4] for i, b in enumerate(dados)))

    def enviar_json(self, url: str, dados: dict) -> None:
        self.enviar(json.dumps({"url": url, "basic": {"ver": "1.0", "time": int(time.time() * 1000), "id": 1,
                                                      "nonce": random.randint(1, 2147483646)}, "data": dados}))

    def receber(self):
        """(opcode, dados) da proxima mensagem completa; responde ping."""
        partes, opcode = [], None
        while True:
            b0, b1 = self._ler(2)
            op, n = b0 & 0x0F, b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._ler(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._ler(8))[0]
            mascara = self._ler(4) if b1 & 0x80 else None
            dados = self._ler(n)
            if mascara:
                dados = bytes(b ^ mascara[i % 4] for i, b in enumerate(dados))
            if op == 9:
                self.enviar(dados, 10)
                continue
            if op == 10:
                continue
            if op == 8:
                raise ErroExportacao("WebSocket fechado pelo NVR")
            if op:
                opcode = op
            partes.append(dados)
            if b0 & 0x80:
                return opcode, b"".join(partes)

    def fechar(self) -> None:
        try:
            self.enviar(b"", 8)
        except OSError:
            pass
        try:
            self.s.close()
        except OSError:
            pass


def _codigo(msg: dict):
    return (msg.get("data") or {}).get("code") or (msg.get("basic") or {}).get("code")


def _exportar_h5(sessao, ip: str, limite: Optional[int], prazo: float) -> bytes:
    sid = getattr(sessao, "tvt_session_id", "") or ""
    if not sid:
        raise ErroExportacao("o login nao devolveu sessionId para o WebSocket")
    _pedir_exportacao(sessao, ip)
    host, porta = _separar_host(ip)
    ws = _WebSocket(host, porta, f"/requestWebsocketConnection?sessionID={sid}")
    try:
        while True:
            if time.monotonic() > prazo:
                raise ErroExportacao("tempo esgotado na autenticacao do WebSocket")
            op, d = ws.receber()
            if op == 1:
                msg = json.loads(d)
                if msg.get("url") == "/device/create_connection#response":
                    if _codigo(msg):
                        raise ErroExportacao(f"WebSocket nao autenticou (codigo {_codigo(msg)})")
                    break
        ws.enviar_json("/device/file/download/start", {"file_id": "config_file"})
        arquivo, indice = bytearray(), 0
        while True:
            if time.monotonic() > prazo:
                raise ErroExportacao("tempo esgotado na transferencia")
            op, d = ws.receber()
            if op == 2:
                cab = 8 if struct.unpack("<I", d[:4])[0] == 0 else 16
                arquivo += d[struct.unpack("<I", d[4:8])[0] + cab:]
                _verificar_limite(len(arquivo), limite)
                indice += 1
                ws.enviar_json("/device/file/download/step#response", {"index": indice})
                continue
            msg = json.loads(d)
            codigo = _codigo(msg)
            if msg.get("url") == "/device/file/download/step" and codigo == _WS_FIM_DOWNLOAD:
                break
            if codigo and codigo != _WS_FIM_DOWNLOAD:
                raise ErroExportacao(f"NVR recusou o download (codigo {codigo})")
        ws.enviar_json("/device/file/download/stop", {})
        if not arquivo:
            raise ErroExportacao("o NVR nao enviou dados")
        return bytes(arquivo)
    finally:
        ws.fechar()


def _firmware_h5(sessao, ip: str) -> bool:
    """Firmware novo (H5/plugin v5) serve o modulo de download por WebSocket da propria tela."""
    try:
        r = sessao.get(f"http://{ip}/js/lib/websocket.download.js", timeout=10, verify=False)
        return r.status_code == 200 and b"download" in r.content
    except Exception:
        return False


# ─── API do modulo ───────────────────────────────────────────────────────────

def baixar_configuracao_motorola_memoria(nvr_ip: str, usuario: str, senha: str,
                                         limite: Optional[int] = None) -> Optional[bytes]:
    """Exporta a configuracao restauravel do NVR Motorola e devolve os bytes (None se falhou).
    LimiteMemoriaExcedido sobe para quem chamou (tunel do Mikrotik)."""
    prazo = time.monotonic() + PRAZO_TOTAL_S
    for tentativa in range(1, TENTATIVAS + 1):
        # Login HTTP novo a cada rodada: a sessao anterior pode ter caido junto com a conexao
        sessao = abrir_sessao_motorola(nvr_ip, usuario, senha)
        if sessao is None:
            logging.warning(f"  Config Motorola: login HTTP no NVR {nvr_ip} falhou.")
            return None  # senha errada/NVR fora: insistir so arriscaria bloquear o usuario
        caminhos = [("binario", lambda: _exportar_binario(sessao, nvr_ip, usuario, senha, limite, prazo)),
                    ("H5", lambda: _exportar_h5(sessao, nvr_ip, limite, prazo))]
        if _firmware_h5(sessao, nvr_ip):
            caminhos.reverse()
        for nome, exportar in caminhos:
            inicio = time.monotonic()
            try:
                dados = exportar()
                logging.info(f"  Config NVR Motorola em memoria ({len(dados):,} bytes, protocolo {nome}).")
                return dados
            except LimiteMemoriaExcedido:
                raise
            except (ErroExportacao, OSError, ValueError) as e:
                logging.warning(f"  Config Motorola pelo protocolo {nome} falhou apos "
                                f"{time.monotonic() - inicio:.0f}s: {e}")
            except Exception:
                logging.warning(f"  Config Motorola pelo protocolo {nome} falhou.", exc_info=True)
        if tentativa < TENTATIVAS and time.monotonic() + PAUSA_NOVA_TENTATIVA_S < prazo:
            logging.info(f"  Nova tentativa da config Motorola em {PAUSA_NOVA_TENTATIVA_S}s...")
            time.sleep(PAUSA_NOVA_TENTATIVA_S)
        else:
            break
    return None


def baixar_configuracao_motorola(nvr_ip: str, usuario: str, senha: str, destino: Path) -> bool:
    """Grava a configuracao restauravel do NVR Motorola em `destino`. True se deu certo."""
    dados = baixar_configuracao_motorola_memoria(nvr_ip, usuario, senha)
    if dados is None:
        return False
    destino.write_bytes(dados)
    logging.info(f"  Backup NVR Motorola OK ({len(dados):,} bytes -> {destino.name}).")
    return True
