import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime,
    BigInteger, Text, JSON, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from database import Base


class Customer(Base):
    """Cliente: a empresa atendida. Agrupa Máquinas (tabela 'client_groups' mantida no BD)."""
    __tablename__ = "client_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    backup_hour = Column(Integer, default=2)
    backup_minute = Column(Integer, default=0)
    # Estado da fila de backup sequencial
    queue_active = Column(Boolean, default=False, nullable=False)
    queue_current_index = Column(Integer, nullable=True)
    # Destinatários do e-mail único por rodada de backup do Cliente
    email_to = Column(ARRAY(String), default=[], nullable=False)
    # Senha do ZIP do cliente (Fernet-encrypted); None = sem senha
    zip_password = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    machines = relationship("Machine", back_populates="customer", order_by="Machine.queue_order")
    runs = relationship(
        "CustomerBackupRun", back_populates="customer",
        cascade="all, delete-orphan", order_by="desc(CustomerBackupRun.started_at)",
    )


class CustomerBackupRun(Base):
    """Rodada de backup do Cliente: agrupa os backups das máquinas e gera 1 e-mail ao fechar."""
    __tablename__ = "customer_backup_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("client_groups.id", ondelete="CASCADE"), nullable=False)
    trigger = Column(String(30), nullable=False)  # scheduled | queue | manual_machine
    started_at = Column(DateTime, nullable=False)
    deadline_at = Column(DateTime, nullable=False)
    closed_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default="EM_ANDAMENTO")  # EM_ANDAMENTO | OK | PARCIAL | ERRO
    expected_machine_ids = Column(JSON, nullable=False, default=list)  # lista de str (UUID)
    email_sent = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    customer = relationship("Customer", back_populates="runs")
    backups = relationship("Backup", back_populates="run")


class CustomerDashboard(Base):
    """Dashboard do Cliente: layout dos widgets e compartilhamento por link com token."""
    __tablename__ = "customer_dashboards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("client_groups.id", ondelete="CASCADE"), nullable=False, unique=True)
    layout = Column(JSON, nullable=False, default=dict)
    # Incrementa a cada gravação do layout: evita que duas edições simultâneas se sobrescrevam
    version = Column(Integer, nullable=False, default=1)
    # Só o hash SHA-256 do token é guardado; o token em texto puro é mostrado uma única vez
    share_token_hash = Column(String(64), nullable=True, unique=True)
    share_enabled = Column(Boolean, nullable=False, default=False)
    share_expires_at = Column(DateTime, nullable=True)
    share_allow_edit = Column(Boolean, nullable=False, default=False)
    share_created_at = Column(DateTime, nullable=True)
    last_viewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    customer = relationship("Customer")


class Machine(Base):
    """Máquina: o computador com o agente instalado (tabela 'clients' mantida no BD)."""
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
    telemetry = Column(JSON, nullable=True)  # Hardware stats (CPU, RAM, Disk, GPU)
    # Cliente ao qual a máquina pertence (coluna 'group_id' mantida no BD)
    customer_id = Column("group_id", UUID(as_uuid=True), ForeignKey("client_groups.id", ondelete="SET NULL"), nullable=True)
    queue_order = Column(Integer, default=0, nullable=False)

    equipamentos = relationship("NVR", back_populates="machine", cascade="all, delete-orphan")
    backups = relationship("Backup", back_populates="machine")
    logs = relationship("AgentLog", back_populates="machine", cascade="all, delete-orphan", order_by="desc(AgentLog.created_at)")
    customer = relationship("Customer", back_populates="machines")


class NVR(Base):
    """Tabela de equipamentos (NVR, OLT, ONU, PABX). Mantém nome 'nvrs' no BD para compatibilidade."""
    __tablename__ = "nvrs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    machine_id = Column(
        "client_id",
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False
    )
    tipo = Column(String(20), nullable=False, default="NVR")  # NVR, OLT, ONU, PABX
    name = Column(String(255), nullable=False)
    ip = Column(String(255), nullable=False)
    username = Column(String(100), nullable=False)
    password = Column(Text, nullable=False)  # Fernet-encrypted
    config_extra = Column(JSON, nullable=True)  # configurações específicas de cada tipo
    last_recording_status = Column(JSON, nullable=True)
    last_telemetry_status = Column(JSON, nullable=True)  # CPU/RAM/discos (NVR Hikvision)
    active = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    machine = relationship("Machine", back_populates="equipamentos")
    cameras_status = relationship("NVRCamera", back_populates="nvr", cascade="all, delete-orphan")


class NVRCamera(Base):
    """Tabela de Câmeras atreladas a um equipamento (NVR, DIGIFORT, DEFENSE). Armazena imagens Base64."""
    __tablename__ = "nvr_cameras"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nvr_id = Column(UUID(as_uuid=True), ForeignKey("nvrs.id", ondelete="CASCADE"), nullable=False)
    canal = Column(Integer, nullable=False)
    nome = Column(String(255), nullable=False)
    # Conexão RTSP individual da câmera — usada por DIGIFORT e DEFENSE (NULL em NVR comum)
    ip = Column(String(255), nullable=True)
    username = Column(String(100), nullable=True)
    password = Column(Text, nullable=True)  # Fernet-encrypted quando preenchido
    modelo = Column(String(50), nullable=True)  # Hikvision, Intelbras, Grandstream, ONVIF
    canal_rtsp = Column(Integer, nullable=True)  # canal da câmera dentro do equipamento do IP (IP compartilhado entre câmeras)
    perfect_image_base64 = Column(Text, nullable=True)
    night_image_base64 = Column(Text, nullable=True)
    night_image_date = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    nvr = relationship("NVR", back_populates="cameras_status")


class NVRPlanilha(Base):
    """Última planilha (CSV/XLSX) importada na Galeria de um equipamento DIGIFORT/DEFENSE. O conteúdo vai criptografado (Fernet), pois pode ter senhas."""
    __tablename__ = "nvr_planilhas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nvr_id = Column(UUID(as_uuid=True), ForeignKey("nvrs.id", ondelete="CASCADE"), nullable=False, unique=True)
    nome_arquivo = Column(String(255), nullable=False)
    linha_cabecalho = Column(Integer, nullable=False, default=0)
    total_linhas = Column(Integer, nullable=False, default=0)
    dados = Column(Text, nullable=False)  # JSON das linhas, criptografado (Fernet)
    importado_em = Column(DateTime, default=datetime.utcnow, nullable=False)


class Backup(Base):
    __tablename__ = "backups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    machine_id = Column("client_id", UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False)  # OK, PARTIAL, ERROR
    nvr_results = Column(JSON, nullable=True)
    zip_filename = Column(String(255), nullable=True)
    zip_size = Column(BigInteger, nullable=True)
    email_sent = Column(Boolean, default=False)
    trigger = Column(String(50), default="scheduled")  # scheduled | manual
    created_at = Column(DateTime, default=datetime.utcnow)
    # Rodada do Cliente à qual o backup pertence (só máquinas com Cliente)
    run_id = Column(UUID(as_uuid=True), ForeignKey("customer_backup_runs.id", ondelete="SET NULL"), nullable=True)

    machine = relationship("Machine", back_populates="backups")
    run = relationship("CustomerBackupRun", back_populates="backups")


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    machine_id = Column("client_id", UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(50), nullable=False)  # ex: ping, backup_trigger, restart_trigger
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    machine = relationship("Machine", back_populates="logs")


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

