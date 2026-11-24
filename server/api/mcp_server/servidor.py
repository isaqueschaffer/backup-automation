"""Endpoint MCP (POST /mcp, Streamable HTTP sem estado, respostas JSON) e as rotas dos tokens em "Minha conta"."""
import base64
import json
import logging
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from auth import Contexto, get_contexto_sem_bloqueio
from database import SessionLocal, get_db
from models import McpToken, Usuario
from services.dashboards.compartilhamento import ip_do_cliente

from . import executor
from .ferramentas import catalogo
from .tokens import PAPEIS_MCP, PREFIXO_PESSOAL, base_url, gerar, validar_access

logger = logging.getLogger("trilan.mcp")

VERSOES = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
LIMITE_TEXTO = 80_000
LIMITE_IMAGEM = 2 * 1024 * 1024

INSTRUCOES = """Trilan Backups: sistema que faz backup automático da configuração de equipamentos (NVRs, câmeras, OLTs,
Mikrotik, centrais de alarme, antenas, DIGIFORT...) e monitora o estado deles.
Hierarquia: Conta (integrador ou cliente final) > Cliente/Setor > Máquina (computador com o agente instalado) >
Equipamento. Os backups e os testes são feitos pelo agente da máquina.
Você age em nome do usuário conectado, com as mesmas permissões dele no painel; tudo o que alterar fica na
Auditoria como "<e-mail> (IA via MCP)". Antes de excluir algo ou de agir em todas as máquinas, confirme com o
usuário. Para achar ids, liste primeiro (clientes, máquinas, equipamentos)."""

router = APIRouter(tags=["MCP"])
tokens_router = APIRouter(prefix="/api/v1/mcp", tags=["MCP"])


def _metadados_recurso(request: Request) -> str:
    return f"{base_url(request)}/.well-known/oauth-protected-resource/mcp"


def _nao_autorizado(request: Request, motivo: str = "") -> Response:
    desafio = f'Bearer resource_metadata="{_metadados_recurso(request)}"'
    if motivo:  # cabeçalho HTTP: só ASCII
        desafio += ', error="invalid_token", error_description="Token invalido, vencido ou revogado"'
    return JSONResponse(
        {"error": "invalid_token", "error_description": motivo or "Conecte-se com o login do Trilan Backups."},
        status_code=401,
        headers={"WWW-Authenticate": desafio},
    )


