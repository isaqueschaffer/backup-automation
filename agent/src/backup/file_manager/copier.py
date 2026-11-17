import os
import shutil
import hashlib
import logging
from pathlib import Path
from typing import Tuple, Union

from src.backup.file_manager.models import BackupStatus, BackupFile

def calculate_sha256(filepath: Path) -> str:
    """Calcula o hash SHA-256 de um arquivo em blocos de 1MB para otimizar chamadas de I/O."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        # Blocos de 1MB (1048576 bytes) em vez de 4KB para evitar milhões de syscalls em backups grandes
        for byte_block in iter(lambda: f.read(1048576), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

class SafeCopier:
    def __init__(self, check_hash: bool = True):
        self.check_hash = check_hash

    def copy_file(self, origem: Union[Path, BackupFile, str], destino: Path) -> Tuple[bool, BackupStatus]:
        """
        Copia de forma segura:
        - Se origem for remota SMB (BackupFile com is_smb=True ou string UNC): streaming via SmbStorage.
        - Se origem for local: copia para destino.tmp, valida integridade e renomeia.
        """
        # Caso SMB
        if isinstance(origem, BackupFile) and origem.is_smb:
            from src.backup.smb_storage import SmbStorage
            remote_unc = origem.remote_path or str(origem.path)
            if origem.file_type == "DIGIFORT_DIR":
                return SmbStorage().copy_directory(remote_unc, destino)
            return SmbStorage().copy_file(remote_unc, destino, check_hash=self.check_hash)

        if isinstance(origem, str) and origem.startswith(("\\\\", "//")):
            from src.backup.smb_storage import SmbStorage
            return SmbStorage().copy_file(origem, destino, check_hash=self.check_hash)

        caminho_origem = origem.path if isinstance(origem, BackupFile) else Path(origem)
        destino_tmp = destino.with_suffix(destino.suffix + ".tmp")
        
        try:
            # 1. Copia para o temporário
            if caminho_origem.is_dir():
                logging.debug(f"    Copiando diretório {caminho_origem.name} -> {destino_tmp.name}...")
                shutil.copytree(caminho_origem, destino_tmp, dirs_exist_ok=True)
            else:
                logging.debug(f"    Copiando {caminho_origem.name} -> {destino_tmp.name}...")
                shutil.copy2(caminho_origem, destino_tmp)
            
            # 2. Valida Tamanho
            if caminho_origem.is_file():
                tamanho_origem = caminho_origem.stat().st_size
                tamanho_tmp = destino_tmp.stat().st_size
                
                if tamanho_origem != tamanho_tmp:
                    logging.error(f"    Tamanho divergente após cópia de {caminho_origem.name}")
                    if destino_tmp.exists():
                        destino_tmp.unlink()
                    return False, BackupStatus.CORROMPIDO
                    
                # Valida Hash
                if self.check_hash:
                    logging.debug(f"    Calculando SHA-256 para {caminho_origem.name}...")
                    hash_origem = calculate_sha256(caminho_origem)
                    hash_tmp = calculate_sha256(destino_tmp)
                    
                    if hash_origem != hash_tmp:
                        logging.error(f"    SHA-256 divergente após cópia de {caminho_origem.name}")
                        if destino_tmp.exists():
                            destino_tmp.unlink()
                        return False, BackupStatus.CORROMPIDO

            # 3. Renomeia para o arquivo final
            if destino.exists():
                destino.unlink() # Remove caso exista algum lixo
            
            destino_tmp.rename(destino)
            return True, BackupStatus.OK
            
        except Exception as e:
            logging.error(f"    Erro ao copiar {caminho_origem.name if hasattr(caminho_origem, 'name') else caminho_origem}: {e}")
            if destino_tmp.exists():
                destino_tmp.unlink()
            return False, BackupStatus.ERRO
