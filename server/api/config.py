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

    # SMTP
    SMTP_SERVER: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_EMAIL: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
