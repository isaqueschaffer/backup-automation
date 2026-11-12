"""Alarmes das centrais Intelbras cadastradas no Defense IA, pelo painel web de alarmes (Next.js, porta
configuravel, padrao 3001, `/api/alarm-centrals`), com as mesmas credenciais do equipamento DEFENSE.

Login igual ao do navegador: o painel gera no proprio cliente um token CSRF (pacote npm `csrf`, assinado com
o segredo padrao "secret-key"), manda no cookie `csrfToken` junto do `POST /api/auth/login` e recebe um
token de sessao, que as consultas seguintes levam no cookie `token` (o header `Authorization` e recusado)."""
import base64
import hashlib
import logging
import secrets
import string

import requests

from src.core.config import parse_config_extra

TIMEOUT_S = 10
PORTA_PADRAO = 3001
SEGREDO_CSRF_PADRAO = "secret-key"


def _texto(valor):
    texto = str(valor).strip() if valor is not None else ""
    return texto or None


def gerar_token_csrf(segredo: str = SEGREDO_CSRF_PADRAO) -> str:
    """Mesmo formato do `Tokens.create()` do pacote npm `csrf`: "<sal>-<base64url(sha1('<sal>-<segredo>'))>"."""
    sal = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
    digest = hashlib.sha1(f"{sal}-{segredo}".encode()).digest()
    assinatura = base64.b64encode(digest).decode().replace("+", "-").replace("/", "_").rstrip("=")
    return f"{sal}-{assinatura}"


def parse_alarmes(dados: list) -> list:
    """[{'id','nome','status','particoes': [{'id','nome','armada','disparada'}]}] da resposta de
    `/api/alarm-centrals`. `status` e o status de comunicacao bruto da central (1 = conectada); `armada` e
    `disparada` vem de `partitions[].armed`/`alarm` (0/1). So copia esses campos: a resposta tambem traz as
    chaves da bridge (`Bridge.private_key`/`access_key`), que nao podem sair da rede do cliente."""
    saida = []
    for central in dados or []:
        if not isinstance(central, dict):
            continue
        particoes = [
            {
                "id": p.get("id"),
                "nome": _texto(p.get("name")) or f"Partição {p.get('index', '?')}",
                "armada": bool(p.get("armed")),
                "disparada": bool(p.get("alarm")),
            }
            for p in (central.get("partitions") or []) if isinstance(p, dict)
        ]
        saida.append({
            "id": central.get("id"),
            "nome": _texto(central.get("name")) or "Central sem nome",
            "modelo": _texto((central.get("Model") or {}).get("name")),
            "status": central.get("status"),
            "particoes": particoes,
        })
    return saida


def parse_incendio(dados: list) -> list:
    """[{'id','nome','modelo','status'}] da resposta de `/api/firestations` (tela "Central de incendio"). Nao copia
    `hmac` nem os dados da bridge, que sao segredos."""
    saida = []
    for central in dados or []:
        if not isinstance(central, dict):
            continue
        saida.append({
            "id": central.get("id"),
            "nome": _texto(central.get("name")) or "Central sem nome",
            "modelo": _texto((central.get("Model") or {}).get("name")),
            "status": central.get("status"),
        })
    return saida


def _abrir_sessao(sessao, base: str, username: str, password: str) -> None:
    """Login no painel de alarmes (token CSRF no cookie, token de sessao no cookie `token`)."""
    sessao.cookies.set("csrfToken", gerar_token_csrf())
    login = sessao.post(f"{base}/api/auth/login", json={"username": username, "password": password}, timeout=TIMEOUT_S)
    if login.status_code in (401, 403):
        raise ValueError(f"login recusado pelo painel de alarmes (HTTP {login.status_code})")
    login.raise_for_status()
    token = ((login.json() or {}).get("token") or {}).get("token")
    if not token:
        raise ValueError("login no painel de alarmes nao devolveu o token de sessao")
    sessao.cookies.set("token", token)


def _pedido_de_comando(modelo: str, station_id, acao: str):
    """(rota, corpo) que a tela /arm-disarm do painel usa para o modelo: AMT 8000 tem rota propria; 4010 manda as 4
    particoes; os demais modelos, A e B."""
    armar = acao == "ARMAR"
    if "8000" in modelo:
        return f"/api/commands/AMT8000/{'Arm' if armar else 'Desarm'}", {"station_id": station_id}
    quatro = "4010" in modelo
    particoes = {"partitionA": True, "partitionB": True, "partitionC": quatro, "partitionD": quatro}
    return "/api/commands/arm-disarm", {"station_id": station_id, "command": 1 if armar else 0, "partitionsState": particoes}


