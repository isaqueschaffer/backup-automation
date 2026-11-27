"""Antenas (Wi-Fi) vistas por um MikroTik: leitura por SSH (só consultas), cruzamento de MACs e descoberta.

O MikroTik é o ponto de vista da rede: o agente entra por SSH e lê vizinhos (`/ip neighbor`), ARP, leases do DHCP e a
tabela da bridge. Uma antena é cadastrada pelo MAC; como o MAC que a nuvem/etiqueta mostra costuma diferir do que a
porta usa por poucos números (rádios e porta Ethernet têm MACs consecutivos), vale qualquer MAC a até `TOLERANCIA_MAC`
endereços do cadastrado. Nada aqui altera o MikroTik, e nenhuma mensagem de erro leva a senha.
"""
import logging
import re
import subprocess
import sys
from typing import Callable, Dict, Iterable, List, Optional

TOLERANCIA_MAC = 32
PORTA_SSH_PADRAO = 22

# Comandos de leitura (propriedades pedidas para o parser conseguir separar valores com espaço, como comentários)
_COMANDOS = {
    "neighbor": ("/ip neighbor print terse without-paging proplist=interface,address,mac-address,identity,platform,system-caps,discovered-by",
                 ["interface", "address", "mac-address", "identity", "platform", "system-caps", "discovered-by"]),
    "arp": ("/ip arp print terse without-paging proplist=address,mac-address,interface,status",
            ["address", "mac-address", "interface", "status"]),
    "lease": ("/ip dhcp-server lease print terse without-paging proplist=address,mac-address,host-name,comment,status,last-seen",
              ["address", "mac-address", "host-name", "comment", "status", "last-seen"]),
    "host": ("/interface bridge host print terse without-paging proplist=mac-address,interface,on-interface,bridge",
             ["mac-address", "interface", "on-interface", "bridge"]),
}

_RE_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_RE_HEX12 = re.compile(r"[0-9A-Fa-f]{12}")


class ErroMikrotik(Exception):
    """Falha ao ler o MikroTik; a mensagem é segura para ir ao painel."""


# ── MAC ───────────────────────────────────────────────────────────────────

def normalizar_mac(texto) -> Optional[str]:
    """'9c2b.a671.6acf', '9C-2B-A6-71-6A-CF' ou '9c2ba6716acf' -> '9C:2B:A6:71:6A:CF'; None se não for um MAC."""
    puro = re.sub(r"[^0-9A-Fa-f]", "", str(texto or ""))
    if len(puro) != 12 or not _RE_HEX12.fullmatch(puro):
        return None
    puro = puro.upper()
    return ":".join(puro[i:i + 2] for i in range(0, 12, 2))


def mac_int(mac: str) -> int:
    return int(mac.replace(":", ""), 16)


def macs_proximos(a: str, b: str, tolerancia: int = TOLERANCIA_MAC) -> bool:
    """True se os dois MACs diferem em no máximo `tolerancia` endereços (e têm o mesmo fabricante, 3 primeiros bytes)."""
    return a[:8] == b[:8] and abs(mac_int(a) - mac_int(b)) <= tolerancia


def prefixos_validos(texto) -> List[str]:
    """Lista de prefixos (OUI) a partir de um texto 'A1:B2:C3, d4e5f6'; ignora o que não tiver 3 bytes."""
    saida = []
    for parte in re.split(r"[,;\s]+", str(texto or "")):
        puro = re.sub(r"[^0-9A-Fa-f]", "", parte).upper()
        if len(puro) == 6:
            oui = ":".join(puro[i:i + 2] for i in range(0, 6, 2))
            if oui not in saida:
                saida.append(oui)
    return saida


# ── Leitura do MikroTik ───────────────────────────────────────────────────

_RE_CHAVE = re.compile(r"(?:(?<=\s)|^)([a-z][a-z0-9.-]*)=")


