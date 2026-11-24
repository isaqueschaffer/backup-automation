"""Servidor OAuth 2.1 do MCP, para os conectores do Claude, do ChatGPT e do app do Gemini.

- Metadados: /.well-known/oauth-protected-resource[/mcp] (RFC 9728) e /.well-known/oauth-authorization-server (RFC 8414).
- Aplicativo: registro dinâmico (POST /oauth/register, RFC 7591) ou client_id em URL com documento de metadados (CIMD).
- Login: GET/POST /oauth/authorize mostra a tela de login do Trilan; só ADMIN e SUPER_ADMIN conectam. PKCE S256 obrigatório.
- Tokens: POST /oauth/token (authorization_code e refresh_token, com rotação) e POST /oauth/revoke (RFC 7009).
"""
import base64
import hashlib
import html
import ipaddress
import json
import secrets
import socket
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import unquote, urlencode, urlparse

import requests
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from models import McpOauthCliente, McpOauthCodigo, McpToken, Usuario
from services import senhas
from services.dashboards.compartilhamento import LimitadorJanela, ip_do_cliente

from .tokens import (
    ACCESS_VALIDADE, PREFIXO_ACCESS, PREFIXO_REFRESH, REFRESH_VALIDADE,
    base_url, gerar, hash_token, usuario_pode_usar_mcp,
)

router = APIRouter(include_in_schema=False)

ESCOPO = "trilan"
CODIGO_VALIDADE = timedelta(minutes=10)
CIMD_CACHE = timedelta(hours=12)

limite_login = LimitadorJanela(maximo=10, janela_s=300)
limite_registro = LimitadorJanela(maximo=30, janela_s=3600)

_SEM_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


# ─── Metadados ───────────────────────────────────────────────────────────
@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
def metadados_recurso(request: Request):
    base = base_url(request)
    return {
        "resource": f"{base}/mcp",
        "authorization_servers": [base],
        "bearer_methods_supported": ["header"],
        "scopes_supported": [ESCOPO],
        "resource_name": "Trilan Backups",
    }


@router.get("/.well-known/oauth-authorization-server")
@router.get("/.well-known/oauth-authorization-server/mcp")
@router.get("/.well-known/openid-configuration")
def metadados_autorizacao(request: Request):
    base = base_url(request)
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "revocation_endpoint": f"{base}/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
        "revocation_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
        "scopes_supported": [ESCOPO],
        "client_id_metadata_document_supported": True,
    }


# ─── Aplicativos (clientes OAuth) ────────────────────────────────────────
_LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def _redirect_aceito(uri: str) -> bool:
    try:
        u = urlparse(uri)
    except ValueError:
        return False
    if u.fragment or not u.scheme:
        return False
    esquema = u.scheme.lower()
    if esquema == "https":
        return bool(u.hostname)
    if esquema == "http":
        return (u.hostname or "") in _LOOPBACK  # apps de linha de comando (RFC 8252)
    return esquema not in ("javascript", "data", "file", "vbscript")  # esquema próprio de app instalado


def _redirect_confere(pedido: str, registrados: List[str]) -> bool:
    if pedido in registrados:
        return True
    p = urlparse(pedido)
    if p.scheme == "http" and (p.hostname or "") in _LOOPBACK:  # loopback: a porta pode variar (RFC 8252 7.3)
        for r in registrados:
            q = urlparse(r)
            if q.scheme == "http" and q.hostname == p.hostname and q.path == p.path:
                return True
    return False


