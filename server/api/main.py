from datetime import date, timedelta, datetime
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date, text

from database import Base, engine, get_db
from models import Client, Backup
from schemas import StatsResponse
from auth import verify_admin_token
from config import settings
from routers import auth_router, clients, nvrs, backups, agent, settings_router, equipamentos

# ─── Create tables on startup ──────────────────────────────────────────────
Base.metadata.create_all(bind=engine)

from sqlalchemy import inspect

# Verifica colunas existentes antes de adicionar
try:
    insp = inspect(engine)
    colunas_existentes = [col['name'] for col in insp.get_columns('clients')]
    
    # Verifica nvrs se a tabela existir
    try:
        colunas_nvrs = [col['name'] for col in insp.get_columns('nvrs')]
    except Exception:
        colunas_nvrs = []
    
    with engine.begin() as conn:
        if 'last_seen' not in colunas_existentes:
            conn.execute(text("ALTER TABLE clients ADD COLUMN last_seen TIMESTAMP WITHOUT TIME ZONE;"))
            
        if 'restart_requested' not in colunas_existentes:
            conn.execute(text("ALTER TABLE clients ADD COLUMN restart_requested BOOLEAN NOT NULL DEFAULT FALSE;"))
            
        if colunas_nvrs and 'last_recording_status' not in colunas_nvrs:
            conn.execute(text("ALTER TABLE nvrs ADD COLUMN last_recording_status JSON;"))

        # Migrações para suporte a múltiplos tipos de equipamentos
        if colunas_nvrs and 'tipo' not in colunas_nvrs:
            conn.execute(text("ALTER TABLE nvrs ADD COLUMN tipo VARCHAR(20) NOT NULL DEFAULT 'NVR';"))

        if colunas_nvrs and 'config_extra' not in colunas_nvrs:
            conn.execute(text("ALTER TABLE nvrs ADD COLUMN config_extra JSON;"))
            
        if colunas_nvrs and 'active' not in colunas_nvrs:
            conn.execute(text("ALTER TABLE nvrs ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE;"))
            
        if colunas_nvrs and 'updated_at' not in colunas_nvrs:
            conn.execute(text("ALTER TABLE nvrs ADD COLUMN updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW();"))
except Exception as e:
    print(f"Erro ao executar migrações de colunas: {e}")

# ─── App ───────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Trilan Backup de Equipamentos API",
    version="3.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
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
app.include_router(clients.router)
app.include_router(equipamentos.router)  # novo router genérico
app.include_router(nvrs.router)           # mantido para compatibilidade
app.include_router(backups.router)
app.include_router(agent.router)
app.include_router(settings_router.router)


# ─── Stats endpoint ────────────────────────────────────────────────────────
@app.get("/api/v1/stats", response_model=StatsResponse, dependencies=[Depends(verify_admin_token)])
def get_stats(db: Session = Depends(get_db)):
    today = date.today()
    total = db.query(func.count(Client.id)).scalar() or 0
    active = db.query(func.count(Client.id)).filter(Client.active == True).scalar() or 0

    backups_today_q = db.query(Backup).filter(
        cast(Backup.started_at, Date) == today
    )
    b_today = backups_today_q.count()
    b_ok = backups_today_q.filter(Backup.status == "OK").count()
    b_err = backups_today_q.filter(Backup.status == "ERROR").count()

    return StatsResponse(
        total_clients=total,
        active_clients=active,
        backups_today=b_today,
        backups_ok=b_ok,
        backups_error=b_err,
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "Trilan Backup de Equipamentos API"}
