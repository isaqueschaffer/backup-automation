"""Cria um cliente de demonstracao com dados reais e um link com edicao liberada. Grava seed.json."""
import json
import sys
import urllib.request
from datetime import datetime, timedelta

BASE = "http://localhost:7001/api/v1"


def call(method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json", **(headers or {})}, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        t = r.read().decode()
        return json.loads(t) if t else None


tok = call("POST", "/auth/login", {"password": sys.argv[1]})["access_token"]
ADM = {"Authorization": "Bearer " + tok}
cli = call("POST", "/clients", {"name": "Cliente Demonstração", "backup_hour": 2, "backup_minute": 0, "email_to": [], "active": True}, ADM)
agora = datetime.utcnow()
maquinas = []
for nome, cpu, disco in [("Servidor Principal", 23.5, 62), ("Servidor Gravação", 81.2, 91)]:
    disco_ruim = nome == "Servidor Gravação"
    m = call("POST", "/machines", {"name": nome, "customer_id": cli["id"]}, ADM)
    ag = {"X-Client-ID": m["id"], "X-API-Key": m["api_key"]}
    call("POST", f"/machines/{m['id']}/equipamentos", {"tipo": "NVR", "name": f"NVR {nome}", "ip": "10.0.0.5", "username": "admin", "password": "x"}, ADM)
    call("POST", "/agent/backup/report", {"started_at": (agora - timedelta(minutes=5)).isoformat(), "finished_at": agora.isoformat(), "status": "OK",
         "nvr_results": [{"nome": f"NVR {nome}", "tipo": "NVR", "status": "OK", "cameras": [
             {"canal": 1, "nome": "Portaria", "status_comunicacao": "ONLINE", "status_gravacao": "COM_GRAVACAO"},
             {"canal": 2, "nome": "Garagem", "status_comunicacao": "OFFLINE", "status_gravacao": "SEM_GRAVACAO"},
             {"canal": 3, "nome": "Recepção", "status_comunicacao": "ONLINE", "status_gravacao": "SEM_GRAVACAO"}],
         "telemetria": {"cpu_percent": 37, "ram_percent": 52, "disks": [
             {"device": "HDD1", "status": "OK", "percent": 71.5, "total_gb": 3726.0, "free_gb": 1060.0},
             {"device": "HDD2", "status": "ERRO" if disco_ruim else "OK", "percent": None if disco_ruim else 38.2, "total_gb": None if disco_ruim else 3726.0, "free_gb": None if disco_ruim else 2302.0}]}}]}, ag)
    call("POST", "/agent/ping", {"telemetry": {"cpu_percent": cpu, "ram_percent": 55, "ram_used_gb": 8.8, "ram_total_gb": 16,
         "disks": [{"device": "C:\\", "fstype": "NTFS", "percent": disco, "total_gb": 500, "used_gb": 310, "free_gb": 190},
                   {"device": "D:\\", "fstype": "NTFS", "percent": 40, "total_gb": 4000, "used_gb": 1600, "free_gb": 2400}],
         "networks": [{"name": "Ethernet", "mbps_sent": 12.5, "mbps_recv": 48.3}]}}, ag)
    maquinas.append(m["id"])

dash = call("GET", f"/clients/{cli['id']}/dashboard", headers=ADM)
lay = dash["layout"]
lay["widgets"].append({"id": "gravadores", "tipo": "telemetria_equipamentos", "titulo": None, "largura": 6, "altura": 8, "config": {"equipamentos": [], "apenas_problemas": False}})
call("PUT", f"/clients/{cli['id']}/dashboard", {"layout": lay, "version": dash["version"]}, ADM)

lk = call("POST", f"/clients/{cli['id']}/dashboard/share", {"permite_edicao": True}, ADM)
json.dump({"customer_id": cli["id"], "token": lk["token"], "jwt": tok, "machines": maquinas}, open(sys.argv[2], "w"))
print("seed ok", cli["id"])
