import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime,
    BigInteger, Text, JSON, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from database import Base


class Client(Base):
    __tablename__ = "clients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    api_key_hash = Column(String(255), nullable=False, unique=True)
    api_key_prefix = Column(String(20), nullable=False)  # first chars shown in UI
    backup_hour = Column(Integer, default=2)
    backup_minute = Column(Integer, default=0)
    zip_password = Column(Text, nullable=True)  # Fernet-encrypted
    email_to = Column(ARRAY(String), default=[], nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    last_seen = Column(DateTime, nullable=True)
    last_backup_at = Column(DateTime, nullable=True)
    last_backup_status = Column(String(20), nullable=True)  # OK, PARTIAL, ERROR
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    restart_requested = Column(Boolean, default=False, nullable=False)

    nvrs = relationship("NVR", back_populates="client", cascade="all, delete-orphan")
    equipamentos = relationship("NVR", back_populates="client", cascade="all, delete-orphan", overlaps="nvrs")
    backups = relationship("Backup", back_populates="client")


class NVR(Base):
    """Tabela de equipamentos (NVR, OLT, ONU, PABX). Mantém nome 'nvrs' no BD para compatibilidade."""
    __tablename__ = "nvrs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False
    )
    tipo = Column(String(20), nullable=False, default="NVR")  # NVR, OLT, ONU, PABX
    name = Column(String(255), nullable=False)
    ip = Column(String(50), nullable=False)
    username = Column(String(100), nullable=False)
    password = Column(Text, nullable=False)  # Fernet-encrypted
    config_extra = Column(JSON, nullable=True)  # configurações específicas de cada tipo
    last_recording_status = Column(JSON, nullable=True)

    client = relationship("Client", back_populates="nvrs", overlaps="equipamentos")


class Backup(Base):
    __tablename__ = "backups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False)  # OK, PARTIAL, ERROR
    nvr_results = Column(JSON, nullable=True)
    zip_filename = Column(String(255), nullable=True)
    zip_size = Column(BigInteger, nullable=True)
    email_sent = Column(Boolean, default=False)
    trigger = Column(String(50), default="scheduled")  # scheduled | manual
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    client = relationship("Client", back_populates="backups")


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)
