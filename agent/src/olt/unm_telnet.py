"""Status das OLTs FiberHome (UNM2000) por Telnet (porta 23), com os comandos de leitura `show` do CLI da OLT.

Duas familias de CLI, detectadas pelo menu depois do login (formatos conferidos em OLTs reais):
- classica (diretorios `onu`, `device`...): estado por `show onu_state`, tipo e serial por `show authorization` e sinal
  optico por `show optic_module`.
- por `config` (so o diretorio `config` na raiz): lista tudo em `show authorization` e le o estado de cada PON em
  `interface pon F/S/P` + `show onu active-state all`; o sinal optico vem de `show onu optical-info N` dentro da
  interface da PON. E a familia das series AN6000/AN6001 (conferido: AN6000-7 firmware V105R002, controladora HSCA
  RP1200, e AN6001-G16 firmware V101R001, controladora HSCP RP1100). A serie 5000 (AN5516, V104R002, controladora
  HSUB RP1800) usa a familia classica. O formato da resposta muda com o software da controladora (slot 9): na RP1100
  `show onu optical-info` e uma lista NOME : VALOR; na RP1200 e uma tabela com uma linha por ONU. Ambos sao lidos.
So comandos de consulta; nada e alterado na OLT.
"""
import logging
import re
import socket
import time
from datetime import datetime, timezone

PORTA_PADRAO = 23
TIMEOUT_CONEXAO_S = 10
TIMEOUT_COMANDO_S = 8
MAX_SLOT = 16
MAX_PON = 16
REVER_SLOTS_S = 6 * 3600       # de quanto em quanto tempo procura de novo as placas autorizadas
ORCAMENTO_OPTICO_S = 150       # tempo por ciclo para ler o sinal optico; o que sobrar fica para o proximo (rodizio)
SLOT_CONTROLADORA = 9          # placa HSUB/HSCA/HSCP; o software dela (RPxxxx) muda o formato de algumas respostas
LIMITE_SINAL_BOM_DBM = -25.9   # mesmo corte da consulta do Zabbix (acima disso = Bom)

ESTADOS_ONU = {"active": "ONLINE", "inactive": "OFFLINE", "power down": "SEM_ENERGIA"}
CONTADOR = {"ONLINE": "online", "FALHA": "falha", "OFFLINE": "offline", "SEM_ENERGIA": "sem_energia"}

_PADRAO_HOST = re.compile(r"^\s*(?:(?P<nome>[^=]+?)\s*=\s*)?(?P<ip>[A-Za-z0-9][A-Za-z0-9.\-_]*)\s*$")
_RE_ESTADO = re.compile(r"SLOT\s+(\d+)\s+PON\s+(\d+)\s+ONU\s+(\d+)\s+status\s*:\s*([A-Za-z ]+?)\s*\.?\s*$", re.M)
_RE_AUTORIZACAO = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\S+)\s+([APR])\s+\d+\s+\w+\s+(\S+)", re.M)
_RE_PROMPT = re.compile(r"Admin[^\s#]*#\s*$")  # Admin#, Admin\onu#, Admin(config)#, Admin(config-if-pon-1/1/1)#
_RE_ATIVO = re.compile(r"^\s*onu\s+(\d+)\s+is\s+([a-z ]+?)\s*\.\s*$", re.M | re.I)
_RE_TABELA_PON = re.compile(r"SLOT\s*=\s*(\d+)\s*,\s*PON\s*=\s*(\d+)")
_RE_VERSAO = re.compile(r"device version is\s*:?\s*(V(\d+)R\d+)", re.I)
_RE_HARDWARE = re.compile(r"hardware version\s*:?\s*(V[\w.]+)", re.I)
_RE_PLACA = re.compile(r"^\s*(\d+)\s+([A-Za-z]\w+)\s+(\S+)\s+(\S+)\s*$", re.M)
# Familia de comandos por versao do firmware (V<maior>R<n>); versao fora da tabela: decide pelo menu da OLT
FAMILIA_POR_VERSAO = {104: "classico", 105: "config"}
ESTADOS_ATIVO = {"active": "ONLINE", "no power": "SEM_ENERGIA", "inactive": "OFFLINE", "link loss": "FALHA"}

# slots autorizados por OLT: {ip: (quando, [slots])}
_slots_por_olt: dict = {}
# ultimas leituras opticas por ONU: {(ip, slot, pon, onu): {...}}
_cache_optico: dict = {}


