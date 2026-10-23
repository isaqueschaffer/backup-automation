from pathlib import Path
from typing import Any, Dict, Optional, Union
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from auth import verify_admin_token
from config import settings
from database import get_db
from models import Machine
from services.storage_service import reorganizar_maquina

router = APIRouter(prefix="/api/v1/admin/storage", tags=["Armazenamento"])


def _to_rel_path(p: Optional[Union[str, Path]]) -> Optional[str]:
    """Converte um caminho para formato relativo a settings.BACKUP_STORAGE_PATH com barras /."""
    if not p:
        return None
    base_dir = Path(settings.BACKUP_STORAGE_PATH).resolve()
    try:
        resolved = Path(p).resolve()
        return resolved.relative_to(base_dir).as_posix()
    except ValueError:
        return Path(p).name


@router.post("/reorganizar", dependencies=[Depends(verify_admin_token)])
def reorganizar_armazenamento(
    aplicar: bool = Query(False, description="Se False apenas simula; se True executa a reorganização"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Reorganiza o armazenamento de todas as máquinas para a estrutura canônica Cliente > Máquina."""
    machines = db.query(Machine).options(joinedload(Machine.customer)).order_by(Machine.name).all()

    resumo = {
        "mover": 0,
        "unir": 0,
        "ja_ok": 0,
        "sem_pasta": 0,
        "ignorado": 0,
        "erro": 0,
    }
    maquinas_resultado = []

    for m in machines:
        res = reorganizar_maquina(m.id, m.name, m.customer, aplicar=aplicar)
        acao = res.get("acao")
        if acao in resumo:
            resumo[acao] += 1
        else:
            resumo["erro"] += 1

        maquinas_resultado.append(
            {
                "maquina": m.name,
                "cliente": m.customer.name if m.customer else None,
                "acao": acao,
                "origem": _to_rel_path(res.get("origem")),
                "destino": _to_rel_path(res.get("destino")),
                "conflitos": res.get("conflitos", []),
            }
        )

    return {
        "aplicado": aplicar,
        "resumo": resumo,
        "maquinas": maquinas_resultado,
    }
