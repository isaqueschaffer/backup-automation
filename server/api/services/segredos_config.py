"""Senhas guardadas dentro do `config_extra` de um equipamento (ex.: acesso Telnet da OLT da UNM2000).

No banco ficam criptografadas (Fernet) em `<campo>_enc`. O painel nunca recebe a senha: só `<campo>_definida`
(True/False), e deixar o campo em branco ao editar mantém a senha atual. O agente recebe a senha em texto, como
já acontece com a senha do equipamento.
"""
from typing import Any, Optional

from services.crypto_service import decrypt, encrypt

SEGREDOS = ("telnet_senha", "telnet_enable", "nomes_db_senha")


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
