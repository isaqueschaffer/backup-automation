"""
Serviço para manipulação e persistência segura de planilhas VMS (DIGIFORT / DEFENSE).
"""
import json
from typing import List


def casar_cameras_por_ip(itens: List, cameras_db: List) -> List:
    """Para cada item da planilha devolve a câmera já existente que ele substitui (ou None se for nova).

    O IP manda: se o IP aparece uma só vez na planilha e em uma só câmera da galeria, é a mesma câmera mesmo com
    nome diferente (a câmera é atualizada em vez de duplicada). IP repetido (um equipamento com vários canais)
    não serve de chave: aí vale o nome, ou o canal quando o item o informa. Cada câmera existente casa com no
    máximo um item."""
    def ip_de(obj) -> str:
        return (getattr(obj, "ip", None) or "").strip()

    def nome_de(obj) -> str:
        return (getattr(obj, "nome", None) or "").strip().lower()

    from collections import Counter
    na_planilha = Counter(ip_de(i) for i in itens if ip_de(i))
    na_galeria = Counter(ip_de(c) for c in cameras_db if ip_de(c))
    por_ip = {ip_de(c): c for c in cameras_db if ip_de(c) and na_galeria[ip_de(c)] == 1}
    por_nome = {}
    for c in cameras_db:
        por_nome.setdefault(nome_de(c), c)
    por_canal = {c.canal: c for c in cameras_db}

    usadas = set()
    resultado = []
    for item in itens:
        ip, nome = ip_de(item), nome_de(item)
        achada = None
        if ip and na_planilha[ip] == 1:
            achada = por_ip.get(ip)
        if achada is None and nome:
            achada = por_nome.get(nome)
        if achada is None and getattr(item, "canal", None):
            achada = por_canal.get(item.canal)
        if achada is not None and id(achada) in usadas:
            achada = None
        if achada is not None:
            usadas.add(id(achada))
        resultado.append(achada)
    return resultado


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
