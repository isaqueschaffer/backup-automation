"""
Serviço para manipulação e persistência segura de planilhas VMS (DIGIFORT / DEFENSE).
"""
import json
from typing import List


def colunas_senha(linhas: List[List[str]], linha_cabecalho: int) -> List[int]:
    """Retorna os índices das colunas de senha baseado no cabeçalho."""
    if linha_cabecalho < 0 or linha_cabecalho >= len(linhas):
        return []
    cabecalho = linhas[linha_cabecalho]
    indices: List[int] = []
    for idx, celula in enumerate(cabecalho):
        texto = str(celula or "").strip().lower()
        if "senha" in texto or "pass" in texto:
            indices.append(idx)
    return indices


def mascarar_senhas(
    linhas: List[List[str]],
    linha_cabecalho: int,
    colunas: List[int],
) -> List[List[str]]:
    """Devolve cópia com as colunas de senha mascaradas após a linha do cabeçalho."""
    cols_set = set(colunas)
    resultado: List[List[str]] = []
    for idx_linha, linha in enumerate(linhas):
        if idx_linha <= linha_cabecalho:
            resultado.append(list(linha))
        else:
            nova_linha: List[str] = []
            for idx_col, celula in enumerate(linha):
                if idx_col in cols_set and celula and str(celula).strip():
                    nova_linha.append("••••••")
                else:
                    nova_linha.append(celula)
            resultado.append(nova_linha)
    return resultado


def empacotar(linhas: List[List[str]]) -> str:
    """Serializa as linhas em JSON e criptografa com Fernet."""
    from services.crypto_service import encrypt

    conteudo_json = json.dumps(linhas, ensure_ascii=False)
    return encrypt(conteudo_json)


def desempacotar(dados: str) -> List[List[str]]:
    """Descriptografa com Fernet e desserializa o JSON das linhas."""
    from services.crypto_service import decrypt

    conteudo_json = decrypt(dados)
    return json.loads(conteudo_json)
