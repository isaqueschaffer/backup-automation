"""Status das ONTs de uma OLT Huawei (MA5800 e similares) por SSH, com os comandos de leitura `display` do
CLI VRP. So comandos de consulta; nada e alterado na OLT.

Fluxo: login e enable -> lista as placas instaladas (`display board 0`) -> para cada slot com placa, tenta
`interface gpon 0/<slot>` (se a OLT rejeitar o comando, a placa nao e GPON e o slot e pulado) -> para cada
porta (0..15) dentro do slot, `display ont info summary <porta>`, que traz duas tabelas: estado (online/
offline, ultima queda e causa) e identificacao (SN, modelo, distancia, sinal Rx/Tx, descricao).

So guarda o motivo da ultima queda (sem energia = dying-gasp, fibra desconectada = LOSi/LOBi) nas ONTs que
estao offline agora; nas online, so o estado atual (sem olhar o historico de queda)."""
import logging
import re
import socket
import time
from datetime import datetime

import paramiko

from .unm_telnet import qualidade_sinal, resumir_onus

PORTA_PADRAO = 22
TIMEOUT_CONEXAO_S = 20
TIMEOUT_COMANDO_S = 20
MAX_PORTA = 16

_RE_PROMPT = re.compile(r"[>#]\s*$")
_RE_MAIS = re.compile(r"---+\s*More")
_RE_SLOT_COM_PLACA = re.compile(r"^[ \t]*(\d+)[ \t]+(\S+)[ \t]+\S", re.M)
_RE_RESUMO_PORTA = re.compile(r"In port (\d+)/(\d+)/(\d+), the total of ONTs are: (\d+), online: (\d+)")
_RE_ESTADO_ONT = re.compile(
    r"^\s*(\d+)\s+(online|offline)\s+(\S+(?:\s\S+)?)\s+(\S+(?:\s\S+)?)\s+(\S+)\s*$", re.M)
_RE_SN_ONT = re.compile(
    r"^\s*(\d+)\s+([0-9A-Fa-f]{16})\s+(\S+)\s+(\d+|-)\s+(-?\d+(?:\.\d+)?|-)\s*/\s*(-?\d+(?:\.\d+)?|-)\s+(.+?)\s*$",
    re.M)

CAUSAS_SEM_ENERGIA = {"dying-gasp"}
CAUSAS_FIBRA = {"losi/lobi", "losi", "lobi"}


def parse_board(texto: str) -> list:
    """Slots com alguma placa instalada em `display board 0` (sem filtrar o tipo; quem decide se e GPON e a
    propria OLT, ao recusar o `interface gpon 0/slot` de uma placa que nao e GPON)."""
    return sorted({int(slot) for slot, nome in _RE_SLOT_COM_PLACA.findall(texto or "") if nome})


def _estado_ont(estado_bruto: str, causa: str) -> str:
    """Estado da ONT: online vira ONLINE direto (sem olhar a causa, que e so historico); offline usa a causa
    da ultima queda para distinguir sem energia / fibra desconectada, com OFFLINE generico quando a causa nao
    e reconhecida ou nao veio ('-')."""
    if estado_bruto == "online":
        return "ONLINE"
    causa = (causa or "").strip().lower()
    if causa in CAUSAS_SEM_ENERGIA:
        return "SEM_ENERGIA"
    if causa in CAUSAS_FIBRA:
        return "FALHA"
    return "OFFLINE"


def parse_ont_summary(texto: str) -> dict:
    """{'frame','slot','porta','total','online','onts': {id: {'estado','serial'?,'tipo'?,'distancia_m'?,
    'sinal_onu_dbm'?,'tx_onu_dbm'?,'nome'?}}} de `display ont info summary N`. Vazio (`{}`) se a resposta nao
    tiver o cabecalho esperado (porta sem ONT configurada ou comando invalido)."""
    cab = _RE_RESUMO_PORTA.search(texto or "")
    if not cab:
        return {}
    frame, slot, porta, total, online = (int(x) for x in cab.groups())
    onts = {}
    for id_ont, estado, _up, _down, causa in _RE_ESTADO_ONT.findall(texto):
        onts[int(id_ont)] = {"estado": _estado_ont(estado, causa)}
    for id_ont, serial, tipo, distancia, rx, tx, nome in _RE_SN_ONT.findall(texto):
        item = onts.setdefault(int(id_ont), {"estado": "OFFLINE"})
        item["serial"] = serial
        if tipo != "-":
            item["tipo"] = tipo
        if distancia != "-":
            item["distancia_m"] = int(distancia)
        if rx != "-":
            item["sinal_onu_dbm"] = float(rx)
        if tx != "-":
            item["tx_onu_dbm"] = float(tx)
        nome = nome.strip()
        if nome:
            item["nome"] = nome
    return {"frame": frame, "slot": slot, "porta": porta, "total": total, "online": online, "onts": onts}


