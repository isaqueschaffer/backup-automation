import asyncio
import logging
from datetime import date
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date, text, inspect

from database import Base, engine, get_db, SessionLocal
from models import Machine, Customer, Backup, Plano
from schemas import StatsResponse
from auth import Contexto, get_contexto
from services.escopo import filtrar_por_conta
from config import settings
from routers import auth_router, machines, customers, nvrs, backups, agent, settings_router, equipamentos, dashboards, public_dashboard, storage_admin, contas_admin, conta
from routers.agent_update import agent_router as update_agent_router, admin_router as update_admin_router

# ─── Create tables on startup ──────────────────────────────────────────────
Base.metadata.create_all(bind=engine)

logger = logging.getLogger("trilan.api")


def _run_ddl(sql: str, descricao: str) -> bool:
    """Executa um DDL em transação própria: a falha de um não impede os demais.

    Retorna True se o DDL foi aplicado.
    """
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
        return True
    except Exception:
        logger.exception("Falha na migração (%s)", descricao)
        return False


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

# Cria tabela client_groups (Clientes) se não existir — antes de clients.group_id (FK)
# Nomes de TABELA/COLUNA no SQL abaixo são os do banco: clients = Máquinas, client_groups = Clientes
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

# Rodadas de backup do Cliente (1 e-mail por rodada) — antes de backups.run_id (FK)
if not _tem_tabela('customer_backup_runs'):
    _run_ddl("""
        CREATE TABLE IF NOT EXISTS customer_backup_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            customer_id UUID NOT NULL REFERENCES client_groups(id) ON DELETE CASCADE,
            trigger VARCHAR(30) NOT NULL,
            started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            deadline_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            closed_at TIMESTAMP WITHOUT TIME ZONE,
            status VARCHAR(20) NOT NULL DEFAULT 'EM_ANDAMENTO',
            expected_machine_ids JSON NOT NULL DEFAULT '[]',
            email_sent BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        );
    """, "criar tabela customer_backup_runs")

# Dashboards por Cliente (layout + link de compartilhamento)
if not _tem_tabela('customer_dashboards'):
    _run_ddl("""
        CREATE TABLE IF NOT EXISTS customer_dashboards (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            customer_id UUID NOT NULL UNIQUE REFERENCES client_groups(id) ON DELETE CASCADE,
            layout JSON NOT NULL DEFAULT '{}',
            version INTEGER NOT NULL DEFAULT 1,
            share_token_hash VARCHAR(64) UNIQUE,
            share_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            share_expires_at TIMESTAMP WITHOUT TIME ZONE,
            share_allow_edit BOOLEAN NOT NULL DEFAULT FALSE,
            share_created_at TIMESTAMP WITHOUT TIME ZONE,
            last_viewed_at TIMESTAMP WITHOUT TIME ZONE,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        );
    """, "criar tabela customer_dashboards")

# Multi-contas: planos, contas (inquilinos), histórico de renovações e usuários do painel
if not _tem_tabela('planos'):
    _run_ddl("""
        CREATE TABLE IF NOT EXISTS planos (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            nome VARCHAR(60) NOT NULL UNIQUE,
            duracao_dias INTEGER NOT NULL CONSTRAINT ck_planos_duracao_positiva CHECK (duracao_dias > 0),
            ativo BOOLEAN NOT NULL DEFAULT TRUE,
            criado_em TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        );
    """, "criar tabela planos")

if not _tem_tabela('contas'):
    _run_ddl("""
        CREATE TABLE IF NOT EXISTS contas (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            nome VARCHAR(255) NOT NULL,
            tipo VARCHAR(20) NOT NULL CONSTRAINT ck_contas_tipo CHECK (tipo IN ('INTEGRADOR', 'CLIENTE_FINAL')),
            documento VARCHAR(20),
            email_contato VARCHAR(255),
            telefone VARCHAR(30),
            plano_id UUID REFERENCES planos(id) ON DELETE SET NULL,
            expira_em TIMESTAMP WITHOUT TIME ZONE,
            ativo BOOLEAN NOT NULL DEFAULT TRUE,
            avisos_enviados JSON NOT NULL DEFAULT '[]',
            observacoes TEXT,
            criado_em TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        );
    """, "criar tabela contas")

