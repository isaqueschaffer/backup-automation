---
name: criar-endpoint-fastapi
description: Padrão do projeto para criar ou alterar endpoints, campos ou tabelas na API FastAPI (server/api) — schemas, model, migração inline, router, autenticação admin/agente, cliente do dashboard e registro no PROJECT_SPEC. Use sempre que mexer em rotas ou no banco da API.
---

# Endpoints na API (`server/api`)

Stack fixo: FastAPI 0.111, SQLAlchemy 2.0 síncrono, Pydantic 2.7, PostgreSQL 15 e `requests`.
Não migrar para SQLModel, HTTPX, sessão async nem Alembic. A skill `fastapi` vale só no que existe nessas versões.

## Nomes no banco

| Tabela | Model | Na interface |
|---|---|---|
| `contas` | `Conta` | Conta (inquilino): Integrador ou Cliente final, com plano e validade (ADR-009) |
| `clients` | `Machine` | Máquina (computador com o agente); `conta_id` obrigatório |
| `client_groups` | `Customer` | Cliente (integrador) ou Setor (cliente final); `conta_id` obrigatório |
| `nvrs` | `NVR` | Equipamento de qualquer tipo (REGRA-002: nunca renomear) |
| `usuarios`, `planos`, `conta_renovacoes` | `Usuario`, `Plano`, `ContaRenovacao` | Logins do painel, planos e histórico de validade |

## Passo a passo

1. **Schemas** (`schemas.py`): entrada `XCreate` e `XUpdate` (campos `Optional`) e saída `XResponse` com `model_config = {"from_attributes": True}`.
2. **Model** (`models.py`): datas em `Column(DateTime)` sem `timezone=True`, com `default=datetime.utcnow` (REGRA-001). Valor gravado nunca vem de `datetime.now()` nem de `datetime.now(timezone.utc)`.
3. **Migração inline** (`main.py`, REGRA-007). O `create_all` só cria tabelas novas; não altera as que já existem.
   - Coluna nova: tupla em `_MIGRACOES_COLUNAS`, ex.: `("nvrs", "x", "ALTER TABLE nvrs ADD COLUMN x TEXT;")`. Datas como `TIMESTAMP WITHOUT TIME ZONE`.
   - Tabela nova: bloco `if not _tem_tabela("x"): _run_ddl("CREATE TABLE IF NOT EXISTS x (...)", "criar tabela x")`, antes das colunas que apontam para ela (FK).
   - Proibido: Alembic, `drop_all`, DDL destrutivo.
4. **Router** (`routers/<modulo>.py`):
   - `router = APIRouter(prefix="/api/v1/...", tags=[...])`. Arquivo novo: `app.include_router(...)` no `main.py`.
   - Handlers `def` síncronos com `db: Session = Depends(get_db)`. `async def` só sem I/O bloqueante (o ping em `routers/agent.py` fecha a sessão antes do long-polling).
   - Autenticação (REGRA-003, nunca misturar):
     - painel: `ctx: Contexto = Depends(get_contexto)` (`auth.py`); só da plataforma: `Depends(exigir_super_admin)`; usuários da conta: `Depends(exigir_admin_conta)`. **Não usar `verify_admin_token` em rota nova** (aceita só o super admin; existe por compatibilidade);
     - agente: `machine: Machine = Depends(get_current_machine)` (headers `X-Client-ID` + `X-API-Key`); conta vencida: `maquina_bloqueada(machine)`.
   - Isolamento por conta (REGRA-010): Cliente/Máquina por `obter_cliente(db, ctx, id)` / `obter_maquina(db, ctx, id)`, listas com `filtrar_por_conta(consulta, Model.conta_id, ctx)` (`services/escopo.py`); outra conta = 404; `Customer(...)`/`Machine(...)` novos com `conta_id=conta_para_criacao(db, ctx)`. O bloqueio de escrita (conta vencida, usuário LEITURA) já está no `get_contexto`. Rota nova com dados de conta ganha um caso em `tests/test_isolamento_contas.py`.
   - Erros: `HTTPException(status_code=..., detail="mensagem em português")`.
   - Senhas de equipamento e de ZIP: `encrypt()`/`decrypt()` de `services/crypto_service.py` (Fernet, REGRA-004). Só o agente recebe a senha aberta (`/agent/config`); respostas do admin nunca trazem senha.
   - Horários de backup são calculados no servidor, não pelo relógio do agente (REGRA-005).
5. **Dashboard** (quando a tela usa o endpoint): função em `server/dashboard/src/api/client.ts` (`api.get("/caminho").then(r => r.data)`; a base já inclui `/api/v1` e o interceptor manda o `X-Conta-ID` do super admin) e tipo em `src/api/types.ts`. As datas chegam naive em UTC: formatar com `fmtDate` (`src/utils/date.ts`). Texto "Cliente" na tela vem de `useRotulos()`; botão que altera dados fica oculto com `useSomenteLeitura()` (`contexts/AuthContext.tsx`).
6. **Agente** (quando ele consome o endpoint): versões antigas continuam rodando até a OTA chegar. Campo novo deve ser opcional e o servidor deve tolerar a ausência dele.
7. **PROJECT_SPEC.md**: tabela de endpoints (seção 8, "Contratos de API") e changelog (seção 16: data, alteração, arquivos, breaking change, branch).
