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

# Criacao automatica do usuario de leitura: o agente roda SEMPRE no proprio servidor da UNM2000, entao se a credencial
# padrao for recusada ele cria o usuario de leitura usando o root do MySQL, so por localhost (127.0.0.1), sem SSH nem
# acesso remoto. A senha do root (padrao de instalacao da UNM2000) pode ser trocada por TRILAN_UNM_ROOT_PASS; a criacao
# pode ser desligada com TRILAN_UNM_AUTOCRIAR=0. O root nunca sai da maquina: e usado so para esse GRANT local.
HOST_LOCAL = "127.0.0.1"
ROOT_USUARIO = os.environ.get("TRILAN_UNM_ROOT_USER") or "root"
ROOT_SENHA = os.environ.get("TRILAN_UNM_ROOT_PASS") or "vislecaina"
AUTO_CRIAR_LEITURA = (os.environ.get("TRILAN_UNM_AUTOCRIAR") or "1") != "0"
TIMEOUT_S = 5
_SQL = "SELECT LOWER(contmac), cobjectname FROM t_ontdevice"
_RE_NOME_AUTOMATICO = re.compile(r"^PON\[\d+\]-.*\[\d+\]$")
_RE_IDENTIFICADOR = re.compile(r"^\w+$")


def nome_automatico(nome: Optional[str]) -> bool:
    """True para o nome que a UNM2000 gera sozinha ("PON[1]-HG6145E[3]"), ou seja, ONU sem nome dado pelo operador."""
    return bool(_RE_NOME_AUTOMATICO.match((nome or "").strip()))


def _acesso_negado(e: Exception) -> bool:
    return bool(getattr(e, "args", None)) and isinstance(e.args[0], int) and e.args[0] in (1044, 1045, 1142)


def criar_usuario_leitura(usuario: str, senha: str, banco: Optional[str] = None, porta: int = PORTA_BANCO_PADRAO) -> None:
    """Cria (ou atualiza) o usuario so-leitura `usuario` no MySQL local da UNM2000, logando como root por 127.0.0.1.
    Da apenas GRANT SELECT no banco. Levanta excecao se o root nao aceitar a conexao."""
    import pymysql
    nome_banco = banco or BANCO_PADRAO
    if not _RE_IDENTIFICADOR.match(nome_banco):
        raise ValueError(f"nome de banco invalido: {nome_banco}")
    conexao = pymysql.connect(host=HOST_LOCAL, port=porta, user=ROOT_USUARIO, password=ROOT_SENHA,
                              charset="utf8mb4", connect_timeout=TIMEOUT_S)
    try:
        with conexao.cursor() as cur:
            cur.execute(f"GRANT SELECT ON `{nome_banco}`.* TO %s@'%%' IDENTIFIED BY %s", (usuario, senha))
            cur.execute("FLUSH PRIVILEGES")
        conexao.commit()
        logging.info(f"Usuario de leitura '{usuario}' criado/ajustado no MySQL local da UNM2000.")
    finally:
        conexao.close()


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


def consultar_nomes(cfg: dict, buscar=None, provisionar=None) -> Tuple[Dict[str, str], List[str]]:
    """({serial: nome}, [erros]) juntando os servidores de `nomes_db_host`. Sem host informado usa 127.0.0.1 (o agente
    roda no proprio servidor da UNM2000). Usuario e senha em branco caem no padrao (`USUARIO_PADRAO`/`SENHA_PADRAO`);
    o cadastro so precisa informa-los quando aquele servidor usar outra credencial. Se o padrao for recusado, cria o
    usuario de leitura pelo root local (uma vez) e refaz a leitura. Um nome dado pelo operador vale mais que o automatico."""
    hosts = hosts_do_banco(cfg) or [HOST_LOCAL]
    usuario_cfg = (cfg.get("nomes_db_usuario") or "").strip()
    if usuario_cfg:  # o que o usuario digitou no cadastro tem prioridade; nesse caso nao criamos nada
        usuario, senha, usa_padrao = usuario_cfg, (cfg.get("nomes_db_senha") or ""), False
    else:
        usuario, senha, usa_padrao = USUARIO_PADRAO, SENHA_PADRAO, True
    try:
        porta = int(cfg.get("nomes_db_porta") or PORTA_BANCO_PADRAO)
    except (TypeError, ValueError):
        porta = PORTA_BANCO_PADRAO
    banco = (cfg.get("nomes_db_nome") or "").strip() or None
    ler = buscar or buscar_nomes
    nomes: Dict[str, str] = {}
    erros: List[str] = []
    ja_tentou_criar = False
    for host in hosts:
        while True:
            try:
                dados = ler(host, usuario, senha, banco, porta)
            except Exception as e:
                if usa_padrao and AUTO_CRIAR_LEITURA and _acesso_negado(e) and not ja_tentou_criar:
                    ja_tentou_criar = True
                    try:
                        (provisionar or criar_usuario_leitura)(usuario, senha, banco, porta)
                        continue  # usuario criado: refaz a leitura deste host
                    except Exception as ec:
                        logging.warning(f"Nao foi possivel criar o usuario de leitura na UNM2000: {ec}")
                        erros.append(f"nao foi possivel criar o usuario de leitura: {explicar_erro(ec, HOST_LOCAL)}")
                        break
                logging.warning(f"Nao foi possivel ler os nomes das ONUs em {host}: {e}")
                erros.append(explicar_erro(e, host))
                break
            for serial, nome in dados.items():
                if serial not in nomes or (nome_automatico(nomes[serial]) and not nome_automatico(nome)):
                    nomes[serial] = nome
            break
    return nomes, erros


def nomes_das_onus(cfg: dict, buscar=None) -> Dict[str, str]:
    """So os nomes de `consultar_nomes` (falhas ficam no log)."""
    return consultar_nomes(cfg, buscar)[0]