def interpretar_terse(texto: str, chaves: Optional[Iterable[str]] = None) -> List[Dict[str, str]]:
    """Linhas do `print terse` -> dicts. Uma chave é um token `nome=` no começo de uma palavra; o valor vai até a
    próxima chave, então comentários com espaços ficam inteiros. Se `chaves` vier, só elas ficam no resultado.
    Linhas sem nenhuma chave (cabeçalho, vazias) são ignoradas."""
    desejadas = set(chaves) if chaves is not None else None
    itens = []
    for linha in (texto or "").splitlines():
        marcas = list(_RE_CHAVE.finditer(linha))
        if not marcas:
            continue
        item = {}
        for i, m in enumerate(marcas):
            if desejadas is not None and m.group(1) not in desejadas:
                continue
            fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(linha)
            item[m.group(1)] = linha[m.end():fim].strip().strip('"')
        itens.append(item)
    return itens


def ler_mikrotik(ip: str, usuario: str, senha: str, porta: int = PORTA_SSH_PADRAO, timeout: int = 15) -> Dict[str, list]:
    """Entra por SSH e devolve {'identity', 'neighbor', 'arp', 'lease', 'host'} (listas de dicts). Só comandos de leitura."""
    import paramiko

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(ip, port=int(porta), username=usuario, password=senha, timeout=timeout,
                    banner_timeout=timeout, auth_timeout=timeout, look_for_keys=False, allow_agent=False)
    except paramiko.AuthenticationException:
        raise ErroMikrotik("O MikroTik recusou o usuário ou a senha do SSH.")
    except Exception as e:
        raise ErroMikrotik(f"Não foi possível entrar por SSH em {ip}:{porta} ({e.__class__.__name__}: {e}).")
    try:
        def executar(cmd: str) -> str:
            _, out, _ = ssh.exec_command(cmd, timeout=30)
            return out.read().decode(errors="replace")

        resultado: Dict[str, list] = {}
        saida = executar("/system identity print")
        resultado["identity"] = saida.split("name:", 1)[1].strip().splitlines()[0].strip() if "name:" in saida else ""
        for nome, (cmd, chaves) in _COMANDOS.items():
            resultado[nome] = interpretar_terse(executar(cmd), chaves)
        return resultado
    except Exception as e:
        raise ErroMikrotik(f"Falha ao ler o MikroTik ({e.__class__.__name__}: {e}).")
    finally:
        ssh.close()


# ── O que a rede enxerga ──────────────────────────────────────────────────

def _primeiro_ipv4(*textos) -> str:
    for t in textos:
        m = _RE_IPV4.search(str(t or ""))
        if m:
            return m.group(0)
    return ""


def consolidar_dispositivos(leitura: Dict[str, list]) -> Dict[str, dict]:
    """Junta vizinhos, ARP, leases e tabela da bridge por MAC: {mac: {mac, ip, hostname, interface, fontes, arp_status,
    lease_status, ultimo_contato, identidade, plataforma, capacidades}}."""
    disp: Dict[str, dict] = {}

    def entrada(mac: str) -> dict:
        return disp.setdefault(mac, {
            "mac": mac, "ip": "", "hostname": "", "interface": "", "fontes": [], "arp_status": "", "lease_status": "",
            "ultimo_contato": "", "identidade": "", "plataforma": "", "capacidades": "",
        })

    def marca(d: dict, fonte: str):
        if fonte not in d["fontes"]:
            d["fontes"].append(fonte)

    for n in leitura.get("neighbor") or []:
        mac = normalizar_mac(n.get("mac-address"))
        if not mac:
            continue
        d = entrada(mac)
        marca(d, "vizinho")
        d["ip"] = d["ip"] or _primeiro_ipv4(n.get("address"))
        d["interface"] = d["interface"] or (n.get("interface") or "").split(",")[0]
        d["identidade"], d["plataforma"], d["capacidades"] = n.get("identity", ""), n.get("platform", ""), n.get("system-caps", "")
    for a in leitura.get("arp") or []:
        mac = normalizar_mac(a.get("mac-address"))
        if not mac:
            continue
        d = entrada(mac)
        marca(d, "arp")
        d["ip"] = _primeiro_ipv4(a.get("address")) or d["ip"]
        d["interface"] = d["interface"] or a.get("interface", "")
        d["arp_status"] = a.get("status", "")
    for le in leitura.get("lease") or []:
        mac = normalizar_mac(le.get("mac-address"))
        if not mac:
            continue
        d = entrada(mac)
        marca(d, "dhcp")
        d["ip"] = d["ip"] or _primeiro_ipv4(le.get("address"))
        d["hostname"] = d["hostname"] or le.get("host-name") or le.get("comment") or ""
        d["lease_status"] = le.get("status", "")
        d["ultimo_contato"] = le.get("last-seen", "")
    for h in leitura.get("host") or []:
        mac = normalizar_mac(h.get("mac-address"))
        if not mac:
            continue
        d = entrada(mac)
        marca(d, "bridge")
        d["interface"] = d["interface"] or h.get("on-interface") or h.get("interface", "")
    return disp


