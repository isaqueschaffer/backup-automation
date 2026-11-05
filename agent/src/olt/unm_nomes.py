"""Nomes cadastrados das ONUs na UNM2000.

O CLI da OLT so devolve o tipo da ONU; o nome que o operador deu (ex.: "1 ANDAR - QUARTO 229") fica no banco
MySQL do servidor da UNM2000 (tabela `t_ontdevice`, coluna `cobjectname`), ligado ao serial pela coluna `contmac`.
A consulta e somente de leitura.

Acesso: por padrao usa o usuario do MySQL da UNM2000 (abaixo), que serve na maioria das instalacoes; so e preciso
informar usuario/senha no cadastro quando aquele servidor for diferente. Em vez do root e possivel criar um usuario
so de leitura e apontar para ele:
    CREATE USER IF NOT EXISTS 'zabbix_reader'@'%' IDENTIFIED BY '<senha>';
    GRANT SELECT ON integratecfgdb.* TO 'zabbix_reader'@'%';  FLUSH PRIVILEGES;
Cada servidor de UNM2000 tem o seu banco (uma OLT pode estar em um e outra em outro): informe todos em `nomes_db_host`.

O usuario e a senha padrao podem ser trocados pelas variaveis de ambiente TRILAN_UNM_DB_USER e TRILAN_UNM_DB_PASS,
para nao deixar a senha fixa no codigo (ver a observacao de seguranca no cadastro).

ONU sem nome dado pelo operador aparece no banco com um nome automatico ("PON[1]-HG6145E[3]"); esse nome so repete a
posicao da ONU e e tratado como "sem nome".
"""
import logging
import os
import re
import time
from typing import Dict, List, Optional, Tuple

PORTA_BANCO_PADRAO = 3306
BANCO_PADRAO = "integratecfgdb"
# Credencial padrao do MySQL da UNM2000, usada para qualquer servidor quando o cadastro nao informa usuario/senha.
# E um usuario SO DE LEITURA (GRANT SELECT em integratecfgdb), nao o root: se vazar, so da para ler o inventario de ONUs.
# Pode ser trocada por TRILAN_UNM_DB_USER/TRILAN_UNM_DB_PASS na maquina do agente, ou por servidor no proprio cadastro.
USUARIO_PADRAO = os.environ.get("TRILAN_UNM_DB_USER") or "zabbix_reader"
SENHA_PADRAO = os.environ.get("TRILAN_UNM_DB_PASS") or "Zabbix@2024"
TIMEOUT_S = 5
_SQL = "SELECT LOWER(contmac), cobjectname FROM t_ontdevice"
_RE_NOME_AUTOMATICO = re.compile(r"^PON\[\d+\]-.*\[\d+\]$")


def nome_automatico(nome: Optional[str]) -> bool:
    """True para o nome que a UNM2000 gera sozinha ("PON[1]-HG6145E[3]"), ou seja, ONU sem nome dado pelo operador."""
    return bool(_RE_NOME_AUTOMATICO.match((nome or "").strip()))


def buscar_nomes(host: str, usuario: str, senha: str, banco: Optional[str] = None, porta: int = PORTA_BANCO_PADRAO) -> Dict[str, str]:
    """{serial em minusculas: nome}. Levanta excecao se nao conseguir ler o banco."""
    import pymysql
    parametros = dict(host=host, port=porta, user=usuario, password=senha, database=banco or BANCO_PADRAO,
                      charset="utf8mb4", connect_timeout=TIMEOUT_S, read_timeout=TIMEOUT_S * 3)
    try:
        conexao = pymysql.connect(**parametros)
    except pymysql.err.OperationalError as e:
        if e.args and e.args[0] in (1044, 1045, 1049, 1142):  # recusa de acesso nao melhora sozinha
            raise
        time.sleep(2)  # a UNM2000 as vezes derruba a primeira conexao; uma nova tentativa resolve
        conexao = pymysql.connect(**parametros)
    try:
        with conexao.cursor() as cur:
            cur.execute(_SQL)
            return {str(s).strip(): str(n).strip() for s, n in cur.fetchall() if s and n and str(n).strip()}
    finally:
        conexao.close()


