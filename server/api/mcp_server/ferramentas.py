"""Catálogo de ferramentas do MCP, montado a partir das rotas do painel (/api/v1).

Cada rota do painel que usa o contexto do usuário (get_contexto e afins) vira uma ferramenta, com o esquema de
entrada tirado do OpenAPI do FastAPI. Assim tudo o que o painel faz fica disponível e rota nova entra sozinha.
Ficam de fora: login/sessão, os próprios tokens do MCP, o link público, as rotas do agente (outra autenticação)
e o cadastro de versão OTA (feito só pelo publish_version.ps1). Rota só do super admin só aparece para ele.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi.routing import APIRoute

import auth as _auth

CAMPO_CONTA = "contexto_conta_id"

_DEPS_CONTEXTO = {
    _auth.get_contexto,
    _auth.get_contexto_teste,
    _auth.get_contexto_sem_bloqueio,
    _auth.exigir_super_admin,
    _auth.exigir_admin_conta,
    _auth.verify_admin_token,
}
_DEPS_SUPER = {_auth.exigir_super_admin, _auth.verify_admin_token}

_PREFIXOS_FORA = ("/api/v1/auth", "/api/v1/mcp", "/api/v1/public", "/api/v1/agent")

_ROTULO_TAG = {
    "clients": "Clientes/Setores",
    "machines": "Máquinas",
    "backups": "Backups",
    "settings": "Configurações",
}


@dataclass
class Ferramenta:
    nome: str
    metodo: str
    caminho: str
    descricao: str
    esquema: Dict[str, Any]
    params_caminho: List[str] = field(default_factory=list)
    params_query: List[str] = field(default_factory=list)
    campos_corpo: List[str] = field(default_factory=list)  # campos do corpo JSON achatados no topo
    corpo_inteiro: bool = False  # corpo não é objeto: vai em "body"
    tem_corpo: bool = False
    so_super: bool = False
    leitura: bool = False
    destrutiva: bool = False

    def para_mcp(self, super_admin: bool) -> dict:
        esquema = self.esquema
        if super_admin:
            esquema = {**esquema, "properties": {**esquema.get("properties", {}), CAMPO_CONTA: {
                "type": "string",
                "description": "Só administrador da plataforma: id da conta em que agir (como escolher a conta no "
                               "painel). Vazio = conta da plataforma. Liste as contas com a ferramenta de contas.",
            }}}
        anot = {"title": self.titulo, "readOnlyHint": self.leitura, "openWorldHint": False}
        if not self.leitura:
            anot["destructiveHint"] = self.destrutiva
            anot["idempotentHint"] = self.metodo in ("PUT", "DELETE")
        return {"name": self.nome, "title": self.titulo, "description": self.descricao,
                "inputSchema": esquema, "annotations": anot}

    @property
    def titulo(self) -> str:
        return self.descricao.split("\n", 1)[0][:120]

    def montar_pedido(self, args: Dict[str, Any]):
        """(caminho, query, corpo, conta_id) a partir dos argumentos da IA. ValueError se faltar parâmetro."""
        args = dict(args or {})
        conta_id = args.pop(CAMPO_CONTA, None) or None
        caminho = self.caminho
        for p in self.params_caminho:
            if args.get(p) in (None, ""):
                raise ValueError(f"Falta o parâmetro obrigatório '{p}'.")
            caminho = caminho.replace("{" + p + "}", quote(str(args[p]), safe=""))
        query = {p: args[p] for p in self.params_query if p in args and args[p] is not None}
        corpo = None
        if self.tem_corpo:
            if self.corpo_inteiro:
                corpo = args.get("body")
            else:
                corpo = {c: args[c] for c in self.campos_corpo if c in args}
        return caminho, query, corpo, conta_id


def _deps(dependant) -> set:
    achadas = set()
    for d in dependant.dependencies:
        if d.call is not None:
            achadas.add(d.call)
        achadas |= _deps(d)
    return achadas


def _limpar(no: Any, comps: Dict[str, Any], pilha: tuple = ()) -> Any:
    """Resolve $ref (o esquema da ferramenta fica autocontido) e tira os "title" que só gastam token."""
    if isinstance(no, list):
        return [_limpar(x, comps, pilha) for x in no]
    if not isinstance(no, dict):
        return no
    if "$ref" in no:
        nome = no["$ref"].rsplit("/", 1)[-1]
        if nome in pilha or nome not in comps:
            return {"type": "object"}
        base = _limpar(comps[nome], comps, pilha + (nome,))
        extra = {k: v for k, v in no.items() if k != "$ref"}
        return {**base, **_limpar(extra, comps, pilha)} if extra else base
    saida = {}
    for k, v in no.items():
        if k == "title" and isinstance(v, str):
            continue
        if k == "properties" and isinstance(v, dict):
            saida[k] = {nome: _limpar(sub, comps, pilha) for nome, sub in v.items()}
        else:
            saida[k] = _limpar(v, comps, pilha)
    return saida


def _nome_valido(nome: str) -> str:
    nome = re.sub(r"[^a-zA-Z0-9_-]", "_", nome)[:64]
    return nome or "ferramenta"


def _destrutiva(metodo: str, caminho: str, nome: str) -> bool:
    if metodo == "DELETE":
        return True
    alvo = f"{caminho} {nome}".lower()
    return any(p in alvo for p in ("-all", "_all", "rotate", "delete", "excluir", "remover", "apagar", "limpar"))


def montar_catalogo(app) -> List[Ferramenta]:
    openapi = app.openapi()
    comps = openapi.get("components", {}).get("schemas", {})
    caminhos = openapi.get("paths", {})
    usados: set = set()
    saida: List[Ferramenta] = []

    for rota in app.routes:
        if not isinstance(rota, APIRoute) or not rota.include_in_schema:
            continue
        if not rota.path.startswith("/api/v1/") or rota.path.startswith(_PREFIXOS_FORA):
            continue
        deps = _deps(rota.dependant)
        if not deps & _DEPS_CONTEXTO:
            continue
        caminho = re.sub(r"\{(\w+):\w+\}", r"{\1}", rota.path)  # "{x:path}" -> "{x}", como no OpenAPI
        for metodo in sorted(rota.methods - {"HEAD", "OPTIONS"}):
            op = caminhos.get(caminho, {}).get(metodo.lower())
            if not op:
                continue
            props: Dict[str, Any] = {}
            obrig: List[str] = []
            f = Ferramenta(nome="", metodo=metodo, caminho=caminho, descricao="", esquema={})

            for p in op.get("parameters", []):
                if p.get("in") not in ("path", "query"):
                    continue
                esquema_p = _limpar(p.get("schema", {}), comps)
                if p.get("description"):
                    esquema_p["description"] = p["description"]
                props[p["name"]] = esquema_p
                if p.get("required"):
                    obrig.append(p["name"])
                (f.params_caminho if p["in"] == "path" else f.params_query).append(p["name"])

            corpo = op.get("requestBody")
            if corpo:
                conteudo = corpo.get("content", {})
                if "application/json" not in conteudo:
                    continue  # upload de arquivo (multipart): a IA não tem como mandar o arquivo
                esquema_c = _limpar(conteudo["application/json"].get("schema", {}), comps)
                f.tem_corpo = True
                if esquema_c.get("type") == "object" and isinstance(esquema_c.get("properties"), dict) \
                        and not set(esquema_c["properties"]) & set(props):
                    props.update(esquema_c["properties"])
                    f.campos_corpo = list(esquema_c["properties"])
                    obrig += [c for c in esquema_c.get("required", [])]
                else:
                    f.corpo_inteiro = True
                    props["body"] = esquema_c
                    if corpo.get("required"):
                        obrig.append("body")

            nome = _nome_valido(rota.name)
            if nome in usados:
                nome = _nome_valido(f"{rota.name}_{metodo.lower()}")
            n = 2
            while nome in usados:
                nome = _nome_valido(f"{rota.name}_{n}")
                n += 1
            usados.add(nome)

            texto = (op.get("description") or "").strip() or op.get("summary") or rota.name
            tags = ", ".join(_ROTULO_TAG.get(t, t) for t in op.get("tags", []))
            f.nome = nome
            f.descricao = f"{texto}\n\nRota do painel: {metodo} {caminho}" + (f" ({tags})" if tags else "")
            f.esquema = {"type": "object", "properties": props, **({"required": obrig} if obrig else {})}
            f.so_super = bool(deps & _DEPS_SUPER)
            f.leitura = metodo == "GET"
            f.destrutiva = not f.leitura and _destrutiva(metodo, caminho, rota.name)
            saida.append(f)
    return saida


_cache: Optional[List[Ferramenta]] = None


def catalogo(app) -> List[Ferramenta]:
    global _cache
    if _cache is None:
        _cache = montar_catalogo(app)
    return _cache