# ── Marca ─────────────────────────────────────────────────────────────────

# Palavras que o vizinho (LLDP/CDP/MNDP) ou o DHCP anunciam -> marca. A ordem importa: a primeira que casar vale.
# (por enquanto só estas marcas; para incluir outra, acrescente aqui e em MARCAS de AntenasModal.tsx)
_MARCAS = (
    ("Ruijie", ("ruijie", "reyee")),
    ("Aruba", ("aruba",)),
    ("Xixian", ("xixian",)),
)


def marca_do_texto(*textos) -> str:
    """Marca reconhecida em nomes/descrições anunciados pelo equipamento ('' se nenhuma palavra conhecida aparece)."""
    texto = " ".join(str(t or "") for t in textos).lower()
    for marca, palavras in _MARCAS:
        if any(p in texto for p in palavras):
            return marca
    return ""


# ── Ping ──────────────────────────────────────────────────────────────────

def pingar(ip: str, timeout_ms: int = 1500) -> Optional[int]:
    """Latência em ms de um ping ICMP (0 = menos de 1 ms); None se não respondeu ou o IP é inválido."""
    if not ip or not _RE_IPV4.fullmatch(ip.strip()):
        return None
    ip = ip.strip()
    if sys.platform == "win32":
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), ip]
        flags = 0
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
                           timeout=timeout_ms / 1000.0 + 2, creationflags=flags)
    except Exception as e:
        logging.debug(f"[ANTENA] ping {ip}: {e}")
        return None
    saida = r.stdout or ""
    if r.returncode != 0 or "TTL=" not in saida.upper():
        return None
    m = re.search(r"(?:tempo|time)\s*([=<])\s*(\d+)", saida, re.IGNORECASE)
    if not m:
        return 0
    return 0 if m.group(1) == "<" else int(m.group(2))


# ── Antenas cadastradas e descoberta ──────────────────────────────────────

_ARP_CONFIRMADO = ("reachable", "delay", "probe")


def _candidatos(disp: Dict[str, dict], mac_alvo: str) -> List[dict]:
    achados = [d for d in disp.values() if macs_proximos(d["mac"], mac_alvo)]
    return sorted(achados, key=lambda d: (abs(mac_int(d["mac"]) - mac_int(mac_alvo)), d["mac"]))


