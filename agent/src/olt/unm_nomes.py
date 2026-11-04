"""Nomes cadastrados das ONUs na UNM2000.

O CLI da OLT so devolve o tipo da ONU; o nome que o operador deu (ex.: "1 ANDAR - QUARTO 229") fica no banco
MySQL do servidor da UNM2000 (tabela `t_ontdevice`, coluna `cobjectname`), ligado ao serial pela coluna `contmac`.
A consulta e somente de leitura.
"""
import logging
from typing import Dict, List, Optional

PORTA_BANCO_PADRAO = 3306
BANCO_PADRAO = "integratecfgdb"
TIMEOUT_S = 5
_SQL = "SELECT LOWER(contmac), cobjectname FROM t_ontdevice"


def buscar_nomes(host: str, usuario: str, senha: str, banco: Optional[str] = None, porta: int = PORTA_BANCO_PADRAO) -> Dict[str, str]:
    """{serial em minusculas: nome}. Levanta excecao se nao conseguir ler o banco."""
    import pymysql
    conexao = pymysql.connect(host=host, port=porta, user=usuario, password=senha, database=banco or BANCO_PADRAO,
                              charset="utf8mb4", connect_timeout=TIMEOUT_S, read_timeout=TIMEOUT_S * 3)
    try:
        with conexao.cursor() as cur:
            cur.execute(_SQL)
            return {str(s).strip(): str(n).strip() for s, n in cur.fetchall() if s and n and str(n).strip()}
    finally:
        conexao.close()


def aplicar_nomes(onus: List[dict], nomes: Dict[str, str]) -> int:
    """Coloca `nome` em cada ONU pelo serial. Devolve quantas ficaram com nome."""
    achadas = 0
    for onu in onus or []:
        nome = nomes.get((onu.get("serial") or "").strip().lower())
        if nome:
            onu["nome"] = nome
            achadas += 1
    return achadas


def nomes_das_onus(cfg: dict, buscar=None) -> Dict[str, str]:
    """Nomes pelo banco configurado (`nomes_db_host`, `nomes_db_usuario`, `nomes_db_senha`, `nomes_db_nome`,
    `nomes_db_porta`). Sem host/usuario configurados devolve vazio; falha de acesso e registrada e devolve vazio."""
    host = (cfg.get("nomes_db_host") or "").strip()
    usuario = (cfg.get("nomes_db_usuario") or "").strip()
    if not host or not usuario:
        return {}
    try:
        porta = int(cfg.get("nomes_db_porta") or PORTA_BANCO_PADRAO)
    except (TypeError, ValueError):
        porta = PORTA_BANCO_PADRAO
    try:
        return (buscar or buscar_nomes)(host, usuario, cfg.get("nomes_db_senha") or "", (cfg.get("nomes_db_nome") or "").strip() or None, porta)
    except Exception as e:
        logging.warning(f"Nao foi possivel ler os nomes das ONUs em {host}: {e}")
        return {}
