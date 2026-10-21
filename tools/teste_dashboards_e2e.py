"""E2E do dashboard por cliente: isolamento, token, validade, edicao e vazamento de dados.

Cria e apaga dados de teste: rode SO contra o ambiente local (docker-compose.local.yml).
Uso: python tools/teste_dashboards_e2e.py <senha-admin-local>   (TRILAN_API muda a URL base)
O limite de tentativas invalidas por IP e em memoria: reinicie a API para rodar de novo em menos de 5 min.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.environ.get("TRILAN_API", "http://localhost:7001/api/v1")
falhas = []


def call(method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json", **(headers or {})}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            t = r.read().decode()
            return r.status, (json.loads(t) if t else None), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        t = e.read().decode()
        try:
            return e.code, json.loads(t), {k.lower(): v for k, v in e.headers.items()}
        except ValueError:
            return e.code, t, {k.lower(): v for k, v in e.headers.items()}


def ok(cond, msg):
    print(("  OK   " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


s, tok, _ = call("POST", "/auth/login", {"password": sys.argv[1]})
ADM = {"Authorization": "Bearer " + tok["access_token"]}
suf = datetime.now().strftime("%H%M%S")


def cliente(nome):
    s, c, _ = call("POST", "/clients", {"name": f"{nome}-{suf}", "backup_hour": 2, "backup_minute": 0, "email_to": [], "active": True}, ADM)
    assert s == 201, (s, c)
    return c["id"]


def maquina(nome, cid):
    s, m, _ = call("POST", "/machines", {"name": nome, "customer_id": cid}, ADM)
    assert s == 201, (s, m)
    return m


A, B = cliente("DASH-A"), cliente("DASH-B")
mA = maquina(f"Servidor-A-{suf}", A)
mB = maquina(f"Servidor-B-{suf}", B)
agA = {"X-Client-ID": mA["id"], "X-API-Key": mA["api_key"]}
agB = {"X-Client-ID": mB["id"], "X-API-Key": mB["api_key"]}

# equipamento + relatorio + telemetria (com chaves que NAO podem vazar)
for m, ag, nome, ip in [(mA, agA, "NVR-A", "10.10.10.10"), (mB, agB, "NVR-B-SEGREDO", "10.20.20.20")]:
    call("POST", f"/machines/{m['id']}/equipamentos", {"tipo": "NVR", "name": nome, "ip": ip, "username": "usuario_interno", "password": "SenhaSecreta123", "config_extra": {"marca": "Hikvision"}}, ADM)
    agora = datetime.utcnow()
    call("POST", "/agent/backup/report", {"started_at": (agora - timedelta(minutes=3)).isoformat(), "finished_at": agora.isoformat(), "status": "OK",
         "nvr_results": [{"nome": nome, "tipo": "NVR", "status": "OK", "cameras": [
             {"canal": 1, "nome": "Cam1", "status_comunicacao": "ONLINE", "status_gravacao": "COM_GRAVACAO"},
             {"canal": 2, "nome": "Cam2", "status_comunicacao": "OFFLINE", "status_gravacao": "SEM_GRAVACAO"}],
         "telemetria": {"cpu_percent": 91, "ram_percent": 40, "ip_interno": "172.16.9.9", "disks": [
             {"device": "HDD1", "status": "OK", "percent": 50.0, "total_gb": 1000.0, "free_gb": 500.0, "serial": "SN-SEGREDO"},
             {"device": "HDD2", "status": "ERRO", "percent": None, "total_gb": None, "free_gb": None}]}}]}, ag)
    call("POST", "/agent/ping", {"telemetry": {"cpu_percent": 12.5, "ram_percent": 40, "ram_used_gb": 4, "ram_total_gb": 8,
         "disks": [{"device": "C:\\", "fstype": "NTFS", "percent": 50, "total_gb": 100, "used_gb": 50, "free_gb": 50, "mountpoint": "SEGREDO_MOUNT"}],
         "networks": [{"name": "Ethernet", "mbps_sent": 1, "mbps_recv": 2, "ip": "192.168.99.99", "mac": "AA:BB:CC"}],
         "hostname": "HOST-INTERNO", "ip_local": "192.168.99.98"}}, ag)

print("\n[1] Admin")
s, cat, _ = call("GET", "/dashboards/widgets", headers=ADM)
ok(s == 200 and {c["tipo"] for c in cat} >= {"resumo", "saude_servidor", "status_backups", "historico_backups", "cameras", "equipamentos", "texto"}, f"catalogo com os 7 tipos ({s})")
s, d, h = call("GET", f"/clients/{A}/dashboard", headers=ADM)
ok(s == 200 and d["version"] == 1 and len(d["layout"]["widgets"]) == 4, f"dashboard padrao criado ({s})")
ok(h.get("cache-control") == "no-store", "Cache-Control no-store no admin")
s, d2, _ = call("GET", f"/clients/{A}/dashboard", headers=ADM)
ok(d2["id"] == d["id"], "segundo GET reutiliza o mesmo dashboard")
s, r, _ = call("GET", f"/clients/{A}/dashboard")
ok(s in (401, 403), f"admin sem JWT recusado ({s})")

print("\n[2] Layout: referencias e versao")
lay = d["layout"]
lay_ruim = json.loads(json.dumps(lay))
lay_ruim["widgets"][1]["config"] = {"maquinas": [mB["id"]]}
s, r, _ = call("PUT", f"/clients/{A}/dashboard", {"layout": lay_ruim, "version": 1}, ADM)
ok(s == 422, f"salvar com maquina de OUTRO cliente -> 422 ({s})")
lay_tipo = json.loads(json.dumps(lay)); lay_tipo["widgets"].append({"id": "x", "tipo": "inexistente", "largura": 6, "altura": 2, "config": {}})
s, r, _ = call("PUT", f"/clients/{A}/dashboard", {"layout": lay_tipo, "version": 1}, ADM)
ok(s == 422, f"tipo de widget desconhecido -> 422 ({s})")
lay_larg = json.loads(json.dumps(lay)); lay_larg["widgets"][0]["largura"] = 5
s, r, _ = call("PUT", f"/clients/{A}/dashboard", {"layout": lay_larg, "version": 1}, ADM)
ok(s == 422, f"largura invalida -> 422 ({s})")
lay_ok = json.loads(json.dumps(lay))
lay_ok["widgets"][1]["config"] = {"maquinas": [mA["id"]]}
lay_ok["widgets"].append({"id": "aviso", "tipo": "texto", "titulo": "Aviso", "largura": 4, "altura": 1, "config": {"texto": "Olá cliente"}})
lay_ok["widgets"].append({"id": "hist", "tipo": "historico_backups", "largura": 6, "altura": 2, "config": {"periodo": "30d", "visual": "tabela"}})
lay_ok["widgets"].append({"id": "eqp", "tipo": "equipamentos", "largura": 6, "altura": 2, "config": {"tipos": ["nvr"]}})
s, r, _ = call("PUT", f"/clients/{A}/dashboard", {"layout": lay_ok, "version": 1}, ADM)
ok(s == 200 and r["version"] == 2, f"salvar layout valido ({s})")
s, r, _ = call("PUT", f"/clients/{A}/dashboard", {"layout": lay_ok, "version": 1}, ADM)
ok(s == 409, f"versao desatualizada -> 409 ({s})")

print("\n[2b] Componente Gravadores (telemetria dos NVR): isolamento e lista branca")
eqA = call("GET", f"/machines/{mA['id']}/equipamentos", headers=ADM)[1][0]["id"]
eqB = call("GET", f"/machines/{mB['id']}/equipamentos", headers=ADM)[1][0]["id"]
s, dtmp, _ = call("GET", f"/clients/{A}/dashboard", headers=ADM)
lay_g = json.loads(json.dumps(dtmp["layout"]))
lay_g["widgets"].append({"id": "grav", "tipo": "telemetria_equipamentos", "titulo": None, "largura": 6, "altura": 2, "config": {"equipamentos": [eqB], "apenas_problemas": False}})
s, r, _ = call("PUT", f"/clients/{A}/dashboard", {"layout": lay_g, "version": dtmp["version"]}, ADM)
ok(s == 422, f"Gravadores com equipamento de OUTRO cliente -> 422 ({s})")
lay_g["widgets"][-1]["config"] = {"equipamentos": [eqA], "apenas_problemas": False}
s, r, _ = call("PUT", f"/clients/{A}/dashboard", {"layout": lay_g, "version": dtmp["version"]}, ADM)
ok(s == 200, f"Gravadores com equipamento do proprio cliente ({s})")
s, dg, _ = call("GET", f"/clients/{A}/dashboard/data", headers=ADM)
gw = dg["widgets"]["grav"]
ok(gw["ok"] and [e["nome"] for e in gw["dados"]["equipamentos"]] == ["NVR-A"], "widget lista so o gravador do cliente A")
eq0 = gw["dados"]["equipamentos"][0]
ok(eq0["tem_problema"] is True and len(eq0["disks"]) == 2 and eq0["disks"][1]["status"] == "ERRO", "alerta: disco em ERRO e CPU 91% marcam o gravador com problema")
gtxt = json.dumps(dg, ensure_ascii=False)
for proibido in ["172.16.9.9", "SN-SEGREDO", "ip_interno", "serial", "NVR-B-SEGREDO", "10.10.10.10"]:
    ok(proibido not in gtxt, f"dados do widget NAO contem '{proibido}'")
rs = dg["widgets"]["resumo"]["dados"]
ok(rs["gravadores_com_telemetria"] == 1 and rs["discos_total"] == 2 and rs["discos_com_problema"] == 1, f"resumo conta so o cliente A: {rs['gravadores_com_telemetria']}/{rs['discos_total']}/{rs['discos_com_problema']}")

print("\n[3] Dados (previa admin)")
s, dados, _ = call("GET", f"/clients/{A}/dashboard/data", headers=ADM)
ok(s == 200 and all(v.get("ok") for v in dados["widgets"].values()), f"todos os widgets montados ({s})")
txt = json.dumps(dados)
res = dados["widgets"]["resumo"]["dados"]
ok(res["maquinas_total"] == 1 and res["cameras_total"] == 2 and res["cameras_offline"] == 1, f"resumo so do cliente A: {res}")
ok(f"Servidor-B-{suf}" not in txt and "NVR-B-SEGREDO" not in txt, "nenhum dado do cliente B na previa de A")

print("\n[4] Link publico")
s, r, _ = call("GET", "/public/dashboard")
ok(s == 404, f"sem token -> 404 ({s})")
s, r, _ = call("GET", "/public/dashboard", headers={"X-Dashboard-Token": "dsh_" + "x" * 43})
ok(s == 404, f"token aleatorio -> 404 ({s})")
s, r, _ = call("PUT", f"/clients/{A}/dashboard/share", {"ativo": True}, ADM)
ok(s == 409, f"ativar sem gerar link -> 409 ({s})")
s, lk, _ = call("POST", f"/clients/{A}/dashboard/share", {"permite_edicao": False}, ADM)
ok(s == 200 and lk["token"].startswith("dsh_") and lk["caminho"] == "/d#" + lk["token"], f"link gerado ({s})")
TA = {"X-Dashboard-Token": lk["token"]}
s, pub, h = call("GET", "/public/dashboard", headers=TA)
ok(s == 200 and pub["pode_editar"] is False and pub["cliente_nome"].startswith("DASH-A"), f"publico le o dashboard de A ({s})")
ok(h.get("cache-control") == "no-store" and "noindex" in h.get("x-robots-tag", "") and h.get("referrer-policy") == "no-referrer", "cabecalhos de privacidade")
ptxt = json.dumps(pub, ensure_ascii=False)
for proibido in ["10.10.10.10", "10.20.20.20", "usuario_interno", "SenhaSecreta123", "SEGREDO_MOUNT", "192.168.99.99", "192.168.99.98", "HOST-INTERNO", "AA:BB:CC", "Servidor-B", "NVR-B-SEGREDO", "api_key", "password"]:
    ok(proibido not in ptxt, f"resposta publica NAO contem '{proibido}'")
ok("Olá cliente" in ptxt and "Ethernet" in ptxt, "publico mostra o conteudo permitido (texto, rede)")
s, r, _ = call("GET", "/public/dashboard/data", headers=TA)
ok(s == 200, f"/data publico ({s})")

print("\n[5] Token nao abre rotas admin")
for caminho in ["/machines", f"/clients/{A}", f"/clients/{A}/dashboard", f"/clients/{A}/dashboard/share", "/dashboards/widgets", "/backups", "/settings", f"/clients/{B}/dashboard"]:
    s, r, _ = call("GET", caminho, headers=TA)
    ok(s in (401, 403, 405), f"GET {caminho} com token publico -> {s}")
s, r, _ = call("POST", f"/clients/{A}/dashboard/share", {}, TA)
ok(s in (401, 403), f"gerar link com token publico -> {s}")
s, r, _ = call("PUT", "/public/dashboard/layout", {"layout": lay_ok, "version": 2}, TA)
ok(s == 403, f"editar sem permissao -> 403 ({s})")

print("\n[6] Edicao permitida")
s, r, _ = call("PUT", f"/clients/{A}/dashboard/share", {"permite_edicao": True}, ADM)
ok(s == 200 and r["permite_edicao"] is True, "permitir edicao")
novo = json.loads(json.dumps(pub["layout"])); novo["widgets"] = [w for w in novo["widgets"] if w["id"] != "eqp"]
s, r, _ = call("PUT", "/public/dashboard/layout", {"layout": novo, "version": pub["version"]}, TA)
ok(s == 200 and r["version"] == pub["version"] + 1 and len(r["layout"]["widgets"]) == len(pub["layout"]["widgets"]) - 1, f"cliente salva o proprio layout ({s})")
s, r, _ = call("PUT", "/public/dashboard/layout", {"layout": novo, "version": pub["version"]}, TA)
ok(s == 409, f"edicao com versao velha -> 409 ({s})")
ruim = json.loads(json.dumps(novo)); ruim["widgets"][1]["config"] = {"maquinas": [mB["id"]]}
s, vv, _ = call("GET", "/public/dashboard", headers=TA)
s, r, _ = call("PUT", "/public/dashboard/layout", {"layout": ruim, "version": vv["version"]}, TA)
ok(s == 422, f"cliente tentando incluir maquina de B -> 422 ({s})")
s, r, _ = call("PUT", "/public/dashboard/layout", {"layout": {**novo, "share_enabled": True}, "version": vv["version"]}, TA)
ok(s == 422, f"campo extra no layout -> 422 ({s})")

print("\n[7] Isolamento entre clientes")
s, lkB, _ = call("POST", f"/clients/{B}/dashboard/share", {}, ADM)
TB = {"X-Dashboard-Token": lkB["token"]}
s, pubB, _ = call("GET", "/public/dashboard", headers=TB)
ok(s == 200 and pubB["cliente_nome"].startswith("DASH-B"), "token de B abre o dashboard de B")
btxt = json.dumps(pubB)
ok(f"Servidor-A-{suf}" not in btxt and "NVR-A" not in btxt and "Olá cliente" not in btxt, "dashboard de B sem nada de A")
ok(lk["token"] != lkB["token"], "tokens diferentes")

print("\n[8] Desativar, validade, regenerar, revogar")
s, r, _ = call("PUT", f"/clients/{A}/dashboard/share", {"ativo": False}, ADM)
s, r, _ = call("GET", "/public/dashboard", headers=TA)
ok(s == 404, f"desativado -> 404 ({s})")
s, r, _ = call("PUT", f"/clients/{A}/dashboard/share", {"ativo": True}, ADM)
s, r, _ = call("GET", "/public/dashboard", headers=TA)
ok(s == 200, f"reativado -> 200 ({s})")
passado = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
s, r, _ = call("PUT", f"/clients/{A}/dashboard/share", {"expira_em": passado}, ADM)
ok(s == 422, f"validade no passado -> 422 ({s})")
em3 = (datetime.now(timezone.utc) + timedelta(seconds=3)).isoformat()
s, r, _ = call("PUT", f"/clients/{A}/dashboard/share", {"expira_em": em3}, ADM)
ok(s == 200 and r["expira_em"], f"validade em 3 s ({s})")
s, r, _ = call("GET", "/public/dashboard", headers=TA)
ok(s == 200, "ainda valido antes de expirar")
time.sleep(4)
s, r, _ = call("GET", "/public/dashboard", headers=TA)
ok(s == 404, f"expirado -> 404 ({s})")
s, r, _ = call("PUT", f"/clients/{A}/dashboard/share", {"limpar_expiracao": True}, ADM)
s, r, _ = call("GET", "/public/dashboard", headers=TA)
ok(s == 200, "sem validade -> 200 de novo")
s, lk2, _ = call("POST", f"/clients/{A}/dashboard/share", {}, ADM)
s, r, _ = call("GET", "/public/dashboard", headers=TA)
ok(s == 404, f"regenerar invalida o link antigo ({s})")
s, r, _ = call("GET", "/public/dashboard", headers={"X-Dashboard-Token": lk2["token"]})
ok(s == 200, "link novo funciona")
s, r, _ = call("DELETE", f"/clients/{A}/dashboard/share", headers=ADM)
ok(s == 204, f"revogar ({s})")
s, r, _ = call("GET", "/public/dashboard", headers={"X-Dashboard-Token": lk2["token"]})
ok(s == 404, f"revogado -> 404 ({s})")
s, dd, _ = call("GET", f"/clients/{A}/dashboard", headers=ADM)
ok(dd["compartilhamento"]["tem_link"] is False and dd["compartilhamento"]["ativo"] is False, "estado do compartilhamento apos revogar")
s, r, _ = call("POST", f"/clients/{A}/dashboard/restore-default", headers=ADM)
ok(s == 200 and len(r["layout"]["widgets"]) == 4, f"restaurar padrao ({s})")

print("\n[9] Limite de tentativas invalidas por IP")
codigos = []
for i in range(14):
    s, r, _ = call("GET", "/public/dashboard", headers={"X-Dashboard-Token": f"dsh_invalido_{i:030d}"})
    codigos.append(s)
ok(429 in codigos, f"bloqueia apos varias tentativas invalidas: {codigos}")
s, r, _ = call("GET", "/public/dashboard", headers={"X-Dashboard-Token": lk2["token"]})
ok(s == 429, f"IP bloqueado nao acessa nem com token (se valido nao existe mais) ({s})")

print("\n[10] Limpeza")
for cid in (A, B):
    print("  cliente", cid[:8], call("DELETE", f"/clients/{cid}", headers=ADM)[0])
for m in (mA, mB):
    print("  maquina", m["name"], call("DELETE", f"/machines/{m['id']}", headers=ADM)[0])

print("\nRESULTADO:", "TUDO OK" if not falhas else f"{len(falhas)} FALHA(S)")
for f in falhas:
    print(" -", f)
