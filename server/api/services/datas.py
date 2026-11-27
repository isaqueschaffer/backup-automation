"""Datas no padrão do projeto (REGRA-001): datetime naive em UTC.

Uma coluna pode voltar do Postgres com fuso (timestamptz criada fora das migrações do projeto) e uma data
pode chegar de fora com fuso. Antes de comparar ou subtrair com `datetime.utcnow()`, normalizar aqui:
misturar naive com aware dá `TypeError` (o fechamento das rodadas falhava assim em 24/11/2026)."""
from datetime import datetime, timezone
from typing import Optional


def para_utc_naive(dt: Optional[datetime]) -> Optional[datetime]:
    """Converte para UTC e tira o fuso; naive é tratado como já em UTC e volta igual. None volta None."""
    if dt is None or dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)
