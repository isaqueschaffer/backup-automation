"""Senhas guardadas dentro do `config_extra` de um equipamento (ex.: acesso Telnet da OLT da UNM2000).

No banco ficam criptografadas (Fernet) em `<campo>_enc`. O painel nunca recebe a senha: só `<campo>_definida`
(True/False), e deixar o campo em branco ao editar mantém a senha atual. O agente recebe a senha em texto, como
já acontece com a senha do equipamento.
"""
import re
from typing import Any, Optional

from services.crypto_service import decrypt, encrypt

SEGREDOS = ("telnet_senha", "telnet_enable", "nomes_db_senha", "smb_senha", "smb_password", "ssh_senha", "ssh_chave")


ACESSOS_REMOTOS = ("sftp", "smb")
_FINGERPRINT = re.compile(r"^(SHA256:)?[A-Za-z0-9+/]{43}=?$")


def validar_acesso_remoto(config: Optional[dict]) -> Optional[str]:
    """Valida os campos do acesso remoto à máquina do cliente (agente do MikroTik). Devolve a mensagem de erro ou None.
    `acesso_remoto` = sftp (SSH, somente leitura, nada criado no cliente) | smb (provisiona usuário e share por SSH);
    `ssh_chave` = chave privada (PEM/OpenSSH, segredo como a `ssh_senha`); `ssh_fingerprint` = SHA256 da chave do host."""
    if not isinstance(config, dict):
        return None
    modo = config.get("acesso_remoto")
    if modo not in (None, "") and str(modo).strip().lower() not in ACESSOS_REMOTOS:
        return f"Método de acesso remoto inválido. Use: {', '.join(ACESSOS_REMOTOS)}."
    chave = config.get("ssh_chave")
    if chave:
        texto = str(chave).strip()
        if "PRIVATE KEY" not in texto[:80]:
            return "A chave SSH precisa ser a chave PRIVADA (começa com '-----BEGIN ... PRIVATE KEY-----')."
        if len(texto) > 16_384:
            return "Chave SSH grande demais."
    fp = config.get("ssh_fingerprint")
    if fp and not _FINGERPRINT.match(str(fp).strip()):
        return "Impressão digital SSH inválida (use o formato SHA256:... do ssh-keygen -lf)."
    porta = config.get("ssh_porta")
    if porta not in (None, ""):
        try:
            if not 1 <= int(porta) <= 65535:
                raise ValueError
        except (TypeError, ValueError):
            return "Porta SSH inválida."
    return None


def tem_segredos(config: Optional[dict]) -> bool:
    return isinstance(config, dict) and any(f"{c}_enc" in config or c in config for c in SEGREDOS)


def proteger_segredos(novo: Optional[dict], antigo: Optional[dict] = None) -> Optional[dict]:
    """Config para gravar: senhas novas criptografadas; em branco mantém a anterior; marcadores do painel saem."""
    if not isinstance(novo, dict):
        return novo
    saida = {k: v for k, v in novo.items() if not any(k in (f"{c}_enc", f"{c}_definida") for c in SEGREDOS)}
    for campo in SEGREDOS:
        valor = novo.get(campo)
        if valor:
            saida.pop(campo, None)
            saida[f"{campo}_enc"] = encrypt(str(valor))
        else:
            saida.pop(campo, None)
            anterior = (antigo or {}).get(f"{campo}_enc")
            if anterior:
                saida[f"{campo}_enc"] = anterior
    return saida


def mascarar_segredos(config: Any) -> Any:
    """Config para o painel: sem senhas, com `<campo>_definida`."""
    if not isinstance(config, dict):
        return config
    saida = {k: v for k, v in config.items() if not any(k in (c, f"{c}_enc") for c in SEGREDOS)}
    for campo in SEGREDOS:
        if config.get(f"{campo}_enc") or config.get(campo):
            saida[f"{campo}_definida"] = True
    return saida


def config_extra_para_agente(config: Any) -> Any:
    """Config para o agente: senhas em texto nos campos originais (`telnet_senha`...)."""
    if not isinstance(config, dict):
        return config
    saida = {k: v for k, v in config.items() if not any(k == f"{c}_enc" for c in SEGREDOS)}
    for campo in SEGREDOS:
        cifrada = config.get(f"{campo}_enc")
        if cifrada:
            try:
                saida[campo] = decrypt(cifrada)
            except Exception:
                saida.pop(campo, None)
    return saida
