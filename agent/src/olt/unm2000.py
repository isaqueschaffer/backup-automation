# -*- coding: utf-8 -*-
"""
Módulo OLT — Backup via UNM2000
Extraído do agente_unm.py da Helena e adaptado para rodar como serviço automático.
"""

import os
import re
import shutil
import logging
import datetime
from pathlib import Path


# ============================================================
# IDENTIFICA DATA/HORA DENTRO DO NOME DO ARQUIVO
# ============================================================

def extrair_data_backup(nome_arquivo: str):
    """
    Procura dentro do nome um trecho no formato YYYYMMDD_HHMMSS.

    Exemplos aceitos:
        20260910_030154_allback.zip
        backup_agerip_20260910_030154_allback.zip
        UNM_backup_20260910_030154.zip
    """
    padrao = r'(\d{8})_(\d{6})'
    resultado = re.search(padrao, nome_arquivo)
    if not resultado:
        return None
    data_str = resultado.group(1)
    hora_str = resultado.group(2)
    try:
        return datetime.datetime.strptime(data_str + "_" + hora_str, "%Y%m%d_%H%M%S")
    except ValueError:
        return None


# ============================================================
# CONVERTE O NOME DO BACKUP PARA FORMATO LEGÍVEL
# 20260910_080532_allback.zip → 10-09-2026_08_05_32.zip
# ============================================================

def novo_nome(nome_original: str) -> str:
    padrao = r'(\d{8})_(\d{6})'
    resultado = re.search(padrao, nome_original)
    if not resultado:
        padrao_digifort = r'^(\d{8})$'
        resultado_digifort = re.match(padrao_digifort, nome_original)
        if resultado_digifort:
            data_backup = datetime.datetime.strptime(resultado_digifort.group(1), "%Y%m%d")
            return data_backup.strftime("%d-%m-%Y.zip")
        raise ValueError(f"Formato de backup desconhecido: {nome_original}")
    data_str = resultado.group(1)
    hora_str = resultado.group(2)
    data_backup = datetime.datetime.strptime(data_str + "_" + hora_str, "%Y%m%d_%H%M%S")
    return data_backup.strftime("%d-%m-%Y_%H_%M_%S.zip")


# ============================================================
# LOCALIZAR BACKUPS NA PASTA DE ORIGEM
# ============================================================

def encontrar_backups(pasta_origem: str) -> list:
    """
    Varre a pasta_origem e retorna lista de backups encontrados,
    ordenados do mais recente ao mais antigo.
    """
    extensoes_aceitas = {".zip", ".tar", ".gz", ".7z"}
    backups = []

    if not os.path.isdir(pasta_origem):
        logging.error(f"  [OLT] Pasta de origem não existe: {pasta_origem}")
        return backups

    for nome in os.listdir(pasta_origem):
        caminho = os.path.join(pasta_origem, nome)
        
        if os.path.isdir(caminho):
            if re.match(r'^\d{8}$', nome):
                try:
                    data_backup = datetime.datetime.strptime(nome, "%Y%m%d")
                    backups.append({"nome": nome, "caminho": caminho, "data": data_backup, "tipo": "digifort"})
                except ValueError:
                    pass
            continue
            
        if not os.path.isfile(caminho):
            continue
        if os.path.splitext(nome)[1].lower() not in extensoes_aceitas:
            continue
        data_backup = extrair_data_backup(nome)
        if data_backup is None:
            continue
        backups.append({"nome": nome, "caminho": caminho, "data": data_backup, "tipo": "unm"})

    backups.sort(key=lambda x: x["data"], reverse=True)
    return backups


# ============================================================
# FUNÇÃO PRINCIPAL — chamada pelo backup_job.py
# ============================================================

def realizar_backup_olt(equipamento: dict, pasta_destino: Path) -> dict:
    """
    Realiza o backup de uma OLT via UNM2000.

    O equipamento deve ter em config_extra:
        pasta_origem: str — caminho onde o UNM2000 exporta os backups

    O backup mais recente ainda não copiado é encontrado e copiado
    para pasta_destino/<nome_equipamento>/

    Retorna dict com: nome, status (OK | JA_PROCESSADO | ERRO), arquivo, destino
    """
    nome = equipamento.get("name", "OLT_desconhecida")
    config_extra = equipamento.get("config_extra") or {}
    pasta_origem = config_extra.get("pasta_origem", "")

    logging.info(f"\n{'='*50}\n{nome} [OLT/UNM2000]\n{'='*50}")

    if not pasta_origem:
        logging.error(f"  [OLT] config_extra.pasta_origem não informado para {nome}.")
        return {"nome": nome, "status": "ERRO", "cameras": None}

    if not os.path.isdir(pasta_origem):
        logging.error(f"  [OLT] Pasta de origem não existe: {pasta_origem}")
        return {"nome": nome, "status": "ERRO", "cameras": None}

    # Garante pasta de destino para este equipamento
    pasta_eq = pasta_destino / nome.replace(" ", "_")
    pasta_eq.mkdir(parents=True, exist_ok=True)

    # Busca backups disponíveis
    backups = encontrar_backups(pasta_origem)
    if not backups:
        logging.error(f"  [OLT] Nenhum backup no formato esperado encontrado em: {pasta_origem}")
        return {"nome": nome, "status": "ERRO", "cameras": None}

    # Procura o mais recente que ainda não foi copiado
    backup_pendente = None
    for backup in backups:
        nome_destino = novo_nome(backup["nome"])
        arquivo_destino = pasta_eq / nome_destino
        if not arquivo_destino.exists():
            backup_pendente = backup
            break
        logging.info(f"  [OLT] Já processado: {arquivo_destino.name}")

    if backup_pendente is None:
        logging.info(f"  [OLT] Todos os backups já existem no destino.")
        return {"nome": nome, "status": "JA_PROCESSADO", "cameras": None}

    # Processa o arquivo ou pasta
    nome_destino = novo_nome(backup_pendente["nome"])
    arquivo_destino = pasta_eq / nome_destino
    arquivo_origem = backup_pendente["caminho"]
    tipo = backup_pendente.get("tipo", "unm")

    logging.info(f"  [OLT] Novo backup encontrado: {backup_pendente['nome']}")
    
    if tipo == "digifort" or os.path.isdir(arquivo_origem):
        logging.info(f"  [OLT] Comprimindo pasta para: {arquivo_destino}")
        base_name = str(arquivo_destino.with_suffix(''))
        shutil.make_archive(base_name, 'zip', arquivo_origem)
    else:
        logging.info(f"  [OLT] Copiando para: {arquivo_destino}")
        shutil.copy2(arquivo_origem, arquivo_destino)

    tamanho_mb = os.path.getsize(arquivo_destino) / (1024 * 1024)

    logging.info(f"  [OLT] Backup processado com sucesso. ({tamanho_mb:.2f} MB)")

    return {
        "nome": nome,
        "status": "OK",
        "arquivo": nome_destino,
        "destino": str(arquivo_destino),
        "tamanho_mb": tamanho_mb,
        "cameras": None,
    }
