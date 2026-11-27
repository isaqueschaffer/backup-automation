"""OTA do agente Linux (container no Mikrotik, >= 1.1.52).

Diferente do Windows, não troca executável: baixa só o CÓDIGO do agente (TrilanAgentLinux.tar.gz, Python puro)
e o grava numa pasta persistente. As bibliotecas compiladas para ARM continuam as da imagem; uma biblioteca nova
do requirements-linux.txt é instalada com pip --user em PYTHONUSERBASE (/app/data/pyuser) quando há wheel pronta
(>= 1.1.58). Imagem nova só para biblioteca compilada sem wheel ARMv7 ou programa novo do sistema.

Pastas (em TRILAN_CODE_DIR, padrão /app/data/code):
- atual/     código em uso (o launcher_linux.py roda daqui quando é mais novo que o da imagem)
- anterior/  versão anterior, para o launcher voltar se a nova não subir
- pendente   versão nova ainda não confirmada; o launcher conta as tentativas e desfaz após 3 falhas
- falhou     versão que o launcher desfez; não é baixada de novo por 24 h

Fluxo: update-check (plataforma=linux) -> download -> SHA-256 -> extração segura -> confere versão e sintaxe
-> troca as pastas -> o serviço encerra e o launcher sobe o código novo -> o 1º ping bem-sucedido confirma.
"""
import hashlib
import importlib
import logging
import os
import re
import shutil
import site
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import requests

from src.application.updater import CURRENT_VERSION

LOG = logging.getLogger("trilan.updater_linux")

DIR_CODIGO = Path(os.getenv("TRILAN_CODE_DIR", "/app/data/code"))
ATUAL = DIR_CODIGO / "atual"
ANTERIOR = DIR_CODIGO / "anterior"
NOVO = DIR_CODIGO / "novo"
PENDENTE = DIR_CODIGO / "pendente"
FALHOU = DIR_CODIGO / "falhou"
TAMANHO_MAXIMO = 20 * 1024 * 1024        # o pacote tem ~1 MB; o roteador tem pouco espaço
BLOQUEIO_FALHA_S = 24 * 3600
PIP_TIMEOUT_S = 900                      # pip no ARMv7 é lento; só roda quando a versão pede biblioteca nova
_RE_VERSAO = re.compile(r"^\d+\.\d+\.\d+$")
_RE_CURRENT = re.compile(r'^CURRENT_VERSION\s*=\s*"([^"]+)"', re.M)


def _parse(v: str):
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except Exception:
        return (0, 0, 0)


def rodando_codigo_ota() -> bool:
    """True quando este processo roda o código baixado (atual/) e não o da imagem."""
    try:
        return ATUAL.resolve() in Path(__file__).resolve().parents
    except Exception:
        return False


def aguardando_confirmacao() -> bool:
    return rodando_codigo_ota() and PENDENTE.exists()


def confirmar() -> None:
    """Chamado após um ping bem-sucedido: a versão nova subiu e fala com o servidor."""
    if aguardando_confirmacao():
        try:
            PENDENTE.unlink()
            LOG.info("[OTA] Versão %s confirmada (ping ok).", CURRENT_VERSION)
        except OSError as exc:
            LOG.warning("[OTA] Não consegui confirmar a versão: %s", exc)


def _versao_do_codigo(pasta: Path) -> str:
    try:
        m = _RE_CURRENT.search((pasta / "src" / "application" / "updater.py").read_text(encoding="utf-8"))
        return m.group(1) if m else ""
    except OSError:
        return ""


def _requisitos(pasta: Path):
    """Linhas do requirements-linux.txt, sem comentários (None se o arquivo não existe)."""
    try:
        linhas = (pasta / "requirements-linux.txt").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    return [l.split("#", 1)[0].strip() for l in linhas if l.split("#", 1)[0].strip()]


def _requirement(linha: str):
    try:
        from packaging.requirements import Requirement
    except ImportError:
        from pip._vendor.packaging.requirements import Requirement
    return Requirement(linha)


