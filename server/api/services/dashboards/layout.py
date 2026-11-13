import copy
from typing import Any, Dict, List, Literal, Optional, Set, Tuple
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from models import CustomerDashboard, Machine, NVR
from . import widgets  # noqa: F401  registra os tipos de widget
from .registro import REGISTRO

# Grade do schema 3: 24 colunas e linhas de 31 px (metade das 12 colunas × 62 px do schema 2),
# com posição livre (x, y) e empilhamento para cima (sem buracos), como no Grafana.
SCHEMA_ATUAL = 3
COLUNAS = 24
LARGURA_MIN = 2
LARGURA_MAX = COLUNAS
ALTURA_MIN = 1
ALTURA_MAX = 80
Y_MAX = 5000
MAX_WIDGETS = 40


class FiltrosGlobais(BaseModel):
    model_config = {"extra": "forbid"}
    periodo: Literal["24h", "7d", "30d"] = "7d"


class WidgetInstancia(BaseModel):
    model_config = {"extra": "forbid"}
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    tipo: str
    titulo: Optional[str] = Field(None, max_length=80)
    # Sem x/y, o widget vai para o primeiro lugar livre da grade
    x: Optional[int] = Field(None, ge=0, le=COLUNAS - 1)
    y: Optional[int] = Field(None, ge=0, le=Y_MAX)
    largura: int = Field(12, ge=LARGURA_MIN, le=LARGURA_MAX)
    altura: int = Field(12, ge=ALTURA_MIN, le=ALTURA_MAX)
    config: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validar_tipo_e_config(self):
        tipo = REGISTRO.get(self.tipo)
        if tipo is None:
            raise ValueError(f"Tipo de widget desconhecido: {self.tipo}")
        # Normaliza a config pelo modelo do tipo (rejeita chaves desconhecidas e valores inválidos)
        self.config = tipo.config_model.model_validate(self.config).model_dump(mode="json")
        return self


def _inteiro(valor: Any, padrao: int, minimo: int, maximo: int) -> int:
    try:
        n = int(valor)
    except (ValueError, TypeError):
        n = padrao
    return max(minimo, min(maximo, n))


def _migrar_widgets_v2(widgets: List[Any]) -> List[Any]:
    """Schema 2 -> 3: reproduz o posicionamento automático do CSS grid antigo
    (12 colunas, em ordem) para achar x/y e dobra tudo para a grade de 24 colunas."""
    ocupado: Set[Tuple[int, int]] = set()
    cursor_l, cursor_c = 0, 0
    saida: List[Any] = []
    for w in widgets:
        if not isinstance(w, dict):
            saida.append(w)
            continue
        w = dict(w)
        larg = _inteiro(w.get("largura"), 6, 1, 12)
        alt = _inteiro(w.get("altura"), 6, 1, 40)
        linha, col = cursor_l, cursor_c
        while True:
            if col + larg > 12:
                linha, col = linha + 1, 0
                continue
            livre = all(
                (linha + i, col + j) not in ocupado for i in range(alt) for j in range(larg)
            )
            if livre:
                break
            col += 1
        for i in range(alt):
            for j in range(larg):
                ocupado.add((linha + i, col + j))
        cursor_l, cursor_c = linha, col + larg
        w.update(
            x=col * 2,
            y=linha * 2,
            largura=max(LARGURA_MIN, larg * 2),
            altura=min(alt * 2, ALTURA_MAX),
        )
        saida.append(w)
    return saida


def _colide(a: WidgetInstancia, b: WidgetInstancia) -> bool:
    return (
        a.x < b.x + b.largura
        and b.x < a.x + a.largura
        and a.y < b.y + b.altura
        and b.y < a.y + a.altura
    )


