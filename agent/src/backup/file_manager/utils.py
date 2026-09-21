import re
import unicodedata
from datetime import datetime

def sanitize_name(nome: str) -> str:
    """
    Substitui espaços por '_' e remove caracteres inválidos, 
    deixando o nome seguro para diretórios e arquivos.
    """
    # Remove acentos
    nome_sem_acento = ''.join(
        c for c in unicodedata.normalize('NFD', nome)
        if unicodedata.category(c) != 'Mn'
    )
    # Substitui caracteres inválidos e espaços por '_'
    nome_seguro = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', nome_sem_acento)
    # Remove multiplos underscores
    nome_seguro = re.sub(r'_+', '_', nome_seguro)
    # Remove '_' do inicio e fim
    return nome_seguro.strip('_')

def parse_backup_date(data_str: str) -> datetime:
    """
    Converte strings de data de backups (UNM2000 ou Huawei) para datetime.
    Suporta:
      - YYYYMMDD_HHMMSS (UNM2000)
      - YYYY-MM-DD-HHMMSS (Huawei)
    Retorna None se não conseguir dar parse.
    """
    # Tenta padrão UNM2000 (ex: 20260910_030154)
    padrao_unm = r'^(\d{8})_(\d{6})$'
    res_unm = re.match(padrao_unm, data_str)
    if res_unm:
        try:
            return datetime.strptime(data_str, "%Y%m%d_%H%M%S")
        except ValueError:
            pass

    # Tenta padrão Huawei (ex: 2026-09-17-033011)
    padrao_huawei = r'^(\d{4}-\d{2}-\d{2})-(\d{6})$'
    res_huawei = re.match(padrao_huawei, data_str)
    if res_huawei:
        try:
            return datetime.strptime(data_str, "%Y-%m-%d-%H%M%S")
        except ValueError:
            pass

    return None

def get_agent_date() -> datetime:
    """
    Retorna a data e hora atual considerada pelo agente.
    Centraliza a chamada de datetime.now() para toda a lógica de backups.
    """
    return datetime.now()
