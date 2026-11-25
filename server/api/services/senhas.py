"""Hash de senhas dos usuários do painel (bcrypt direto, sem passlib)."""
import re

import bcrypt

SENHA_MIN = 10
SENHA_MAX_BYTES = 72  # limite do bcrypt
# Hash fixo para igualar o tempo de resposta quando o e-mail não existe
_HASH_FALSO = bcrypt.hashpw(b"senha-inexistente-trilan", bcrypt.gensalt()).decode()


def validar_senha_nova(senha: str) -> None:
    """ValueError com a mensagem para o usuário se a senha não serve."""
    if len(senha or "") < SENHA_MIN:
        raise ValueError(f"A senha precisa ter pelo menos {SENHA_MIN} caracteres.")
    if len(senha.encode()) > SENHA_MAX_BYTES:
        raise ValueError("A senha pode ter no máximo 72 bytes.")


_FORMATO_BCRYPT = re.compile(r"^\$2[aby]?\$\d{2}\$[./A-Za-z0-9]{53}$")


def eh_hash_bcrypt(valor: str | None) -> bool:
    """True se o valor tem o formato de um hash bcrypt ($2b$12$ + 53 caracteres)."""
    return bool(valor) and bool(_FORMATO_BCRYPT.match(valor))


def gerar_hash(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


def conferir(senha: str, senha_hash: str | None) -> bool:
    """Compara em tempo constante; sem hash (usuário inexistente) compara com o hash falso e devolve False."""
    try:
        ok = bcrypt.checkpw((senha or "").encode()[:SENHA_MAX_BYTES], (senha_hash or _HASH_FALSO).encode())
    except ValueError:
        return False
    return ok and senha_hash is not None
