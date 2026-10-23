"""Salva as respostas XML completas dos comandos de cameras do NVR Motorola (NVMS-9000):
lista de canais/IPs, parametros de stream, eventos (movimento, alarme) e agendamentos.

Uso: python dump_motorola_cameras.py <ip> <usuario> <senha>
Grava um arquivo por comando/envelope em respostas_cameras_<ip>/. Comandos que o firmware
nao conhece voltam 404 ou <status>fail</status> e sao so listados no console.
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

try:
    from dump_motorola_telemetria import autenticar_nvms9000
except ImportError:
    try:
        from teste_motorola_telemetria import autenticar_nvms9000
    except ImportError:
        pass

# Nomes candidatos (variam entre versoes de firmware TVT/NVMS-9000)
GERAIS = [
    # Canais e cameras IP (nome, IP, porta, protocolo, modelo)
    "queryDevList", "queryChlList", "queryChlStatus", "queryOnlineChlList", "queryIPChlORChlGroupList",
    "queryChlsExistRec",
    # Streams
    "queryNodeEncodeInfo", "queryRecordStreamCfg", "queryRecStreamCfg", "queryStreamCfg",
    "queryRecordDistributeInfo",
    # Eventos
    "queryMotionCfg", "queryMotionDetectionCfg", "queryAlarmInCfg", "queryAlarmOutCfg",
    "queryVideoLossCfg", "queryAbnormalTrigger", "queryEventNotifyParam", "queryTriggerCfg",
    # Agendamentos
    "queryScheduleList", "queryRecordScheduleList", "queryRecScheduleCfg", "queryRecordCfg",
    "queryRecordParam", "querySnapScheduleList",
]

# Comandos que costumam exigir o canal na condicao
POR_CANAL = [
    "queryNodeEncodeInfo", "queryRecordStreamCfg", "queryRecStreamCfg", "queryStreamCfg",
    "queryMotionCfg", "queryMotionDetectionCfg", "queryVideoLossCfg", "queryRecScheduleCfg",
    "queryRecordCfg", "queryRecordParam", "queryChlCfg", "queryImageCfg", "queryOsdCfg",
    "queryIPChlCfg", "queryChlInfo",
]


def main():
    if len(sys.argv) < 4:
        print("Uso: python dump_motorola_cameras.py <ip> <usuario> <senha>")
        return
    ip, usuario, senha = sys.argv[1:4]

    session = requests.Session()
    if not autenticar_nvms9000(session, ip, usuario, senha):
        print(f"[-] Falha no login em {ip}.")
        return

    header = '<?xml version="1.0" encoding="utf-8" ?>'
    token = getattr(session, "tvt_token", "")
    token_tag = f"<token>{token}</token>" if token else ""

    def corpo(extra=""):
        return f'{header}<request version="1.0" systemType="NVMS-9000" clientType="WEB">{token_tag}{extra}</request>'

    def post(ep, payload):
        return session.post(f"http://{ip}/{ep}", data=payload.encode("utf-8"),
                            headers={"Content-Type": "application/xml"}, timeout=8, verify=False)

    pasta = Path(f"respostas_cameras_{ip.replace(':', '_')}")
    pasta.mkdir(exist_ok=True)

    def salvar(ep, nome, payload):
        try:
            r = post(ep, payload)
        except Exception as e:
            print(f"  [!] {ep} ({nome}): {e}")
            return
        if r.status_code == 404:
            print(f"  [ ] {ep} ({nome}): 404")
            return
        marca = "+" if "<status>success</status>" in r.text else "~"
        arquivo = pasta / f"{ep}__{nome}.xml"
        arquivo.write_bytes(r.content)
        print(f"  [{marca}] {ep} ({nome}): HTTP {r.status_code}, {len(r.content)} bytes")

    # Primeiro canal (GUID) para os comandos por canal
    canal = None
    r = post("queryChlStatus", corpo())
    if r.status_code == 200:
        for item in ET.fromstring(r.content).findall(".//item"):
            chl = item.find("chl")
            if chl is not None and chl.get("id"):
                canal = chl.get("id")
                break
    print(f"[+] Canal usado nos testes por canal: {canal}")

    print("\n[*] Comandos gerais")
    for ep in GERAIS:
        salvar(ep, "padrao", corpo())

    if canal:
        print("\n[*] Comandos por canal")
        envelopes = [
            ("chlId", f"<condition><chlId>{canal}</chlId></condition>"),
            ("chlsItem", f'<condition><chlId type="list"><item id="{canal}"/></chlId></condition>'),
            ("itemId", f'<condition><item id="{canal}"/></condition>'),
        ]
        for ep in POR_CANAL:
            for nome, extra in envelopes:
                salvar(ep, nome, corpo(extra))

    # queryNodeEncodeInfo sem requireField so devolve o nome; a interface web pede os campos de stream
    print("\n[*] Parametros de stream (requireField)")
    campos = "<requireField><name/><chlType/><mainCaps/><subCaps/><main/><sub/><an/><ae/></requireField>"
    salvar("queryNodeEncodeInfo", "requireField", corpo(campos))
    if canal:
        salvar("queryNodeEncodeInfo", "requireField_chlId",
               corpo(f"<condition><chlId>{canal}</chlId></condition>{campos}"))
    # queryMotion/queryAlarmIn respondem vazios sem requireField (mesmo padrao do queryNodeEncodeInfo)
    print("\n[*] Movimento e entrada de alarme (requireField)")
    campos_evento = "<requireField><param/><trigger/></requireField>"
    for ep in ("queryMotion", "queryAlarmIn"):
        salvar(ep, "requireField", corpo(campos_evento))
        if canal:
            salvar(ep, "requireField_chlId",
                   corpo(f"<condition><chlId>{canal}</chlId></condition>{campos_evento}"))
            salvar(ep, "requireField_alarmInId",
                   corpo(f"<condition><alarmInId>{canal}</alarmInId></condition>{campos_evento}"))

    print(f"\n[*] Pronto. [+] = success, [~] = respondeu mas com fail. Envie a pasta {pasta.resolve()}")


if __name__ == "__main__":
    main()
