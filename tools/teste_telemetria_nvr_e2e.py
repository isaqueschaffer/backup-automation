"""Telemetria de NVR ponta a ponta: post_report REAL do agente -> API -> equipamento -> dashboard publico.

Uso (contra a stack local, em container; a senha e a ADMIN_PASSWORD da stack local):
  docker run --rm --add-host=host.docker.internal:host-gateway -v <repo>/agent:/agent:ro -v <repo>/tools:/t:ro \
    python:3.12-slim sh -c "pip install -q requests && python /t/teste_telemetria_nvr_e2e.py <senha>"
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, os.environ.get("TRILAN_AGENT_DIR", "/agent"))
from src.application.api_client import post_report  # noqa: E402

BASE = os.environ.get("TRILAN_BASE", "http://host.docker.internal:7001")
res = []


def call(method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + "/api/v1" + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def ok(c, m):
    res.append(("OK    " if c else "FALHA ") + m)


s, tok = call("POST", "/auth/login", {"password": sys.argv[1]})
ADM = {"Authorization": "Bearer " + tok["access_token"]}
suf = datetime.now().strftime("%H%M%S")
s, cli = call("POST", "/clients", {"name": f"TELE-{suf}", "backup_hour": 2, "backup_minute": 0, "email_to": [], "active": True}, ADM)
s, maq = call("POST", "/machines", {"name": f"Maq-{suf}", "customer_id": cli["id"]}, ADM)
for nome, marca in (("NVR-HIK", "Hikvision"), ("NVR-INTELBRAS", "Intelbras"), ("NVR-SEM", "Hikvision")):
    call("POST", f"/machines/{maq['id']}/equipamentos", {"tipo": "NVR", "name": nome, "ip": "10.1.1.1", "username": "u", "password": "p", "config_extra": {"marca": marca}}, ADM)

conf = {"client_id": maq["id"], "api_key": maq["api_key"], "server_url": BASE}
cam = [{"canal": 1, "nome": "Cam1", "ip": "10.0.0.5", "online": True, "status_comunicacao": "ONLINE", "status_gravacao": "COM_GRAVACAO", "total_dias": 1, "mapa": "x", "dias_com_gravacao": []}]
resultados = [
    {"nome": "NVR-HIK", "tipo": "NVR", "status": "OK", "cameras": cam,
     "telemetria": {"cpu_percent": 12, "ram_percent": 34, "disks": [{"device": "HDD1", "status": "OK", "percent": 55.5, "total_gb": 3725.0, "free_gb": 1657.0}]}},
    {"nome": "NVR-INTELBRAS", "tipo": "NVR", "status": "OK", "cameras": cam,
     "telemetria": {"ram_percent": 41, "disks": [{"device": "HDD1", "status": "OK", "percent": 91.0, "total_gb": 1000, "free_gb": 90}]}},
    {"nome": "NVR-SEM", "tipo": "NVR", "status": "OK", "cameras": cam, "telemetria": None},
]
agora = datetime.utcnow()
bid = post_report(conf, agora - timedelta(minutes=2), agora, resultados, "manual")
ok(bool(bid), f"post_report do agente aceito pelo servidor (backup_id={bid})")

s, eqs = call("GET", f"/machines/{maq['id']}/equipamentos", headers=ADM)
por = {e["name"]: e for e in eqs}
t = por["NVR-HIK"].get("last_telemetry_status") or {}
ok(t.get("cpu_percent") == 12 and t.get("ram_percent") == 34 and len(t.get("disks", [])) == 1, f"Hikvision: telemetria gravada no equipamento: {t}")
t = por["NVR-INTELBRAS"].get("last_telemetry_status") or {}
ok(t.get("ram_percent") == 41 and "cpu_percent" not in t and t["disks"][0]["percent"] == 91.0, f"Intelbras: RAM+discos gravados, sem CPU: {t}")
ok(por["NVR-SEM"].get("last_telemetry_status") is None, "NVR sem telemetria (None) nao grava nada")

# widget no dashboard publico
s, d = call("GET", f"/clients/{cli['id']}/dashboard", headers=ADM)
lay = d["layout"]
lay["widgets"] = lay["widgets"] + [{"id": "tele", "tipo": "telemetria_equipamentos", "titulo": None, "largura": 12, "altura": 8, "config": {"equipamentos": [], "apenas_problemas": False}}]
rs, r = call("PUT", f"/clients/{cli['id']}/dashboard", {"layout": lay, "version": d["version"]}, ADM)
s, sh = call("POST", f"/clients/{cli['id']}/dashboard/share", {}, ADM)
tokn = (sh or {}).get("token") if isinstance(sh, dict) else None
ok(bool(tokn), f"link publico criado (status {s})"); ok(rs == 200, f"layout com widget Gravadores salvo ({rs})")
if tokn:
    s, dados = call("GET", "/public/dashboard/data", headers={"X-Dashboard-Token": tokn})
    txt = json.dumps(dados)
    eq = (dados.get("widgets", {}).get("tele", {}) or {}).get("dados", {}).get("equipamentos", [])
    nomes = {e["nome"]: e for e in eq}
    ok("NVR-HIK" in nomes and "NVR-INTELBRAS" in nomes and "NVR-SEM" not in nomes, f"widget Gravadores lista so quem tem telemetria: {sorted(nomes)}")
    ok(nomes.get("NVR-INTELBRAS", {}).get("tem_problema") is True, "Intelbras com disco a 91% marcado como 'Atencao'")
    ok(nomes.get("NVR-HIK", {}).get("tem_problema") is False, "Hikvision saudavel")
    ok("10.1.1.1" not in txt and '"p"' not in txt, "dashboard publico nao vaza IP/credenciais")

call("DELETE", f"/machines/{maq['id']}", headers=ADM)
call("DELETE", f"/clients/{cli['id']}", headers=ADM)
print("\n".join(res))
sys.exit(0 if all(x.startswith("OK") for x in res) else 1)
