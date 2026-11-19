"""
Origem SFTP (agente do Mikrotik): lê os arquivos de backup de uma máquina do cliente (Windows com OpenSSH Server ou
Linux) por SSH/SFTP, em blocos, direto para o ZIP em fluxo do túnel. Nada é criado na máquina do cliente (sem usuário
novo, sem share, sem porta 445) e nada é gravado no roteador.

Segurança:
- SOMENTE LEITURA: `PastaSftp` só expõe listar/stat/tamanho/abrir("rb"). Nunca escreve, renomeia nem apaga.
- Todo caminho é normalizado e precisa ficar dentro da `pasta_origem` cadastrada (`..` é recusado).
- Chave do host verificada como no OpenSSH (TOFU): a 1ª conexão grava a impressão digital em
  `data/known_hosts_trilan` (arquivo de configuração, minúsculo); nas seguintes, chave diferente = recusa.
  Se o cadastro trouxer `ssh_fingerprint` (SHA256:...), ela prevalece e é exigida.
- Autenticação por senha ou por chave privada (PEM/OpenSSH, em memória; nunca vai ao disco). Senha e chave nunca
  entram no log.
"""
import base64
import hashlib
import io
import logging
import os
import posixpath
import re
import stat as _stat
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import paramiko

TIMEOUT_CONEXAO_S = 20
TIMEOUT_SOCKET_S = 120       # sem resposta por esse tempo = a leitura falha (nunca fica pendurada)
JANELA_PEDIDOS = 64          # pedidos de 32 KB em voo por vez (~2 MB): leitura em lote sem encher a memória
TAM_PEDIDO = 32768
_LOCK_ARQUIVO = threading.Lock()
_LOCK_REGISTRO = threading.Lock()
_CONEXOES: Dict[tuple, "ConexaoSftp"] = {}


class ErroSftp(Exception):
    """Falha de acesso por SSH/SFTP (a mensagem já vem em português e sem segredos)."""


class ErroChaveHost(ErroSftp):
    """A chave SSH do host não confere com a conhecida/cadastrada."""


# ─── caminhos ────────────────────────────────────────────────────────────────

def para_sftp(pasta: str) -> str:
    """Converte o formato do cadastro para o caminho do servidor SFTP.
    `D:UNM2000/emsback`, `D:\\UNM2000\\emsback`, `host:D:\\x` -> `/D:/UNM2000/emsback` (OpenSSH do Windows);
    `/var/backups` continua `/var/backups`. Recusa `..`, caminho relativo e caminho de rede (`\\\\host\\share`)."""
    p = (pasta or "").strip().strip('"').strip("'")
    if not p:
        raise ErroSftp("pasta de backup não informada")
    if p.startswith("\\\\") or p.startswith("//"):
        raise ErroSftp("caminho de rede (\\\\servidor\\pasta) não serve para SFTP; use o caminho local da máquina, "
                       "ex.: D:\\UNM2000\\emsback")
    # "host:D:\x" (prefixo de host aceito no cadastro para SMB): descarta o host
    m = re.match(r"^[^\\/:]{2,}:([A-Za-z]:.*)$", p)
    if m:
        p = m.group(1)
    p = p.replace("\\", "/")
    m = re.match(r"^([A-Za-z]):/*(.*)$", p)
    if m:
        resto = m.group(2)
        partes = [x for x in resto.split("/") if x not in ("", ".")]
        if ".." in partes:
            raise ErroSftp("caminho com '..' não é permitido")
        return "/" + m.group(1).upper() + ":" + ("/" + "/".join(partes) if partes else "/")
    if not p.startswith("/"):
        raise ErroSftp(f"caminho '{pasta}' não é absoluto (use D:\\pasta ou /pasta)")
    partes = [x for x in p.split("/") if x not in ("", ".")]
    if ".." in partes:
        raise ErroSftp("caminho com '..' não é permitido")
    return "/" + "/".join(partes)


def _sem_barra_final(c: str) -> str:
    return c if c in ("/", "") or re.fullmatch(r"/[A-Za-z]:/", c) else c.rstrip("/")


def unir(base: str, nome: str) -> str:
    return base.rstrip("/") + "/" + nome if base else nome


# ─── chave do host (TOFU) ────────────────────────────────────────────────────

def arquivo_known_hosts() -> Path:
    env = os.environ.get("TRILAN_KNOWN_HOSTS")
    if env:
        return Path(env)
    from src.core.config import DIR_AGENT
    return DIR_AGENT / "data" / "known_hosts_trilan"


