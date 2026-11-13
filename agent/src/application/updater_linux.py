"""OTA do agente Linux (container no Mikrotik, >= 1.1.52).

Diferente do Windows, não troca executável: baixa só o CÓDIGO do agente (TrilanAgentLinux.tar.gz, Python puro)
e o grava numa pasta persistente. As bibliotecas compiladas para ARM continuam as da imagem.

Pastas (em TRILAN_CODE_DIR, padrão /app/data/code):
- atual/     código em uso (o launcher_linux.py roda daqui quando é mais novo que o da imagem)
- anterior/  versão anterior, para o launcher voltar se a nova não subir
- pendente   versão nova ainda não confirmada; o launcher conta as tentativas e desfaz após 3 falhas
- falhou     versão que o launcher desfez; não é baixada de novo por 24 h

Fluxo: update-check (plataforma=linux) -> download -> SHA-256 -> extração segura -> confere versão e sintaxe
-> troca as pastas -> o serviço encerra e o launcher sobe o código novo -> o 1º ping bem-sucedido confirma.
"""
import hashlib
import logging
import os
import re
import shutil
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
    try:
        linhas = (pasta / "requirements-linux.txt").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    return sorted(l.strip().lower() for l in linhas if l.strip() and not l.strip().startswith("#"))


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
        r = requests.get(f"{server_url}/api/v1/agent/update-check", headers=headers, timeout=20, verify=False,
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
        # Biblioteca nova exige imagem nova (compilada para ARM): o código sozinho não basta
        imagem = Path(os.getenv("TRILAN_AGENT_DIR", "/app"))
        req_img, req_novo = _requisitos(imagem), _requisitos(NOVO)
        if req_img is not None and req_novo is not None and req_img != req_novo:
            LOG.error("[OTA] A versão %s muda o requirements-linux.txt: precisa de imagem nova do container. "
                      "Atualização ignorada.", versao)
            return False
        if not _sintaxe_ok(NOVO):
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
