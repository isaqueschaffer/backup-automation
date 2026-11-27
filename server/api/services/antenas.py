"""Equipamento ANTENA: antenas Wi-Fi acompanhadas por um MikroTik (acesso SSH nos campos do próprio equipamento).

O cadastro fica em `NVR.config_extra`: `porta_ssh`, `prefixos_mac` (OUI da busca automática) e `antenas`
(`[{"nome", "mac", "ip"?, "notificar"}]`). O agente lê o MikroTik, cruza os MACs (tolerância de 32 endereços) e envia o
status em `NVR.antena_status`; aqui ficam a validação do cadastro e a mescla do status recebido com o anterior
(quando a antena caiu, quando foi vista online, último IP). Datas em UTC naive (REGRA-001)."""
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

TOLERANCIA_MAC = 32
MAX_ANTENAS = 200
FORMATO_DATA = "%Y-%m-%dT%H:%M:%S"
SITUACOES = ("ONLINE", "OFFLINE", "SEM_REGISTRO", "ERRO")
_RE_IPV4 = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")


def normalizar_mac(texto: Any) -> Optional[str]:
    """'9c2b.a671.6acf', '9C-2B-A6-71-6A-CF' ou '9c2ba6716acf' -> '9C:2B:A6:71:6A:CF'; None se não for um MAC."""
    puro = re.sub(r"[^0-9A-Fa-f]", "", str(texto or "")).upper()
    if len(puro) != 12 or re.sub(r"[0-9A-F]", "", puro):
        return None
    return ":".join(puro[i:i + 2] for i in range(0, 12, 2))


def macs_proximos(a: str, b: str, tolerancia: int = TOLERANCIA_MAC) -> bool:
    return a[:8] == b[:8] and abs(int(a.replace(":", ""), 16) - int(b.replace(":", ""), 16)) <= tolerancia


def normalizar_prefixos(texto: Any) -> str:
    """'9c:2b:a6, 54-16-51' -> '9C:2B:A6, 54:16:51'; ignora o que não tiver 3 bytes."""
    saida: List[str] = []
    for parte in re.split(r"[,;\s]+", str(texto or "")):
        puro = re.sub(r"[^0-9A-Fa-f]", "", parte).upper()
        if len(puro) == 6:
            oui = ":".join(puro[i:i + 2] for i in range(0, 6, 2))
            if oui not in saida:
                saida.append(oui)
    return ", ".join(saida)


def normalizar_config(config: Optional[dict]) -> Optional[dict]:
    """Valida e normaliza o `config_extra` de um equipamento ANTENA. Levanta ValueError com a mensagem para o painel."""
    if config is None:
        return None
    if not isinstance(config, dict):
        raise ValueError("Configuração da antena inválida.")
    saida = dict(config)
    try:
        porta = int(saida.get("porta_ssh") or 22)
    except (TypeError, ValueError):
        raise ValueError("A porta SSH do MikroTik deve ser um número.")
    if not 1 <= porta <= 65535:
        raise ValueError("A porta SSH do MikroTik deve estar entre 1 e 65535.")
    saida["porta_ssh"] = porta
    saida["prefixos_mac"] = normalizar_prefixos(saida.get("prefixos_mac"))

    brutas = saida.get("antenas") or []
    if not isinstance(brutas, list):
        raise ValueError("A lista de antenas é inválida.")
    if len(brutas) > MAX_ANTENAS:
        raise ValueError(f"No máximo {MAX_ANTENAS} antenas por equipamento.")
    antenas, vistos = [], []
    for i, a in enumerate(brutas, start=1):
        if not isinstance(a, dict):
            raise ValueError(f"Antena {i}: formato inválido.")
        mac = normalizar_mac(a.get("mac"))
        if not mac:
            raise ValueError(f"Antena {i} ('{str(a.get('nome') or '').strip()[:60]}'): MAC inválido. Use o formato 9C:2B:A6:71:6A:CF.")
        if mac in vistos:
            raise ValueError(f"O MAC {mac} está repetido.")
        vistos.append(mac)
        ip = str(a.get("ip") or "").strip()
        if ip and not _RE_IPV4.match(ip):
            raise ValueError(f"Antena '{a.get('nome') or mac}': IP inválido.")
        marca = " ".join(str(a.get("marca") or "").split())[:40]
        antenas.append({
            "nome": (str(a.get("nome") or "").strip() or f"Antena {mac[-5:]}")[:120],
            "mac": mac,
            **({"ip": ip} if ip else {}),
            **({"marca": marca} if marca else {}),
            "notificar": a.get("notificar", True) is not False,
        })
    saida["antenas"] = antenas
    return saida


def _data(texto: Any) -> Optional[datetime]:
    try:
        return datetime.strptime(str(texto or ""), FORMATO_DATA)
    except ValueError:
        return None


def mesclar_status(anterior: Optional[dict], item: dict, agora: datetime) -> dict:
    """Status a gravar em `NVR.antena_status` a partir do relatório do agente (`item`) e do status anterior.

    - Falha de leitura do MikroTik (`erro`): mantém antenas/descobertas anteriores (não dá para saber se caíram).
    - Antena online: `ultimo_online` = agora e some o `offline_desde`; sem estar online, `offline_desde` fica na
      primeira vez em que deixou de responder (é dele que sai o tempo de queda da notificação).
    - Sem IP agora, mantém o último IP/hostname conhecido (`ip_ultimo=True`) para o painel mostrar onde ela estava."""
    anterior = anterior or {}
    agora_txt = agora.strftime(FORMATO_DATA)
    erro = (item.get("erro") or "").strip() or None
    if erro:
        return {
            "atualizado_em": agora_txt, "erro": erro[:500], "mikrotik": anterior.get("mikrotik") or {},
            "antenas": anterior.get("antenas") or [], "descobertas": anterior.get("descobertas") or [],
        }
    antes = {a.get("mac"): a for a in anterior.get("antenas") or [] if isinstance(a, dict)}
    antenas = []
    for a in item.get("antenas") or []:
        if not isinstance(a, dict):
            continue
        prev = antes.get(a.get("mac")) or {}
        novo = dict(a)
        if novo.get("status") not in SITUACOES:
            novo["status"] = "ERRO"
        if novo["status"] == "ONLINE":
            novo["ultimo_online"], novo["offline_desde"] = agora_txt, None
        else:
            novo["ultimo_online"] = prev.get("ultimo_online")
            novo["offline_desde"] = prev.get("offline_desde") or agora_txt
        if not novo.get("ip") and prev.get("ip"):
            novo["ip"], novo["ip_ultimo"] = prev["ip"], True
            novo["hostname"] = novo.get("hostname") or prev.get("hostname") or ""
        antenas.append(novo)
    return {
        "atualizado_em": agora_txt, "erro": None, "mikrotik": item.get("mikrotik") or {},
        "antenas": antenas, "descobertas": [d for d in (item.get("descobertas") or []) if isinstance(d, dict)][:100],
    }
