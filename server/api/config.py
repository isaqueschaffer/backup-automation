from typing import List, Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # Security
    SECRET_KEY: str
    FERNET_KEY: str  # Base64-encoded 32-byte key for Fernet encryption
    ACCESS_TOKEN_EXPIRE_HOURS: int = 8

    # Admin
    ADMIN_PASSWORD: str  # Obrigatório — defina via variável de ambiente ADMIN_PASSWORD
    PUBLIC_URL: Optional[str] = None

    # CORS — lista de origens permitidas separadas por vírgula.
    # Ex: CORS_ORIGINS=https://painel.suaempresa.com,https://outro.dominio.com
    # Use "*" apenas em desenvolvimento local.
    CORS_ORIGINS: str = ""

    # Storage
    BACKUP_STORAGE_PATH: str = "/data/backups"
    # Tamanho máximo aceito no upload de ZIP do agente (em MB)
    MAX_UPLOAD_MB: int = 1024

    # Rodadas de backup do Cliente (1 e-mail por rodada)
    # Prazo máximo da rodada a partir do início (horas)
    RUN_DEADLINE_HOURS: int = 2
    # Espera após o último relatório antes de fechar (tempo para o ZIP chegar)
    RUN_UPLOAD_GRACE_SECONDS: int = 90

    # SMTP
    SMTP_SERVER: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_EMAIL: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