def _coletar(ip: str, usuario: str, senha: str, porta: int) -> dict:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    # OLTs Huawei antigas usam apenas o algoritmo ssh-rsa (SHA-1).
    ssh.connect(
        ip, port=porta, username=usuario, password=senha, timeout=TIMEOUT_CONEXAO_S,
        look_for_keys=False, allow_agent=False, disabled_algorithms={"keys": [], "pubkeys": []},
    )
    shell = ssh.invoke_shell()
    shell.settimeout(2.0)

    def ler_ate(fim, limite_s):
        buf, prazo = "", time.monotonic() + limite_s
        while time.monotonic() < prazo:
            try:
                if not shell.recv_ready():
                    time.sleep(0.2)
                    continue
                buf += shell.recv(8192).decode("utf-8", errors="ignore")
            except socket.timeout:
                continue
            if _RE_MAIS.search(buf):
                shell.send(" ")
                continue
            if fim(buf):
                return buf
        return buf

    prompt_atual = [""]

    def comando(cmd, limite_s=TIMEOUT_COMANDO_S):
        shell.send(cmd + "\n")
        bruto = ler_ate(lambda b: bool(_RE_PROMPT.search(b.rstrip())), limite_s)
        linhas = bruto.replace("\r", "").split("\n")
        prompt_atual[0] = linhas[-1] if linhas else ""  # o prompt novo fica so na ultima linha, cortada abaixo
        return "\n".join(linhas[1:-1]) if len(linhas) > 2 else bruto

    onus = []
    try:
        ler_ate(lambda b: ">" in b, 15)  # banner de login ate o prompt inicial
        comando("enable", limite_s=10)
        comando("undo smart")  # desliga a paginacao "---- More ----" antes de qualquer `display`

        slots = parse_board(comando("display board 0"))
        comando("config")
        comando("undo smart")  # o ajuste e por contexto; repete ao entrar no `config`
        for slot in slots:
            comando(f"interface gpon 0/{slot}")
            # quando o comando da certo ele nao imprime nada: a mudanca de prompt (unica evidencia) fica
            # so na ultima linha, que `comando()` corta do retorno por ser o prompt; por isso o teste e
            # contra `prompt_atual`, nao contra o texto que `comando()` devolve.
            if "config-if-gpon" not in prompt_atual[0].lower():
                continue  # placa sem suporte a GPON (controladora, alarme...): o prompt nao mudou
            comando("undo smart")  # e de novo dentro da interface, antes do primeiro `display`
            try:
                for porta_pon in range(MAX_PORTA):
                    resumo = parse_ont_summary(comando(f"display ont info summary {porta_pon}"))
                    if not resumo:
                        continue
                    for id_ont, dados in resumo["onts"].items():
                        onus.append({
                            "indice": f"{resumo['frame']}/{resumo['slot']}/{resumo['porta']}:{id_ont}",
                            "slot": resumo["slot"], "pon": resumo["porta"], "onu": id_ont,
                            **dados,
                        })
            finally:
                comando("quit")
    finally:
        ssh.close()

    for onu in onus:
        if "sinal_onu_dbm" in onu:
            onu["qualidade"] = qualidade_sinal(onu["sinal_onu_dbm"])

    totais, por_pon = resumir_onus(onus)
    return {
        "ip": ip,
        "coletado_em": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
        "totais": totais,
        "por_pon": por_pon,
        "onus": onus,
    }


def explicar_erro_ssh(e: Exception, ip: str = "", porta: int = PORTA_PADRAO) -> str:
    """Traduz a falha do SSH na causa provavel e no que fazer. O texto cru do paramiko (ex.: "Authentication failed:
    transport shut down or saw EOF") nao diz se a senha esta errada ou se a OLT so fechou a conexao."""
    bruto = (str(e) or e.__class__.__name__).strip()
    baixo = bruto.lower()
    alvo = f"{ip}:{porta}" if ip else "a OLT"
    if isinstance(e, (socket.timeout, TimeoutError)) or "timed out" in baixo:
        return f"A OLT {alvo} não respondeu a tempo. Confira o IP, a porta SSH e se ela está ligada e alcançável. ({bruto})"
    if isinstance(e, ConnectionRefusedError) or "refused" in baixo:
        return f"A OLT {alvo} recusou a conexão: o SSH está desligado ou a porta SSH do cadastro está errada. ({bruto})"
    if "no acceptable" in baixo or "incompatible ssh" in baixo or "unable to negotiate" in baixo or "no matching" in baixo:
        return ("A OLT usa um algoritmo de segurança do SSH que o agente não aceita (firmware antigo). "
                f"Envie o detalhe ao suporte para liberar o algoritmo. ({bruto})")
    # A OLT aceitou o TCP e fechou durante o login: nao e senha errada
    if ("saw eof" in baixo or "transport shut down" in baixo or "error reading ssh protocol banner" in baixo
            or "connection reset" in baixo or isinstance(e, (EOFError, ConnectionResetError))):
        return ("A OLT fechou a conexão durante o login (a senha não foi avaliada). Causas mais comuns: todas as sessões "
                "SSH da OLT estão ocupadas (confira `display users` e feche as paradas), o usuário ficou bloqueado por "
                "tentativas anteriores (aguarde alguns minutos) ou o usuário não tem o serviço SSH/terminal habilitado. "
                f"({bruto})")
    if isinstance(e, paramiko.AuthenticationException) or "authentication failed" in baixo:
        return ("A OLT recusou o usuário ou a senha do SSH. Redigite a senha no cadastro e confira se o usuário tem "
                "o serviço SSH habilitado. Evite tentar várias vezes: a OLT bloqueia o usuário.")
    return bruto


def coletar_huawei(ip: str, usuario: str, senha: str, porta: int = PORTA_PADRAO) -> dict:
    """Status das ONTs de uma OLT Huawei. Nunca levanta erro: em falha devolve {'ip', 'erro'}."""
    try:
        return _coletar(ip, usuario, senha, porta)
    except Exception as e:
        logging.warning(f"[HUAWEI] Falha ao consultar status de {ip}: {e}")
        return {"ip": ip, "erro": explicar_erro_ssh(e, ip, porta)}
