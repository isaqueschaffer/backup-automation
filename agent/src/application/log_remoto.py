"""
Módulo de captura, filtragem, deduplicação e envio de logs do agente para o servidor.
"""
from __future__ import annotations

import collections
from contextlib import contextmanager
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

INTERVALO_ENVIO_S = 20
MAX_FILA = 500
MAX_POR_ENVIO = 100
TAMANHO_MAX_MENSAGEM = 4000
JANELA_DEDUP_S = 600

# Contexto por thread para rastrear o equipamento em execução e envio em andamento
_contexto_thread = threading.local()


def _obter_equipamento_contexto() -> Optional[str]:
    """Retorna o equipamento atual associado à thread."""
    return getattr(_contexto_thread, "equipamento", None)


def _esta_enviando() -> bool:
    """Indica se a thread atual está em processo de envio HTTP de logs."""
    return getattr(_contexto_thread, "enviando_logs", False)


@contextmanager
def _marcar_enviando():
    """Gerenciador de contexto que marca a thread atual como em envio de logs."""
    _contexto_thread.enviando_logs = True
    try:
        yield
    finally:
        _contexto_thread.enviando_logs = False


@contextmanager
def equipamento_atual(nome: Optional[str]):
    """
    Context manager que define o nome do equipamento na thread atual
    e restaura o valor anterior ao finalizar o bloco.
    """
    anterior = getattr(_contexto_thread, "equipamento", None)
    _contexto_thread.equipamento = (nome.strip() if isinstance(nome, str) and nome.strip() else None)
    try:
        yield
    finally:
        _contexto_thread.equipamento = anterior


# Regex para ocultar senhas em URLs: ://usuario:senha@host -> ://usuario:***@host
_PADRAO_URL = re.compile(r"://([^:\s/@]+):([^@\s/]+)@")

# Chaves sensíveis que devem ter seus valores mascarados
_CHAVES_SEGREDO = (
    "password", "passwd", "pwd", "senha", "secret", "secretkey",
    "token", "api_key", "apikey", "x-api-key", "authorization",
)
_CHAVES_PIPE = "|".join(re.escape(k) for k in _CHAVES_SEGREDO)

# Pares com aspas: "senha": "abc" ou 'senha': 'abc' ou "senha"="abc"
_PADRAO_ASPAS = re.compile(
    rf'(?i)(["\']?(?:{_CHAVES_PIPE})["\']?\s*[:=]\s*)(["\'])(?:(?!\2).)*\2'
)

# Pares sem aspas: chave=valor ou chave: valor (inclui Authorization: Bearer ...)
_PADRAO_SEM_ASPAS = re.compile(
    rf'(?i)(\b(?:{_CHAVES_PIPE})\b\s*[:=]\s*)(?:Bearer\s+[^\s,;&"\']+|[^\s,;&"\']+)'
)


def ocultar_segredos(texto: str, extras: tuple = ()) -> str:
    """
    Mascara senhas e segredos no texto:
    (a) Senhas em URLs (://usuario:senha@host);
    (b) Pares chave=valor, chave: valor e "chave": "valor" para chaves sensíveis;
    (c) Textos literais fornecidos em extras (ex: api_key).
    """
    if not texto or not isinstance(texto, str):
        return ""

    # (a) URL com senha
    texto = _PADRAO_URL.sub(r"://\1:***@", texto)

    # (b) Pares chave-valor com aspas e sem aspas
    texto = _PADRAO_ASPAS.sub(r"\g<1>\g<2>***\g<2>", texto)
    texto = _PADRAO_SEM_ASPAS.sub(r"\g<1>***", texto)

    # (c) Textos literais extras
    if extras:
        for extra in extras:
            if extra and isinstance(extra, str):
                extra_limpo = extra.strip()
                if extra_limpo:
                    texto = texto.replace(extra_limpo, "***")

    return texto


