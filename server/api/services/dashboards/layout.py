import copy
from typing import Any, Dict, List, Literal, Optional, Set, Tuple
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from models import CustomerDashboard, Machine, NVR
from . import widgets  # noqa: F401  registra os tipos de widget
from .registro import REGISTRO

LARGURA_MIN = 2
LARGURA_MAX = 12
ALTURA_MIN = 1
ALTURA_MAX = 40
MAX_WIDGETS = 40


class FiltrosGlobais(BaseModel):
    model_config = {"extra": "forbid"}
    periodo: Literal["24h", "7d", "30d"] = "7d"


class WidgetInstancia(BaseModel):
    model_config = {"extra": "forbid"}
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    tipo: str
    titulo: Optional[str] = Field(None, max_length=80)
    largura: int = Field(6, ge=LARGURA_MIN, le=LARGURA_MAX)
    altura: int = Field(6, ge=ALTURA_MIN, le=ALTURA_MAX)
    config: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validar_tipo_e_config(self):
        tipo = REGISTRO.get(self.tipo)
        if tipo is None:
            raise ValueError(f"Tipo de widget desconhecido: {self.tipo}")
        # Normaliza a config pelo modelo do tipo (rejeita chaves desconhecidas e valores inválidos)
        self.config = tipo.config_model.model_validate(self.config).model_dump(mode="json")
        return self


class DashboardLayout(BaseModel):
    model_config = {"extra": "forbid"}
    schema_version: int = 2
    filtros: FiltrosGlobais = Field(default_factory=FiltrosGlobais)
    widgets: List[WidgetInstancia] = Field(default_factory=list, max_length=MAX_WIDGETS)

    @model_validator(mode="after")
    def _ids_unicos(self):
        ids = [w.id for w in self.widgets]
        if len(ids) != len(set(ids)):
            raise ValueError("Há widgets com id repetido")
        return self


def layout_padrao() -> DashboardLayout:
    return DashboardLayout(
        schema_version=2,
        filtros=FiltrosGlobais(periodo="7d"),
        widgets=[
            WidgetInstancia(id="resumo", tipo="resumo", largura=12, altura=3, config={}),
            WidgetInstancia(id="saude_servidor", tipo="saude_servidor", largura=12, altura=9, config={}),
            WidgetInstancia(id="status_backups", tipo="status_backups", largura=6, altura=6, config={}),
            WidgetInstancia(id="cameras", tipo="cameras", largura=6, altura=6, config={}),
        ],
    )


def _parse_uuid(val: Any) -> Optional[UUID]:
    if isinstance(val, UUID):
        return val
    try:
        return UUID(str(val))
    except (ValueError, TypeError, AttributeError):
        return None


def ids_referenciados(layout: DashboardLayout) -> Tuple[Set[UUID], Set[UUID]]:
    ids_de_maquinas: Set[UUID] = set()
    ids_de_equipamentos: Set[UUID] = set()
    for w in layout.widgets:
        maqs = w.config.get("maquinas")
        if isinstance(maqs, list):
            for m in maqs:
                u = _parse_uuid(m)
                if u:
                    ids_de_maquinas.add(u)
        if w.tipo in ("cameras", "telemetria_equipamentos", "status_nvr"):
            eqs = w.config.get("equipamentos")
            if isinstance(eqs, list):
                for e in eqs:
                    u = _parse_uuid(e)
                    if u:
                        ids_de_equipamentos.add(u)
    return ids_de_maquinas, ids_de_equipamentos


def validar_referencias(db: Session, customer_id: UUID, layout: DashboardLayout) -> None:
    maq_rows = db.query(Machine.id).filter(Machine.customer_id == customer_id).all()
    maq_ids = {r[0] for r in maq_rows}
    eq_ids: Set[UUID] = set()
    if maq_ids:
        eq_rows = db.query(NVR.id).filter(NVR.machine_id.in_(maq_ids)).all()
        eq_ids = {r[0] for r in eq_rows}
    ids_m, ids_e = ids_referenciados(layout)
    if not ids_m.issubset(maq_ids) or not ids_e.issubset(eq_ids):
        raise HTTPException(
            status_code=422,
            detail="O dashboard referencia máquinas ou equipamentos que não pertencem a este cliente.",
        )


def layout_do_banco(dashboard: CustomerDashboard) -> DashboardLayout:
    if not dashboard.layout or not isinstance(dashboard.layout, dict):
        return layout_padrao()
    try:
        dados = copy.deepcopy(dashboard.layout)
        schema_ver = dados.get("schema_version")
        try:
            versao = int(schema_ver) if schema_ver is not None else 1
        except (ValueError, TypeError):
            versao = 1

        if versao < 2:
            widgets_list = dados.get("widgets")
            if isinstance(widgets_list, list):
                for w in widgets_list:
                    if isinstance(w, dict):
                        alt = w.get("altura", 2)
                        try:
                            alt_int = int(alt)
                        except (ValueError, TypeError):
                            alt_int = 2
                        w["altura"] = min(alt_int * 3, ALTURA_MAX)
            dados["schema_version"] = 2

        return DashboardLayout.model_validate(dados)
    except Exception:
        return layout_padrao()


def catalogo() -> List[Dict[str, Any]]:
    return [
        {
            "tipo": tw.tipo,
            "rotulo": tw.rotulo,
            "descricao": tw.descricao,
            "largura_padrao": tw.largura_padrao,
            "altura_padrao": tw.altura_padrao,
            "config_schema": tw.config_model.model_json_schema(),
        }
        for tw in REGISTRO.values()
    ]
