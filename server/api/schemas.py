from __future__ import annotations
from typing import List, Optional, Any, Dict, Union
from datetime import datetime
from uuid import UUID
import re
from pydantic import BaseModel, Field, field_validator

from services.contas import TIPOS_CONTA
from services.senhas import validar_senha_nova


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
    last_telemetry_status: Optional[Any] = None
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
    ip: Optional[str] = None
    username: Optional[str] = None
    modelo: Optional[str] = None
    canal_rtsp: Optional[int] = None
    ip_compartilhado: bool = False
    has_password: bool = False
    perfect_image_base64: Optional[str] = None
    night_image_base64: Optional[str] = None
    night_image_date: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    status_comunicacao: Optional[str] = None
    status_gravacao: Optional[str] = None
    captura_status: Optional[str] = None
    captura_motivo: Optional[str] = None
    captura_horario: Optional[datetime] = None
    offline_segundos: Optional[int] = None
    offline_aprox: bool = False

    model_config = {"from_attributes": True}


# ─── Câmeras RTSP individuais na Galeria (DIGIFORT / DEFENSE) ──────────────
class NVRCameraConfigItem(BaseModel):
    canal: Optional[int] = None
    nome: str
    ip: str
    username: str = "admin"
    password: Optional[str] = None
    modelo: str = "Hikvision"
    canal_rtsp: Optional[int] = Field(None, ge=1, le=512)


class NVRCameraBulkImport(BaseModel):
    cameras: List[NVRCameraConfigItem] = []
    sync_from_machine: bool = False
    replace_existing: bool = False


class NVRPlanilhaEntrada(BaseModel):
    nome_arquivo: str = Field(..., min_length=1, max_length=255)
    linha_cabecalho: int = Field(0, ge=0, le=20)
    linhas: List[List[str]]

    @field_validator("linhas")
    @classmethod
    def _validar_linhas(cls, v: List[List[str]]) -> List[List[str]]:
        if not v:
            raise ValueError("A planilha não pode estar vazia.")
        if len(v) > 5000:
            raise ValueError("A planilha não pode ter mais de 5000 linhas.")
        resultado: List[List[str]] = []
        for linha in v:
            if len(linha) > 100:
                raise ValueError("Cada linha pode ter no máximo 100 colunas.")
            resultado.append([
                (c[:500] if isinstance(c, str) else ("" if c is None else str(c)[:500]))
                for c in linha
            ])
        return resultado


class NVRPlanilhaResposta(BaseModel):
    nome_arquivo: str
    linha_cabecalho: int
    total_linhas: int
    importado_em: datetime
    colunas_senha: List[int]
    senhas_ocultas: bool
    linhas: List[List[str]]


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
    ip: Optional[str] = None
    modelo: Optional[str] = None
    canal_rtsp: Optional[int] = None


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
    telemetria: Optional[Dict[str, Any]] = None  # CPU/RAM/discos (NVR Hikvision)


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
    # Câmeras RTSP da Galeria (DIGIFORT/DEFENSE), decriptadas — usadas na captura da imagem da noite
    cameras_config: Optional[List[Dict[str, Any]]] = None


# Mantido para compatibilidade com agentes mais antigos
class AgentNVR(AgentEquipamento):
    pass


class AgentConfigResponse(BaseModel):
    client_name: str
    customer_name: Optional[str] = None  # nome do Cliente da máquina (vai no nome da planilha do NVR Motorola)
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


class CameraPresenca(BaseModel):
    canal: Optional[Union[int, str]] = None
    nome: Optional[str] = Field(None, max_length=255)
    online: bool


class EquipamentoPresenca(BaseModel):
    nome: str = Field(max_length=255)
    cameras: List[CameraPresenca] = Field(default_factory=list, max_length=1000)


class PresencaCamerasReport(BaseModel):
    equipamentos: List[EquipamentoPresenca] = Field(default_factory=list, max_length=200)


# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: Optional[str] = None
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


# ─────────────────────────────────────────────
# Multi-contas
# ─────────────────────────────────────────────
_EMAIL_USUARIO_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validar_email_usuario(v: Optional[str], obrigatorio: bool = True) -> Optional[str]:
    if v is None:
        if obrigatorio:
            raise ValueError("E-mail inválido.")
        return None
    s = v.strip().lower()
    if not s:
        if obrigatorio:
            raise ValueError("E-mail inválido.")
        return None
    if len(s) > 255 or not _EMAIL_USUARIO_RE.match(s):
        raise ValueError("E-mail inválido.")
    return s


def _validar_senha_schema(v: Optional[str], obrigatorio: bool = True) -> Optional[str]:
    if v is None:
        if obrigatorio:
            raise ValueError("A senha é obrigatória.")
        return None
    validar_senha_nova(v)
    return v


