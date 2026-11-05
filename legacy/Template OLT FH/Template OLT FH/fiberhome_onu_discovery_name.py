#!/usr/bin/env python3
import json
import sys
import subprocess
import re
import socket
import time
import os

try:
    import pymysql
    HAS_MYSQL = True
except ImportError:
    HAS_MYSQL = False

# Configurações dos Bancos UNM2000
IPS_PADRAO = ["192.168.31.5", "192.168.91.6"]
DB_PORT    = 3306
DB_USER    = "zabbix_reader"
DB_PASS    = "Zabbix@2024"
DB_NAME    = "integratecfgdb"

# Prefixos SNMP para FiberHome
PREFIXOS = [
    "1.3.6.1.4.1.5875.800.3.10.1.1",  # Série 5500
    "1.3.6.1.4.1.5875.800.3.9.1.1"    # Série 5000 / EPON
]


# ---------------------------------------------------------------------------
# Classe Telnet simples via socket puro (sem telnetlib)
# ---------------------------------------------------------------------------
class SimpleTelnet:
    def __init__(self, host, port=23, timeout=10):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._buf = b""
        # Negocia opções Telnet básicas (rejeita tudo)
        self._negotiate()

    def _negotiate(self):
        """Descarta bytes de negociação Telnet (IAC sequences)."""
        time.sleep(0.3)
        try:
            data = self.sock.recv(1024)
            # Responde com "WONT" para qualquer "WILL/DO" do servidor
            out = b""
            i = 0
            while i < len(data):
                if data[i] == 255 and i + 2 < len(data):  # IAC
                    cmd = data[i + 1]
                    if cmd in (251, 252):   # WILL/WONT → responde DONT
                        out += bytes([255, 254, data[i + 2]])
                    elif cmd in (253, 254): # DO/DONT   → responde WONT
                        out += bytes([255, 252, data[i + 2]])
                    i += 3
                else:
                    self._buf += data[i:i+1]
                    i += 1
            if out:
                self.sock.sendall(out)
        except Exception:
            pass

    def write(self, data: bytes):
        self.sock.sendall(data)

    def read_until(self, pattern: bytes, timeout: float = 5) -> bytes:
        deadline = time.time() + timeout
        while pattern not in self._buf:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            self.sock.settimeout(min(remaining, 1.0))
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                self._buf += chunk
            except socket.timeout:
                break
            except Exception:
                break
        idx = self._buf.find(pattern)
        if idx != -1:
            result = self._buf[:idx + len(pattern)]
            self._buf = self._buf[idx + len(pattern):]
            return result
        result = self._buf
        self._buf = b""
        return result

    def expect(self, patterns: list, timeout: float = 5) -> tuple:
        deadline = time.time() + timeout
        while True:
            for i, p in enumerate(patterns):
                if p in self._buf:
                    idx = self._buf.find(p)
                    result = self._buf[:idx + len(p)]
                    self._buf = self._buf[idx + len(p):]
                    return i, None, result
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            self.sock.settimeout(min(remaining, 1.0))
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                self._buf += chunk
            except socket.timeout:
                break
            except Exception:
                break
        return -1, None, self._buf

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Funções Principais
# ---------------------------------------------------------------------------
def get_onu_names(db_host_param=None):
    if not HAS_MYSQL:
        return {}
    ips_to_try = [db_host_param] if db_host_param else IPS_PADRAO
    all_names = {}
    for ip in ips_to_try:
        try:
            conn = pymysql.connect(
                host=ip, port=DB_PORT, user=DB_USER,
                password=DB_PASS, database=DB_NAME,
                charset="utf8mb4", connect_timeout=3
            )
            with conn.cursor() as cur:
                cur.execute("SELECT LOWER(contmac), cobjectname FROM t_ontdevice")
                for row in cur.fetchall():
                    if row[0] and row[0] not in all_names:
                        all_names[row[0]] = row[1]
            conn.close()
        except Exception:
            continue
    return all_names


