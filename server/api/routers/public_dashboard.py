from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from database import get_db
from services.dashboards.compartilhamento import AcessoDashboard, acesso_publico
from services.dashboards.dados import listar_opcoes, montar_dados
from services.dashboards.esquemas import (
    DadosResposta,
    LayoutSalvoResposta,
    OpcoesResposta,
    PublicoResposta,
    SalvarLayoutEntrada,
)
from services.dashboards.layout import layout_do_banco, validar_referencias

router = APIRouter(prefix="/api/v1/public/dashboard", tags=["Dashboards"])


def _cabecalhos(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Referrer-Policy"] = "no-referrer"


@router.get("", response_model=PublicoResposta)
def get_public_dashboard(
    response: Response,
    acesso: AcessoDashboard = Depends(acesso_publico),
    db: Session = Depends(get_db),
):
    """Retorna o dashboard público (layout e dados dos widgets)."""
    _cabecalhos(response)
    dashboard = acesso.dashboard
    layout = layout_do_banco(dashboard)
    dados = montar_dados(db, dashboard.customer, layout)

    return PublicoResposta(
        cliente_nome=dashboard.customer.name,
        layout=layout,
        version=dashboard.version,
        pode_editar=acesso.pode_editar,
        dados=DadosResposta(gerado_em=dados["gerado_em"], widgets=dados["widgets"]),
    )


@router.get("/data", response_model=DadosResposta)
def get_public_dashboard_data(
    response: Response,
    acesso: AcessoDashboard = Depends(acesso_publico),
    db: Session = Depends(get_db),
):
    """Atualiza apenas os dados dos widgets do dashboard público."""
    _cabecalhos(response)
    dashboard = acesso.dashboard
    layout = layout_do_banco(dashboard)
    dados = montar_dados(db, dashboard.customer, layout)

    return DadosResposta(gerado_em=dados["gerado_em"], widgets=dados["widgets"])


@router.get("/opcoes", response_model=OpcoesResposta)
def get_public_dashboard_opcoes(
    response: Response,
    acesso: AcessoDashboard = Depends(acesso_publico),
    db: Session = Depends(get_db),
):
    """Lista opções disponíveis para configuração caso o link tenha permissão de edição."""
    _cabecalhos(response)
    if not acesso.pode_editar:
        raise HTTPException(status_code=403, detail="Edição não permitida para este link.")

    return listar_opcoes(db, acesso.dashboard.customer)


@router.put("/layout", response_model=LayoutSalvoResposta)
def save_public_dashboard_layout(
    body: SalvarLayoutEntrada,
    response: Response,
    acesso: AcessoDashboard = Depends(acesso_publico),
    db: Session = Depends(get_db),
):
    """Permite salvar o layout quando o link compartilhado foi configurado com permissão de edição."""
    _cabecalhos(response)
    if not acesso.pode_editar:
        raise HTTPException(status_code=403, detail="Edição não permitida para este link.")

    dashboard = acesso.dashboard

    if body.version != dashboard.version:
        raise HTTPException(
            status_code=409,
            detail="O dashboard foi alterado por outra pessoa. Recarregue antes de salvar.",
        )

    validar_referencias(db, dashboard.customer_id, body.layout)

    dashboard.layout = body.layout.model_dump(mode="json")
    dashboard.version += 1
    db.commit()
    db.refresh(dashboard)

    return LayoutSalvoResposta(layout=layout_do_banco(dashboard), version=dashboard.version)