def impressao_digital(chave: paramiko.PKey) -> str:
    """Formato do OpenSSH moderno: SHA256:<base64 sem '=' >."""
    return "SHA256:" + base64.b64encode(hashlib.sha256(chave.asbytes()).digest()).decode().rstrip("=")


def _normalizar_fp(fp: str) -> str:
    fp = (fp or "").strip()
    if fp.upper().startswith("SHA256:"):
        fp = fp[7:]
    return fp.rstrip("=")


class _PoliticaTofu(paramiko.MissingHostKeyPolicy):
    """Chamada pelo paramiko só quando o host NÃO tem chave conhecida (chave conhecida diferente já vira
    BadHostKeyException lá dentro). Com fingerprint cadastrada: exige igualdade. Sem ela: grava (1ª conexão)."""

    def __init__(self, arquivo: Path, fingerprint: Optional[str]):
        self.arquivo = arquivo
        self.fingerprint = _normalizar_fp(fingerprint) if fingerprint else ""

    def missing_host_key(self, client, hostname, key):
        fp = impressao_digital(key)
        if self.fingerprint:
            if _normalizar_fp(fp) != self.fingerprint:
                raise ErroChaveHost(f"a impressão digital da chave SSH de {hostname} ({fp}) não confere com a "
                                    f"cadastrada; conexão recusada")
            return
        with _LOCK_ARQUIVO:
            self.arquivo.parent.mkdir(parents=True, exist_ok=True)
            with open(self.arquivo, "a", encoding="utf-8") as f:
                f.write(f"{hostname} {key.get_name()} {key.get_base64()}\n")
        client.get_host_keys().add(hostname, key.get_name(), key)
        logging.warning(f"  [SSH] Primeira conexão com {hostname}: chave {key.get_name()} {fp} gravada. "
                        f"Confira a impressão digital no equipamento (ou cadastre em 'ssh_fingerprint'); "
                        f"se mudar depois, a conexão será recusada.", extra={"enviar_servidor": True})


def carregar_chave(texto: str) -> paramiko.PKey:
    """Chave privada em memória (ed25519, RSA ou ECDSA; formato OpenSSH ou PEM, sem senha)."""
    t = (texto or "").replace("\r\n", "\n").strip() + "\n"
    ultimo = None
    for cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            return cls.from_private_key(io.StringIO(t))
        except Exception as e:      # tipo errado, formato inválido ou protegida por senha
            ultimo = e
    raise ErroSftp(f"chave privada SSH inválida ou protegida por senha ({type(ultimo).__name__})")


def abrir_ssh(host: str, porta: int, usuario: str, senha: Optional[str] = None, chave: Optional[str] = None,
              fingerprint: Optional[str] = None, timeout: float = TIMEOUT_CONEXAO_S, **extra) -> paramiko.SSHClient:
    """Conexão SSH com a chave do host verificada (TOFU ou fingerprint cadastrada). Nunca usa AutoAddPolicy.
    `extra` vai ao `connect` (ex.: `disabled_algorithms` das OLTs Huawei antigas)."""
    if not (senha or chave):
        raise ErroSftp(f"faltam senha ou chave privada de SSH para {host}")
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(_PoliticaTofu(arquivo_known_hosts(), fingerprint))
    if not fingerprint:
        try:
            if arquivo_known_hosts().exists():
                cli.get_host_keys().load(str(arquivo_known_hosts()))
        except Exception as e:
            logging.warning(f"  [SSH] Não foi possível ler {arquivo_known_hosts().name}: {e}")
    pkey = carregar_chave(chave) if chave else None
    try:
        cli.connect(host, port=porta, username=usuario, password=None if pkey else senha, pkey=pkey,
                    timeout=timeout, banner_timeout=timeout, auth_timeout=timeout,
                    look_for_keys=False, allow_agent=False, **extra)
        return cli
    except paramiko.BadHostKeyException:
        cli.close()
        raise ErroChaveHost(f"a chave SSH de {host} mudou desde a primeira conexão; conexão recusada "
                            f"(se a troca foi legítima, apague a linha do host em {arquivo_known_hosts().name} "
                            f"ou atualize 'ssh_fingerprint')") from None
    except ErroSftp:
        cli.close()
        raise
    except paramiko.AuthenticationException:
        cli.close()
        raise ErroSftp(f"usuário/senha ou chave de SSH recusados por {host}:{porta}") from None
    except Exception as e:
        cli.close()
        # ErroChaveHost levantado dentro da política chega embrulhado em alguns caminhos do paramiko
        causa = e if isinstance(e, ErroSftp) else getattr(e, "__cause__", None)
        if isinstance(causa, ErroChaveHost):
            raise causa
        raise ErroSftp(f"falha de conexão SSH em {host}:{porta}: {type(e).__name__}: {e}") from None


