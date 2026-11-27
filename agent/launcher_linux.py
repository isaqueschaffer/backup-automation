"""Processo principal do container do agente Linux (Mikrotik, >= 1.1.52). Fica só na imagem; a OTA não o troca.

- Roda o service_linux.py da pasta da OTA (/app/data/code/atual) quando ela tem versão mais nova que a da
  imagem; senão, o da imagem (/app). Imagem mais nova que a pasta (container recriado) descarta a pasta.
- Quando o agente encerra (reinício pedido pelo painel, versão nova instalada ou falha), sobe de novo.
- Versão nova ainda não confirmada (arquivo "pendente") que cai 3 vezes é desfeita: volta à anterior (ou à da
  imagem) e grava a versão em "falhou" para não ser baixada de novo por 24 h.
- Repassa SIGTERM/SIGINT ao agente (parada do container no RouterOS).
"""
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

IMAGEM = Path(__file__).resolve().parent
DIR_CODIGO = Path(os.getenv("TRILAN_CODE_DIR", "/app/data/code"))
ATUAL = DIR_CODIGO / "atual"
ANTERIOR = DIR_CODIGO / "anterior"
PENDENTE = DIR_CODIGO / "pendente"
FALHOU = DIR_CODIGO / "falhou"
MAX_TENTATIVAS = 3
_RE_CURRENT = re.compile(r'^CURRENT_VERSION\s*=\s*"([^"]+)"', re.M)

parar = False
filho = None


def log(msg):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} LAUNCHER {msg}", flush=True)


def versao(pasta: Path) -> str:
    try:
        m = _RE_CURRENT.search((pasta / "src" / "application" / "updater.py").read_text(encoding="utf-8"))
        return m.group(1) if m else ""
    except OSError:
        return ""


def parse(v: str):
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except Exception:
        return (0, 0, 0)


def valida(pasta: Path) -> bool:
    return (pasta / "service_linux.py").is_file() and parse(versao(pasta)) > parse(versao(IMAGEM))


def desfazer():
    """A versão nova não subiu: volta à anterior (se ainda for mais nova que a imagem) ou à da imagem."""
    ruim = versao(ATUAL)
    log(f"versão {ruim or '?'} não subiu após {MAX_TENTATIVAS} tentativas: desfazendo")
    try:
        FALHOU.write_text(ruim, encoding="utf-8")
    except OSError:
        pass
    shutil.rmtree(ATUAL, ignore_errors=True)
    if valida(ANTERIOR):
        ANTERIOR.rename(ATUAL)
        log(f"voltou para a versão {versao(ATUAL)}")
    else:
        shutil.rmtree(ANTERIOR, ignore_errors=True)
        log(f"voltou para a versão da imagem {versao(IMAGEM)}")
    try:
        PENDENTE.unlink()
    except OSError:
        pass


def escolher() -> Path:
    if PENDENTE.exists() and not ATUAL.exists():
        try:
            PENDENTE.unlink()
        except OSError:
            pass
    if PENDENTE.exists():
        try:
            n = int(PENDENTE.read_text(encoding="utf-8").strip() or "0") + 1
        except (OSError, ValueError):
            n = 1
        if n > MAX_TENTATIVAS:
            desfazer()
        else:
            try:
                PENDENTE.write_text(str(n), encoding="utf-8")
            except OSError:
                pass
            log(f"versão nova {versao(ATUAL)}: tentativa {n} de {MAX_TENTATIVAS}")
    if ATUAL.exists():
        if valida(ATUAL):
            return ATUAL
        log(f"código da OTA ({versao(ATUAL) or '?'}) não é mais novo que o da imagem ({versao(IMAGEM)}): descartado")
        shutil.rmtree(ATUAL, ignore_errors=True)
        try:
            PENDENTE.unlink()
        except OSError:
            pass
    return IMAGEM


def ao_sinal(signum, _frame):
    global parar
    parar = True
    if filho and filho.poll() is None:
        filho.send_signal(signum)


def main():
    signal.signal(signal.SIGTERM, ao_sinal)
    signal.signal(signal.SIGINT, ao_sinal)
    env = dict(os.environ)
    env.setdefault("TRILAN_AGENT_DIR", str(IMAGEM))   # agent.conf, logs e temporários sempre em /app
    env.setdefault("TRILAN_CODE_DIR", str(DIR_CODIGO))
    global filho
    while not parar:
        pasta = escolher()
        log(f"iniciando agente {versao(pasta) or '?'} de {pasta}")
        inicio = time.monotonic()
        filho = subprocess.Popen([sys.executable, "-u", str(pasta / "service_linux.py")], cwd=str(pasta), env=env)
        rc = filho.wait()
        if parar:
            break
        durou = time.monotonic() - inicio
        log(f"agente encerrou (código {rc}, {int(durou)} s)")
        # Saída normal (reinício/atualização): volta logo. Falha rápida: espera mais para não girar em laço.
        espera = 2 if rc == 0 else (30 if durou < 60 else 5)
        for _ in range(espera * 2):
            if parar:
                break
            time.sleep(0.5)
    log("container parando")


if __name__ == "__main__":
    main()
