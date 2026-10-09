from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

class BackupStatus(str, Enum):
    OK = "OK"
    JA_PROCESSADO = "JA_PROCESSADO"
    ANTIGO = "BACKUP_ANTIGO"
    INCOMPLETO = "BACKUP_INCOMPLETO"
    INCONSISTENTE = "BACKUP_INCONSISTENTE"
    NAO_ENCONTRADO = "BACKUP_NAO_ENCONTRADO"
    EM_PROCESSAMENTO = "BACKUP_EM_PROCESSAMENTO"
    CORROMPIDO = "BACKUP_CORROMPIDO"
    ERRO = "ERRO"
    TIPO_NAO_SUPORTADO = "TIPO_NAO_SUPORTADO"
    SEM_ARQUIVOS = "SEM_ARQUIVOS"
    PARCIAL = "PARCIAL"

@dataclass
class BackupFile:
    path: Path
    file_type: str  # "ZIP", "TAR", "CONFIGURATION", "DB", etc.
    
    @property
    def size_bytes(self) -> int:
        if not self.path.exists():
            return 0
        if self.path.is_file():
            return self.path.stat().st_size
        if self.path.is_dir():
            return sum(f.stat().st_size for f in self.path.rglob('*') if f.is_file())
        return 0

@dataclass
class BackupGroup:
    """Um grupo lógico de arquivos que formam um backup (ex: 1 zip, ou 1 config + 1 db)"""
    date: datetime
    files: List[BackupFile] = field(default_factory=list)
    ip: Optional[str] = None
    group_id: str = ""
    
    @property
    def total_size_mb(self) -> float:
        return sum(f.size_bytes for f in self.files) / (1024 * 1024)