def _satisfeito(linha: str) -> bool:
    """True se a biblioteca está instalada (imagem ou pasta da OTA) numa versão que atende a linha."""
    import importlib.metadata as md
    try:
        req = _requirement(linha)
    except Exception:
        LOG.warning("[OTA] Linha do requirements-linux.txt não entendida: %r", linha[:80])
        return False
    if req.marker is not None and not req.marker.evaluate():
        return True
    try:
        versao = md.version(req.name)
    except md.PackageNotFoundError:
        return False
    return req.specifier.contains(versao, prereleases=True)


def _pasta_pip_user() -> Path:
    base = Path(os.environ.setdefault("PYTHONUSERBASE", "/app/data/pyuser"))
    return base / "lib" / f"python{sys.version_info[0]}.{sys.version_info[1]}" / "site-packages"


def _instalar_com_pip(faltam: list) -> bool:
    """Instala as que faltam com pip --user na pasta persistente, só com wheel pronta (nada é compilado no
    roteador): bibliotecas Python puras passam; uma compilada sem wheel ARMv7 falha e pede imagem nova."""
    cmd = [sys.executable, "-m", "pip", "install", "--user", "--only-binary=:all:", "--no-cache-dir",
           "--disable-pip-version-check", "--no-warn-script-location", "--quiet", *faltam]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=PIP_TIMEOUT_S,
                           env=dict(os.environ))
    except Exception as exc:
        LOG.error("[OTA] pip não rodou: %s", exc)
        return False
    if r.returncode != 0:
        LOG.error("[OTA] pip falhou (código %s): %s", r.returncode, (r.stderr or r.stdout or "").strip()[-500:])
        return False
    pasta = _pasta_pip_user()
    if pasta.is_dir() and str(pasta) not in sys.path:
        site.addsitedir(str(pasta))
    importlib.invalidate_caches()
    return True


def garantir_requisitos(pasta: Path) -> bool:
    """Confere se as bibliotecas pedidas pela versão nova estão instaladas e instala as que faltam (>= 1.1.58).
    Antes, qualquer mudança no requirements-linux.txt exigia imagem nova do container."""
    linhas = _requisitos(pasta)
    if not linhas:
        return True
    faltam = [l for l in linhas if not _satisfeito(l)]
    if not faltam:
        return True
    LOG.warning("[OTA] Bibliotecas que a versão nova pede e a imagem não tem: %s. Instalando...", ", ".join(faltam))
    if not _instalar_com_pip(faltam):
        return False
    ainda = [l for l in faltam if not _satisfeito(l)]
    if ainda:
        LOG.error("[OTA] Continuam faltando depois do pip: %s", ", ".join(ainda))
        return False
    LOG.info("[OTA] Bibliotecas instaladas: %s", ", ".join(faltam))
    return True


def _bloqueada(versao: str) -> bool:
    try:
        return (FALHOU.read_text(encoding="utf-8").strip() == versao
                and time.time() - FALHOU.stat().st_mtime < BLOQUEIO_FALHA_S)
    except OSError:
        return False


def _extrair(pacote: Path, destino: Path) -> None:
    """Extrai só arquivos e pastas comuns, sem caminho absoluto, '..' ou links."""
    with tarfile.open(pacote, "r:gz") as tar:
        membros = tar.getmembers()
        for m in membros:
            nome = m.name.replace("\\", "/")
            if nome.startswith("/") or ".." in nome.split("/") or not (m.isfile() or m.isdir()):
                raise ValueError(f"item recusado no pacote: {m.name}")
        try:
            tar.extractall(destino, members=membros, filter="data")
        except TypeError:   # Python sem o parâmetro filter (< 3.11.4); a checagem acima já vale
            tar.extractall(destino, members=membros)


def _sintaxe_ok(pasta: Path) -> bool:
    for arq in pasta.rglob("*.py"):
        try:
            compile(arq.read_bytes(), str(arq), "exec")
        except SyntaxError as exc:
            LOG.error("[OTA] Erro de sintaxe no pacote (%s): %s", arq.name, exc)
            return False
    return True


