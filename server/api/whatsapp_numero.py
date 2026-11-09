"""Normalização de números de WhatsApp (módulo puro, sem dependências do projeto).

Formato guardado no banco e enviado ao container do WhatsApp: só dígitos com DDI (ex.: 5511999998888).
Número com 10 ou 11 dígitos (DDD + telefone) é tratado como brasileiro e ganha o DDI 55.
"""
import re
from typing import Iterable, List, Optional

_SO_DIGITOS = re.compile(r"\D+")


def normalizar_numero(valor: Optional[str]) -> Optional[str]:
    """Devolve só os dígitos com DDI, ou None se `valor` estiver vazio. Levanta ValueError se for inválido."""
    bruto = (valor or "").strip()
    if not bruto:
        return None
    digitos = _SO_DIGITOS.sub("", bruto)
    # "+" ou "00" na frente = o usuário já informou o DDI: não presumir Brasil
    internacional = bruto.startswith("+") or digitos.startswith("00")
    if digitos.startswith("00"):
        digitos = digitos[2:]
    if not internacional and len(digitos) in (10, 11):
        digitos = "55" + digitos
    # Sem "+": só passa com DDI (12 a 15 dígitos, ex.: 55 + DDD + número). Com "+": E.164 permite de 8 a 15.
    if not (8 if internacional else 12) <= len(digitos) <= 15:
        raise ValueError(f"Número de WhatsApp inválido: {bruto}. Use DDD + número (ex.: 11 99999-8888) ou o formato internacional.")
    return digitos


def normalizar_lista(valores: Optional[Iterable[str]]) -> Optional[List[str]]:
    """Normaliza cada item, descarta vazios e repetidos (ordem mantida). None continua None."""
    if valores is None:
        return None
    resultado: List[str] = []
    for item in valores:
        # aceita vários números na mesma entrada, separados por vírgula, ponto e vírgula ou quebra de linha
        for parte in re.split(r"[,;\n]", item or ""):
            numero = normalizar_numero(parte)
            if numero and numero not in resultado:
                resultado.append(numero)
    return resultado
