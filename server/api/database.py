import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker, DeclarativeBase
from config import settings

logger = logging.getLogger(__name__)


def _engine_kwargs(url: str) -> dict:
    """Pool e limites da conexão. Postgres (produção): pool com espera curta, reciclagem e
    `idle_in_transaction_session_timeout` (o banco encerra a sessão esquecida aberta numa transação, que antes
    prendia a conexão para sempre: pool esgotado em 24/11/2026). SQLite (testes): só o pre_ping, porque o pool
    dele (SingletonThreadPool/StaticPool) não aceita pool_size/pool_timeout."""
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        return kwargs
    kwargs.update(
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT_S,
        pool_recycle=settings.DB_POOL_RECYCLE_S,
    )
    if url.startswith("postgresql") and settings.DB_IDLE_IN_TRANSACTION_TIMEOUT_MS > 0:
        kwargs["connect_args"] = {
            "options": f"-c idle_in_transaction_session_timeout={int(settings.DB_IDLE_IN_TRANSACTION_TIMEOUT_MS)}"
        }
    return kwargs


engine = create_engine(settings.DATABASE_URL, **_engine_kwargs(settings.DATABASE_URL))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def encerrar_transacao(db: Session) -> None:
    """Grava o que estiver pendente e devolve a conexão ao pool ANTES de uma espera longa sem banco
    (SMTP, upload do ZIP, leitura de arquivos num disco lento). Sem isso a sessão fica "idle in transaction"
    segurando uma das 15 conexões do pool durante toda a espera. Os objetos carregados expiram e são relidos
    no próximo acesso (nova transação, conexão nova do pool)."""
    if db is None:
        return
    try:
        em_transacao = db.in_transaction()
    except Exception:
        return
    if em_transacao:
        try:
            db.commit()
        except Exception:
            db.rollback()  # deixa a sessão utilizável para o chamador (senão tudo depois dá PendingRollbackError)
            raise
