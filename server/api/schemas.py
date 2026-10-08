from __future__ import annotations
from typing import List, Optional, Any, Dict
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, field_validator


# ─────────────────────────────────────────────
# Equipamento (antes chamado NVR)
# ─────────────────────────────────────────────
TIPOS_EQUIPAMENTO = ["NVR", "OLT", "ONU", "PABX", "MIKROTIK", "DIGIFORT", "MIXED", "DEFENSE", "CAMERA"]

class NVRBase(BaseModel):
    tipo: str = "NVR"  # NVR, OLT, ONU, PABX
    name: str
    ip: str
    username: str
    config_extra: Optional[Dict[str, Any]] = None
    active: bool = True


class NVRCreate(NVRBase):
    password: str


class NVRUpdate(BaseModel):
    tipo: Optional[str] = None
    name: Optional[str] = None
    ip: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    config_extra: Optional[Dict[str, Any]] = None
    active: Optional[bool] = None


class NVRResponse(NVRBase):
    id: UUID
    client_id: UUID
    last_recording_status: Optional[Any] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# Alias para nomenclatura de equipamentos
EquipamentoBase = NVRBase
EquipamentoCreate = NVRCreate
EquipamentoUpdate = NVRUpdate
EquipamentoResponse = NVRResponse


# ─────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────
class ClientBase(BaseModel):
    name: str
    backup_hour: int = 2
    backup_minute: int = 0
    email_to: List[str] = []
    active: bool = True


class ClientCreate(ClientBase):
    zip_password: Optional[str] = None


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    backup_hour: Optional[int] = None
    backup_minute: Optional[int] = None
    email_to: Optional[List[str]] = None
    active: Optional[bool] = None
    zip_password: Optional[str] = None


class ClientResponse(ClientBase):
    id: UUID
    api_key_prefix: str
    last_seen: Optional[datetime] = None
    last_backup_at: Optional[datetime] = None
    last_backup_status: Optional[str] = None
    created_at: datetime
    nvr_count: int = 0
    restart_requested: bool = False
    backup_requested: bool = False
    telemetry: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}


class ClientWithKey(ClientResponse):
    """Returned only on creation — contains the raw API key."""
    api_key: str


# ─────────────────────────────────────────────
# Backup
# ─────────────────────────────────────────────
class NVRResult(BaseModel):
    nome: str
    tipo: str = "NVR"  # NVR, OLT, ONU, PABX
    status: str  # OK, PARCIAL, ERRO
    cameras: Optional[List[Dict[str, Any]]] = None


class BackupReportCreate(BaseModel):
    started_at: datetime
    finished_at: datetime
    status: str  # OK, PARTIAL, ERROR
    nvr_results: List[NVRResult]
    trigger: str = "scheduled"


class BackupReportResponse(BaseModel):
    backup_id: UUID


class BackupResponse(BaseModel):
    id: UUID
    client_id: UUID
    client_name: Optional[str] = None
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    status: str
    nvr_results: Optional[Any]
    zip_filename: Optional[str]
    zip_size: Optional[int]
    email_sent: bool
    trigger: str
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}


class PaginatedBackups(BaseModel):
    items: List[BackupResponse]
    total: int
    page: int
    pages: int


# ─────────────────────────────────────────────
# Agent (config payload sent to Windows agent)
# ─────────────────────────────────────────────
class AgentEquipamento(BaseModel):
    """Representa qualquer equipamento enviado ao agente Windows."""
    tipo: str  # NVR, OLT, ONU, PABX
    name: str
    ip: str
    username: str
    password: str  # decrypted — sent over HTTPS only
    config_extra: Optional[Dict[str, Any]] = None


# Mantido para compatibilidade com agentes mais antigos
class AgentNVR(AgentEquipamento):
    pass


class AgentConfigResponse(BaseModel):
    client_name: str
    backup_hour: int
    backup_minute: int
    zip_password: Optional[str]
    equipamentos: List[AgentEquipamento]
    nvrs: List[AgentEquipamento] = []  # alias de compatibilidade — igual a equipamentos


class PingResponse(BaseModel):
    status: str
    restart: bool = False
    backup: bool = False


class PingRequest(BaseModel):
    telemetry: Optional[Dict[str, Any]] = None


# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────
class LoginRequest(BaseModel):
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ─────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────
class SettingUpdate(BaseModel):
    value: Optional[str] = None


class SettingsResponse(BaseModel):
    smtp_server: Optional[str]
    smtp_port: Optional[str]
    smtp_email: Optional[str]
    retention_days: Optional[str]


# ─────────────────────────────────────────────
# Stats (overview dashboard)
# ─────────────────────────────────────────────
class StatsResponse(BaseModel):
    total_clients: int
    active_clients: int
    backups_today: int
    backups_ok: int
    backups_error: int


# ─────────────────────────────────────────────
# Agent Logs
# ─────────────────────────────────────────────
class AgentLogResponse(BaseModel):
    id: UUID
    client_id: UUID
    event_type: str
    message: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# Agent OTA (Over The Air Updates)
# ─────────────────────────────────────────────
class AgentVersionCreate(BaseModel):
    version: str                             # ex: "2.1.0"
    notes: Optional[str] = None
    url_service: str                         # URL pública do exe (ex: GitHub Release asset)
    url_tray: Optional[str] = None
    sha256_service: str                      # SHA256 do service.exe (64 chars hex)
    sha256_tray: Optional[str] = None


class AgentVersionUpdate(BaseModel):
    version: Optional[str] = None
    url_service: Optional[str] = None
    sha256_service: Optional[str] = None
    url_tray: Optional[str] = None
    sha256_tray: Optional[str] = None


class AgentVersionResponse(BaseModel):
    id: UUID
    version: str
    notes: Optional[str]
    url_service: str
    url_tray: Optional[str]
    sha256_service: str
    sha256_tray: Optional[str]
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdateCheckResponse(BaseModel):
    """Resposta ao agente ao verificar se há nova versão disponível."""
    has_update: bool
    version: Optional[str] = None
    url_service: Optional[str] = None
    url_tray: Optional[str] = None
    sha256_service: Optional[str] = None
    sha256_tray: Optional[str] = None
    notes: Optional[str] = None


# "?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?
# Teste RTSP Automático
# "?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?
class RTSPTestRequest(BaseModel):
    nome: str
    ip: str
    modelo: str
    senha: str = "navarro@123"

class RTSPTestResponse(BaseModel):
    success: bool
    error_message: Optional[str] = None
    image_base64: Optional[str] = None