# ─── conexão e pasta (somente leitura) ───────────────────────────────────────

@dataclass
class EntradaSftp:
    name: str
    is_dir: bool
    size: int
    mtime: float
    path: str


class ConexaoSftp:
    """Uma conexão SSH + sessão SFTP por host, reaproveitada durante o backup e fechada no fim."""

    def __init__(self, host: str, porta: int, usuario: str, senha: Optional[str] = None, chave: Optional[str] = None,
                 fingerprint: Optional[str] = None, timeout: float = TIMEOUT_SOCKET_S, **extra_ssh):
        self.host, self.porta, self.usuario = host, porta, usuario
        self._senha, self._chave, self._fp, self._extra = senha, chave, fingerprint, extra_ssh
        self._timeout = timeout
        self.ssh: Optional[paramiko.SSHClient] = None
        self._sftp: Optional[paramiko.SFTPClient] = None
        self._lock = threading.Lock()

    def conectar(self) -> "ConexaoSftp":
        with self._lock:
            if self.ssh is not None and self.ssh.get_transport() is not None and self.ssh.get_transport().is_active():
                return self
            self.fechar()
            self.ssh = abrir_ssh(self.host, self.porta, self.usuario, self._senha, self._chave, self._fp,
                                 **self._extra)
            return self

    def sftp(self) -> paramiko.SFTPClient:
        self.conectar()
        with self._lock:
            if self._sftp is None:
                try:
                    self._sftp = self.ssh.open_sftp()
                    self._sftp.get_channel().settimeout(self._timeout)
                except Exception as e:
                    raise ErroSftp(f"{self.host} não ofereceu SFTP (o servidor SSH precisa ter o subsistema sftp): "
                                   f"{e}") from None
            return self._sftp

    def fechar(self) -> None:
        for obj in (self._sftp, self.ssh):
            try:
                if obj is not None:
                    obj.close()
            except Exception:
                pass
        self._sftp = None
        self.ssh = None


def obter_conexao(host: str, porta: int, usuario: str, senha: Optional[str] = None, chave: Optional[str] = None,
                  fingerprint: Optional[str] = None, **extra_ssh) -> ConexaoSftp:
    """Conexão compartilhada por (host, porta, usuário) durante o backup; `fechar_todas()` no fim."""
    k = (host, int(porta), usuario)
    with _LOCK_REGISTRO:
        con = _CONEXOES.get(k)
        if con is None:
            con = _CONEXOES[k] = ConexaoSftp(host, int(porta), usuario, senha, chave, fingerprint, **extra_ssh)
    return con.conectar()


def fechar_todas() -> None:
    with _LOCK_REGISTRO:
        conexoes = list(_CONEXOES.values())
        _CONEXOES.clear()
    for c in conexoes:
        c.fechar()


