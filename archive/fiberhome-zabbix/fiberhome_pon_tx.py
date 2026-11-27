#!/usr/bin/env python3
import warnings
import sys
import time
import re

warnings.filterwarnings("ignore", category=DeprecationWarning)

try:
    import telnetlib
except ImportError:
    sys.exit(1)


def limpa_linha(linha):
    """Remove ANSI e todos os caracteres de controle, normaliza espaços."""
    s = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', linha)
    s = re.sub(r'[\x00-\x1f\x7f]', ' ', s)
    return ' '.join(s.split())


def ler_ate_prompt(tn, timeout=8):
    """Lê bytes da OLT até encontrar '#' ou esgotar o timeout."""
    buf = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            chunk = tn.read_very_eager()
            if chunk:
                buf += chunk
                if b"#" in chunk:
                    break
            else:
                time.sleep(0.2)
        except Exception:
            break
    return buf


def get_pon_tx(ip, user, password, enable_pass, slot, pon):
    tn = None

    # ── Login com re-tentativa ───────────────────────────────────────────────
    for attempt in range(3):
        try:
            tn = telnetlib.Telnet(ip, 23, timeout=12)
            tn.read_until(b"Login:", timeout=8)
            tn.write(user.encode() + b"\r\n")
            tn.read_until(b"Password:", timeout=8)
            tn.write(password.encode() + b"\r\n")

            idx, _, _ = tn.expect([b">", b"#"], timeout=8)
            if idx == 0:                          # precisa de enable
                tn.write(b"enable\r\n")
                tn.read_until(b"Password:", timeout=8)
                tn.write(enable_pass.encode() + b"\r\n")
                tn.read_until(b"#", timeout=8)
            break
        except Exception:
            if tn:
                tn.close()
            if attempt < 2:
                time.sleep(3)
            else:
                return "0.00"

    try:
        # ── TENTA 1: AN5516 — navega para cd card (sem config) ──────────────
        # Prompt esperado: Admin\card#
        ler_ate_prompt(tn, timeout=3)             # Garante que o buffer de login está limpo
        tn.write(b"cd card\r\n")
        ler_ate_prompt(tn, timeout=3)             # Espera chegar no prompt Admin\card#

        tn.write(f"show optic_module_para slot {slot} pon {pon}\r\n".encode())
        raw1 = ler_ate_prompt(tn, timeout=10)

        # Trata paginação se houver (como tem muitas ONUs, pode aparecer --More--)
        if b"--Press" in raw1 or b"--More" in raw1:
            tn.write(b"\x03")                     # Manda Ctrl+C para parar, pois o SEND POWER está no topo
            time.sleep(0.5)
            raw1 += tn.read_very_eager()

        output1 = raw1.decode(errors="ignore")

        # Se funcionou, extrai o valor
        for line in output1.splitlines():
            lc = limpa_linha(line)
            m = re.search(r"SEND\s+POWER\s*[:\s]+(-?[\d.]+)", lc, re.IGNORECASE)
            if m:
                try:
                    return f"{float(m.group(1)):.2f}"
                except ValueError:
                    pass

        # ── TENTA 2: AN6001 — interface pon X/1/Y → show optical info ───────
        # Prompt esperado: Admin(config-if-pon-X/1/Y)#
        tn.write(b"cd /\r\n")
        time.sleep(0.5)
        tn.read_very_eager()

        tn.write(b"config\r\n")
        ler_ate_prompt(tn, timeout=5)

        tn.write(f"interface pon {slot}/1/{pon}\r\n".encode())
        ler_ate_prompt(tn, timeout=5)

        tn.read_very_eager()
        tn.write(b"show optical info\r\n")
        raw2 = ler_ate_prompt(tn, timeout=8)

        # Se a OLT paginação, mandar Ctrl+C e pegar o que tem
        if b"--Press" in raw2 or b"--More" in raw2:
            tn.write(b"\x03")
            time.sleep(0.5)
            raw2 += tn.read_very_eager()

        output2 = raw2.decode(errors="ignore")

        for line in output2.splitlines():
            lc = limpa_linha(line)
            m = re.search(r"SEND\s+POWER\s*:\s*(-?[\d.]+)", lc, re.IGNORECASE)
            if m:
                try:
                    return f"{float(m.group(1)):.2f}"
                except ValueError:
                    pass

        tn.write(b"exit\r\n")
        tn.close()

        # Se não encontrou em nenhuma tentativa, retorna 0.00 para não quebrar o Zabbix (float)
        return "0.00"

    except Exception:
        if tn:
            tn.close()
        return "0.00"


if __name__ == "__main__":
    if len(sys.argv) < 7:
        sys.exit(1)

    params = [p.replace('"', '').strip() for p in sys.argv[1:7]]
    ip, user, password, enable_pass, slot, pon = params

    print(str(get_pon_tx(ip, user, password, enable_pass, slot, pon)).strip())