def _erro(id_: Any, codigo: int, mensagem: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": codigo, "message": mensagem}}


def _ok(id_: Any, resultado: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": resultado}


def _autenticar(bruto: str):
    with SessionLocal() as db:
        achado = validar_access(db, bruto)
        if not achado:
            return None
        _, u = achado
        # cópia simples: a sessão fecha aqui e o objeto do ORM não pode ser usado depois
        return SimpleNamespace(id=u.id, email=u.email, papel=u.papel, token_versao=u.token_versao)


def _texto_resultado(resp: executor.Resposta) -> dict:
    if resp.status >= 400:
        try:
            detalhe = json.loads(resp.corpo).get("detail")
        except Exception:
            detalhe = resp.corpo[:2000].decode(errors="replace")
        if not isinstance(detalhe, str):
            detalhe = json.dumps(detalhe, ensure_ascii=False, default=str)
        return {"content": [{"type": "text", "text": f"Erro {resp.status}: {detalhe}"}], "isError": True}
    if not resp.corpo:
        return {"content": [{"type": "text", "text": f"OK ({resp.status}, sem conteúdo)."}]}
    if resp.tipo.startswith("image/") and len(resp.corpo) <= LIMITE_IMAGEM:
        return {"content": [{"type": "image", "mimeType": resp.tipo, "data": base64.b64encode(resp.corpo).decode()}]}
    if resp.tipo == "application/json" or resp.tipo.startswith("text/"):
        texto = resp.corpo.decode(errors="replace")
        if resp.tipo == "application/json":
            try:
                texto = json.dumps(json.loads(texto), ensure_ascii=False, default=str)
            except Exception:
                pass
        if len(texto) > LIMITE_TEXTO:
            texto = texto[:LIMITE_TEXTO] + f"\n\n[Resposta cortada: {len(texto)} caracteres. Use filtros ou paginação.]"
        return {"content": [{"type": "text", "text": texto}]}
    nome = resp.headers.get("content-disposition", "")
    return {"content": [{"type": "text", "text": (
        f"A rota devolveu um arquivo ({resp.tipo or 'binário'}, {len(resp.corpo)} bytes) {nome}. "
        "Arquivos não passam pela IA: baixe pelo painel."
    )}]}


async def _tratar(msg: Any, request: Request, usuario: Usuario) -> Optional[dict]:
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return _erro(msg.get("id") if isinstance(msg, dict) else None, -32600, "Pedido JSON-RPC inválido.")
    metodo = msg["method"]
    id_ = msg.get("id")
    notificacao = "id" not in msg
    params = msg.get("params") or {}
    super_admin = usuario.papel == "SUPER_ADMIN"

    if notificacao:
        return None
    if metodo == "initialize":
        pedida = params.get("protocolVersion")
        versao = pedida if pedida in VERSOES else VERSOES[0]
        return _ok(id_, {
            "protocolVersion": versao,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "trilan-backups", "title": "Trilan Backups", "version": "1.0.0"},
            "instructions": INSTRUCOES,
        })
    if metodo == "ping":
        return _ok(id_, {})
    if metodo == "tools/list":
        ferramentas = [f.para_mcp(super_admin) for f in catalogo(request.app) if super_admin or not f.so_super]
        return _ok(id_, {"tools": ferramentas})
    if metodo in ("resources/list", "resources/templates/list", "prompts/list"):
        chave = {"resources/list": "resources", "resources/templates/list": "resourceTemplates"}.get(metodo, "prompts")
        return _ok(id_, {chave: []})
    if metodo == "logging/setLevel":
        return _ok(id_, {})
    if metodo == "tools/call":
        nome = params.get("name")
        f = next((x for x in catalogo(request.app) if x.nome == nome), None)
        if not f or (f.so_super and not super_admin):
            return _erro(id_, -32602, f"Ferramenta desconhecida: {nome}")
        try:
            caminho, query, corpo, conta_id = f.montar_pedido(params.get("arguments") or {})
        except ValueError as e:
            return _ok(id_, {"content": [{"type": "text", "text": str(e)}], "isError": True})
        if not super_admin:
            conta_id = None
        logger.info("MCP %s %s %s (%s)", usuario.email, f.metodo, caminho, f.nome)
        resp = await executor.chamar(request.app, usuario, f.metodo, caminho, query, corpo, conta_id,
                                     ip=ip_do_cliente(request))
        return _ok(id_, _texto_resultado(resp))
    return _erro(id_, -32601, f"Método não suportado: {metodo}")


@router.post("/mcp", include_in_schema=False)
async def mcp(request: Request):
    cab = request.headers.get("authorization", "")
    bruto = cab[7:].strip() if cab.lower().startswith("bearer ") else ""
    if not bruto:
        return _nao_autorizado(request)
    usuario = await run_in_threadpool(_autenticar, bruto)
    if not usuario:
        return _nao_autorizado(request, "Token inválido, vencido ou revogado.")
    try:
        corpo = await request.json()
    except Exception:
        return JSONResponse(_erro(None, -32700, "JSON inválido."), status_code=400)

    if isinstance(corpo, list):
        respostas = [r for r in [await _tratar(m, request, usuario) for m in corpo] if r is not None]
        return JSONResponse(respostas) if respostas else Response(status_code=202)
    resposta = await _tratar(corpo, request, usuario)
    if resposta is None:
        return Response(status_code=202)
    return JSONResponse(resposta)


@router.get("/mcp", include_in_schema=False)
@router.delete("/mcp", include_in_schema=False)
async def mcp_sem_stream():
    # Sem estado e sem notificações do servidor: não há stream SSE nem sessão para encerrar
    return Response(status_code=405, headers={"Allow": "POST"})


# ─── Tokens em "Minha conta" ─────────────────────────────────────────────
class NovoToken(BaseModel):
    nome: str = Field(min_length=1, max_length=100)


def _exigir_admin_com_usuario(ctx: Contexto) -> None:
    if ctx.via == "mcp":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A IA não gerencia os próprios acessos.")
    if ctx.usuario_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Entre com um usuário com e-mail para conectar uma IA.")
    if ctx.papel not in PAPEIS_MCP:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Só administradores podem conectar uma IA ao sistema.")


def _resumo(t: McpToken) -> dict:
    return {
        "id": str(t.id), "tipo": t.tipo, "nome": t.nome, "criado_em": t.criado_em,
        "ultimo_uso": t.ultimo_uso, "expira_em": t.refresh_expira_em if t.tipo == "OAUTH" else None,
    }


@tokens_router.get("/info")
def info_mcp(request: Request, ctx: Contexto = Depends(get_contexto_sem_bloqueio)):
    return {
        "url": f"{base_url(request)}/mcp",
        "pode_usar": ctx.usuario_id is not None and ctx.papel in PAPEIS_MCP,
    }


@tokens_router.get("/tokens")
def listar_tokens(ctx: Contexto = Depends(get_contexto_sem_bloqueio), db: Session = Depends(get_db)):
    _exigir_admin_com_usuario(ctx)
    agora = datetime.utcnow()
    tokens = (
        db.query(McpToken)
        .filter(McpToken.usuario_id == ctx.usuario_id, McpToken.revogado == False)  # noqa: E712
        .order_by(McpToken.criado_em.desc())
        .all()
    )
    return [_resumo(t) for t in tokens if t.tipo == "PESSOAL" or (t.refresh_expira_em and t.refresh_expira_em > agora)]


@tokens_router.post("/tokens", status_code=201)
def criar_token(body: NovoToken, ctx: Contexto = Depends(get_contexto_sem_bloqueio), db: Session = Depends(get_db)):
    _exigir_admin_com_usuario(ctx)
    usuario = db.query(Usuario).filter(Usuario.id == ctx.usuario_id).first()
    bruto, h = gerar(PREFIXO_PESSOAL)
    t = McpToken(usuario_id=usuario.id, tipo="PESSOAL", nome=body.nome.strip(), token_hash=h,
                 token_versao=usuario.token_versao)
    db.add(t)
    db.commit()
    db.refresh(t)
    return {**_resumo(t), "token": bruto}


@tokens_router.delete("/tokens/{token_id}", status_code=204)
def revogar_token(token_id: UUID, ctx: Contexto = Depends(get_contexto_sem_bloqueio), db: Session = Depends(get_db)):
    _exigir_admin_com_usuario(ctx)
    t = db.query(McpToken).filter(McpToken.id == token_id, McpToken.usuario_id == ctx.usuario_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Acesso não encontrado.")
    t.revogado = True
    db.commit()
    return Response(status_code=204)