def _validar_documento(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    digitos = "".join(c for c in str(v) if c.isdigit())
    if not digitos:
        return None
    if len(digitos) not in (11, 14):
        raise ValueError("CPF/CNPJ inválido.")
    return digitos


def _validar_nome(v: Optional[str], obrigatorio: bool = True, max_len: int = 255) -> Optional[str]:
    if v is None:
        if obrigatorio:
            raise ValueError("Nome é obrigatório.")
        return None
    s = v.strip()
    if not s:
        if obrigatorio:
            raise ValueError("Nome não pode ser vazio.")
        return None
    if len(s) > max_len:
        raise ValueError(f"Nome pode ter no máximo {max_len} caracteres.")
    return s


def _validar_tipo_conta(v: Optional[str], obrigatorio: bool = True) -> Optional[str]:
    if v is None:
        if obrigatorio:
            raise ValueError("Tipo de conta é obrigatório.")
        return None
    s = v.strip().upper()
    if s not in TIPOS_CONTA:
        raise ValueError(f"Tipo de conta inválido. Opções: {', '.join(TIPOS_CONTA)}.")
    return s


def _validar_papel_usuario(v: Optional[str], obrigatorio: bool = True) -> Optional[str]:
    if v is None:
        if obrigatorio:
            raise ValueError("Papel é obrigatório.")
        return None
    s = v.strip().upper()
    if s not in ("ADMIN", "LEITURA"):
        raise ValueError("Papel inválido. Deve ser ADMIN ou LEITURA.")
    return s


class TrocarSenhaRequest(BaseModel):
    senha_atual: str
    senha_nova: str

    @field_validator("senha_nova")
    @classmethod
    def _check_senha_nova(cls, v: str) -> str:
        return _validar_senha_schema(v, obrigatorio=True)


class UsuarioMe(BaseModel):
    id: Optional[UUID] = None
    nome: str
    email: Optional[str] = None
    papel: str

    model_config = {"from_attributes": True}


class ContaResumo(BaseModel):
    id: UUID
    nome: str
    tipo: str
    plano_nome: Optional[str] = None
    expira_em: Optional[datetime] = None
    dias_restantes: Optional[int] = None
    status: str
    bloqueada: bool
    plataforma: bool

    model_config = {"from_attributes": True}


class Rotulos(BaseModel):
    grupo_singular: str
    grupo_plural: str


class MeResponse(BaseModel):
    usuario: UsuarioMe
    conta: Optional[ContaResumo] = None
    somente_leitura: bool
    rotulos: Rotulos


class PlanoCreate(BaseModel):
    nome: str
    duracao_dias: int = Field(..., ge=1, le=3650)

    @field_validator("nome")
    @classmethod
    def _check_nome(cls, v: str) -> str:
        return _validar_nome(v, obrigatorio=True, max_len=60)


class PlanoUpdate(BaseModel):
    nome: Optional[str] = None
    duracao_dias: Optional[int] = Field(None, ge=1, le=3650)
    ativo: Optional[bool] = None

    @field_validator("nome")
    @classmethod
    def _check_nome(cls, v: Optional[str]) -> Optional[str]:
        return _validar_nome(v, obrigatorio=False, max_len=60)


class PlanoResponse(BaseModel):
    id: UUID
    nome: str
    duracao_dias: int
    ativo: bool
    criado_em: datetime

    model_config = {"from_attributes": True}


class UsuarioCreate(BaseModel):
    nome: str
    email: str
    senha: str
    papel: str

    @field_validator("nome")
    @classmethod
    def _check_nome(cls, v: str) -> str:
        return _validar_nome(v, obrigatorio=True, max_len=255)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _validar_email_usuario(v, obrigatorio=True)

    @field_validator("senha")
    @classmethod
    def _check_senha(cls, v: str) -> str:
        return _validar_senha_schema(v, obrigatorio=True)

    @field_validator("papel")
    @classmethod
    def _check_papel(cls, v: str) -> str:
        return _validar_papel_usuario(v, obrigatorio=True)


class UsuarioUpdate(BaseModel):
    nome: Optional[str] = None
    papel: Optional[str] = None
    ativo: Optional[bool] = None
    senha: Optional[str] = None

    @field_validator("nome")
    @classmethod
    def _check_nome(cls, v: Optional[str]) -> Optional[str]:
        return _validar_nome(v, obrigatorio=False, max_len=255)

    @field_validator("papel")
    @classmethod
    def _check_papel(cls, v: Optional[str]) -> Optional[str]:
        return _validar_papel_usuario(v, obrigatorio=False)

    @field_validator("senha")
    @classmethod
    def _check_senha(cls, v: Optional[str]) -> Optional[str]:
        return _validar_senha_schema(v, obrigatorio=False)


class UsuarioResponse(BaseModel):
    id: UUID
    nome: str
    email: str
    papel: str
    ativo: bool
    ultimo_login: Optional[datetime] = None
    criado_em: datetime

    model_config = {"from_attributes": True}


class SuperAdminCreate(BaseModel):
    nome: str
    email: str
    senha: str

    @field_validator("nome")
    @classmethod
    def _check_nome(cls, v: str) -> str:
        return _validar_nome(v, obrigatorio=True, max_len=255)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _validar_email_usuario(v, obrigatorio=True)

    @field_validator("senha")
    @classmethod
    def _check_senha(cls, v: str) -> str:
        return _validar_senha_schema(v, obrigatorio=True)


class SuperAdminUpdate(BaseModel):
    nome: Optional[str] = None
    ativo: Optional[bool] = None
    senha: Optional[str] = None

    @field_validator("nome")
    @classmethod
    def _check_nome(cls, v: Optional[str]) -> Optional[str]:
        return _validar_nome(v, obrigatorio=False, max_len=255)

    @field_validator("senha")
    @classmethod
    def _check_senha(cls, v: Optional[str]) -> Optional[str]:
        return _validar_senha_schema(v, obrigatorio=False)


class AdminInicial(BaseModel):
    nome: str
    email: str
    senha: str

    @field_validator("nome")
    @classmethod
    def _check_nome(cls, v: str) -> str:
        return _validar_nome(v, obrigatorio=True, max_len=255)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _validar_email_usuario(v, obrigatorio=True)

    @field_validator("senha")
    @classmethod
    def _check_senha(cls, v: str) -> str:
        return _validar_senha_schema(v, obrigatorio=True)


class ContaCreate(BaseModel):
    nome: str
    tipo: str
    documento: Optional[str] = None
    email_contato: Optional[str] = None
    telefone: Optional[str] = None
    observacoes: Optional[str] = None
    plano_id: UUID
    admin: AdminInicial

    @field_validator("nome")
    @classmethod
    def _check_nome(cls, v: str) -> str:
        return _validar_nome(v, obrigatorio=True, max_len=255)

    @field_validator("tipo")
    @classmethod
    def _check_tipo(cls, v: str) -> str:
        return _validar_tipo_conta(v, obrigatorio=True)

    @field_validator("documento")
    @classmethod
    def _check_documento(cls, v: Optional[str]) -> Optional[str]:
        return _validar_documento(v)

    @field_validator("email_contato")
    @classmethod
    def _check_email_contato(cls, v: Optional[str]) -> Optional[str]:
        return _validar_email_usuario(v, obrigatorio=False)


class ContaUpdate(BaseModel):
    nome: Optional[str] = None
    tipo: Optional[str] = None
    documento: Optional[str] = None
    email_contato: Optional[str] = None
    telefone: Optional[str] = None
    observacoes: Optional[str] = None
    expira_em: Optional[datetime] = None

    @field_validator("nome")
    @classmethod
    def _check_nome(cls, v: Optional[str]) -> Optional[str]:
        return _validar_nome(v, obrigatorio=False, max_len=255)

    @field_validator("tipo")
    @classmethod
    def _check_tipo(cls, v: Optional[str]) -> Optional[str]:
        return _validar_tipo_conta(v, obrigatorio=False)

    @field_validator("documento")
    @classmethod
    def _check_documento(cls, v: Optional[str]) -> Optional[str]:
        return _validar_documento(v)

    @field_validator("email_contato")
    @classmethod
    def _check_email_contato(cls, v: Optional[str]) -> Optional[str]:
        return _validar_email_usuario(v, obrigatorio=False)

    @field_validator("expira_em")
    @classmethod
    def _check_expira_em(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is not None and v.tzinfo is not None:
            from datetime import timezone
            return v.astimezone(timezone.utc).replace(tzinfo=None)
        return v


class RenovarRequest(BaseModel):
    plano_id: UUID


class MoverContaRequest(BaseModel):
    conta_id: UUID


class RenovacaoResponse(BaseModel):
    id: UUID
    plano_nome: str
    dias: int
    expira_em_anterior: Optional[datetime] = None
    expira_em_nova: datetime
    feito_por: Optional[str] = None
    criado_em: datetime

    model_config = {"from_attributes": True}


class ContaResponse(ContaResumo):
    documento: Optional[str] = None
    email_contato: Optional[str] = None
    telefone: Optional[str] = None
    observacoes: Optional[str] = None
    plano_id: Optional[UUID] = None
    ativo: bool = True
    criado_em: datetime
    total_clientes: int = 0
    total_maquinas: int = 0
    total_usuarios: int = 0

    model_config = {"from_attributes": True}


class ContaDetalheResponse(ContaResponse):
    renovacoes: List[RenovacaoResponse] = []

    model_config = {"from_attributes": True}