class ManipuladorLogRemoto(logging.Handler):
    """
    Handler de logging que enfileira avisos, erros e marcos de backup
    para envio em lote ao servidor Trilan.
    """

    def __init__(self):
        super().__init__()
        self.fila: collections.deque[Dict[str, Any]] = collections.deque(maxlen=MAX_FILA)
        self.lock = threading.Lock()
        self.dedup: Dict[Tuple[str, Optional[str], str], float] = {}
        self.extras: Tuple[str, ...] = ()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            nome = record.name or ""
            # (1) Ignora bibliotecas de rede/warnings, o próprio módulo e recursão de envio
            if (
                nome.startswith("urllib3")
                or nome.startswith("requests")
                or nome.startswith("py.warnings")
                or nome == __name__
                or nome.startswith(__name__ + ".")
                or _esta_enviando()
            ):
                return

            # (2) Aceita apenas >= WARNING ou se explicitamente marcado para envio
            enviar_servidor = bool(getattr(record, "enviar_servidor", False))
            if record.levelno < logging.WARNING and not enviar_servidor:
                return

            # (3) Obtém mensagem, formata exceção se houver, mascara segredos e trunca
            mensagem = record.getMessage()
            if record.exc_info:
                tb = self.formatException(record.exc_info)
                if tb:
                    mensagem = f"{mensagem}\n{tb}"

            mensagem = ocultar_segredos(mensagem, extras=self.extras).strip()
            if not mensagem:
                return
            if len(mensagem) > TAMANHO_MAX_MENSAGEM:
                mensagem = mensagem[:TAMANHO_MAX_MENSAGEM]

            # (4) Nível normalizado
            if record.levelno >= logging.ERROR:
                nivel = "ERROR"
            elif record.levelno >= logging.WARNING:
                nivel = "WARNING"
            else:
                nivel = "INFO"

            # (5) Equipamento associado
            equipamento = getattr(record, "equipamento", None) or _obter_equipamento_contexto()
            if isinstance(equipamento, str):
                equipamento = equipamento.strip() or None
            else:
                equipamento = None

            agora = time.monotonic()

            # (6) Deduplicação para registros ordinários (não marcados com enviar_servidor)
            if not enviar_servidor:
                chave = (nivel, equipamento, mensagem[:200])
                with self.lock:
                    ultimo = self.dedup.get(chave)
                    if ultimo is not None and (agora - ultimo) < JANELA_DEDUP_S:
                        return
                    self.dedup[chave] = agora
                    if len(self.dedup) > 1000:
                        self.dedup = {
                            k: v for k, v in self.dedup.items()
                            if (agora - v) < JANELA_DEDUP_S
                        }

            # (7) Enfileira o registro
            item = {
                "nivel": nivel,
                "mensagem": mensagem,
                "equipamento": equipamento,
                "_t": agora,
            }
            with self.lock:
                self.fila.append(item)

        except Exception:
            # O manipulador de log NUNCA pode derrubar o agente
            pass


_instancia: Optional[ManipuladorLogRemoto] = None


def instalar(conf: dict) -> ManipuladorLogRemoto:
    """
    Cria ou recupera a instância única do manipulador de log remoto,
    configura a extração de segredos e adiciona ao logger raiz.
    """
    global _instancia
    if _instancia is None:
        _instancia = ManipuladorLogRemoto()
        logging.getLogger().addHandler(_instancia)

    extras: List[str] = []
    if isinstance(conf, dict):
        api_key = conf.get("api_key")
        if api_key and isinstance(api_key, str):
            extras.append(api_key)
    _instancia.extras = tuple(extras)

    return _instancia


def enviar_pendentes(conf: dict) -> int:
    """
    Envia até MAX_POR_ENVIO logs pendentes ao servidor via HTTP.
    Calcula segundos_atras no momento do envio e remove da fila somente após confirmação.
    """
    if _instancia is None:
        return 0

    with _instancia.lock:
        if not _instancia.fila:
            return 0
        qtd = min(len(_instancia.fila), MAX_POR_ENVIO)
        itens_para_enviar = [_instancia.fila[i] for i in range(qtd)]

    agora = time.monotonic()
    lista_payload = []
    for item in itens_para_enviar:
        segundos_atras = max(0, min(86400, int(agora - item["_t"])))
        lista_payload.append({
            "nivel": item["nivel"],
            "mensagem": item["mensagem"],
            "equipamento": item["equipamento"],
            "segundos_atras": segundos_atras,
        })

    # Importação tardia para evitar dependência circular
    from src.application.api_client import send_logs

    with _marcar_enviando():
        try:
            sucesso = send_logs(conf, lista_payload)
        except Exception:
            sucesso = False

    if sucesso:
        with _instancia.lock:
            # Remove exatamente os itens enviados confirmados
            for item in itens_para_enviar:
                if _instancia.fila and _instancia.fila[0] is item:
                    _instancia.fila.popleft()
                else:
                    break
        return qtd

    return 0
