import logging
from datetime import date
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date, text, inspect

from database import Base, engine, get_db
from models import Client, Backup
from schemas import StatsResponse
from auth import verify_admin_token
from config import settings
from routers import auth_router, clients, nvrs, backups, agent, settings_router, equipamentos, groups
from routers.agent_update import agent_router as update_agent_router, admin_router as update_admin_router

# ─── Create tables on startup ──────────────────────────────────────────────
Base.metadata.create_all(bind=engine)

logger = logging.getLogger("trilan.api")


def _run_ddl(sql: str, descricao: str) -> None:
    """Executa um DDL em transação própria: a falha de um não impede os demais."""
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
    except Exception:
        logger.exception("Falha na migração (%s)", descricao)


def _tem_tabela(nome: str) -> bool:
    try:
        return inspect(engine).has_table(nome)
    except Exception:
        logger.exception("Falha ao inspecionar tabela '%s'", nome)
        return False


def _colunas(nome: str) -> list:
    try:
        return [col['name'] for col in inspect(engine).get_columns(nome)]
    except Exception:
        return []


# ─── Migrações inline (sem Alembic) — idempotentes ────────────────────────
# Cria tabela agent_versions se não existir (OTA)
if not _tem_tabela('agent_versions'):
    _run_ddl("""
        CREATE TABLE IF NOT EXISTS agent_versions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            version VARCHAR(20) NOT NULL UNIQUE,
            notes TEXT,
            url_service TEXT NOT NULL,
            url_tray TEXT,
            sha256_service VARCHAR(64) NOT NULL,
            sha256_tray VARCHAR(64),
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
        );
    """, "criar tabela agent_versions")

# Cria tabela client_groups se não existir (Clientes) — antes de clients.group_id (FK)
if not _tem_tabela('client_groups'):
    _run_ddl("""
        CREATE TABLE IF NOT EXISTS client_groups (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            description TEXT,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            backup_hour INTEGER DEFAULT 2,
            backup_minute INTEGER DEFAULT 0,
            queue_active BOOLEAN NOT NULL DEFAULT FALSE,
            queue_current_index INTEGER,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
        );
    """, "criar tabela client_groups")

# (tabela, coluna, DDL) — cada ALTER roda em transação separada
_MIGRACOES_COLUNAS = [
    ("clients", "last_seen", "ALTER TABLE clients ADD COLUMN last_seen TIMESTAMP WITHOUT TIME ZONE;"),
    ("clients", "restart_requested", "ALTER TABLE clients ADD COLUMN restart_requested BOOLEAN NOT NULL DEFAULT FALSE;"),
    ("clients", "backup_requested", "ALTER TABLE clients ADD COLUMN backup_requested BOOLEAN NOT NULL DEFAULT FALSE;"),
    ("clients", "telemetry", "ALTER TABLE clients ADD COLUMN telemetry JSON;"),
    ("clients", "group_id", "ALTER TABLE clients ADD COLUMN group_id UUID REFERENCES client_groups(id) ON DELETE SET NULL;"),
    ("clients", "queue_order", "ALTER TABLE clients ADD COLUMN queue_order INTEGER NOT NULL DEFAULT 0;"),
    ("nvrs", "last_recording_status", "ALTER TABLE nvrs ADD COLUMN last_recording_status JSON;"),
    # Suporte a múltiplos tipos de equipamentos
    ("nvrs", "tipo", "ALTER TABLE nvrs ADD COLUMN tipo VARCHAR(20) NOT NULL DEFAULT 'NVR';"),
    ("nvrs", "config_extra", "ALTER TABLE nvrs ADD COLUMN config_extra JSON;"),
    ("nvrs", "active", "ALTER TABLE nvrs ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE;"),
    ("nvrs", "updated_at", "ALTER TABLE nvrs ADD COLUMN updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW();"),
]

_colunas_cache: dict = {}
for _tabela, _coluna, _ddl in _MIGRACOES_COLUNAS:
    if _tabela not in _colunas_cache:
        _colunas_cache[_tabela] = _colunas(_tabela)
    # tabela inexistente (lista vazia): nada a migrar
    if _colunas_cache[_tabela] and _coluna not in _colunas_cache[_tabela]:
        _run_ddl(_ddl, f"{_tabela}.{_coluna}")

openapi_tags = [
    {"name": "auth", "description": "Autenticação administrativa"},
    {"name": "Clientes", "description": "Gestão de Clientes (agrupamentos de máquinas, fila de backup e download consolidado)"},
    {"name": "Máquinas", "description": "Gestão de Máquinas/Agentes (configuração individual, IP, status e chaves)"},
    {"name": "Equipamentos", "description": "Equipamentos vinculados às máquinas (NVR, OLT, ONU, PABX, etc.)"},
    {"name": "backups", "description": "Histórico e relatórios de backups"},
    {"name": "agent", "description": "Comunicação e heartbeat com os Agentes Windows"},
    {"name": "settings", "description": "Configurações do sistema (SMTP, retenção)"},
]

# ─── App ───────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Trilan Backup de Equipamentos API",
    version="3.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    openapi_tags=openapi_tags,
)

_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ───────────────────────────────────────────────────────────────
app.include_router(auth_router.router)
app.include_router(groups.router)        # Clientes: /api/v1/clients
app.include_router(clients.router)       # Máquinas: /api/v1/machines
app.include_router(equipamentos.router)  # Equipamentos: /api/v1/machines/{client_id}/equipamentos
app.include_router(nvrs.router, include_in_schema=False)  # mantido para compatibilidade
app.include_router(backups.router)
app.include_router(agent.router)
app.include_router(settings_router.router)
app.include_router(update_agent_router)   # OTA: /api/v1/agent/update-check
app.include_router(update_admin_router)   # OTA: /api/v1/admin/agent-version


# ─── Stats endpoint ────────────────────────────────────────────────────────
@app.get("/api/v1/stats", response_model=StatsResponse, dependencies=[Depends(verify_admin_token)])
def get_stats(db: Session = Depends(get_db)):
    today = date.today()
    # Contagens agregadas em 2 queries (em vez de 5)
    total, active = db.query(
        func.count(Client.id),
        func.count(Client.id).filter(Client.active == True),
    ).one()

    b_today, b_ok, b_err = db.query(
        func.count(Backup.id),
        func.count(Backup.id).filter(Backup.status == "OK"),
        func.count(Backup.id).filter(Backup.status == "ERROR"),
    ).filter(cast(Backup.started_at, Date) == today).one()

    return StatsResponse(
        total_clients=total or 0,
        active_clients=active or 0,
        backups_today=b_today or 0,
        backups_ok=b_ok or 0,
        backups_error=b_err or 0,
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "Trilan Backup de Equipamentos API"}
