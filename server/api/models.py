import uuid
from datetime import datetime
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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    restart_requested = Column(Boolean, default=False, nullable=False)
    backup_requested = Column(Boolean, default=False, nullable=False)

    nvrs = relationship("NVR", back_populates="client", cascade="all, delete-orphan")
    equipamentos = relationship("NVR", back_populates="client", cascade="all, delete-orphan", overlaps="nvrs")
    backups = relationship("Backup", back_populates="client")
    logs = relationship("AgentLog", back_populates="client", cascade="all, delete-orphan", order_by="desc(AgentLog.created_at)")


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
    active = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("Client", back_populates="nvrs", overlaps="equipamentos")
    cameras_status = relationship("NVRCamera", back_populates="nvr", cascade="all, delete-orphan")


class NVRCamera(Base):
    """Tabela de Câmeras atreladas a um NVR. Armazena imagens Base64."""
    __tablename__ = "nvr_cameras"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nvr_id = Column(UUID(as_uuid=True), ForeignKey("nvrs.id", ondelete="CASCADE"), nullable=False)
    canal = Column(Integer, nullable=False)
    nome = Column(String(255), nullable=False)
    perfect_image_base64 = Column(Text, nullable=True)
    night_image_base64 = Column(Text, nullable=True)
    night_image_date = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    nvr = relationship("NVR", back_populates="cameras_status")


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
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client", back_populates="backups")


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(50), nullable=False)  # ex: ping, backup_trigger, restart_trigger
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    client = relationship("Client", back_populates="logs")


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)


class AgentVersion(Base):
    """Controla versões do agente Windows para atualização OTA via GitHub Releases."""
    __tablename__ = "agent_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version = Column(String(20), nullable=False, unique=True)       # ex: "2.1.0"
    notes = Column(Text, nullable=True)                              # release notes
    url_service = Column(Text, nullable=False)                       # URL do TrilanAgentService.exe
    url_tray = Column(Text, nullable=True)                           # URL do TrilanAgentTray.exe
    sha256_service = Column(String(64), nullable=False)              # hash SHA256 do service exe
    sha256_tray = Column(String(64), nullable=True)                  # hash SHA256 do tray exe
    active = Column(Boolean, default=True, nullable=False)           # se False, não será distribuída
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

