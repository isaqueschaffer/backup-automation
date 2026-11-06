"""Coletor de teste das OLTs: a cada 60s le as OLTs cadastradas (estado, sinal, nomes das ONUs) e envia ao servidor,
igual fara o servico do Windows, so que mais rapido e enquanto este terminal ficar aberto. So para testar sem instalar
o agente novo. Pare com Ctrl+C.

Uso: python testar_olt_loop.py            (le a config do agent.conf desta pasta)
"""
import sys
import time
from datetime import datetime

sys.path.insert(0, ".")
from src.application.api_client import fetch_server_config, send_status_olts
from src.application.status_olt import coletar_status_olts
from src.core.config import load_conf

INTERVALO_S = 60


def uma_rodada(conf):
    srv = fetch_server_config(conf)
    equipamentos = srv.get("equipamentos") or srv.get("nvrs") or []
    lista = coletar_status_olts(equipamentos)
    enviado = send_status_olts(conf, lista) if lista else False
    agora = datetime.now().strftime("%H:%M:%S")
    for eq in lista:
        for olt in eq.get("olts", []):
            onus = olt.get("onus") or []
            com_nome = sum(1 for o in onus if o.get("nome"))
            nomes_info = olt.get("nomes") or {}
            erro = olt.get("erro") or nomes_info.get("erro") or ""
            print(f"[{agora}] {eq['nome']} / {olt['ip']}: {len(onus)} ONUs, {com_nome} com nome. {erro}".rstrip())
    print(f"[{agora}] enviado ao servidor: {enviado}\n", flush=True)


def main():
    conf = load_conf()
    print(f"Servidor: {conf.get('server_url')} | enviando a cada {INTERVALO_S}s | Ctrl+C para parar\n", flush=True)
    while True:
        try:
            uma_rodada(conf)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[{datetime.now():%H:%M:%S}] erro na rodada: {e}", flush=True)
        try:
            time.sleep(INTERVALO_S)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