def parse_hosts(texto) -> list:
    """OLTs configuradas: uma por linha (ou separadas por virgula/ponto e virgula), 'IP' ou 'Nome=IP'.
    Aceita tambem uma lista. Retorna [{'nome': ..., 'ip': ...}] sem repetir IP."""
    if isinstance(texto, (list, tuple)):
        partes = [str(p) for p in texto]
    else:
        partes = re.split(r"[\n,;]+", str(texto or ""))
    saida, vistos = [], set()
    for parte in partes:
        m = _PADRAO_HOST.match(parte)
        if not m or m.group("ip") in vistos:
            continue
        vistos.add(m.group("ip"))
        saida.append({"nome": (m.group("nome") or m.group("ip")).strip(), "ip": m.group("ip")})
    return saida


# ── interpretacao das respostas ────────────────────────────────────────────────

def parse_onu_state(texto: str) -> list:
    """[{'slot','pon','onu','estado'}] de `show onu_state slot S pon P`."""
    return [{"slot": int(s), "pon": int(p), "onu": int(o), "estado": ESTADOS_ONU.get(e.strip().lower(), "DESCONHECIDO")}
            for s, p, o, e in _RE_ESTADO.findall(texto or "")]


def parse_version(texto: str) -> dict:
    """Firmware, hardware e placas de `show version`: {'firmware': 'V104R002', 'maior': 104, 'hardware': 'V1.2',
    'placas': [{'slot','tipo','hardware','software'}]}. Vazio se a resposta nao for de versao."""
    m = _RE_VERSAO.search(texto or "")
    if not m:
        return {}
    h = _RE_HARDWARE.search(texto)
    return {
        "firmware": m.group(1).upper(), "maior": int(m.group(2)), "hardware": h.group(1) if h else None,
        "placas": [{"slot": int(n), "tipo": t, "hardware": hw, "software": sw}
                   for n, t, hw, sw in _RE_PLACA.findall(texto) if not t.startswith("-")],
    }


def parse_active_state(texto: str, slot: int, pon: int) -> list:
    """[{'slot','pon','onu','estado'}] de `show onu active-state all` (modo config). Ignora 'not authorized!'."""
    saida = []
    for onu, estado in _RE_ATIVO.findall(texto or ""):
        estado = estado.strip().lower()
        if estado in ESTADOS_ATIVO:
            saida.append({"slot": slot, "pon": pon, "onu": int(onu), "estado": ESTADOS_ATIVO[estado]})
    return saida


def pons_da_autorizacao(texto: str) -> list:
    """[(slot, pon)] que aparecem no `show authorization` (cabecalho 'SLOT = S, PON = P')."""
    return sorted({(int(s), int(p)) for s, p in _RE_TABELA_PON.findall(texto or "")})


def parse_authorization(texto: str) -> dict:
    """{(slot, pon, onu): {'tipo', 'serial'}} de `show authorization slot S pon P`."""
    return {(int(s), int(p), int(o)): {"tipo": tipo, "serial": serial}
            for s, p, o, tipo, _, serial in _RE_AUTORIZACAO.findall(texto or "")}


_RE_MODELO = re.compile(r"-{3,}\s*(AN\d+(?:-[A-Za-z0-9]+)*)\s*-{3,}", re.I)
# colunas da tabela de `show onu optical-info`, na ordem em que a OLT as imprime
_COLUNAS_OPTICO = ("id", "tipo_km", "temperatura_onu", "tensao", "corrente", "tx_onu_dbm", "sinal_onu_dbm", "sinal_olt_dbm")


def parse_modelo(texto: str):
    """Modelo do chassi (ex.: 'AN6000-7') do cabecalho de `show card`; None se nao houver."""
    m = _RE_MODELO.search(texto or "")
    return m.group(1).upper() if m else None


def parse_controladora(placas: list, slot: int = SLOT_CONTROLADORA):
    """Placa do slot da controladora (HSUB/HSCA/HSCP...) com seu software (RPxxxx), do `show version`."""
    for p in placas or []:
        if p.get("slot") == slot:
            return {"slot": slot, "tipo": p.get("tipo"), "software": p.get("software")}
    return None


def _decimal(padrao: str, texto: str):
    m = re.search(padrao, texto or "", re.M | re.I)
    return float(m.group(1)) if m else None