def aplicar_nomes(onus: List[dict], nomes: Dict[str, str]) -> Tuple[int, int]:
    """Coloca `nome` em cada ONU pelo serial. Nome automatico da UNM2000 nao conta: a ONU fica sem `nome`.
    Devolve (com nome, sem nome) entre as ONUs que tem serial."""
    com, sem = 0, 0
    for onu in onus or []:
        serial = (onu.get("serial") or "").strip().lower()
        if not serial:
            continue
        nome = nomes.get(serial)
        if nome and not nome_automatico(nome):
            onu["nome"] = nome
            com += 1
        else:
            sem += 1
    return com, sem


def explicar_erro(erro: Exception, host: str) -> str:
    """Mensagem curta, em portugues, do que fazer para a consulta ao banco funcionar."""
    codigo = erro.args[0] if getattr(erro, "args", None) and isinstance(erro.args[0], int) else None
    if codigo in (1045, 1044, 1142):
        return (f"{host}: o banco recusou o usuario/senha. Crie o usuario somente leitura no MySQL da UNM2000 "
                "(GRANT SELECT ON integratecfgdb.*) e confira a senha.")
    if codigo == 1049:
        return f"{host}: banco de dados nao encontrado (o padrao e integratecfgdb)."
    if codigo in (2003, 2002, 2013) or isinstance(erro, (OSError, TimeoutError)):
        return (f"{host}: nao conectou na porta 3306. Use o IP do servidor da UNM2000 (nao o da OLT) e libere a porta "
                "para esta maquina.")
    if isinstance(erro, ImportError):
        return "o agente nao tem o modulo pymysql (instale a versao nova do agente)."
    return f"{host}: {erro}"


def hosts_do_banco(cfg: dict) -> List[str]:
    """IPs dos servidores da UNM2000 (`nomes_db_host`: um ou varios, separados por virgula, ponto e virgula ou linha)."""
    vistos, saida = set(), []
    for h in re.split(r"[\s,;]+", str(cfg.get("nomes_db_host") or "")):
        if h and h not in vistos:
            vistos.add(h)
            saida.append(h)
    return saida


def consultar_nomes(cfg: dict, buscar=None) -> Tuple[Dict[str, str], List[str]]:
    """({serial: nome}, [erros]) juntando os servidores de `nomes_db_host`. Usuario e senha em branco caem no padrao
    (`USUARIO_PADRAO`/`SENHA_PADRAO`), igual para qualquer servidor; o cadastro so precisa informa-los quando aquele
    servidor usar outra credencial. Um nome dado pelo operador vale mais que o automatico, venha de qual servidor vier.
    Sem host devolve vazio e sem erro."""
    hosts = hosts_do_banco(cfg)
    if not hosts:
        return {}, []
    usuario_cfg = (cfg.get("nomes_db_usuario") or "").strip()
    if usuario_cfg:  # o que o usuario digitou no cadastro tem prioridade
        usuario, senha = usuario_cfg, (cfg.get("nomes_db_senha") or "")
    else:
        usuario, senha = USUARIO_PADRAO, SENHA_PADRAO
    try:
        porta = int(cfg.get("nomes_db_porta") or PORTA_BANCO_PADRAO)
    except (TypeError, ValueError):
        porta = PORTA_BANCO_PADRAO
    banco = (cfg.get("nomes_db_nome") or "").strip() or None
    nomes: Dict[str, str] = {}
    erros: List[str] = []
    for host in hosts:
        try:
            for serial, nome in (buscar or buscar_nomes)(host, usuario, senha, banco, porta).items():
                if serial not in nomes or (nome_automatico(nomes[serial]) and not nome_automatico(nome)):
                    nomes[serial] = nome
        except Exception as e:
            logging.warning(f"Nao foi possivel ler os nomes das ONUs em {host}: {e}")
            erros.append(explicar_erro(e, host))
    return nomes, erros


def nomes_das_onus(cfg: dict, buscar=None) -> Dict[str, str]:
    """So os nomes de `consultar_nomes` (falhas ficam no log)."""
    return consultar_nomes(cfg, buscar)[0]
