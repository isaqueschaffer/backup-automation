"""Verificação da imagem do agente Linux (Mikrotik, 1.1.58): roda no fim do build (Dockerfile.mikrotik) e reprova a
imagem se faltar algo que o agente usa. Também serve para conferir um container já em uso:
    python verificar_imagem.py

Confere: programas do sistema (ffmpeg com RTSP/H.264/H.265/JPEG, ping), fuso horário, bibliotecas do
requirements-linux.txt nas versões pedidas, sintaxe de todos os .py e importação de todos os módulos do agente.
"""
import importlib
import os
import pkgutil
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

# O que o rtsp_client pede ao ffmpeg: RTSP por TCP/UDP, H.264/H.265/MJPEG/MPEG-4 e um JPEG na saída (image2pipe)
FFMPEG_PRECISA = {
    "-demuxers": ["rtsp", "h264", "hevc", "mjpeg"],
    "-muxers": ["image2pipe", "image2"],
    "-decoders": ["h264", "hevc", "mjpeg", "mpeg4"],
    "-encoders": ["mjpeg"],
    "-protocols": ["tcp", "udp", "rtp", "file", "pipe"],
}
# Programa e argumento que só imprime a versão (roda de verdade: pega biblioteca .so faltando)
# (sem mysqldump: o Mikrotik é ponte e não faz backup)
PROGRAMAS = {"ffmpeg": "-version", "ping": "-V"}
# Só do Windows (serviço, bandeja, GPU): não entram na verificação de importação
SO_WINDOWS = ("win32", "pystray", "GPUtil", "servicemanager", "imageio_ffmpeg")
falhas = []


def falha(msg):
    falhas.append(msg)
    print("FALHA", msg)


def ok(msg):
    print("ok   ", msg)


def programas():
    for nome, arg in PROGRAMAS.items():
        caminho = shutil.which(nome)
        if not caminho:
            falha(f"programa ausente: {nome}")
            continue
        r = subprocess.run([caminho, arg], capture_output=True, text=True, errors="replace")
        primeira = ((r.stdout or r.stderr).strip().splitlines() or [""])[0][:80]
        ok(f"{nome}: {primeira}") if r.returncode == 0 else falha(f"{nome} não roda: {(r.stderr or '').strip()[:200]}")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return
    for opcao, itens in FFMPEG_PRECISA.items():
        saida = subprocess.run([ffmpeg, "-hide_banner", opcao], capture_output=True, text=True).stdout
        palavras = {p for linha in saida.splitlines() for p in linha.replace(",", " ").split()}
        faltam = [i for i in itens if i not in palavras]
        falha(f"ffmpeg sem {opcao[1:]}: {', '.join(faltam)}") if faltam else ok(f"ffmpeg {opcao[1:]}: {', '.join(itens)}")


def fuso():
    tz = os.environ.get("TZ", "")
    if not tz:
        falha("TZ não definido (o container ficaria em UTC: horário do backup e janela da noite errados)")
    elif not Path("/usr/share/zoneinfo", tz).is_file():
        falha(f"fuso {tz} sem dados em /usr/share/zoneinfo")
    else:
        ok(f"fuso {tz} ({time.strftime('%Z %z')})")


def bibliotecas():
    from src.application.updater_linux import _requisitos, _satisfeito
    for linha in _requisitos(BASE) or []:
        ok(f"biblioteca {linha}") if _satisfeito(linha) else falha(f"biblioteca ausente ou fora da versão: {linha}")


def sintaxe():
    n = 0
    for arq in list(BASE.glob("*.py")) + list((BASE / "src").rglob("*.py")):
        try:
            compile(arq.read_bytes(), str(arq), "exec")
            n += 1
        except SyntaxError as exc:
            falha(f"sintaxe: {arq.relative_to(BASE)}: {exc}")
    ok(f"sintaxe de {n} arquivos")


def importacoes():
    import src
    n = 0
    for m in pkgutil.walk_packages(src.__path__, "src."):
        try:
            importlib.import_module(m.name)
            n += 1
        except Exception as exc:
            if not any(w in str(exc) for w in SO_WINDOWS):
                falha(f"importação: {m.name}: {type(exc).__name__}: {exc}")
    for nome in ("service_linux", "launcher_linux"):
        try:
            importlib.import_module(nome)
            n += 1
        except Exception as exc:
            falha(f"importação: {nome}: {type(exc).__name__}: {exc}")
    ok(f"importação de {n} módulos")


def tunel():
    """Autoteste do backup em túnel: monta em memória o ZIP com senha (AES) com outro ZIP dentro, sem seek e sem
    arquivo, e confere o conteúdo. Pega aqui, no build, qualquer problema de zipfile/pyzipper/cripto no ARMv7."""
    import hashlib
    import io
    import threading
    import zipfile
    from types import SimpleNamespace
    from unittest import mock

    import pyzipper
    from src.backup import tunel as t

    dados = os.urandom(3 * 1024 * 1024 + 5)

    class SmbFalso:
        def stat(self, p):
            return SimpleNamespace(st_size=len(dados))

        def open_file(self, p, mode="rb"):
            return io.BytesIO(dados)

    origem = SimpleNamespace(remote_path="remoto-falso", path="x", is_smb=True, file_type="UNM2000")
    pronto = {"nome": "T", "pasta_zip": "OLT/backup_olt_T", "arquivos_origem": [(origem, "x.zip")]}
    fila, falha_montagem = t.FilaSaida(), {}
    with mock.patch.object(t, "_smbclient", return_value=SmbFalso()):
        th = threading.Thread(target=t._produtor, args=(fila, [pronto], "segredo", falha_montagem))
        th.start()
        corpo = b"".join(fila.pedacos())
        th.join()
    with pyzipper.AESZipFile(io.BytesIO(corpo)) as ext:
        ext.setpassword(b"segredo")
        if ext.testzip() is not None:
            raise RuntimeError("ZIP externo corrompido")
        interno = ext.read("OLT/backup_olt_T/backup.zip")
    with zipfile.ZipFile(io.BytesIO(interno)) as z:
        if hashlib.sha256(z.read("x.zip")).digest() != hashlib.sha256(dados).digest():
            raise RuntimeError("conteúdo diferente")
    ok(f"túnel: ZIP com senha montado em fluxo ({len(corpo) // 1024} KB) e conferido")


def main():
    print(f"Python {sys.version.split()[0]} em {os.uname().machine if hasattr(os, 'uname') else sys.platform}")
    for etapa in (programas, fuso, bibliotecas, sintaxe, importacoes, tunel):
        try:
            etapa()
        except Exception as exc:
            falha(f"{etapa.__name__}: {type(exc).__name__}: {exc}")
    if falhas:
        print(f"\nIMAGEM REPROVADA: {len(falhas)} problema(s)")
        return 1
    print("\nIMAGEM APROVADA")
    return 0


if __name__ == "__main__":
    sys.exit(main())