def comandar_central(ip: str, username: str, password: str, porta: int, central_id: str, acao: str) -> str:
    """Arma (`acao="ARMAR"`) ou desarma (`"DESARMAR"`) uma central de alarme pelo painel. O modelo e o id numerico vem
    de `/api/alarm-centrals` na hora (nao de um status antigo). Devolve a mensagem do painel; levanta
    `requests.RequestException`/`ValueError` em falha."""
    if acao not in ("ARMAR", "DESARMAR"):
        raise ValueError(f"acao invalida: {acao}")
    base = f"http://{ip}:{porta}"
    with requests.Session() as sessao:
        _abrir_sessao(sessao, base, username, password)
        resposta = sessao.get(f"{base}/api/alarm-centrals", timeout=TIMEOUT_S)
        resposta.raise_for_status()
        centrais = resposta.json()
        central = next((c for c in (centrais if isinstance(centrais, list) else [])
                        if isinstance(c, dict) and str(c.get("id")) == str(central_id)), None)
        if central is None:
            raise ValueError(f"central {central_id} nao encontrada no painel de alarmes")
        rota, corpo = _pedido_de_comando((central.get("Model") or {}).get("name") or "", central.get("id"), acao)
        resposta = sessao.patch(f"{base}{rota}", json=corpo, timeout=TIMEOUT_S * 3)
        if resposta.status_code >= 400:
            raise ValueError(f"painel recusou o comando (HTTP {resposta.status_code}): {resposta.text[:200]}")
        try:
            dados = resposta.json()
        except ValueError:
            dados = None
        return _mensagem_do_painel(dados) or ("Central armada." if acao == "ARMAR" else "Central desarmada.")


def _mensagem_do_painel(dados) -> str:
    """Texto da resposta de um comando. O painel manda `{"Code": 200, "message": {"0": "Central Deactivated"}}`:
    `message` pode vir como objeto, lista ou texto."""
    mensagem = (dados.get("message") or dados.get("desc")) if isinstance(dados, dict) else None
    if isinstance(mensagem, dict):
        mensagem = "; ".join(str(v) for v in mensagem.values())
    elif isinstance(mensagem, list):
        mensagem = "; ".join(str(v) for v in mensagem)
    return str(mensagem).strip() if mensagem else ""


def consultar_alarmes_defense(ip: str, username: str, password: str, porta: int = PORTA_PADRAO) -> dict:
    """{'alarmes': [...], 'incendio': [...]}: centrais de alarme (`/api/alarm-centrals`) e de incendio
    (`/api/firestations`) de um Defense IA. Levanta `requests.RequestException` ou `ValueError` (login sem token,
    resposta nao-JSON ou com formato inesperado) se a consulta das centrais de alarme falhar; falha so na de
    incendio vira `incendio: []` com aviso no log. Quem coleta por equipamento decide o que fazer com o erro."""
    base = f"http://{ip}:{porta}"
    with requests.Session() as sessao:
        _abrir_sessao(sessao, base, username, password)

        resposta = sessao.get(f"{base}/api/alarm-centrals", timeout=TIMEOUT_S)
        resposta.raise_for_status()
        dados = resposta.json()
        if not isinstance(dados, list):
            raise ValueError("resposta da API de alarmes nao e uma lista")

        incendio = []
        try:
            resposta = sessao.get(f"{base}/api/firestations", timeout=TIMEOUT_S)
            resposta.raise_for_status()
            dados_incendio = resposta.json()
            incendio = parse_incendio(dados_incendio if isinstance(dados_incendio, list) else [])
        except (requests.RequestException, ValueError) as e:
            logging.warning(f"  [DEFENSE] Falha ao consultar centrais de incendio em {ip}:{porta}: {e}")
    return {"alarmes": parse_alarmes(dados), "incendio": incendio}


def coletar_alarmes_equipamento(equipamento: dict, consultar=None) -> dict:
    """{'ip','alarmes','incendio'} ou {'ip','erro'} das centrais de um equipamento DEFENSE. Nunca levanta erro.
    `consultar(ip, usuario, senha, porta)` e injetavel para teste."""
    consultar = consultar or consultar_alarmes_defense
    config_extra = parse_config_extra(equipamento)
    ip = equipamento.get("ip") or config_extra.get("ip")
    username = equipamento.get("username") or "system"
    password = equipamento.get("password") or ""
    try:
        porta = int(config_extra.get("porta_alarme") or PORTA_PADRAO)
    except (TypeError, ValueError):
        porta = PORTA_PADRAO

    if not ip or not password:
        return {"ip": ip, "erro": "IP ou senha nao informados"}

    try:
        return {"ip": ip, **consultar(ip, username, password, porta)}
    except Exception as e:
        logging.warning(f"  [DEFENSE] Falha ao consultar alarmes em {ip}:{porta}: {e}")
        return {"ip": ip, "erro": str(e) or e.__class__.__name__}
