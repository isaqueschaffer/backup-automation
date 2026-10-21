from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .layout import DashboardLayout


def para_utc_naive(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


class CompartilhamentoResposta(BaseModel):
    ativo: bool
    tem_link: bool
    expira_em: Optional[datetime] = None
    permite_edicao: bool = False
    criado_em: Optional[datetime] = None
    ultimo_acesso: Optional[datetime] = None
    expirado: bool = False


class DashboardAdminResposta(BaseModel):
    id: UUID
    customer_id: UUID
    cliente_nome: str
    layout: DashboardLayout
    version: int
    atualizado_em: datetime
    compartilhamento: CompartilhamentoResposta


class SalvarLayoutEntrada(BaseModel):
    layout: DashboardLayout
    version: int = Field(ge=1)


class LayoutSalvoResposta(BaseModel):
    layout: DashboardLayout
    version: int


class GerarLinkEntrada(BaseModel):
    expira_em: Optional[datetime] = None
    permite_edicao: bool = False


class AtualizarLinkEntrada(BaseModel):
    ativo: Optional[bool] = None
    expira_em: Optional[datetime] = None
    limpar_expiracao: bool = False
    permite_edicao: Optional[bool] = None


class LinkGeradoResposta(BaseModel):
    token: str
    caminho: str
    url: Optional[str] = None
    compartilhamento: CompartilhamentoResposta


class DadosResposta(BaseModel):
    gerado_em: str
    widgets: Dict[str, Any]


class PublicoResposta(BaseModel):
    cliente_nome: str
    layout: DashboardLayout
    version: int
    pode_editar: bool
    dados: DadosResposta