def parse_optico(texto: str) -> dict:
    """Sinal optico de `show optic_module slot S pon P onu N`. Vazio se a ONU nao respondeu (ex.: inativa)."""
    tabela = re.search(r"^\s*\d+((?:\s+-?\d+(?:\.\d+)?){7})\s*$", texto or "", re.M)
    if tabela:  # firmware com uma linha por ONU: ID TIPO TEMP TENSAO CORRENTE TX RX RX_NA_OLT
        v = [float(x) for x in tabela.group(1).split()]
        leitura = dict(zip(_COLUNAS_OPTICO[1:], v))
        return {k: leitura[k] for k in ("sinal_olt_dbm", "sinal_onu_dbm", "tx_onu_dbm", "temperatura_onu")}
    leitura = {
        "sinal_olt_dbm": _decimal(r"^\s*OLT RECV POWER\s*:\s*(-?\d+(?:\.\d+)?)", texto),
        "sinal_onu_dbm": _decimal(r"^\s*RECV POWER\s*:\s*(-?\d+(?:\.\d+)?)", texto),
        "tx_onu_dbm": _decimal(r"^\s*SEND POWER\s*:\s*(-?\d+(?:\.\d+)?)", texto),
        "temperatura_onu": _decimal(r"^\s*TEMPERATURE\s*:\s*(-?\d+(?:\.\d+)?)", texto),
    }
    return {k: v for k, v in leitura.items() if v is not None}


def qualidade_sinal(dbm):
    """BOM acima de -25,9 dBm (sinal recebido na OLT), RUIM no limite ou abaixo; None sem leitura."""
    if dbm is None:
        return None
    return "BOM" if dbm > LIMITE_SINAL_BOM_DBM else "RUIM"


def resumir_onus(onus: list) -> tuple:
    """(totais, por_pon) das ONUs [{'slot','pon','estado', 'qualidade'?}]."""
    totais = {"total": len(onus), "online": 0, "offline": 0, "falha": 0, "sem_energia": 0, "sinal_ruim": 0}
    por_pon = {}
    for onu in onus:
        campo = CONTADOR.get(onu["estado"])
        ruim = onu.get("qualidade") == "RUIM"
        if campo:
            totais[campo] += 1
        totais["sinal_ruim"] += ruim
        pon = por_pon.setdefault((onu["slot"], onu["pon"]), {
            "slot": onu["slot"], "pon": onu["pon"], "total": 0, "online": 0, "offline": 0, "falha": 0,
            "sem_energia": 0, "sinal_ruim": 0})
        pon["total"] += 1
        pon["sinal_ruim"] += ruim
        if campo:
            pon[campo] += 1
    return totais, sorted(por_pon.values(), key=lambda p: (p["slot"], p["pon"]))


# ── sessao Telnet ──────────────────────────────────────────────────────────────

def _limpar_telnet(dados: bytes) -> str:
    """Remove as negociacoes Telnet (IAC) e deixa so texto imprimivel."""
    saida, i, n = [], 0, len(dados)
    while i < n:
        b = dados[i]
        if b == 255:  # IAC
            if i + 1 < n and dados[i + 1] in (251, 252, 253, 254):
                i += 3
                continue
            if i + 1 < n and dados[i + 1] == 250:  # subnegociacao ate IAC SE
                i += 2
                while i < n and dados[i] != 240:
                    i += 1
                i += 1
                continue
            i += 2
            continue
        if b in (9, 10, 13) or 32 <= b <= 126:
            saida.append(chr(b))
        i += 1
    return "".join(saida)


