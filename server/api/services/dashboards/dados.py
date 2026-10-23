import logging
from typing import Any, Dict

from sqlalchemy.orm import Session

from models import Customer
from .layout import DashboardLayout
from .registro import REGISTRO
from .widgets import carregar_contexto, equipamentos_ativos, iso

logger = logging.getLogger(__name__)


def montar_dados(db: Session, customer: Customer, layout: DashboardLayout) -> Dict[str, Any]:
    ctx = carregar_contexto(db, customer, layout.filtros.periodo)
    resultado: Dict[str, Any] = {}

    for w in layout.widgets:
        tipo = REGISTRO.get(w.tipo)
        if tipo is None:
            resultado[w.id] = {"ok": False, "erro": "Não foi possível carregar este widget."}
            continue
        try:
            config = tipo.config_model.model_validate(w.config)
            resultado[w.id] = {"ok": True, "dados": tipo.construir(ctx, config)}
        except Exception:
            logger.exception("Falha ao montar widget %s (tipo %s) para cliente %s", w.id, w.tipo, customer.id)
            resultado[w.id] = {"ok": False, "erro": "Não foi possível carregar este widget."}

    return {
        "gerado_em": iso(ctx.agora),
        "widgets": resultado,
    }


def listar_opcoes(db: Session, customer: Customer) -> Dict[str, Any]:
    ctx = carregar_contexto(db, customer, "7d")
    maquinas = [{"id": m.id, "nome": m.name} for m in ctx.maquinas]
    equipamentos = []
    for m in ctx.maquinas:
        for e in equipamentos_ativos(m):
            equipamentos.append({
                "id": e.id,
                "nome": e.name,
                "tipo": e.tipo or "NVR",
                "maquina_id": m.id,
                "maquina": m.name,
            })
    return {
        "maquinas": maquinas,
        "equipamentos": equipamentos,
    }
