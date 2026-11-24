"""Executa uma rota do painel dentro do próprio processo (ASGI), como se o usuário tivesse clicado no painel.

A rota recebe um JWT de 5 min do usuário com "via": "mcp": as mesmas regras de papel, somente leitura e
isolamento por conta (REGRA-010) valem, e a Auditoria registra "<e-mail> (IA via MCP)".
"""
import asyncio
import json
from datetime import timedelta
from typing import Any, Optional
from urllib.parse import urlencode

from auth import create_access_token
from models import Usuario

TEMPO_MAXIMO_S = 120


class Resposta:
    def __init__(self, status: int, headers: dict, corpo: bytes):
        self.status = status
        self.headers = headers
        self.corpo = corpo

    @property
    def tipo(self) -> str:
        return self.headers.get("content-type", "").split(";")[0].strip().lower()


def token_interno(usuario: Usuario) -> str:
    return create_access_token(
        {"sub": str(usuario.id), "tv": usuario.token_versao, "via": "mcp"},
        expires_delta=timedelta(minutes=5),
    )


async def chamar(
    app,
    usuario: Usuario,
    metodo: str,
    caminho: str,
    query: Optional[dict] = None,
    corpo: Any = None,
    conta_id: Optional[str] = None,
    ip: str = "mcp",
) -> Resposta:
    dados = b""
    headers = [
        (b"host", b"mcp.interno"),
        (b"authorization", f"Bearer {token_interno(usuario)}".encode()),
        (b"accept", b"application/json"),
        (b"x-forwarded-for", ip.encode()),
        (b"user-agent", b"trilan-mcp"),
    ]
    if corpo is not None:
        dados = json.dumps(corpo, ensure_ascii=False, default=str).encode()
        headers.append((b"content-type", b"application/json"))
    headers.append((b"content-length", str(len(dados)).encode()))
    if conta_id:
        headers.append((b"x-conta-id", str(conta_id).encode()))

    qs = urlencode({k: v for k, v in (query or {}).items() if v is not None}, doseq=True)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": metodo.upper(),
        "scheme": "https",
        "path": caminho,
        "raw_path": caminho.encode(),
        "query_string": qs.encode(),
        "root_path": "",
        "headers": headers,
        "client": (ip, 0),
        "server": ("mcp.interno", 443),
    }

    terminou = asyncio.Event()
    corpo_enviado = False

    async def receive():
        nonlocal corpo_enviado
        if not corpo_enviado:
            corpo_enviado = True
            return {"type": "http.request", "body": dados, "more_body": False}
        await terminou.wait()
        return {"type": "http.disconnect"}

    status = 500
    resp_headers: dict = {}
    partes: list = []

    async def send(msg):
        nonlocal status, resp_headers
        if msg["type"] == "http.response.start":
            status = msg["status"]
            resp_headers = {k.decode().lower(): v.decode(errors="replace") for k, v in msg.get("headers", [])}
        elif msg["type"] == "http.response.body":
            partes.append(msg.get("body", b""))
            if not msg.get("more_body", False):
                terminou.set()

    try:
        await asyncio.wait_for(app(scope, receive, send), timeout=TEMPO_MAXIMO_S)
    except asyncio.TimeoutError:
        terminou.set()
        return Resposta(504, {"content-type": "application/json"},
                        json.dumps({"detail": f"A operação passou de {TEMPO_MAXIMO_S} s."}).encode())
    terminou.set()
    return Resposta(status, resp_headers, b"".join(partes))
