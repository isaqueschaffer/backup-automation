import os
import re
from pathlib import Path
from typing import List, Dict
import logging

from src.backup.file_manager.models import BackupFile, BackupGroup
from src.backup.file_manager.utils import parse_backup_date

class BaseParser:
    def find_backups(self, pasta_origem: Path) -> List[BackupGroup]:
        raise NotImplementedError

class UNM2000Parser(BaseParser):
    def find_backups(self, pasta_origem: Path) -> List[BackupGroup]:
        """
        Encontra backups do UNM2000 (YYYYMMDD_HHMMSS) e Digifort (diretórios YYYYMMDD).
        """
        extensoes_aceitas = {".zip", ".tar", ".gz", ".7z"}
        grupos = []

        if not pasta_origem.is_dir():
            logging.error(f"  [UNM2000] Pasta de origem não existe: {pasta_origem}")
            return grupos

        for arquivo in pasta_origem.iterdir():
            if arquivo.is_dir():
                # Verifica formato Digifort (YYYYMMDD)
                match = re.match(r'^(\d{8})$', arquivo.name)
                if match:
                    data_str = match.group(1)
                    data_obj = parse_backup_date(data_str)
                    if data_obj:
                        bf = BackupFile(path=arquivo, file_type="DIGIFORT_DIR")
                        bg = BackupGroup(date=data_obj, files=[bf], group_id=data_str)
                        grupos.append(bg)
                continue

            if not arquivo.is_file():
                continue
            if arquivo.suffix.lower() not in extensoes_aceitas:
                continue

            padrao = r'(\d{8}_\d{6})'
            match = re.search(padrao, arquivo.name)
            if not match:
                continue
            
            data_str = match.group(1)
            data_obj = parse_backup_date(data_str)
            if not data_obj:
                continue

            bf = BackupFile(path=arquivo, file_type="ZIP")
            bg = BackupGroup(date=data_obj, files=[bf], group_id=data_str)
            grupos.append(bg)

        # Ordenar do mais recente para o mais antigo
        grupos.sort(key=lambda x: x.date, reverse=True)
        return grupos


class HuaweiParser(BaseParser):
    def find_backups(self, pasta_origem: Path) -> List[BackupGroup]:
        """
        Encontra backups da OLT Huawei. 
        Precisa encontrar os pares: CONFIGURATION e DB com mesmo IP e Data.
        """
        grupos_dict: Dict[str, BackupGroup] = {}
        
        if not pasta_origem.is_dir():
            logging.error(f"  [HUAWEI] Pasta de origem não existe: {pasta_origem}")
            return []

        # Exemplo: CONFIGURATION_10.11.104.2-2026-09-17-033011-1206916249.txt
        # Exemplo: DB_10.11.104.2-2026-09-17-030011-1206736256.dat
        padrao = r'^(CONFIGURATION|DB)_(\d{1,3}(?:\.\d{1,3}){3})-(\d{4}-\d{2}-\d{2})-(\d{6})-\d+\.(txt|dat)$'

        for arquivo in pasta_origem.iterdir():
            if not arquivo.is_file():
                continue
                
            match = re.match(padrao, arquivo.name, re.IGNORECASE)
            if not match:
                continue
            
            tipo = match.group(1).upper()
            ip = match.group(2)
            data_str = f"{match.group(3)}-{match.group(4)}" # YYYY-MM-DD-HHMMSS
            
            data_obj = parse_backup_date(data_str)
            if not data_obj:
                continue
                
            # A chave de agrupamento será IP e Data (ignorando a hora para o agrupamento pois CONFIG e DB podem ter horas ligeiramente diferentes)
            data_pura_str = match.group(3)
            chave = f"{ip}_{data_pura_str}"
            
            if chave not in grupos_dict:
                grupos_dict[chave] = BackupGroup(date=data_obj, files=[], ip=ip, group_id=chave)
                
            # Se já existir, a data no BackupGroup pode ser de qualquer um dos arquivos, isso será validado depois se for mto discrepante.
            # Aqui, apenas adicionamos o arquivo ao grupo.
            bf = BackupFile(path=arquivo, file_type=tipo)
            grupos_dict[chave].files.append(bf)

        grupos = list(grupos_dict.values())
        # Ordenar do mais recente para o mais antigo (baseado na data de um dos arquivos do grupo)
        grupos.sort(key=lambda x: x.date, reverse=True)
        return grupos
