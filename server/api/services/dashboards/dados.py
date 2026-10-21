import logging
from typing import Any, Dict

from sqlalchemy.orm import Session

from models import Customer
from .layout import DashboardLayout
from .registro import REGISTRO
from .widgets import carregar_contexto, iso

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