class SessaoOlt:
    def __init__(self, ip, porta=PORTA_PADRAO):
        self.sock = socket.create_connection((ip, porta), timeout=TIMEOUT_CONEXAO_S)
        self.sock.settimeout(1.0)
        self.versao = {}
        self.modelo = None

    def fechar(self):
        try:
            self.sock.close()
        except OSError:
            pass

    def _ler_ate(self, fim, limite_s) -> str:
        """Le ate `fim(texto)` ser verdadeiro ou passar `limite_s`."""
        buf, prazo = "", time.monotonic() + limite_s
        while time.monotonic() < prazo:
            try:
                pedaco = self.sock.recv(4096)
            except socket.timeout:
                continue
            if not pedaco:
                break
            buf += _limpar_telnet(pedaco)
            if fim(buf):
                break
        return buf

    def enviar(self, texto):
        self.sock.sendall((texto + "\r\n").encode("latin-1", "replace"))

    def esperar(self, *trechos, limite_s=8) -> str:
        return self._ler_ate(lambda b: any(t in b for t in trechos), limite_s)

    def comando(self, cmd, limite_s=TIMEOUT_COMANDO_S) -> str:
        """Executa um comando e devolve a resposta (sem o eco e sem o prompt), passando as paginas se houver."""
        self.enviar(cmd)
        resposta, fim = "", time.monotonic() + limite_s
        while time.monotonic() < fim:
            bloco = self._ler_ate(lambda b: bool(_RE_PROMPT.search(b)) or "--Press any key" in b, limite_s)
            resposta += bloco
            if "--Press any key" in bloco:
                self.sock.sendall(b" ")
                continue
            break
        linhas = resposta.replace("\r", "").split("\n")
        return "\n".join(l for l in linhas[1:] if not _RE_PROMPT.search(l) and "--Press any key" not in l)

    def entrar(self, usuario, senha, enable) -> str:
        """Faz login e enable e prepara o CLI. Retorna a familia do CLI: 'classico' ou 'config'."""
        self.esperar("Login:")
        self.enviar(usuario)
        self.esperar("Password:")
        self.enviar(senha)
        resposta = self.esperar("User>", "Admin#", "Login:", "incorrect", "failed", limite_s=8)
        if "User>" not in resposta and "Admin#" not in resposta:
            raise PermissionError("login recusado pela OLT (usuario ou senha)")
        if "User>" in resposta:
            self.enviar("enable")
            self.esperar("Password:")
            self.enviar(enable)
            if "Admin#" not in self.esperar("Admin#", limite_s=8):
                raise PermissionError("senha enable recusada pela OLT")
        tem_onu = bool(re.search(r"<DIR>\s+onu\b", self.comando("dir"), re.I))
        no_config = False
        versao = parse_version(self.comando("show version"))
        if not versao:  # alguns firmwares so respondem a `show version` dentro do config
            self.comando("config")
            no_config = True
            versao = parse_version(self.comando("show version"))
        familia = FAMILIA_POR_VERSAO.get(versao.get("maior")) or ("classico" if tem_onu else "config")
        if familia == "classico":
            if no_config:
                self.comando("exit")
            for cmd in ("cd service", "terminal length 0", "cd ..", "cd onu"):
                self.comando(cmd)
        else:
            if not no_config:
                self.comando("config")
            self.comando("terminal length 0")
        self.versao = versao
        return familia


def _slots_autorizados(sessao, ip, agora) -> list:
    quando, slots = _slots_por_olt.get(ip, (0, []))
    if slots and agora - quando < REVER_SLOTS_S:
        return slots
    slots, desconhecido = [], False
    for slot in range(1, MAX_SLOT + 1):
        resposta = sessao.comando(f"show onu_state slot {slot} pon 1")
        desconhecido = desconhecido or "Unknown command" in resposta
        if "ERR" not in resposta and "% " not in resposta:  # "card is not authorized" etc.
            slots.append(slot)
    if not slots and desconhecido:
        raise RuntimeError("modelo de OLT nao reconhecido (comando 'show onu_state' ausente)")
    _slots_por_olt[ip] = (agora, slots)
    return slots


