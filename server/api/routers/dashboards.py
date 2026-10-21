from datetime import datetime
from typing import Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from auth import verify_admin_token
from config import settings
from database import get_db
from models import Customer, CustomerDashboard
from services.dashboards.compartilhamento import gerar_token
from services.dashboards.dados import listar_opcoes, montar_dados
from services.dashboards.esquemas import (
    AtualizarLinkEntrada,
    CompartilhamentoResposta,
    DadosResposta,
    DashboardAdminResposta,
    GerarLinkEntrada,
    LayoutSalvoResposta,
    LinkGeradoResposta,
    OpcoesResposta,
    SalvarLayoutEntrada,
    para_utc_naive,
)
from services.dashboards.layout import (
    catalogo,
    layout_do_banco,
    layout_padrao,
    validar_referencias,
)

router = APIRouter(tags=["Dashboards"], dependencies=[Depends(verify_admin_token)])


def _cliente_ou_404(db: Session, customer_id: UUID) -> Customer:
    cliente = db.query(Customer).filter(Customer.id == customer_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return cliente


def _obter_ou_criar(db: Session, customer: Customer) -> CustomerDashboard:
    dashboard = (
        db.query(CustomerDashboard)
        .filter(CustomerDashboard.customer_id == customer.id)
        .first()
    )
    if dashboard is None:
        dashboard = CustomerDashboard(
            customer_id=customer.id,
            layout=layout_padrao().model_dump(mode="json"),
            version=1,
        )
        db.add(dashboard)
        db.commit()
        db.refresh(dashboard)
    return dashboard


def _compartilhamento(d: CustomerDashboard) -> CompartilhamentoResposta:
    agora = datetime.utcnow()
    expirado = bool(d.share_expires_at and d.share_expires_at <= agora)
    tem_link = bool(d.share_token_hash)
    return CompartilhamentoResposta(
        ativo=bool(d.share_enabled),
        tem_link=tem_link,
        expira_em=d.share_expires_at,
        permite_edicao=bool(d.share_allow_edit),
        criado_em=d.share_created_at,
        ultimo_acesso=d.last_viewed_at,
        expirado=expirado,
    )


def _resposta_admin(d: CustomerDashboard) -> DashboardAdminResposta:
    return DashboardAdminResposta(
        id=d.id,
        customer_id=d.customer_id,
        cliente_nome=d.customer.name,
        layout=layout_do_banco(d),
        version=d.version,
        atualizado_em=d.updated_at,
        compartilhamento=_compartilhamento(d),
    )


@router.get("/api/v1/dashboards/widgets", response_model=List[dict])
def get_catalogo_widgets():
    """Retorna os tipos de widgets disponíveis e seus schemas de configuração."""
    return catalogo()


@router.get("/api/v1/clients/{customer_id}/dashboard", response_model=DashboardAdminResposta)
def get_customer_dashboard(
    customer_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
):
    """Carrega o layout e informações de compartilhamento do dashboard do cliente."""
    response.headers["Cache-Control"] = "no-store"
    customer = _cliente_ou_404(db, customer_id)
    dashboard = _obter_ou_criar(db, customer)
    return _resposta_admin(dashboard)


@router.put("/api/v1/clients/{customer_id}/dashboard", response_model=LayoutSalvoResposta)
def save_customer_dashboard_layout(
    customer_id: UUID,
    body: SalvarLayoutEntrada,
    response: Response,
    db: Session = Depends(get_db),
):
    """Salva o layout do dashboard com controle otimista de versão."""
    response.headers["Cache-Control"] = "no-store"
    customer = _cliente_ou_404(db, customer_id)
    dashboard = _obter_ou_criar(db, customer)

    if body.version != dashboard.version:
        raise HTTPException(
            status_code=409,
            detail="O dashboard foi alterado por outra pessoa. Recarregue antes de salvar.",
        )

    validar_referencias(db, customer_id, body.layout)

    dashboard.layout = body.layout.model_dump(mode="json")
    dashboard.version += 1
    db.commit()
    db.refresh(dashboard)

    return LayoutSalvoResposta(layout=layout_do_banco(dashboard), version=dashboard.version)


@router.post("/api/v1/clients/{customer_id}/dashboard/restore-default", response_model=LayoutSalvoResposta)
def restore_customer_dashboard_default(
    customer_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
):
    """Restaura o layout padrão do dashboard."""
    response.headers["Cache-Control"] = "no-store"
    customer = _cliente_ou_404(db, customer_id)
    dashboard = _obter_ou_criar(db, customer)

    padrao = layout_padrao()
    dashboard.layout = padrao.model_dump(mode="json")
    dashboard.version += 1
    db.commit()
    db.refresh(dashboard)

    return LayoutSalvoResposta(layout=padrao, version=dashboard.version)


@router.get("/api/v1/clients/{customer_id}/dashboard/data", response_model=DadosResposta)
def get_customer_dashboard_data(
    customer_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
):
    """Monta os dados de cada widget do layout atual para prévia no painel admin."""
    response.headers["Cache-Control"] = "no-store"
    customer = _cliente_ou_404(db, customer_id)
    dashboard = _obter_ou_criar(db, customer)
    dados = montar_dados(db, customer, layout_do_banco(dashboard))
    return DadosResposta(gerado_em=dados["gerado_em"], widgets=dados["widgets"])


@router.get("/api/v1/clients/{customer_id}/dashboard/opcoes", response_model=OpcoesResposta)
def get_customer_dashboard_opcoes(
    customer_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
):
    """Lista opções de máquinas e equipamentos disponíveis para configurar widgets."""
    response.headers["Cache-Control"] = "no-store"
    customer = _cliente_ou_404(db, customer_id)
    return listar_opcoes(db, customer)


@router.post("/api/v1/clients/{customer_id}/dashboard/share", response_model=LinkGeradoResposta)
def generate_customer_dashboard_share_link(
    customer_id: UUID,
    body: GerarLinkEntrada,
    response: Response,
    db: Session = Depends(get_db),
):
    """Gera ou regenera o token de compartilhamento público por link."""
    response.headers["Cache-Control"] = "no-store"
    customer = _cliente_ou_404(db, customer_id)
    dashboard = _obter_ou_criar(db, customer)

    expira_em = para_utc_naive(body.expira_em)
    agora = datetime.utcnow()
    if expira_em is not None and expira_em <= agora:
        raise HTTPException(status_code=422, detail="A data de expiração deve estar no futuro.")

    token_puro, token_hash = gerar_token()
    dashboard.share_token_hash = token_hash
    dashboard.share_enabled = True
    dashboard.share_expires_at = expira_em
    dashboard.share_allow_edit = body.permite_edicao
    dashboard.share_created_at = agora
    dashboard.last_viewed_at = None

    db.commit()
    db.refresh(dashboard)

    caminho = f"/d#{token_puro}"
    url = f"{settings.PUBLIC_URL.rstrip('/')}{caminho}" if settings.PUBLIC_URL else None

    return LinkGeradoResposta(
        token=token_puro,
        caminho=caminho,
        url=url,
        compartilhamento=_compartilhamento(dashboard),
    )


@router.put("/api/v1/clients/{customer_id}/dashboard/share", response_model=CompartilhamentoResposta)
def update_customer_dashboard_share_link(
    customer_id: UUID,
    body: AtualizarLinkEntrada,
    response: Response,
    db: Session = Depends(get_db),
):
    """Atualiza as configurações do link de compartilhamento existente."""
    response.headers["Cache-Control"] = "no-store"
    customer = _cliente_ou_404(db, customer_id)
    dashboard = _obter_ou_criar(db, customer)

    if body.ativo is True and not dashboard.share_token_hash:
        raise HTTPException(status_code=409, detail="Gere um link antes de ativar.")

    if body.ativo is not None:
        dashboard.share_enabled = body.ativo

    if body.permite_edicao is not None:
        dashboard.share_allow_edit = body.permite_edicao

    if body.limpar_expiracao:
        dashboard.share_expires_at = None
    elif body.expira_em is not None:
        exp = para_utc_naive(body.expira_em)
        if exp is not None and exp <= datetime.utcnow():
            raise HTTPException(status_code=422, detail="A data de expiração deve estar no futuro.")
        dashboard.share_expires_at = exp

    db.commit()
    db.refresh(dashboard)
    return _compartilhamento(dashboard)


@router.delete("/api/v1/clients/{customer_id}/dashboard/share", status_code=status.HTTP_204_NO_CONTENT)
def revoke_customer_dashboard_share_link(
    customer_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
):
    """Revoga o link de compartilhamento atual."""
    response.headers["Cache-Control"] = "no-store"
    customer = _cliente_ou_404(db, customer_id)
    dashboard = _obter_ou_criar(db, customer)

    dashboard.share_token_hash = None
    dashboard.share_enabled = False
    dashboard.share_allow_edit = False
    dashboard.share_expires_at = None
    dashboard.share_created_at = None

    db.commit()
    return None
