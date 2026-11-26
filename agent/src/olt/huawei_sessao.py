"""Uma sessao SSH por vez em cada OLT Huawei e nova tentativa quando a OLT fecha a conexao no login.

A OLT Huawei limita as sessoes simultaneas do usuario. O agente abre SSH nela para a coleta de status (a cada 5 min),
para o backup e para o "Testar conexao"; quando um caia em cima do outro, a OLT fechava a conexao nova no meio do login
("Authentication failed: transport shut down or saw EOF") e o backup saia como "senha incorreta" (Recanto Real e
Georgina, 26/11/2026; a coleta seguinte, segundos depois, entrava com a mesma senha).

- `sessao_exclusiva(ip)`: trava por IP dentro do agente; quem chega depois espera a sessao anterior terminar.
- `conectar_com_novas_tentativas(abrir, ...)`: repete o login so quando a OLT fechou a conexao (a senha nem foi
  avaliada). Senha recusada de verdade nao e repetida, para nao bloquear o usuario na OLT.
"""
import logging
import threading
import time
from contextlib import contextmanager

ESPERA_SESSAO_S = 600          # backup completo (config + data por FTP) leva 1 a 3 min; folga para fila de varios
TENTATIVAS_LOGIN = 3
PAUSA_LOGIN_S = 30

_travas = {}
_guarda = threading.Lock()


class OltOcupada(TimeoutError):
    """Outra sessao do proprio agente continua aberta na OLT depois do tempo de espera."""


def _trava(ip: str) -> threading.Lock:
    with _guarda:
        return _travas.setdefault((ip or "").strip(), threading.Lock())


@contextmanager
def sessao_exclusiva(ip: str, espera_s: float = None):
    """Garante uma sessao SSH por vez do agente na OLT `ip`. Levanta OltOcupada se esperou demais."""
    espera_s = ESPERA_SESSAO_S if espera_s is None else espera_s
    trava = _trava(ip)
    if not trava.acquire(blocking=False):
        logging.info(f"[HUAWEI] Outra sessao do agente esta aberta em {ip}; aguardando ela terminar...")
        if not trava.acquire(timeout=espera_s):
            raise OltOcupada(f"outra sessao do agente continua aberta na OLT {ip} depois de {int(espera_s)} s")
    try:
        yield
    finally:
        trava.release()


def login_fechado_pela_olt(e: Exception) -> bool:
    """True quando a OLT fechou a conexao durante o login (sessoes esgotadas, bloqueio temporario), sem avaliar
    a senha. O paramiko levanta AuthenticationException tambem nesse caso, com outro texto."""
    if isinstance(e, (EOFError, ConnectionResetError)):
        return True
    baixo = (str(e) or "").lower()
    return any(m in baixo for m in ("saw eof", "transport shut down", "error reading ssh protocol banner",
                                    "connection reset"))


def conectar_com_novas_tentativas(abrir, descricao: str, tentativas: int = None, pausa_s: float = None):
    """Chama `abrir()` (que devolve o cliente SSH conectado) e repete, com pausa, so quando a OLT fechou a
    conexao no login. Qualquer outro erro (senha recusada, timeout, porta fechada) sobe na hora."""
    tentativas = TENTATIVAS_LOGIN if tentativas is None else tentativas
    pausa_s = PAUSA_LOGIN_S if pausa_s is None else pausa_s
    for n in range(1, tentativas + 1):
        try:
            return abrir()
        except Exception as e:
            if n >= tentativas or not login_fechado_pela_olt(e):
                raise
            logging.warning(f"[HUAWEI] {descricao}: a OLT fechou a conexao no login (tentativa {n}/{tentativas}); "
                            f"nova tentativa em {int(pausa_s)} s. ({e})")
            time.sleep(pausa_s)