def snmp_walk(ip, community, oid):
    try:
        proc = subprocess.run(
            ["snmpbulkwalk", "-v2c", "-On", "-c", community,
             "-Cr50", "-t", "2", "-r", "1", ip, oid],
            capture_output=True, text=True, timeout=20
        )
        data = {}
        for line in proc.stdout.strip().splitlines():
            m = re.search(
                r'\.([\d]+)\s*=\s*(?:STRING|INTEGER|Hex-STRING):\s*"?([^"\s]+)"?', line
            )
            if m:
                data[m.group(1)] = m.group(2).replace('"', '')
        return data
    except Exception:
        return {}


def get_bulk_signals(ip, user, password, enable, active_onus_by_pon):
    signals = {}
    if not user or not password:
        return signals
    try:
        tn = SimpleTelnet(ip, 23, timeout=10)

        # Login
        tn.expect([b"Login:", b"username:", b"user:"], timeout=5)
        tn.write(user.encode('ascii') + b"\r\n")
        tn.expect([b"Password:", b"password:"], timeout=5)
        tn.write(password.encode('ascii') + b"\r\n")

        # Modo Enable
        i, _, text = tn.expect([b"Password:", b"#", b">"], timeout=5)
        if b"Password:" in text or b">" in text:
            tn.write(b"enable\r\n")
            tn.read_until(b"Password:", timeout=3)
            tn.write(enable.encode('ascii') + b"\r\n")
            tn.read_until(b"#", timeout=5)

        def run_cmds(cmds):
            for c in cmds:
                tn.write(c.encode('ascii') + b"\r\n")
                tn.read_until(b"#", timeout=3)

        # Descobre o método na primeira ONU
        working_method = None
        first_pon = list(active_onus_by_pon.keys())[0]
        f_slot, f_port = first_pon.split('/')
        f_onu = active_onus_by_pon[first_pon][0]

        run_cmds(["cd /", "config", "cd gpononu"])
        tn.write(f"show optic_module slot {f_slot} link {f_port} onu {f_onu}\r\n".encode('ascii'))
        out = tn.read_until(b"#", timeout=5).decode('ascii', errors='ignore')
        if "RECV POWER" in out.upper():
            working_method = "gpononu"
        else:
            run_cmds(["cd /", "config", "cd onu"])
            tn.write(f"show optic_module slot {f_slot} pon {f_port} onu {f_onu}\r\n".encode('ascii'))
            out = tn.read_until(b"#", timeout=5).decode('ascii', errors='ignore')
            if "RECV POWER" in out.upper():
                working_method = "onu"
            else:
                working_method = "interface"

        # Coleta otimizada
        for pon, onus in active_onus_by_pon.items():
            slot, port = pon.split('/')
            if working_method == "interface":
                run_cmds(["cd /", "config", f"interface pon {slot}/1/{port}"])
            else:
                run_cmds(["cd /", "config", f"cd {working_method}"])

            for onu_id in onus:
                if working_method == "interface":
                    cmd = f"show onu optical-info {onu_id}"
                elif working_method == "gpononu":
                    cmd = f"show optic_module slot {slot} link {port} onu {onu_id}"
                else:
                    cmd = f"show optic_module slot {slot} pon {port} onu {onu_id}"

                tn.write(f"{cmd}\r\n".encode('ascii'))
                output = tn.read_until(b"#", timeout=5).decode('ascii', errors='ignore')

                match = re.search(
                    r"(?:RECV|RX|Sinal).*?[:=]\s*(-?\s*[\d.]+)", output, re.IGNORECASE
                )
                if match:
                    try:
                        signals[f"{slot}/{port}/{onu_id}"] = f"{float(match.group(1).replace(' ', '')):.2f}"
                    except Exception:
                        pass

        tn.write(b"logout\r\n")
        tn.close()
    except Exception as e:
        try:
            with open("/tmp/debug_onu_discovery.txt", "a") as f:
                f.write(f"Erro Telnet: {str(e)}\n")
        except Exception:
            pass
    return signals


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 3:
        print(json.dumps({"data": []}))
        sys.exit(1)

    ip        = sys.argv[1]
    community = sys.argv[2]
    db_host   = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None
    user      = sys.argv[4] if len(sys.argv) > 4 else None
    passw     = sys.argv[5] if len(sys.argv) > 5 else None
    enable    = sys.argv[6] if len(sys.argv) > 6 else None
    mode      = sys.argv[7] if len(sys.argv) > 7 else "discovery"

    cache_path         = f"/tmp/cache_fh_{ip}.json"
    cache_ttl          = 600  # 10 minutos
    is_bg_update       = "--update" in sys.argv

    # Serve do cache se existir e não for execução de atualização
    if mode == "inventory" and not is_bg_update:
        if os.path.exists(cache_path):
            with open(cache_path, "r") as f:
                cached = f.read()
            print(cached)
            # Dispara atualização em background se o cache expirou
            if time.time() - os.path.getmtime(cache_path) > cache_ttl:
                try:
                    clean_args = [a for a in sys.argv if a != "--update"]
                    subprocess.Popen(
                        [sys.executable] + clean_args + ["--update"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                except Exception:
                    pass
            sys.exit(0)

    # 1. Nomes das ONUs via banco
    names = get_onu_names(db_host)

    # 2. Seriais via SNMP
    serials = {}
    prefixo = ""
    for pref in PREFIXOS:
        res = snmp_walk(ip, community, f"{pref}.10")
        if res:
            serials = res
            prefixo = pref
            break

    if not serials:
        if is_bg_update:
            sys.exit(0)
        print(json.dumps({"data": []}))
        sys.exit(0)

    # 3. Dados complementares via SNMP
    slots   = snmp_walk(ip, community, f"{prefixo}.2")
    pons    = snmp_walk(ip, community, f"{prefixo}.3")
    onu_ids = snmp_walk(ip, community, f"{prefixo}.4")
    stats   = snmp_walk(ip, community, f"{prefixo}.11") if mode == "inventory" else {}

    # 4. Sinais via CLI (Telnet)
    signals = {}
    if mode == "inventory" and user and passw:
        active_onus_by_pon = {}
        for idx, s in stats.items():
            if s == "1":
                key = f"{slots.get(idx, '1')}/{pons.get(idx, '1')}"
                active_onus_by_pon.setdefault(key, []).append(onu_ids.get(idx, '1'))
        if active_onus_by_pon:
            signals = get_bulk_signals(ip, user, passw, enable, active_onus_by_pon)

    # 5. Monta JSON de saída
    data = []
    for idx in serials:
        serial = serials[idx]
        slot   = slots.get(idx, "1")
        pon    = pons.get(idx, "1")
        onuid  = onu_ids.get(idx, "1")
        nome   = names.get(serial.lower(), f"ONU_{serial}")

        item = {
            "{#SNMPINDEX}": idx,
            "{#IFSERIAL}":  serial,
            "{#ONUNAME}":   nome,
            "{#SLOT}":      slot,
            "{#PON}":       pon,
            "{#ONU}":       onuid,
        }

        if mode == "inventory":
            st      = "Online" if stats.get(idx) == "1" else "Offline"
            sig_val = signals.get(f"{slot}/{pon}/{onuid}", "0.00") if st == "Online" else "0.00"
            item["{#SIGNAL}"] = f"{sig_val} dBm"
            item["{#STATUS}"] = st

        data.append(item)

    final_json = json.dumps({"data": data}, ensure_ascii=False, indent=4)

    # Salva cache
    if mode == "inventory":
        try:
            with open(cache_path, "w") as f:
                f.write(final_json)
        except Exception:
            pass

    if not is_bg_update:
        print(final_json)


if __name__ == "__main__":
    main()