class ArquivoSftp:
    """Leitura em blocos de um arquivo remoto: pedidos de 32 KB em lote (rápido) e janela limitada (~2 MB)."""

    def __init__(self, arq: paramiko.SFTPFile, tamanho: int):
        self._arq, self._tam = arq, tamanho
        self._pos = 0
        self._buf = bytearray()

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = max(self._tam - self._pos + len(self._buf), 0)
        while len(self._buf) < n and self._pos < self._tam:
            blocos = [(self._pos + i * TAM_PEDIDO, TAM_PEDIDO) for i in range(JANELA_PEDIDOS)
                      if self._pos + i * TAM_PEDIDO < self._tam]
            lido = 0
            for dados in self._arq.readv(blocos):
                self._buf += dados
                lido += len(dados)
                if len(dados) < TAM_PEDIDO:
                    break
            if lido == 0:
                break           # fim antes do tamanho informado: quem chamou confere os bytes lidos
            self._pos += lido
            if lido < len(blocos) * TAM_PEDIDO:
                self._tam = self._pos       # arquivo encolheu: não insiste
        saida = bytes(self._buf[:n])
        del self._buf[:n]
        return saida

    def close(self) -> None:
        try:
            self._arq.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class PastaSftp:
    """Visão SOMENTE LEITURA de uma pasta (`raiz`) de um host. Todo acesso é conferido contra a raiz."""

    def __init__(self, conexao: ConexaoSftp, raiz: str, relativo: bool = False):
        """`relativo=True`: raiz = home do usuário e só nomes de arquivo simples (RouterOS)."""
        self.conexao = conexao
        self.relativo = relativo
        self.raiz = "" if relativo else _sem_barra_final(para_sftp(raiz))
        self._ci = self.raiz[2:3] == ":"        # drive do Windows: sem diferença de maiúsculas

    @classmethod
    def de_cadastro(cls, conexao: ConexaoSftp, pasta_origem: str) -> "PastaSftp":
        return cls(conexao, pasta_origem)

    def _conferir(self, caminho: str) -> str:
        if self.relativo:
            if not caminho or "/" in caminho or "\\" in caminho or caminho in (".", ".."):
                raise ErroSftp(f"caminho '{caminho}' fora do permitido")
            return caminho
        c = (caminho or "").replace("\\", "/")
        if ".." in c.split("/"):
            raise ErroSftp("caminho com '..' não é permitido")
        c = _sem_barra_final(posixpath.normpath(c))
        if re.fullmatch(r"/[A-Za-z]:", c):
            c += "/"            # raiz do drive: normpath tira a barra
        a, b = (c.lower(), self.raiz.lower()) if self._ci else (c, self.raiz)
        if not (a == b or a.startswith(b.rstrip("/") + "/")):
            raise ErroSftp(f"caminho '{caminho}' fora da pasta de backup configurada")
        return c

    def listar(self, caminho: Optional[str] = None) -> List[EntradaSftp]:
        c = self._conferir(caminho if caminho is not None else self.raiz)
        try:
            attrs = self.conexao.sftp().listdir_attr(c)
        except Exception as e:
            raise ErroSftp(f"falha ao listar {c}: {e}") from None
        return [EntradaSftp(a.filename, _stat.S_ISDIR(a.st_mode or 0), a.st_size or 0, float(a.st_mtime or 0),
                            unir(c, a.filename)) for a in attrs]

    def stat(self, caminho: str) -> EntradaSftp:
        c = self._conferir(caminho)
        try:
            a = self.conexao.sftp().stat(c)
        except Exception as e:
            raise ErroSftp(f"falha ao ler {c}: {e}") from None
        return EntradaSftp(posixpath.basename(c), _stat.S_ISDIR(a.st_mode or 0), a.st_size or 0,
                           float(a.st_mtime or 0), c)

    def tamanho(self, caminho: str) -> int:
        """Tamanho do arquivo; de uma pasta, a soma recursiva."""
        e = self.stat(caminho)
        if not e.is_dir:
            return e.size
        return sum(self.tamanho(x.path) if x.is_dir else x.size for x in self.listar(e.path))

    def abrir(self, caminho: str) -> ArquivoSftp:
        c = self._conferir(caminho)
        try:
            tam = self.stat(c).size
            return ArquivoSftp(self.conexao.sftp().open(c, "rb"), tam)
        except ErroSftp:
            raise
        except Exception as e:
            raise ErroSftp(f"falha ao abrir {c}: {e}") from None


# ─── cadastro (config_extra) ─────────────────────────────────────────────────

def usa_sftp(config_extra: dict) -> bool:
    """`acesso_remoto == "sftp"`. Cadastro antigo (campo ausente) mantém o comportamento anterior (SMB)."""
    return str((config_extra or {}).get("acesso_remoto") or "").strip().lower() == "sftp"


def conexao_do_cadastro(equipamento: dict, config_extra: dict) -> Tuple[Optional[ConexaoSftp], str]:
    """Conexão (compartilhada) a partir do cadastro. (None, motivo) se faltar dado ou a conexão falhar."""
    ip = (equipamento.get("ip") or "").strip()
    host = (config_extra.get("smb_host") or "").strip() or (ip if ip not in ("127.0.0.1", "localhost") else "")
    if not host:
        return None, "IP da máquina do cliente não informado."
    usuario = (config_extra.get("ssh_usuario") or "").strip()
    senha = config_extra.get("ssh_senha") or None
    chave = config_extra.get("ssh_chave") or None
    if not usuario or not (senha or chave):
        return None, "Faltam usuário e senha (ou chave privada) de SSH no cadastro."
    try:
        porta = int(config_extra.get("ssh_porta") or 22)
    except (ValueError, TypeError):
        porta = 22
    try:
        con = obter_conexao(host, porta, usuario, senha, chave, (config_extra.get("ssh_fingerprint") or None))
        con.sftp()
        return con, f"SFTP em {host}:{porta}"
    except ErroSftp as e:
        return None, str(e)
