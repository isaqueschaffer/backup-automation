import time
import logging
from datetime import datetime
from typing import Tuple

from src.backup.file_manager.models import BackupGroup, BackupStatus

class Validator:
    @staticmethod
    def is_expected_date(group: BackupGroup, expected_date: datetime) -> bool:
        """
        Verifica se a data do grupo de backup é a data esperada (normalmente o dia de hoje).
        """
        return group.date.date() == expected_date.date()

    @staticmethod
    def is_complete_huawei(group: BackupGroup) -> bool:
        """
        Para Huawei, o backup só é válido se tiver CONFIGURATION e DB.
        """
        tipos_encontrados = {f.file_type for f in group.files}
        return "CONFIGURATION" in tipos_encontrados and "DB" in tipos_encontrados

    @staticmethod
    def validate_group_for_copy(group: BackupGroup, expected_date: datetime, is_huawei: bool = False) -> Tuple[bool, BackupStatus]:
        """
        Aplica todas as validações de regras de negócio antes de copiar um grupo.
        Retorna (sucesso_na_validacao, status_do_backup).
        """
        if not group.files:
            return False, BackupStatus.SEM_ARQUIVOS

        if not Validator.is_expected_date(group, expected_date):
            return False, BackupStatus.ANTIGO

        if is_huawei:
            if not Validator.is_complete_huawei(group):
                return False, BackupStatus.INCOMPLETO

        return True, BackupStatus.OK

    @staticmethod
    def is_stable(group: BackupGroup, wait_seconds: int = 3) -> bool:
        """
        Verifica se os arquivos do grupo pararam de crescer.
        """
        tamanhos_iniciais = {}
        for f in group.files:
            chave = f.remote_path if ((f.is_smb or f.is_sftp) and f.remote_path) else f.path
            tamanhos_iniciais[chave] = f.size_bytes
        
        # Espera um pouco para ver se os arquivos estão sendo escritos
        time.sleep(wait_seconds)
        
        for f in group.files:
            chave = f.remote_path if ((f.is_smb or f.is_sftp) and f.remote_path) else f.path
            if f.is_sftp and f.remote_path:
                try:
                    tamanho_atual = f.sftp.tamanho(f.remote_path)
                except Exception:
                    tamanho_atual = f.size_bytes
            elif f.is_smb and f.remote_path:
                try:
                    from src.backup.smb_storage import SmbStorage
                    tamanho_atual = SmbStorage.get_file_size(f.remote_path)
                except Exception:
                    tamanho_atual = f.size_bytes
            else:
                tamanho_atual = f.size_bytes

            if tamanho_atual != tamanhos_iniciais[chave]:
                logging.warning(f"  Arquivo instável (sendo escrito): {f.path.name}")
                return False
                
        return True
