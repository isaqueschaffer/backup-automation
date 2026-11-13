"""Gera dist/TrilanAgentLinux.tar.gz: o código do agente Linux (Mikrotik) para a OTA (>= 1.1.52).

Leva só Python puro: agent.py, service_linux.py, requirements-linux.txt e src/ (sem __pycache__). As bibliotecas
compiladas para ARM ficam na imagem do container. Chamado pelo build.ps1; também roda sozinho:
    python pacote_linux.py
"""
import tarfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
SAIDA = BASE / "dist" / "TrilanAgentLinux.tar.gz"
ARQUIVOS = ["agent.py", "service_linux.py", "requirements-linux.txt"]


def _filtro(info: tarfile.TarInfo):
    partes = info.name.split("/")
    if "__pycache__" in partes or info.name.endswith((".pyc", ".pyo")):
        return None
    if not (info.isfile() or info.isdir()):
        return None
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mode = 0o755 if info.isdir() else 0o644
    return info


def main():
    SAIDA.parent.mkdir(exist_ok=True)
    with tarfile.open(SAIDA, "w:gz") as tar:
        for nome in ARQUIVOS:
            tar.add(BASE / nome, arcname=nome, filter=_filtro)
        tar.add(BASE / "src", arcname="src", filter=_filtro)
    print(f"Pacote Linux: {SAIDA} ({SAIDA.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