if not _tem_tabela('conta_renovacoes'):
    _run_ddl("""
        CREATE TABLE IF NOT EXISTS conta_renovacoes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conta_id UUID NOT NULL REFERENCES contas(id) ON DELETE CASCADE,
            plano_id UUID REFERENCES planos(id) ON DELETE SET NULL,
            plano_nome VARCHAR(60) NOT NULL,
            dias INTEGER NOT NULL,
            expira_em_anterior TIMESTAMP WITHOUT TIME ZONE,
            expira_em_nova TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            feito_por VARCHAR(255),
            criado_em TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        );
    """, "criar tabela conta_renovacoes")

if not _tem_tabela('usuarios'):
    _run_ddl("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conta_id UUID REFERENCES contas(id) ON DELETE CASCADE,
            nome VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL UNIQUE,
            senha_hash VARCHAR(255) NOT NULL,
            papel VARCHAR(20) NOT NULL CONSTRAINT ck_usuarios_papel CHECK (papel IN ('SUPER_ADMIN', 'ADMIN', 'LEITURA')),
            ativo BOOLEAN NOT NULL DEFAULT TRUE,
            token_versao INTEGER NOT NULL DEFAULT 1,
            ultimo_login TIMESTAMP WITHOUT TIME ZONE,
            criado_em TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_usuarios_super_admin_sem_conta CHECK ((papel = 'SUPER_ADMIN') = (conta_id IS NULL))
        );
    """, "criar tabela usuarios")

# (tabela, coluna, DDL) — cada ALTER roda em transação separada
_MIGRACOES_COLUNAS = [
    ("clients", "last_seen", "ALTER TABLE clients ADD COLUMN last_seen TIMESTAMP WITHOUT TIME ZONE;"),
    ("clients", "restart_requested", "ALTER TABLE clients ADD COLUMN restart_requested BOOLEAN NOT NULL DEFAULT FALSE;"),
    ("clients", "backup_requested", "ALTER TABLE clients ADD COLUMN backup_requested BOOLEAN NOT NULL DEFAULT FALSE;"),
    ("clients", "telemetry", "ALTER TABLE clients ADD COLUMN telemetry JSON;"),
    ("clients", "group_id", "ALTER TABLE clients ADD COLUMN group_id UUID REFERENCES client_groups(id) ON DELETE SET NULL;"),
    ("clients", "queue_order", "ALTER TABLE clients ADD COLUMN queue_order INTEGER NOT NULL DEFAULT 0;"),
    ("nvrs", "last_recording_status", "ALTER TABLE nvrs ADD COLUMN last_recording_status JSON;"),
    ("nvrs", "last_telemetry_status", "ALTER TABLE nvrs ADD COLUMN last_telemetry_status JSON;"),
    # Suporte a múltiplos tipos de equipamentos
    ("nvrs", "tipo", "ALTER TABLE nvrs ADD COLUMN tipo VARCHAR(20) NOT NULL DEFAULT 'NVR';"),
    ("nvrs", "config_extra", "ALTER TABLE nvrs ADD COLUMN config_extra JSON;"),
    ("nvrs", "active", "ALTER TABLE nvrs ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE;"),
    ("nvrs", "updated_at", "ALTER TABLE nvrs ADD COLUMN updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW();"),
    # Rodadas de backup do Cliente
    ("backups", "run_id", "ALTER TABLE backups ADD COLUMN run_id UUID REFERENCES customer_backup_runs(id) ON DELETE SET NULL;"),
    ("client_groups", "email_to", "ALTER TABLE client_groups ADD COLUMN email_to TEXT[] NOT NULL DEFAULT '{}';"),
    # Senha do ZIP do cliente (Fernet-encrypted) — prioridade de download por cliente
    ("client_groups", "zip_password", "ALTER TABLE client_groups ADD COLUMN zip_password TEXT;"),
    # Campos RTSP por câmera na galeria (usados por DIGIFORT e DEFENSE)
    ("nvr_cameras", "ip", "ALTER TABLE nvr_cameras ADD COLUMN ip VARCHAR(50);"),
    ("nvr_cameras", "username", "ALTER TABLE nvr_cameras ADD COLUMN username VARCHAR(100);"),
    ("nvr_cameras", "password", "ALTER TABLE nvr_cameras ADD COLUMN password TEXT;"),
    ("nvr_cameras", "modelo", "ALTER TABLE nvr_cameras ADD COLUMN modelo VARCHAR(50);"),
    ("nvr_cameras", "canal_rtsp", "ALTER TABLE nvr_cameras ADD COLUMN canal_rtsp INTEGER;"),
    # Multi-contas: conta dona do Cliente/Setor e da Máquina (nullable até a etapa 2b)
    ("client_groups", "conta_id", "ALTER TABLE client_groups ADD COLUMN conta_id UUID REFERENCES contas(id) ON DELETE RESTRICT;"),
    ("clients", "conta_id", "ALTER TABLE clients ADD COLUMN conta_id UUID REFERENCES contas(id) ON DELETE RESTRICT;"),
    # Logs do agente no painel: nível e equipamento
    ("agent_logs", "nivel", "ALTER TABLE agent_logs ADD COLUMN nivel VARCHAR(10) NOT NULL DEFAULT 'INFO';"),
    ("agent_logs", "equipamento", "ALTER TABLE agent_logs ADD COLUMN equipamento VARCHAR(255);"),
]

_colunas_cache: dict = {}
_colunas_criadas: set = set()
for _tabela, _coluna, _ddl in _MIGRACOES_COLUNAS:
    if _tabela not in _colunas_cache:
        _colunas_cache[_tabela] = _colunas(_tabela)
    # tabela inexistente (lista vazia): nada a migrar
    if _colunas_cache[_tabela] and _coluna not in _colunas_cache[_tabela]:
        if _run_ddl(_ddl, f"{_tabela}.{_coluna}"):
            _colunas_criadas.add((_tabela, _coluna))

# Expansão de colunas existentes para acomodar hosts/caminhos longos
_run_ddl("ALTER TABLE nvrs ALTER COLUMN ip TYPE VARCHAR(255);", "nvrs.ip VARCHAR(255)")
_run_ddl("ALTER TABLE nvr_cameras ALTER COLUMN ip TYPE VARCHAR(255);", "nvr_cameras.ip VARCHAR(255)")


def _popular_email_to_clientes() -> None:
    """Preenche client_groups.email_to com a UNIÃO (sem repetição, ordem estável) dos
    e-mails das máquinas de cada Cliente. Só roda quando a coluna acabou de ser criada."""
    try:
        with SessionLocal() as db:
            for customer in db.query(Customer).all():
                emails: list = []
                for machine in customer.machines:  # ordem da fila
                    for email in (machine.email_to or []):
                        email = (email or "").strip()
                        if email and email not in emails:
                            emails.append(email)
                customer.email_to = emails
            db.commit()
        logger.info("Migração: client_groups.email_to preenchido com os e-mails das máquinas")
    except Exception:
        logger.exception("Falha ao preencher client_groups.email_to")


if ("client_groups", "email_to") in _colunas_criadas:
    _popular_email_to_clientes()

# Índices das colunas de conta (o create_all só cria índices em tabelas novas)
_INDICES = [
    "CREATE INDEX IF NOT EXISTS ix_client_groups_conta_id ON client_groups (conta_id);",
    "CREATE INDEX IF NOT EXISTS ix_clients_conta_id ON clients (conta_id);",
    "CREATE INDEX IF NOT EXISTS ix_usuarios_conta_id ON usuarios (conta_id);",
    "CREATE INDEX IF NOT EXISTS ix_conta_renovacoes_conta_id ON conta_renovacoes (conta_id);",
    "CREATE INDEX IF NOT EXISTS ix_agent_logs_client_created ON agent_logs (client_id, created_at);",
]
for _ddl in _INDICES:
    _run_ddl(_ddl, _ddl.split(" ON ")[0])


def _semear_multicontas() -> None:
    """Idempotente, roda em todo startup: planos iniciais (só com a tabela vazia), conta da plataforma
    e backfill de conta_id dos Clientes e Máquinas ainda sem conta (os criados pelo código antigo)."""
    from services.contas import PLANOS_INICIAIS, garantir_conta_plataforma
    try:
        with SessionLocal() as db:
            if db.query(Plano.id).first() is None:
                for nome, dias in PLANOS_INICIAIS:
                    db.add(Plano(nome=nome, duracao_dias=dias))
                logger.info("Migração: planos iniciais criados")
            conta_id = garantir_conta_plataforma(db)
            clientes = db.execute(
                text("UPDATE client_groups SET conta_id = :c WHERE conta_id IS NULL"), {"c": conta_id}
            ).rowcount
            # Máquina herda a conta do seu Cliente; sem Cliente, vai para a conta da plataforma
            maquinas = db.execute(text(
                "UPDATE clients SET conta_id = COALESCE("
                "(SELECT g.conta_id FROM client_groups g WHERE g.id = clients.group_id), :c) "
                "WHERE conta_id IS NULL"
            ), {"c": conta_id}).rowcount
            db.commit()
            if clientes or maquinas:
                logger.info("Migração: conta_id preenchido em %s clientes e %s máquinas", clientes, maquinas)
    except Exception:
        logger.exception("Falha na semente/backfill do multi-contas")


_semear_multicontas()


def _conta_id_obrigatorio() -> None:
    """Depois do backfill, torna conta_id NOT NULL em client_groups e clients (idempotente)."""
    for tabela in ("client_groups", "clients"):
        try:
            coluna = next((c for c in inspect(engine).get_columns(tabela) if c["name"] == "conta_id"), None)
        except Exception:
            logger.exception("Falha ao inspecionar %s.conta_id", tabela)
            continue
        if coluna is not None and coluna.get("nullable", False):
            _run_ddl(f"ALTER TABLE {tabela} ALTER COLUMN conta_id SET NOT NULL;", f"{tabela}.conta_id NOT NULL")


_conta_id_obrigatorio()

openapi_tags = [
    {"name": "auth", "description": "Autenticação administrativa"},
    {"name": "Contas", "description": "Contas (inquilinos), planos e super admins — só administrador da plataforma"},
    {"name": "Conta", "description": "Minha conta: validade do plano e usuários"},
    {"name": "Clientes", "description": "Gestão de Clientes (empresas atendidas: máquinas vinculadas, fila de backup e download consolidado)"},
    {"name": "Máquinas", "description": "Gestão de Máquinas (computadores com o agente: configuração, status e chaves)"},
    {"name": "Equipamentos", "description": "Equipamentos vinculados às máquinas (NVR, OLT, ONU, PABX, etc.)"},
    {"name": "Dashboards", "description": "Dashboards personalizáveis por Cliente e link público de visualização"},
    {"name": "backups", "description": "Histórico e relatórios de backups"},
    {"name": "agent", "description": "Comunicação e heartbeat com os Agentes Windows"},
    {"name": "settings", "description": "Configurações do sistema (SMTP, retenção)"},
    {"name": "Armazenamento", "description": "Operações administrativas sobre o armazenamento de backups"},
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
app.include_router(contas_admin.router)  # Multi-contas (super admin): /api/v1/admin/contas, planos, super-admins
app.include_router(conta.router)  # Multi-contas: /api/v1/conta (minha conta e usuários)
app.include_router(customers.router)     # Clientes: /api/v1/clients
app.include_router(machines.router)      # Máquinas: /api/v1/machines
app.include_router(equipamentos.router)  # Equipamentos: /api/v1/machines/{machine_id}/equipamentos
app.include_router(dashboards.router)         # Dashboards (admin): /api/v1/clients/{id}/dashboard e /api/v1/dashboards
app.include_router(public_dashboard.router)   # Dashboard público por link: /api/v1/public/dashboard
app.include_router(nvrs.router, include_in_schema=False)  # mantido para compatibilidade
app.include_router(backups.router)
app.include_router(agent.router)
app.include_router(settings_router.router)
app.include_router(update_agent_router)   # OTA: /api/v1/agent/update-check
app.include_router(update_admin_router)   # OTA: /api/v1/admin/agent-version
app.include_router(storage_admin.router)  # Armazenamento admin: /api/v1/admin/storage


# ─── Tarefa de fundo: fechamento das rodadas de backup do Cliente ──────────
# A cada 30s fecha as rodadas vencidas/completas e envia o e-mail do Cliente.
# LIMITAÇÃO (a mesma do pending_rtsp_tasks em routers/agent.py): pensado para 1 worker
# uvicorn. Com vários workers cada processo rodaria o seu loop; o fechamento é protegido
# por UPDATE condicional (closed_at IS NULL), então o e-mail não duplica, mas o trabalho sim.
RUN_CLOSER_INTERVAL_SECONDS = 30
_run_closer_task = None


def _close_due_runs_once() -> None:
    from services.backup_runs import close_due_runs
    with SessionLocal() as db:
        close_due_runs(db)


async def _run_closer_loop() -> None:
    while True:
        try:
            # SMTP e banco são bloqueantes: roda no threadpool para não travar o event loop
            await asyncio.to_thread(_close_due_runs_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falha na tarefa de fechamento das rodadas de backup")
        await asyncio.sleep(RUN_CLOSER_INTERVAL_SECONDS)


@app.on_event("startup")
async def _start_run_closer() -> None:
    global _run_closer_task
    _run_closer_task = asyncio.create_task(_run_closer_loop())


@app.on_event("shutdown")
async def _stop_run_closer() -> None:
    if _run_closer_task is not None:
        _run_closer_task.cancel()


# ─── Tarefa de fundo: avisos de vencimento das Contas (multi-contas) ───────
# A cada hora envia os e-mails de 7/3/1 dia e do vencimento (marcos em contas.avisos_enviados).
# Mesma limitação de 1 worker uvicorn do laço acima; o marco gravado evita e-mail repetido.
VENCIMENTOS_INTERVAL_SECONDS = 3600
_vencimentos_task = None


def _verificar_vencimentos_once() -> None:
    from services.avisos_conta import verificar_vencimentos
    with SessionLocal() as db:
        verificar_vencimentos(db)


async def _vencimentos_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(_verificar_vencimentos_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falha na tarefa de avisos de vencimento das contas")
        await asyncio.sleep(VENCIMENTOS_INTERVAL_SECONDS)


@app.on_event("startup")
async def _start_vencimentos() -> None:
    global _vencimentos_task
    _vencimentos_task = asyncio.create_task(_vencimentos_loop())


@app.on_event("shutdown")
async def _stop_vencimentos() -> None:
    if _vencimentos_task is not None:
        _vencimentos_task.cancel()


@app.on_event("startup")
async def _sincronizar_imagens_cameras() -> None:
    from services.storage_service import sincronizar_imagens_existentes
    try:
        res = await asyncio.to_thread(sincronizar_imagens_existentes, SessionLocal)
        logger.info("Imagens das câmeras gravadas em pasta: %s", res)
    except Exception:
        logger.exception("Falha ao gravar as imagens das câmeras existentes em pasta")


# ─── Stats endpoint ────────────────────────────────────────────────────────
@app.get("/api/v1/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    today = date.today()
    # Contagens agregadas em 3 queries
    q_machines = db.query(
        func.count(Machine.id),
        func.count(Machine.id).filter(Machine.active == True),
    )
    q_machines = filtrar_por_conta(q_machines, Machine.conta_id, ctx)
    machines_total, machines_active = q_machines.one()

    q_customers = db.query(func.count(Customer.id))
    q_customers = filtrar_por_conta(q_customers, Customer.conta_id, ctx)
    customers_total = q_customers.scalar()

    q_backup = db.query(
        func.count(Backup.id),
        func.count(Backup.id).filter(Backup.status == "OK"),
        func.count(Backup.id).filter(Backup.status == "ERROR"),
    ).filter(cast(Backup.started_at, Date) == today)

    if ctx.conta_id is not None:
        q_backup = q_backup.filter(
            Backup.machine_id.in_(filtrar_por_conta(db.query(Machine.id), Machine.conta_id, ctx))
        )

    b_today, b_ok, b_err = q_backup.one()

    return StatsResponse(
        machines_total=machines_total or 0,
        machines_active=machines_active or 0,
        customers_total=customers_total or 0,
        backups_today=b_today or 0,
        backups_ok=b_ok or 0,
        backups_error=b_err or 0,
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "Trilan Backup de Equipamentos API"}