def avaliar_antena(antena: dict, disp: Dict[str, dict], ping: Callable[[str], Optional[int]] = pingar) -> dict:
    """Situação de uma antena cadastrada ({'nome', 'mac', 'ip'(opcional), 'notificar'}):
    ONLINE (respondeu ao ping, ou o ARP a confirma, ou foi vista na bridge), OFFLINE (IP conhecido que não responde)
    ou SEM_REGISTRO (o MikroTik não enxerga nenhum MAC dela e não há IP para testar)."""
    mac = normalizar_mac(antena.get("mac")) or ""
    base = {
        "nome": antena.get("nome") or mac, "mac": mac, "ip": "", "mac_visto": "", "hostname": "", "interface": "",
        "fontes": [], "arp_status": "", "ping_ms": None, "status": "SEM_REGISTRO",
        "notificar": antena.get("notificar", True) is not False,
        "marca": str(antena.get("marca") or "").strip(), "marca_detectada": "",
    }
    if not mac:
        return {**base, "status": "ERRO", "erro": "MAC inválido no cadastro"}
    cands = _candidatos(disp, mac)
    # A marca do cadastro (digitada pelo usuário) vale sobre a detectada; sem ela, vale o que o vizinho/DHCP anuncia
    base["marca_detectada"] = next((m for m in (marca_do_texto(c["identidade"], c["plataforma"], c["hostname"]) for c in cands) if m), "")
    base["marca"] = base["marca"] or base["marca_detectada"]
    ip = next((c["ip"] for c in cands if c["ip"]), "") or (antena.get("ip") or "").strip()
    visto = next((c for c in cands if c["ip"]), cands[0] if cands else None)
    if visto:
        base.update(mac_visto=visto["mac"], hostname=visto["hostname"], interface=visto["interface"],
                    arp_status=visto["arp_status"])
    base["fontes"] = sorted({f for c in cands for f in c["fontes"]})
    base["ip"] = ip
    ms = ping(ip) if ip else None
    base["ping_ms"] = ms
    arp_ok = any(c["arp_status"] in _ARP_CONFIRMADO for c in cands)
    if ms is not None or arp_ok:
        base["status"] = "ONLINE"
    elif ip:
        base["status"] = "OFFLINE"
    elif cands:
        base["status"] = "ONLINE"  # frames recentes na bridge, sem IP para testar
    return base


def descobrir_antenas(disp: Dict[str, dict], cadastradas: List[dict], prefixos: List[str]) -> List[dict]:
    """Dispositivos que parecem antenas e ainda não estão cadastrados: vizinhos com capacidade `wlan-ap` ou nome
    Ruijie/Reyee, e qualquer MAC cujo prefixo (OUI) esteja em `prefixos`. MACs próximos (±32) viram um só."""
    macs_cad = [m for m in (normalizar_mac(a.get("mac")) for a in cadastradas) if m]
    achados = []
    for d in disp.values():
        motivo = ""
        if d["identidade"] or d["plataforma"] or d["capacidades"]:
            texto = f"{d['identidade']} {d['plataforma']}".lower()
            if "wlan-ap" in d["capacidades"].lower():
                motivo = "Vizinho com função de ponto de acesso (wlan-ap)"
            elif "ruijie" in texto or "reyee" in texto:
                motivo = "Vizinho identificado como Ruijie/Reyee"
        if not motivo and d["mac"][:8] in prefixos:
            motivo = f"MAC do fabricante {d['mac'][:8]}"
        if not motivo:
            continue
        if any(macs_proximos(d["mac"], m) for m in macs_cad):
            continue
        achados.append({**d, "motivo": motivo})
    # agrupa MACs próximos (a mesma antena aparece com o MAC da porta e o dos rádios): fica o que tem IP
    achados.sort(key=lambda d: d["mac"])
    grupos: List[List[dict]] = []
    for d in achados:
        if grupos and macs_proximos(grupos[-1][-1]["mac"], d["mac"]):
            grupos[-1].append(d)
        else:
            grupos.append([d])
    saida = []
    for g in grupos:
        melhor = next((d for d in g if d["ip"]), g[0])
        saida.append({
            "mac": melhor["mac"], "ip": melhor["ip"], "hostname": melhor["hostname"] or melhor["identidade"],
            "interface": melhor["interface"], "fontes": sorted({f for d in g for f in d["fontes"]}),
            "motivo": melhor["motivo"], "macs": [d["mac"] for d in g],
            "marca": next((m for m in (marca_do_texto(d["identidade"], d["plataforma"], d["hostname"]) for d in g) if m), ""),
        })
    return saida
