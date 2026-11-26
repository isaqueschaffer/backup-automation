#!/usr/bin/env python3
import warnings
import sys
import time

# Silencia o aviso de telnetlib depreciado
warnings.filterwarnings("ignore", category=DeprecationWarning)

try:
    import telnetlib
    import re
except ImportError:
    sys.exit(1)

def get_optical(ip, user, password, enable_pass, slot, pon, onu):
    tn = None
    # Lógica de Re-tentativa
    for attempt in range(3):
        try:
            tn = telnetlib.Telnet(ip, 23, timeout=12)
            
            # Login
            tn.read_until(b"Login:", timeout=8)
            tn.write(user.encode() + b"\r\n")

            tn.read_until(b"Password:", timeout=8)
            tn.write(password.encode() + b"\r\n")

            # Entrar no modo Enable
            index, match, text = tn.expect([b">", b"#"], timeout=8)
            if index == 0:
                tn.write(b"enable\r\n")
                tn.read_until(b"Password:", timeout=8)
                tn.write(enable_pass.encode() + b"\r\n")
                tn.read_until(b"#", timeout=8)
            
            break
        except Exception:
            if tn: tn.close()
            if attempt < 2:
                time.sleep(3)
            else:
                return "0.0"

    try:
        # Navegação base
        tn.write(b"config\r\n")
        tn.read_until(b"#", timeout=5)
        
        # TENTA 1: RP 700 (show optic_module ... link ...)
        tn.write(b"cd gpononu\r\n") # Tenta entrar em gpononu
        tn.read_until(b"#", timeout=3)
        tn.write(f"show optic_module slot {slot} link {pon} onu {onu}\r\n".encode())
        output = tn.read_until(b"#", timeout=10).decode(errors="ignore")

        # TENTA 2: Série 5000 (show optic_module ... pon ...)
        if "OLT RECV POWER" not in output.upper():
            tn.write(b"cd ..\r\n")
            tn.read_until(b"#", timeout=3)
            tn.write(b"cd onu\r\n")
            tn.read_until(b"#", timeout=3)
            tn.write(f"show optic_module slot {slot} pon {pon} onu {onu}\r\n".encode())
            output = tn.read_until(b"#", timeout=10).decode(errors="ignore")

        # TENTA 3: Série 5516 (show onu optical-info)
        if "OLT RECV POWER" not in output.upper() or "Unknown command" in output:
            tn.write(b"cd ..\r\n")
            tn.read_until(b"#", timeout=5)
            tn.write(f"interface pon {slot}/1/{pon}\r\n".encode())
            tn.read_until(b"#", timeout=5)
            tn.write(f"show onu optical-info {onu}\r\n".encode())
            output = tn.read_until(b"#", timeout=10).decode(errors="ignore")

        tn.write(b"exit\r\n")
        tn.close()

        # Regex para capturar o valor
        match = re.search(r"OLT RECV POWER\s*:\s*(-?\s*[\d.]+)", output, re.IGNORECASE)
        if not match:
            match = re.search(r"RECV POWER\s*:\s*(-?\s*[\d.]+)", output, re.IGNORECASE)
            
        if match:
            valor_bruto = match.group(1).replace(" ", "")
            try:
                num = float(valor_bruto)
                if num > 0:
                    return f"-{num:.2f}"
                return f"{num:.2f}"
            except ValueError:
                return "0.0"
        
        return "0.0"

    except Exception:
        if tn: tn.close()
        return "0.0"

if __name__ == "__main__":
    if len(sys.argv) < 8:
        sys.exit(1)

    params = [p.replace('"', '').strip() for p in sys.argv[1:8]]
    ip, user, password, enable_pass, slot, pon, onu = params
    
    print(str(get_optical(ip, user, password, enable_pass, slot, pon, onu)).strip())