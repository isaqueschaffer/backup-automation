"""
Trilan NVR Backup Agent — System Tray App
Run with: pythonw tray.py
"""
import os
import sys
import time
import threading
import subprocess
from pathlib import Path

import win32event
import win32con
import pystray
from PIL import Image, ImageDraw
from pystray import MenuItem as item

DIRETORIO = Path(__file__).resolve().parent
SERVICO = "TrilanAgentNVR"
PASTA_LOG = Path(os.environ.get("ProgramData", "C:\\ProgramData")) / "Trilan NVR Backup Agent" / "logs"
ARQUIVO_LOG = PASTA_LOG / "servico.log"
EVENTO_BACKUP_MANUAL = r"Global\TrilanAgentNVR_RunNow"
NO_WINDOW = subprocess.CREATE_NO_WINDOW


# ─────────────────────────────────────────────────────────────
# ICON
# ─────────────────────────────────────────────────────────────
def criar_icone(status_ok: bool = True):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cor = (40, 200, 80) if status_ok else (220, 50, 50)
    d.rectangle((8, 10, 56, 24), outline=(180, 180, 180), width=2, fill=(30, 30, 40))
    d.rectangle((8, 28, 56, 42), outline=(180, 180, 180), width=2, fill=(30, 30, 40))
    d.ellipse((14, 14, 20, 20), fill=cor)
    d.ellipse((14, 32, 20, 38), fill=cor)
    d.line((32, 46, 32, 58), fill=(180, 180, 180), width=3)
    d.line((32, 58, 26, 52), fill=(180, 180, 180), width=3)
    d.line((32, 58, 38, 52), fill=(180, 180, 180), width=3)
    return img


# ─────────────────────────────────────────────────────────────
# SERVICE CONTROL
# ─────────────────────────────────────────────────────────────
def cmd_servico(acao):
    try:
        subprocess.run(["sc.exe", acao, SERVICO], creationflags=NO_WINDOW, check=False)
    except Exception as e:
        print(f"Erro sc.exe {acao}: {e}")


def servico_rodando() -> bool:
    try:
        r = subprocess.run(["sc.exe", "query", SERVICO], capture_output=True,
                           text=True, creationflags=NO_WINDOW)
        return "RUNNING" in r.stdout
    except Exception:
        return False


def reiniciar_servico(icone, _):
    def _fn():
        cmd_servico("stop")
        time.sleep(2)
        cmd_servico("start")
    threading.Thread(target=_fn, daemon=True).start()


def monitorar_servico(icone):
    while True:
        try:
            ok = servico_rodando()
            status = "em execucao" if ok else "PARADO"
            icone.title = f"Trilan Agente NVR — {status}"
            icone.icon = criar_icone(ok)
        except Exception:
            pass
        time.sleep(10)


# ─────────────────────────────────────────────────────────────
# MENU ACTIONS
# ─────────────────────────────────────────────────────────────
def executar_backup_agora(icone, _):
    try:
        ev = win32event.OpenEvent(win32con.EVENT_MODIFY_STATE, False, EVENTO_BACKUP_MANUAL)
        win32event.SetEvent(ev)
        ev.Close()
        icone.notify("Backup solicitado ao servico.", "Trilan Agente NVR")
    except Exception as e:
        icone.notify(f"Erro: {e}\nO servico esta rodando?", "Trilan Agente NVR")


def abrir_log(icone, _):
    try:
        ARQUIVO_LOG.parent.mkdir(exist_ok=True)
        if not ARQUIVO_LOG.exists():
            ARQUIVO_LOG.touch()
        subprocess.Popen(["notepad.exe", str(ARQUIVO_LOG)])
    except Exception as e:
        print(f"Erro ao abrir log: {e}")


def criar_menu():
    return pystray.Menu(
        item("Executar backup agora", executar_backup_agora),
        pystray.Menu.SEPARATOR,
        item("Iniciar servico", lambda i, j: cmd_servico("start")),
        item("Parar servico", lambda i, j: cmd_servico("stop")),
        item("Reiniciar servico", reiniciar_servico),
        pystray.Menu.SEPARATOR,
        item("Abrir log", abrir_log),
        pystray.Menu.SEPARATOR,
        item("Sair", lambda i, j: i.stop()),
    )


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    while True:
        try:
            icone = pystray.Icon("TrilanAgentNVR", criar_icone(), "Trilan Agente NVR", criar_menu())
            threading.Thread(target=monitorar_servico, args=(icone,), daemon=True).start()
            icone.run()
            break
        except Exception as e:
            print(f"Erro na bandeja: {e} — reiniciando em 5s")
            time.sleep(5)


if __name__ == "__main__":
    main()
