"""Status das ONUs de uma OLT VSOL por HTTP, sem alterar nada na OLT.

Junta duas paginas (ONU ID no formato "<prefixo><slot>/<pon>:<onu>", ex.: "EPON0/1:18"):
- `onustatusinfo.html`: todas as ONUs autorizadas (online e offline), com MAC, descricao e status.
- `onuopmdiag.html`: so as ONUs que responderam ao diagnostico optico (online), com temperatura e RX Power.

Usa a mesma sessao/login HTTP do backup (`src.olt.vsol`).
"""
import logging
import re
from datetime import datetime
from urllib.parse import urljoin

import requests
import urllib3

from .unm_telnet import qualidade_sinal, resumir_onus
from .vsol import LegacySSLAdapter, TIMEOUT, _fazer_login, _montar_base_url, _obter_config_extra, _parece_tela_login

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_RE_LINHA = re.compile(r"<tr>(.*?)</tr>", re.S | re.I)
_RE_CELULA = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_INDICE = re.compile(r"^[A-Za-z]*(\d+)/(\d+):(\d+)$")

ESTADOS_VSOL = {"online": "ONLINE", "offline": "OFFLINE"}

# colunas de `onuopmdiag.html`: ONU ID, MAC, Description, Distance, Temperature, SupplyVoltage,
# TXBiasCurrent, TXPower, RXPower
_COL_TEMPERATURA = 4
_COL_RX_POWER = 8


def _texto_celula(html: str) -> str:
    return re.sub(r"\s+", " ", _RE_TAG.sub("", html)).strip()


def _paraf(texto: str):
    try:
        return float(texto)
    except (TypeError, ValueError):
        return None


def _linhas_com_onu(texto: str):
    """Linhas (`<tr>`) de uma tabela com ONU ID reconhecivel na primeira celula. [(indice, slot, pon, onu, celulas)]."""
    for bloco in _RE_LINHA.findall(texto or ""):
        celulas = [_texto_celula(c) for c in _RE_CELULA.findall(bloco)]
        if not celulas:
            continue
        m = _RE_INDICE.match(celulas[0])
        if not m:
            continue
        slot, pon, onu = (int(x) for x in m.groups())
        yield celulas[0], slot, pon, onu, celulas


def parse_onu_status(texto: str) -> list:
    """[{'indice','slot','pon','onu','estado','mac','nome'}] de `onustatusinfo.html` (colunas: ONU ID,
    Status, MAC, Description, ...). Ignora o cabecalho e linhas sem ONU ID reconhecivel."""
    saida = []
    for indice, slot, pon, onu, celulas in _linhas_com_onu(texto):
        if len(celulas) < 4:
            continue
        saida.append({
            "indice": indice, "slot": slot, "pon": pon, "onu": onu,
            "estado": ESTADOS_VSOL.get(celulas[1].strip().lower(), "DESCONHECIDO"),
            "mac": celulas[2] or None,
            "nome": celulas[3] or None,
        })
    return saida


def parse_onu_opm(texto: str) -> dict:
    """{indice: {'temperatura_onu'?, 'sinal_onu_dbm'?, 'qualidade'?}} de `onuopmdiag.html` (colunas:
    ONU ID, MAC, Description, Distance, Temperature, SupplyVoltage, TXBiasCurrent, TXPower, RXPower). So
    tem entrada as ONUs que responderam ao diagnostico optico (online)."""
    saida = {}
    for indice, _slot, _pon, _onu, celulas in _linhas_com_onu(texto):
        if len(celulas) <= _COL_RX_POWER:
            continue
        leitura = {}
        temperatura = _paraf(celulas[_COL_TEMPERATURA])
        if temperatura is not None:
            leitura["temperatura_onu"] = temperatura
        rx_power = _paraf(celulas[_COL_RX_POWER])
        if rx_power is not None:
            leitura["sinal_onu_dbm"] = rx_power
            leitura["qualidade"] = qualidade_sinal(rx_power)
        if leitura:
            saida[indice] = leitura
    return saida


def _pedir(session: requests.Session, base_url: str, pagina: str, **dados) -> str:
    """POST (ou GET, se o POST falhar) numa pagina de `/action/`, pedindo todas as portas (select=255)."""
    url = urljoin(base_url.rstrip("/") + "/", f"action/{pagina}")
    resposta = session.post(url, data={"select": "255", **dados}, timeout=TIMEOUT)
    if resposta.status_code != 200:
        resposta = session.get(url, params={"select": "255", **dados}, timeout=TIMEOUT)
    resposta.raise_for_status()
    texto = resposta.text
    if _parece_tela_login(texto):
        # a sessao criada no login nao fica valida para essa pagina (ex.: endpoint de login errado) —
        # sem isso, o parser so acha 0 ONUs e o log nao mostra motivo nenhum.
        raise requests.RequestException(f"sessao nao autenticada ao acessar {pagina} (OLT redirecionou para login)")
    return texto


def coletar_vsol(equipamento: dict) -> dict:
    """Status das ONUs de uma OLT VSOL (todas, com temperatura e RX Power das que estao online). Nunca
    levanta erro: em falha devolve {'ip', 'erro'}."""
    config_extra = _obter_config_extra(equipamento)
    ip = equipamento.get("ip") or config_extra.get("ip") or config_extra.get("host")
    usuario = equipamento.get("username") or config_extra.get("username") or config_extra.get("usuario")
    senha = equipamento.get("password") or config_extra.get("password") or config_extra.get("senha")

    if not ip or not usuario or not senha:
        return {"ip": ip, "erro": "IP, usuario ou senha nao informados"}

    base_url = _montar_base_url(str(ip), config_extra)
    session = requests.Session()
    adapter = LegacySSLAdapter()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.verify = False

    try:
        if not _fazer_login(session, base_url, usuario, senha):
            return {"ip": ip, "erro": "falha na autenticacao"}
        onus = parse_onu_status(_pedir(session, base_url, "onustatusinfo.html", port_refresh="Refresh"))
        opticos = parse_onu_opm(_pedir(session, base_url, "onuopmdiag.html", who="100"))
    except requests.RequestException as e:
        logging.warning(f"[VSOL] Falha ao consultar status de {ip}: {e}")
        return {"ip": ip, "erro": str(e) or e.__class__.__name__}
    finally:
        session.close()

    for onu in onus:
        onu.update(opticos.get(onu["indice"], {}))

    totais, por_pon = resumir_onus(onus)
    return {
        "ip": ip,
        "coletado_em": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
        "totais": totais,
        "por_pon": por_pon,
        "onus": onus,
    }