def _ler_opticos(sessao, ip, onus_online, orcamento_s):
    """Le o sinal das ONUs online, as de leitura mais antiga primeiro; guarda em cache e para no orcamento."""
    fila = sorted(onus_online, key=lambda o: _cache_optico.get((ip, o["slot"], o["pon"], o["onu"]), {}).get("t", 0))
    fim = time.monotonic() + orcamento_s
    for o in fila:
        if time.monotonic() >= fim:
            break
        chave = (ip, o["slot"], o["pon"], o["onu"])
        leitura = parse_optico(sessao.comando(f"show optic_module slot {o['slot']} pon {o['pon']} onu {o['onu']}"))
        if leitura:
            _cache_optico[chave] = {**leitura, "t": time.monotonic(),
                                    "medido_em": datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")}


def _coletar_classico(sessao, ip):
    slots = _slots_autorizados(sessao, ip, time.monotonic())
    onus, cadastro = [], {}
    for slot in slots:
        for pon in range(1, MAX_PON + 1):
            estados = parse_onu_state(sessao.comando(f"show onu_state slot {slot} pon {pon}"))
            if not estados:
                continue
            onus += estados
            cadastro.update(parse_authorization(sessao.comando(f"show authorization slot {slot} pon {pon}")))
    _ler_opticos(sessao, ip, [o for o in onus if o["estado"] == "ONLINE"], ORCAMENTO_OPTICO_S)
    return onus, cadastro


def _ler_opticos_config(sessao, ip, onus_online, orcamento_s):
    """Sinal optico no modo config: `show onu optical-info N` dentro de `interface pon 1/S/P`. As mais antigas primeiro."""
    fila = sorted(onus_online, key=lambda o: _cache_optico.get((ip, o["slot"], o["pon"], o["onu"]), {}).get("t", 0))
    fim, pon_aberta = time.monotonic() + orcamento_s, None
    try:
        for o in fila:
            if time.monotonic() >= fim:
                break
            if pon_aberta != (o["slot"], o["pon"]):
                if pon_aberta:
                    sessao.comando("exit")
                    pon_aberta = None
                sessao.comando(f"interface pon 1/{o['slot']}/{o['pon']}")
                pon_aberta = (o["slot"], o["pon"])
            leitura = parse_optico(sessao.comando(f"show onu optical-info {o['onu']}"))
            if leitura:
                _cache_optico[(ip, o["slot"], o["pon"], o["onu"])] = {
                    **leitura, "t": time.monotonic(),
                    "medido_em": datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")}
    finally:
        if pon_aberta:
            sessao.comando("exit")


def _coletar_config(sessao, ip):
    autorizacao = sessao.comando("show authorization")
    if "Unknown command" in autorizacao:
        raise RuntimeError("modelo de OLT nao reconhecido (comando 'show authorization' ausente)")
    cadastro = parse_authorization(autorizacao)
    onus = []
    for slot, pon in pons_da_autorizacao(autorizacao):
        sessao.comando(f"interface pon 1/{slot}/{pon}")
        try:
            onus += parse_active_state(sessao.comando("show onu active-state all"), slot, pon)
        finally:
            sessao.comando("exit")
    _ler_opticos_config(sessao, ip, [o for o in onus if o["estado"] == "ONLINE"], ORCAMENTO_OPTICO_S)
    sessao.modelo = parse_modelo(sessao.comando("show card"))
    return onus, cadastro


def _coletar(ip, usuario, senha, enable, porta) -> dict:
    sessao = SessaoOlt(ip, porta)
    try:
        familia = sessao.entrar(usuario, senha, enable)
        versao = sessao.versao
        onus, cadastro = (_coletar_classico if familia == "classico" else _coletar_config)(sessao, ip)
    finally:
        sessao.fechar()

    saida = []
    for o in onus:
        cad = cadastro.get((o["slot"], o["pon"], o["onu"]), {})
        item = {
            "indice": f"{o['slot']}/{o['pon']}/{o['onu']}", "slot": o["slot"], "pon": o["pon"], "onu": o["onu"],
            "estado": o["estado"], "tipo": cad.get("tipo"), "serial": cad.get("serial"),
        }
        leitura = _cache_optico.get((ip, o["slot"], o["pon"], o["onu"]))
        if leitura and o["estado"] == "ONLINE":
            item.update({k: v for k, v in leitura.items() if k != "t"})
            item["qualidade"] = qualidade_sinal(leitura.get("sinal_olt_dbm"))
        saida.append(item)
    totais, por_pon = resumir_onus(saida)
    return {
        "ip": ip,
        "coletado_em": datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S"),
        "firmware": versao.get("firmware"),
        "hardware": versao.get("hardware"),
        "modelo": sessao.modelo,
        "controladora": parse_controladora(versao.get("placas")),
        "placas": versao.get("placas") or [],
        "totais": totais,
        "por_pon": por_pon,
        "onus": saida,
    }


def coletar_olt(ip: str, usuario: str, senha: str, enable: str, porta: int = PORTA_PADRAO) -> dict:
    """Status de uma OLT. Nunca levanta erro: em falha devolve {'ip', 'erro'}."""
    try:
        return _coletar(ip, usuario, senha, enable, porta)
    except Exception as e:
        logging.warning(f"[OLT] Falha ao consultar {ip} por Telnet: {e}")
        return {"ip": ip, "erro": str(e) or e.__class__.__name__}
