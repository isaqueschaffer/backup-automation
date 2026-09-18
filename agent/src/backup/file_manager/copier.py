import os
import shutil
import hashlib
import logging
from pathlib import Path
from typing import Tuple

from src.backup.file_manager.models import BackupStatus

def calculate_sha256(filepath: Path) -> str:
    """Calcula o hash SHA-256 de um arquivo em chunks."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        # Read and update hash string value in blocks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

class SafeCopier:
    def __init__(self, check_hash: bool = True):
        self.check_hash = check_hash

    def copy_file(self, origem: Path, destino: Path) -> Tuple[bool, BackupStatus]:
        """
        Copia de forma segura:
        1. Copia para destino.tmp
        2. Verifica integridade (tamanho e opcionalmente SHA256)
        3. Renomeia para destino
        """
        destino_tmp = destino.with_suffix(destino.suffix + ".tmp")
        
        try:
            # 1. Copia para o temporário
            logging.debug(f"    Copiando {origem.name} -> {destino_tmp.name}...")
            shutil.copy2(origem, destino_tmp)
            
            # 2. Valida Tamanho
            tamanho_origem = origem.stat().st_size
            tamanho_tmp = destino_tmp.stat().st_size
            
            if tamanho_origem != tamanho_tmp:
                logging.error(f"    Tamanho divergente após cópia de {origem.name}")
                if destino_tmp.exists():
                    destino_tmp.unlink()
                return False, BackupStatus.CORROMPIDO
                
            # Valida Hash
            if self.check_hash:
                logging.debug(f"    Calculando SHA-256 para {origem.name}...")
                hash_origem = calculate_sha256(origem)
                hash_tmp = calculate_sha256(destino_tmp)
                
                if hash_origem != hash_tmp:
                    logging.error(f"    SHA-256 divergente após cópia de {origem.name}")
                    if destino_tmp.exists():
                        destino_tmp.unlink()
                    return False, BackupStatus.CORROMPIDO

            # 3. Renomeia para o arquivo final
            if destino.exists():
                destino.unlink() # Remove caso exista algum lixo
            
            destino_tmp.rename(destino)
            return True, BackupStatus.OK
            
        except Exception as e:
            logging.error(f"    Erro ao copiar {origem.name}: {e}")
            if destino_tmp.exists():
                destino_tmp.unlink()
            return False, BackupStatus.ERRO