def _compactar(widgets: List[WidgetInstancia]) -> List[WidgetInstancia]:
    """Sobe cada widget o máximo possível e desfaz sobreposições (mesma regra do painel)."""
    colocados: List[WidgetInstancia] = []
    for w in sorted(widgets, key=lambda w: (w.y, w.x)):
        # Encosta no widget mais baixo que esteja acima dele na mesma faixa de colunas
        w.y = max(
            (
                o.y + o.altura
                for o in colocados
                if o.x < w.x + w.largura and w.x < o.x + o.largura and o.y + o.altura <= w.y
            ),
            default=0,
        )
        while True:
            choque = next((o for o in colocados if _colide(w, o)), None)
            if choque is None:
                break
            w.y = choque.y + choque.altura
        colocados.append(w)
    return colocados


def _primeiro_lugar_livre(colocados: List[WidgetInstancia], w: WidgetInstancia) -> None:
    fundo = max((o.y + o.altura for o in colocados), default=0)
    for y in range(fundo + 1):
        for x in range(COLUNAS - w.largura + 1):
            w.x, w.y = x, y
            if not any(_colide(w, o) for o in colocados):
                return
    w.x, w.y = 0, fundo


class DashboardLayout(BaseModel):
    model_config = {"extra": "forbid"}
    schema_version: int = SCHEMA_ATUAL
    filtros: FiltrosGlobais = Field(default_factory=FiltrosGlobais)
    widgets: List[WidgetInstancia] = Field(default_factory=list, max_length=MAX_WIDGETS)

    @model_validator(mode="before")
    @classmethod
    def _migrar_schema(cls, dados: Any) -> Any:
        # Também cobre uma aba aberta antes da atualização que salve no formato antigo
        if not isinstance(dados, dict):
            return dados
        try:
            versao = int(dados.get("schema_version", SCHEMA_ATUAL))
        except (ValueError, TypeError):
            versao = SCHEMA_ATUAL
        if versao < SCHEMA_ATUAL:
            dados = dict(dados)
            if isinstance(dados.get("widgets"), list):
                dados["widgets"] = _migrar_widgets_v2(dados["widgets"])
            dados["schema_version"] = SCHEMA_ATUAL
        return dados

    @model_validator(mode="after")
    def _ids_unicos(self):
        ids = [w.id for w in self.widgets]
        if len(ids) != len(set(ids)):
            raise ValueError("Há widgets com id repetido")
        return self

    @model_validator(mode="after")
    def _normalizar_grade(self):
        com_posicao: List[WidgetInstancia] = []
        sem_posicao: List[WidgetInstancia] = []
        for w in self.widgets:
            if w.x is None or w.y is None:
                sem_posicao.append(w)
            else:
                w.x = min(w.x, COLUNAS - w.largura)
                com_posicao.append(w)
        colocados = _compactar(com_posicao)
        for w in sem_posicao:
            _primeiro_lugar_livre(colocados, w)
            colocados.append(w)
        # Ordem de leitura (de cima para baixo): é a ordem usada no celular
        self.widgets = _compactar(colocados)
        self.schema_version = SCHEMA_ATUAL
        return self


def layout_padrao() -> DashboardLayout:
    return DashboardLayout(
        schema_version=SCHEMA_ATUAL,
        filtros=FiltrosGlobais(periodo="7d"),
        widgets=[
            WidgetInstancia(id="resumo", tipo="resumo", x=0, y=0, largura=24, altura=6, config={}),
            WidgetInstancia(id="saude_servidor", tipo="saude_servidor", x=0, y=6, largura=24, altura=18, config={}),
            WidgetInstancia(id="status_backups", tipo="status_backups", x=0, y=24, largura=12, altura=12, config={}),
            WidgetInstancia(id="cameras", tipo="cameras", x=12, y=24, largura=12, altura=12, config={}),
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
        if w.tipo in ("cameras", "telemetria_equipamentos", "status_nvr", "antenas", "status_olt", "alarmes_defense"):
            eqs = w.config.get("equipamentos")
            if isinstance(eqs, list):
                for e in eqs:
                    u = _parse_uuid(e)
                    if u:
                        ids_de_equipamentos.add(u)
            if w.tipo == "telemetria_equipamentos":
                discos_cfg = w.config.get("discos")
                if isinstance(discos_cfg, dict):
                    for chave in discos_cfg.keys():
                        u = _parse_uuid(chave)
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