def _host_publico(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    return bool(infos) and all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


def _buscar_cimd(url: str) -> Optional[dict]:
    """Documento de metadados do aplicativo (client_id é a URL). Só HTTPS em IP público, até 64 KB."""
    u = urlparse(url)
    if u.scheme != "https" or not u.hostname or not _host_publico(u.hostname):
        return None
    try:
        r = requests.get(url, timeout=5, allow_redirects=False, stream=True, headers={"Accept": "application/json"})
        if r.status_code != 200:
            return None
        dados = r.raw.read(65536 + 1, decode_content=True)
        if len(dados) > 65536:
            return None
        doc = json.loads(dados)
    except Exception:
        return None
    if not isinstance(doc, dict) or doc.get("client_id") != url:
        return None
    uris = doc.get("redirect_uris")
    if not isinstance(uris, list) or not uris or not all(isinstance(x, str) and _redirect_aceito(x) for x in uris):
        return None
    return doc


def obter_cliente(db: Session, client_id: str) -> Optional[McpOauthCliente]:
    if not client_id:
        return None
    cliente = db.query(McpOauthCliente).filter(McpOauthCliente.client_id == client_id).first()
    if not client_id.startswith("https://"):
        return cliente
    agora = datetime.utcnow()
    if cliente and cliente.atualizado_em > agora - CIMD_CACHE:
        return cliente
    doc = _buscar_cimd(client_id)
    if not doc:
        return cliente  # sem conseguir atualizar, usa o que já tinha (se tinha)
    nome = str(doc.get("client_name") or urlparse(client_id).hostname)[:255]
    if cliente:
        cliente.nome, cliente.redirect_uris, cliente.atualizado_em = nome, doc["redirect_uris"], agora
    else:
        cliente = McpOauthCliente(client_id=client_id, nome=nome, redirect_uris=doc["redirect_uris"],
                                  metadados_url=True, criado_em=agora, atualizado_em=agora)
        db.add(cliente)
    db.commit()
    return cliente


def _erro_oauth(codigo: str, descricao: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": codigo, "error_description": descricao}, status_code=status, headers=_SEM_CACHE)


@router.post("/oauth/register")
async def registrar_cliente(request: Request, db: Session = Depends(get_db)):
    ip = ip_do_cliente(request)
    if not limite_registro.disponivel(ip):
        return _erro_oauth("invalid_request", "Muitos registros. Tente mais tarde.", 429)
    limite_registro.registrar(ip)
    try:
        meta = await request.json()
    except Exception:
        return _erro_oauth("invalid_client_metadata", "Corpo JSON inválido.")
    uris = meta.get("redirect_uris") if isinstance(meta, dict) else None
    if not isinstance(uris, list) or not uris or len(uris) > 10 or \
            not all(isinstance(u, str) and len(u) <= 2000 and _redirect_aceito(u) for u in uris):
        return _erro_oauth("invalid_redirect_uri", "redirect_uris precisa de endereços https (ou http de loopback).")
    metodo = meta.get("token_endpoint_auth_method") or "none"
    if metodo not in ("none", "client_secret_post", "client_secret_basic"):
        metodo = "none"
    segredo = None
    cliente = McpOauthCliente(
        client_id=f"trilan-{secrets.token_urlsafe(16)}",
        nome=str(meta.get("client_name") or "Aplicativo de IA")[:255],
        redirect_uris=uris,
    )
    if metodo != "none":
        segredo = secrets.token_urlsafe(32)
        cliente.secret_hash = hash_token(segredo)
    db.add(cliente)
    db.commit()
    resp = {
        "client_id": cliente.client_id,
        "client_id_issued_at": int(datetime.utcnow().timestamp()),
        "client_name": cliente.nome,
        "redirect_uris": uris,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": metodo,
        "scope": ESCOPO,
    }
    if segredo:
        resp["client_secret"] = segredo
        resp["client_secret_expires_at"] = 0
    return JSONResponse(resp, status_code=201, headers=_SEM_CACHE)


# ─── Tela de login (autorização) ─────────────────────────────────────────
_CAMPOS = ("client_id", "redirect_uri", "state", "code_challenge", "code_challenge_method", "scope", "resource")


def _pagina(titulo: str, corpo: str, status: int = 200) -> HTMLResponse:
    doc = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(titulo)}</title>
<style>
:root{{--bg:#07070f;--card:#0d0d1a;--borda:rgba(255,255,255,.08);--txt:#f1f5f9;--sec:#94a3b8;--ac:#7c3aed;--err:#ef4444}}
@media (prefers-color-scheme: light){{:root{{--bg:#f4f4f8;--card:#fff;--borda:#e2e2ea;--txt:#111827;--sec:#4b5563}}}}
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);
color:var(--txt);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:16px}}
.card{{width:100%;max-width:400px;background:var(--card);border:1px solid var(--borda);border-radius:16px;padding:28px}}
h1{{font-size:20px;margin:0 0 6px}}p{{color:var(--sec);margin:0 0 16px}}label{{display:block;font-size:13px;
color:var(--sec);margin:12px 0 4px}}input{{width:100%;padding:10px 12px;border-radius:8px;border:1px solid var(--borda);
background:transparent;color:var(--txt);font-size:15px}}button{{width:100%;margin-top:18px;padding:11px;border:0;
border-radius:8px;background:var(--ac);color:#fff;font-weight:600;font-size:15px;cursor:pointer}}
.erro{{color:var(--err);margin:12px 0 0}}.marca{{font-weight:700;letter-spacing:.04em;font-size:12px;color:var(--sec);
margin-bottom:14px}}small{{display:block;color:var(--sec);margin-top:14px;font-size:12px}}
</style></head><body><main class="card"><div class="marca">TRILAN BACKUPS</div>{corpo}</main></body></html>"""
    return HTMLResponse(doc, status_code=status, headers={
        **_SEM_CACHE, "X-Frame-Options": "DENY",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'",
        "Referrer-Policy": "no-referrer",
    })


def _tela_login(cliente: McpOauthCliente, campos: dict, erro: str = "", email: str = "") -> HTMLResponse:
    ocultos = "".join(
        f'<input type="hidden" name="{k}" value="{html.escape(campos.get(k) or "")}">' for k in _CAMPOS
    )
    destino = urlparse(campos.get("redirect_uri") or "").hostname or "o aplicativo"
    msg_erro = f'<p class="erro">{html.escape(erro)}</p>' if erro else ""
    corpo = f"""<h1>Conectar {html.escape(cliente.nome or "aplicativo")}</h1>
<p>Entre com o seu login do Trilan Backups. A IA vai poder ver e alterar o sistema com as mesmas permissões que
você tem no painel, e cada alteração fica na Auditoria.</p>
<form method="post" action="/oauth/authorize" autocomplete="on">{ocultos}
<label for="email">E-mail</label><input id="email" name="email" type="email" required value="{html.escape(email)}" autofocus>
<label for="senha">Senha</label><input id="senha" name="senha" type="password" required>
{msg_erro}<button type="submit">Entrar e conectar</button></form>
<small>O acesso será entregue a <strong>{html.escape(destino)}</strong>. Só continue se foi você quem pediu a conexão
nesse aplicativo agora. Para desconectar depois, use "Minha conta" no painel.</small>"""
    return _pagina("Conectar IA - Trilan Backups", corpo)


def _validar_pedido(db: Session, campos: dict):
    """(cliente, erro_exibivel). Erro de cliente/redirect não volta ao app (RFC 6749 4.1.2.1)."""
    cliente = obter_cliente(db, campos.get("client_id") or "")
    if not cliente:
        return None, "Aplicativo não reconhecido. Remova o conector e adicione de novo."
    uri = campos.get("redirect_uri") or ""
    if not uri and len(cliente.redirect_uris or []) == 1:
        campos["redirect_uri"] = uri = cliente.redirect_uris[0]
    if not uri or not _redirect_confere(uri, cliente.redirect_uris or []):
        return None, "Endereço de retorno do aplicativo não confere com o registrado."
    return cliente, ""


def _voltar_com_erro(campos: dict, codigo: str, descricao: str) -> RedirectResponse:
    q = {"error": codigo, "error_description": descricao}
    if campos.get("state"):
        q["state"] = campos["state"]
    sep = "&" if "?" in campos["redirect_uri"] else "?"
    return RedirectResponse(f"{campos['redirect_uri']}{sep}{urlencode(q)}", status_code=302)


@router.get("/oauth/authorize")
def autorizar_tela(request: Request, db: Session = Depends(get_db)):
    campos = {k: request.query_params.get(k) for k in _CAMPOS}
    cliente, erro = _validar_pedido(db, campos)
    if not cliente:
        return _pagina("Erro - Trilan Backups", f"<h1>Não foi possível conectar</h1><p>{html.escape(erro)}</p>", 400)
    if request.query_params.get("response_type") != "code":
        return _voltar_com_erro(campos, "unsupported_response_type", "Só response_type=code.")
    if not campos.get("code_challenge") or (campos.get("code_challenge_method") or "S256") != "S256":
        return _voltar_com_erro(campos, "invalid_request", "PKCE com S256 é obrigatório.")
    return _tela_login(cliente, campos)


@router.post("/oauth/authorize")
async def autorizar_login(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    campos = {k: (form.get(k) or None) for k in _CAMPOS}
    cliente, erro = _validar_pedido(db, campos)
    if not cliente:
        return _pagina("Erro - Trilan Backups", f"<h1>Não foi possível conectar</h1><p>{html.escape(erro)}</p>", 400)
    if not campos.get("code_challenge"):
        return _voltar_com_erro(campos, "invalid_request", "PKCE com S256 é obrigatório.")

    email = str(form.get("email") or "").strip().lower()
    senha = str(form.get("senha") or "")
    ip = ip_do_cliente(request)
    if not limite_login.disponivel(ip):
        return _tela_login(cliente, campos, "Muitas tentativas. Tente de novo em alguns minutos.", email)
    usuario = db.query(Usuario).filter(Usuario.email == email).first() if email else None
    if not senhas.conferir(senha, usuario.senha_hash if usuario else None) or not usuario or not usuario.ativo:
        limite_login.registrar(ip)
        return _tela_login(cliente, campos, "E-mail ou senha incorretos.", email)
    if not usuario_pode_usar_mcp(usuario):
        return _tela_login(cliente, campos, "Só administradores podem conectar uma IA ao sistema.", email)

    codigo = secrets.token_urlsafe(32)
    db.add(McpOauthCodigo(
        codigo_hash=hash_token(codigo), client_id=cliente.client_id, usuario_id=usuario.id,
        redirect_uri=campos["redirect_uri"], code_challenge=campos["code_challenge"],
        expira_em=datetime.utcnow() + CODIGO_VALIDADE,
    ))
    # limpeza dos códigos vencidos
    db.query(McpOauthCodigo).filter(McpOauthCodigo.expira_em < datetime.utcnow() - timedelta(days=1)).delete()
    db.commit()
    q = {"code": codigo}
    if campos.get("state"):
        q["state"] = campos["state"]
    sep = "&" if "?" in campos["redirect_uri"] else "?"
    return RedirectResponse(f"{campos['redirect_uri']}{sep}{urlencode(q)}", status_code=303)


# ─── Token ───────────────────────────────────────────────────────────────
def _autenticar_cliente(db: Session, request: Request, form) -> Optional[McpOauthCliente]:
    client_id = form.get("client_id")
    segredo = form.get("client_secret")
    cab = request.headers.get("authorization", "")
    if cab.lower().startswith("basic "):
        try:
            client_id, segredo = base64.b64decode(cab[6:]).decode().split(":", 1)
        except Exception:
            return None
        client_id, segredo = unquote(client_id), unquote(segredo)
    cliente = obter_cliente(db, client_id or "")
    if not cliente:
        return None
    if cliente.secret_hash:
        if not segredo or not secrets.compare_digest(hash_token(segredo), cliente.secret_hash):
            return None
    return cliente


def _emitir(db: Session, registro: McpToken) -> JSONResponse:
    access, h_access = gerar(PREFIXO_ACCESS)
    refresh, h_refresh = gerar(PREFIXO_REFRESH)
    agora = datetime.utcnow()
    registro.token_hash, registro.expira_em = h_access, agora + ACCESS_VALIDADE
    registro.refresh_hash, registro.refresh_expira_em = h_refresh, agora + REFRESH_VALIDADE
    registro.ultimo_uso = agora
    db.commit()
    return JSONResponse({
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": int(ACCESS_VALIDADE.total_seconds()),
        "refresh_token": refresh,
        "scope": ESCOPO,
    }, headers=_SEM_CACHE)


def _pkce_ok(verificador: str, desafio: str) -> bool:
    if not verificador or not (43 <= len(verificador) <= 128):
        return False
    calc = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).decode().rstrip("=")
    return secrets.compare_digest(calc, desafio)


@router.post("/oauth/token")
async def token(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    cliente = _autenticar_cliente(db, request, form)
    if not cliente:
        return _erro_oauth("invalid_client", "Aplicativo não reconhecido.", 401)
    tipo = form.get("grant_type")

    if tipo == "authorization_code":
        cod = db.query(McpOauthCodigo).filter(McpOauthCodigo.codigo_hash == hash_token(form.get("code") or "")).first()
        if not cod or cod.usado or cod.expira_em < datetime.utcnow() or cod.client_id != cliente.client_id:
            return _erro_oauth("invalid_grant", "Código inválido ou vencido.")
        if (form.get("redirect_uri") or cod.redirect_uri) != cod.redirect_uri:
            return _erro_oauth("invalid_grant", "redirect_uri não confere.")
        if not _pkce_ok(form.get("code_verifier") or "", cod.code_challenge):
            return _erro_oauth("invalid_grant", "code_verifier não confere (PKCE).")
        cod.usado = True
        usuario = db.query(Usuario).filter(Usuario.id == cod.usuario_id).first()
        if not usuario_pode_usar_mcp(usuario):
            db.commit()
            return _erro_oauth("invalid_grant", "Usuário sem permissão para conectar uma IA.")
        registro = McpToken(usuario_id=usuario.id, tipo="OAUTH", nome=cliente.nome or "Aplicativo de IA",
                            token_hash="", client_id=cliente.client_id, token_versao=usuario.token_versao)
        db.add(registro)
        return _emitir(db, registro)

    if tipo == "refresh_token":
        registro = db.query(McpToken).filter(
            McpToken.refresh_hash == hash_token(form.get("refresh_token") or ""), McpToken.tipo == "OAUTH"
        ).first()
        agora = datetime.utcnow()
        if not registro or registro.revogado or registro.client_id != cliente.client_id or \
                not registro.refresh_expira_em or registro.refresh_expira_em < agora:
            return _erro_oauth("invalid_grant", "Conexão expirada ou desconectada. Conecte de novo.")
        usuario = db.query(Usuario).filter(Usuario.id == registro.usuario_id).first()
        if not usuario_pode_usar_mcp(usuario) or usuario.token_versao != registro.token_versao:
            registro.revogado = True
            db.commit()
            return _erro_oauth("invalid_grant", "A senha ou o papel do usuário mudou. Conecte de novo.")
        return _emitir(db, registro)

    return _erro_oauth("unsupported_grant_type", "Use authorization_code ou refresh_token.")


@router.post("/oauth/revoke")
async def revogar(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    h = hash_token(form.get("token") or "")
    registro = db.query(McpToken).filter((McpToken.token_hash == h) | (McpToken.refresh_hash == h)).first()
    if registro and registro.tipo == "OAUTH":
        registro.revogado = True
        db.commit()
    return JSONResponse({}, headers=_SEM_CACHE)