def verificar_e_instalar(conf: dict) -> bool:
    """Retorna True quando instalou uma versão nova: o chamador deve encerrar o processo para o launcher subi-la."""
    server_url = conf.get("server_url", "").rstrip("/")
    headers = {"X-Client-ID": conf.get("client_id", ""), "X-API-Key": conf.get("api_key", "")}
    try:
        # Certificado validado (AGT-01, auditoria de 25/11/2026): a resposta escolhe a URL e o SHA-256 do pacote que
        # será executado; com verify=False quem interceptasse a conexão trocaria os dois e rodaria código no container.
        r = requests.get(f"{server_url}/api/v1/agent/update-check", headers=headers, timeout=20,
                         params={"current_version": CURRENT_VERSION, "plataforma": "linux"})
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        LOG.warning("[OTA] Falha ao verificar atualização: %s", exc)
        return False
    if not data.get("has_update"):
        LOG.info("[OTA] Versão atual (%s) está atualizada.", CURRENT_VERSION)
        return False

    versao = str(data.get("version") or "").strip()
    url = str(data.get("url_linux") or "")
    sha = str(data.get("sha256_linux") or "").lower()
    if not _RE_VERSAO.match(versao) or _parse(versao) <= _parse(CURRENT_VERSION):
        LOG.warning("[OTA] Versão oferecida inválida ou não mais nova: %r", versao[:40])
        return False
    if not url.lower().startswith("https://") or not re.fullmatch(r"[0-9a-f]{64}", sha):
        LOG.error("[OTA] Pacote Linux sem https:// ou sem SHA-256 válido. Atualização ignorada.")
        return False
    if _bloqueada(versao):
        LOG.warning("[OTA] Versão %s falhou ao subir há menos de 24 h; não será instalada de novo agora.", versao)
        return False

    LOG.info("[OTA] Atualização encontrada: %s -> %s. Baixando pacote...", CURRENT_VERSION, versao)
    DIR_CODIGO.mkdir(parents=True, exist_ok=True)
    pacote = DIR_CODIGO / "pacote.tar.gz"
    shutil.rmtree(NOVO, ignore_errors=True)
    try:
        h = hashlib.sha256()
        total = 0
        with requests.get(url, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            with open(pacote, "wb") as f:
                for bloco in resp.iter_content(65536):
                    total += len(bloco)
                    if total > TAMANHO_MAXIMO:
                        raise ValueError("pacote maior que o limite")
                    h.update(bloco)
                    f.write(bloco)
        if h.hexdigest() != sha:
            LOG.error("[OTA] FALHA DE INTEGRIDADE: esperado %s, recebido %s. Cancelado.", sha, h.hexdigest())
            return False
        NOVO.mkdir(parents=True)
        _extrair(pacote, NOVO)
        if not (NOVO / "service_linux.py").is_file():
            LOG.error("[OTA] Pacote sem service_linux.py. Cancelado.")
            return False
        if _versao_do_codigo(NOVO) != versao:
            LOG.error("[OTA] Pacote é da versão %r, não da %s. Cancelado.", _versao_do_codigo(NOVO), versao)
            return False
        if not _sintaxe_ok(NOVO):
            return False
        # Biblioteca nova: instalada aqui se for Python puro; compilada sem wheel ARMv7 exige imagem nova
        if not garantir_requisitos(NOVO):
            LOG.error("[OTA] A versão %s pede biblioteca que não deu para instalar: precisa de imagem nova do "
                      "container. Atualização ignorada.", versao)
            return False
        # Troca: atual -> anterior, novo -> atual. O processo encerra logo em seguida.
        shutil.rmtree(ANTERIOR, ignore_errors=True)
        if ATUAL.exists():
            ATUAL.rename(ANTERIOR)
        NOVO.rename(ATUAL)
        PENDENTE.write_text("0", encoding="utf-8")
        LOG.warning("[OTA] Versão %s instalada; reiniciando o agente para aplicá-la.", versao)
        return True
    except Exception as exc:
        LOG.error("[OTA] Falha ao instalar a versão %s: %s", versao, exc)
        return False
    finally:
        try:
            pacote.unlink()
        except OSError:
            pass
        shutil.rmtree(NOVO, ignore_errors=True)
