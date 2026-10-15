from __future__ import annotations
from typing import List, Optional, Any, Dict
from datetime import datetime
from uuid import UUID
import re
from pydantic import BaseModel, Field, field_validator


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
    machine_id: UUID
    last_recording_status: Optional[Any] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# Câmeras atreladas a um NVR
# ─────────────────────────────────────────────
class NVRCameraResponse(BaseModel):
    id: Optional[UUID] = None
    nvr_id: UUID
    canal: int
    nome: str
    perfect_image_base64: Optional[str] = None
    night_image_base64: Optional[str] = None
    night_image_date: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    status_comunicacao: Optional[str] = None
    status_gravacao: Optional[str] = None
    captura_status: Optional[str] = None
    captura_motivo: Optional[str] = None
    captura_horario: Optional[datetime] = None

    model_config = {"from_attributes": True}

class NVRCameraSetPerfect(BaseModel):
    canal: int
    nome: str
    image_base64: str

    @field_validator("image_base64")
    @classmethod
    def _jpeg_valido(cls, v: str) -> str:
        """Captura RTSP ou upload do painel (já convertido para JPEG no navegador)."""
        import base64, binascii
        v = v.split(",", 1)[1] if v.startswith("data:") else v
        try:
            dados = base64.b64decode(v, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("Imagem inválida (base64)")
        if not dados.startswith(b"\xff\xd8"):
            raise ValueError("A imagem de referência precisa ser JPEG")
        if len(dados) > 10 * 1024 * 1024:
            raise ValueError("Imagem de referência maior que 10 MB")
        return v

class NVRCameraNightImage(BaseModel):
    nvr_name: str
    canal: int
    nome: str
    image_base64: str
    night_image_date: datetime


# ─────────────────────────────────────────────
# Máquina (computador com o agente instalado)
# ─────────────────────────────────────────────
class MachineBase(BaseModel):
    name: str
    backup_hour: int = Field(2, ge=0, le=23)
    backup_minute: int = Field(0, ge=0, le=59)
    email_to: List[str] = []
    active: bool = True


class MachineCreate(MachineBase):
    zip_password: Optional[str] = None
    # Opcional: vincula ao Cliente (fim da fila) e herda o horário dele
    customer_id: Optional[UUID] = None


class MachineUpdate(BaseModel):
    # Vínculo com Cliente e ordem na fila só pelas rotas /api/v1/clients/{id}/...
    name: Optional[str] = None
    backup_hour: Optional[int] = Field(None, ge=0, le=23)
    backup_minute: Optional[int] = Field(None, ge=0, le=59)
    email_to: Optional[List[str]] = None
    active: Optional[bool] = None
    zip_password: Optional[str] = None


class MachineResponse(MachineBase):
    # Sem limites na saída: registros antigos fora da faixa não podem derrubar a listagem (500)
    backup_hour: int
    backup_minute: int
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
    # Calculado no servidor — nunca depende do relógio do navegador
    is_online: bool = False
    current_server_time: Optional[datetime] = None
    customer_id: Optional[UUID] = None
    customer_name: Optional[str] = None
    # True quando o horário vem do Cliente (máquina vinculada)
    schedule_from_customer: bool = False
    # True quando os e-mails do relatório são os do Cliente (máquina vinculada)
    email_from_customer: bool = False
    queue_order: int = 0

    model_config = {"from_attributes": True}


class MachineWithKey(MachineResponse):
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
    machine_id: UUID
    machine_name: Optional[str] = None
    # Cliente da máquina hoje (não histórico)
    customer_id: Optional[UUID] = None
    customer_name: Optional[str] = None
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    status: str
    nvr_results: Optional[Any]
    zip_filename: Optional[str]
    zip_size: Optional[int]
    email_sent: bool
    trigger: str
    created_at: Optional[datetime]
    # Rodada do Cliente (null para máquinas sem Cliente ou backups antigos)
    run_id: Optional[UUID] = None

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
    rtsp_task: Optional[dict] = None


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
    machines_total: int
    machines_active: int
    customers_total: int
    backups_today: int
    backups_ok: int
    backups_error: int


# ─────────────────────────────────────────────
# Agent Logs
# ─────────────────────────────────────────────
class AgentLogResponse(BaseModel):
    id: UUID
    machine_id: UUID
    event_type: str
    message: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# Agent OTA (Over The Air Updates)
# ─────────────────────────────────────────────
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _validate_version(v: Optional[str]) -> Optional[str]:
    """Versão do agente precisa seguir o formato X.Y.Z (REGRA-009)."""
    if v is not None and not _VERSION_RE.match(v.strip()):
        raise ValueError("Versão inválida: use o formato X.Y.Z (ex: 2.1.0)")
    return v.strip() if v is not None else v


def _validate_sha256(v: Optional[str], obrigatorio: bool = False) -> Optional[str]:
    """SHA-256 precisa ter 64 caracteres hexadecimais, quando informado.

    Campo vazio ("") vindo do formulário conta como não informado (o Tray é opcional).
    """
    if v is None or not v.strip():
        if obrigatorio:
            raise ValueError("Informe o SHA-256 do TrilanAgentService.exe")
        return None
    if not _SHA256_RE.match(v.strip()):
        raise ValueError("SHA-256 inválido: deve ter 64 caracteres hexadecimais")
    return v.strip()


def _blank_to_none(v: Optional[str]) -> Optional[str]:
    """URL opcional vazia ("") vinda do formulário vira None."""
    if v is None or not v.strip():
        return None
    return v.strip()


class AgentVersionCreate(BaseModel):
    version: str                             # ex: "2.1.0"
    notes: Optional[str] = None
    url_service: str                         # URL pública do exe (ex: GitHub Release asset)
    url_tray: Optional[str] = None
    sha256_service: str                      # SHA256 do service.exe (64 chars hex)
    sha256_tray: Optional[str] = None

    @field_validator("version")
    @classmethod
    def _check_version(cls, v):
        return _validate_version(v)

    @field_validator("sha256_service")
    @classmethod
    def _check_sha256_service(cls, v):
        return _validate_sha256(v, obrigatorio=True)

    @field_validator("sha256_tray")
    @classmethod
    def _check_sha256_tray(cls, v):
        return _validate_sha256(v)

    @field_validator("url_tray")
    @classmethod
    def _check_url_tray(cls, v):
        return _blank_to_none(v)


class AgentVersionUpdate(BaseModel):
    version: Optional[str] = None
    url_service: Optional[str] = None
    sha256_service: Optional[str] = None
    url_tray: Optional[str] = None
    sha256_tray: Optional[str] = None

    @field_validator("version")
    @classmethod
    def _check_version(cls, v):
        return _validate_version(v)

    @field_validator("sha256_service", "sha256_tray")
    @classmethod
    def _check_sha256(cls, v):
        return _validate_sha256(v)

    @field_validator("url_tray")
    @classmethod
    def _check_url_tray(cls, v):
        return _blank_to_none(v)


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


# ─────────────────────────────────────────────
# Cliente (empresa atendida; agrupa Máquinas)
# ─────────────────────────────────────────────
class CustomerBase(BaseModel):
    name: str
    description: Optional[str] = None
    active: bool = True
    backup_hour: int = Field(2, ge=0, le=23)
    backup_minute: int = Field(0, ge=0, le=59)


_EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


def _clean_email_list(v: Optional[List[str]]) -> Optional[List[str]]:
    """Remove strings vazias e repetidas (ordem mantida) e valida o formato básico do e-mail."""
    if v is None:
        return None
    result: List[str] = []
    for item in v:
        email = (item or "").strip()
        if not email:
            continue
        if not _EMAIL_RE.match(email):
            raise ValueError(f"E-mail inválido: {email}")
        if email not in result:
            result.append(email)
    return result


class CustomerCreate(CustomerBase):
    # Destinatários do e-mail único por rodada de backup
    email_to: List[str] = []
    # Senha do ZIP do cliente (plaintext; armazenada criptografada)
    zip_password: Optional[str] = None

    @field_validator("email_to")
    @classmethod
    def _check_email_to(cls, v):
        return _clean_email_list(v) or []


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    # Enviar "" ou null limpa a descrição (detectado via model_fields_set)
    description: Optional[str] = None
    active: Optional[bool] = None
    backup_hour: Optional[int] = Field(None, ge=0, le=23)
    backup_minute: Optional[int] = Field(None, ge=0, le=59)
    email_to: Optional[List[str]] = None
    # Senha do ZIP do cliente (plaintext); "" ou null remove a senha
    zip_password: Optional[str] = None

    @field_validator("email_to")
    @classmethod
    def _check_email_to(cls, v):
        return _clean_email_list(v)


class CustomerResponse(CustomerBase):
    # Sem limites na saída: registros antigos fora da faixa não podem derrubar a listagem (500)
    backup_hour: int
    backup_minute: int
    id: UUID
    created_at: datetime
    email_to: List[str] = []
    machines_total: int = 0
    machines_online: int = 0
    health: str = "NO_DATA"  # ALL_OK | PARTIAL | ALL_ERROR | NO_DATA
    last_backup_at: Optional[datetime] = None
    queue_active: bool = False
    queue_current_index: Optional[int] = None
    # Informa ao frontend se o cliente tem senha no ZIP (sem expor a senha)
    has_zip_password: bool = False
    machines: List[MachineResponse] = []  # ordenadas por queue_order

    model_config = {"from_attributes": True}


class CustomerQueueOrder(BaseModel):
    """Nova ordem da fila: precisa conter exatamente as máquinas do Cliente."""
    machine_ids: List[UUID]


class CustomerRunMachine(BaseModel):
    machine_id: UUID
    machine_name: str
    backup_id: Optional[UUID] = None
    # Status do backup; "NAO_EXECUTOU" se a rodada fechou sem relatório; null se ainda aberta
    status: Optional[str] = None
    zip: bool = False


class CustomerRunResponse(BaseModel):
    """Rodada de backup do Cliente (1 e-mail por rodada)."""
    id: UUID
    trigger: str  # scheduled | queue | manual_machine
    started_at: datetime
    deadline_at: datetime
    closed_at: Optional[datetime] = None
    status: str  # EM_ANDAMENTO | OK | PARCIAL | ERRO
    email_sent: bool = False
    machines_expected: int = 0
    machines_reported: int = 0
    machines_ok: int = 0
    has_zip: bool = False
    machines: List[CustomerRunMachine] = []


# ─────────────────────────────────────────────
# Teste RTSP Automático
# ─────────────────────────────────────────────
class RTSPTestResponse(BaseModel):
    success: bool
    error_message: Optional[str] = None
    image_base64: Optional[str] = None
    # Agente >= 1.1.6: horário exibido no NVR do frame da gravação e origem ("ao_vivo" | "gravacao")
    horario: Optional[str] = None
    origem: Optional[str] = None
