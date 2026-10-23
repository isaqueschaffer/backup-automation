# PROJECT_SPEC.md
# Trilan NVR Backup Automation — Especificação Técnica e Fonte de Verdade

> **Este documento é a fonte de verdade do projeto.**
> Qualquer alteração de arquitetura, banco de dados, API, contrato de dados ou decisão técnica
> DEVE ser registrada aqui ANTES ou SIMULTANEAMENTE à implementação.
> Merges não auditados contra este documento são considerados **INSEGUROS**.

---

## Índice

1. [Visão Geral](#1-visão-geral)
2. [Stack Tecnológico](#2-stack-tecnológico)
3. [Estrutura de Diretórios](#3-estrutura-de-diretórios)
4. [Arquitetura do Sistema](#4-arquitetura-do-sistema)
5. [Banco de Dados](#5-banco-de-dados)
6. [Regras Protegidas — Contratos Imutáveis](#6-regras-protegidas--contratos-imutáveis)
7. [Autenticação e Segurança](#7-autenticação-e-segurança)
8. [Contratos de API](#8-contratos-de-api)
9. [Agente Windows](#9-agente-windows)
10. [Sistema OTA](#10-sistema-ota-over-the-air-update)
11. [Infraestrutura e Deploy](#11-infraestrutura-e-deploy)
12. [Variáveis de Ambiente](#12-variáveis-de-ambiente)
13. [Tipos de Equipamento Suportados](#13-tipos-de-equipamento-suportados)
14. [Decisões Arquiteturais (ADRs)](#14-decisões-arquiteturais-adrs)
15. [Incompatibilidades Conhecidas](#15-incompatibilidades-conhecidas)
16. [Architecture Changelog](#16-architecture-changelog)

---

## 1. Visão Geral

**Nome:** Trilan NVR Backup Automation
**Propósito:** Sistema de backup automatizado de configurações de equipamentos de rede instalados em clientes (NVRs, DVRs, OLTs, PABXs, Mikrotiks, etc.).
**Modelo:** SaaS multi-tenant — um servidor central recebe dados de múltiplos agentes Windows instalados nos clientes.

### Componentes Principais

| Componente | Tecnologia | Responsabilidade |
|---|---|---|
| Servidor API | FastAPI (Python 3.11+) | Recebe dados dos agentes, expõe painel |
| Dashboard | React + TypeScript (Vite) | Interface web de administração |
| Banco de Dados | PostgreSQL 15 | Persistência de todos os dados |
| Agente Windows (Service) | Python compilado via PyInstaller | Coleta backups e faz upload ao servidor |
| Agente Windows (Tray) | Python compilado via PyInstaller | Interface visual no ícone da bandeja do Windows |
| Proxy/Gateway | Nginx 1.25-alpine | Reverse proxy entre dashboard, API e internet |

---

## 2. Stack Tecnológico

### Servidor (Backend)

| Dependência | Versão Fixada | Uso |
|---|---|---|
| Python | 3.11+ | Runtime |
| FastAPI | 0.111.0 | Framework API |
| Uvicorn | 0.29.0 | ASGI server |
| SQLAlchemy | 2.0.30 | ORM |
| psycopg2-binary | 2.9.9 | Driver PostgreSQL |
| Pydantic | 2.7.1 | Validação de dados / schemas |
| pydantic-settings | 2.2.1 | Configuração via env vars |
| python-jose | 3.3.0 | JWT (autenticação admin) |
| passlib[bcrypt] | 1.7.4 | Hash de senhas |
| cryptography | 42.0.7 | Fernet (criptografia de senhas) |
| python-multipart | 0.0.9 | Upload de arquivos |
| aiofiles | 23.2.1 | I/O assíncrono de arquivos |
| requests | 2.31.0 | HTTP client |

### Dashboard (Frontend)

| Dependência | Versão | Uso |
|---|---|---|
| React | 18.x | UI framework |
| TypeScript | 5.x | Tipagem |
| Vite | 5.x | Build tool |

### Agente Windows

| Dependência | Versão | Uso |
|---|---|---|
| Python | 3.11+ via PyInstaller | Runtime compilado |
| requests | >=2.31.0 | HTTP para API |
| pyzipper | >=0.3.6 | ZIP com senha AES-256 |
| pycryptodome | >=3.20.0 | Criptografia local |
| pypiwin32 | >=223 | Win32 API (serviço Windows) |
| pystray | >=0.19.5 | Ícone na bandeja do Windows |
| Pillow | >=10.3.0 | Renderização de ícone |
| paramiko | >=3.4.0,<4.0.0 | SSH (para OLTs/Mikrotiks) |
| pyftpdlib | >=1.5.8 | FTP (para equipamentos que usam FTP) |
| imageio-ffmpeg | — | ffmpeg embarcado (captura RTSP / imagem noturna) |
| psutil | >=5.9.0 | Telemetria (CPU, RAM, disco, rede) |
| GPUtil | >=1.4.0 | Telemetria de GPU (opcional, falha silenciosa) |

---

## 3. Estrutura de Diretórios

```
trilan-nvr-backup-automation/
├── PROJECT_SPEC.md              <- ESTE ARQUIVO (fonte de verdade)
├── README.md
├── agent/                       <- Agente Windows (PyInstaller)
│   ├── service.py               <- Entry point do serviço Windows (ping em thread + loop principal)
│   ├── tray.py                  <- Entry point do app de bandeja
│   ├── agent.py                 <- Orquestrador de backup (reexporta run_backup)
│   ├── agent.conf               <- Configuração local do agente (NAO versionar)
│   ├── agent.conf.example
│   ├── build.ps1                <- Gera os EXEs em dist/ (hidden-imports aqui)
│   ├── publish_version.ps1
│   ├── installer.iss            <- Instalador Inno Setup (versão do agente)
│   ├── requirements.txt
│   ├── dist/                    <- EXEs compilados (NAO versionados; vão por upload no OTA Manager)
│   └── src/
│       ├── application/
│       │   ├── api_client.py    <- HTTP client para o servidor (ping, upload, telemetria)
│       │   ├── backup_job.py    <- Orquestra o backup por equipamento + captura da imagem da noite
│       │   ├── updater.py       <- Auto-atualização OTA (CURRENT_VERSION)
│       │   ├── webhook_defense.py / webhook_digifort.py
│       ├── backup/              <- archiver, crypto, downloader, file_manager/
│       ├── camera/rtsp_client.py<- Teste RTSP, referência ideal e imagem da noite (ffmpeg)
│       ├── core/config.py       <- Lê agent.conf (ConfigError, parse_config_extra)
│       ├── nvr/
│       │   ├── factory.py       <- Detecta tipo de NVR e orquestra busca/gravação
│       │   ├── hikvision/       <- NVR/DVR Hikvision (ISAPI)
│       │   └── motorola/        <- NVR Motorola/NVMS-9000 (cameras, recordings, queryChlRecLog)
│       ├── olt/                 <- huawei_active, unm2000, vsol
│       ├── pabx/issabel.py
│       ├── mikrotik/routeros.py
│       ├── vms/defense.py       <- Intelbras Defense
│       └── utils/               <- http.py, xml_parser.py
├── server/
│   ├── .env                     <- Configuração de produção (NAO versionar)
│   ├── .env.example / .env.local.example
│   ├── docker-compose.yml       <- Produção (Dokploy)
│   ├── docker-compose.local.yml <- Desenvolvimento local
│   ├── nginx/nginx.conf
│   ├── api/                     <- Backend FastAPI
│   │   ├── main.py              <- App + migrações inline (sem Alembic)
│   │   ├── models.py            <- Machine (tabela clients), Customer (tabela client_groups), NVR, Backup...
│   │   ├── schemas.py / auth.py / database.py / config.py
│   │   ├── routers/
│   │   │   ├── agent.py         <- /api/v1/agent/*
│   │   │   ├── agent_update.py  <- OTA: /agent/update-check e /admin/agent-version/*
│   │   │   ├── machines.py      <- /api/v1/machines/*  (Máquinas = computadores com o agente)
│   │   │   ├── customers.py     <- /api/v1/clients/*   (Clientes = empresas; fila de backup)
│   │   │   ├── equipamentos.py  <- /api/v1/machines/{id}/equipamentos/*
│   │   │   ├── nvrs.py          <- legado, fora do schema (candidato a remoção)
│   │   │   ├── backups.py       <- /api/v1/backups/*
│   │   │   ├── dashboards.py    <- /api/v1/clients/{id}/dashboard/* e /api/v1/dashboards/widgets (admin, JWT)
│   │   │   ├── public_dashboard.py <- /api/v1/public/dashboard/* (só X-Dashboard-Token)
│   │   │   ├── settings_router.py / auth_router.py
│   │   ├── services/            <- crypto_service, email_service, storage_service, galeria_vms
│   │   │   └── dashboards/      <- registro, widgets, layout, dados, compartilhamento (token/limitador), esquemas
│   │   └── tests/
│   └── dashboard/               <- React + Vite + TypeScript
│       ├── Dockerfile / nginx-spa.conf
│       └── src/
│           ├── api/             <- client.ts (axios) e types.ts
│           ├── components/ / utils/date.ts
│           └── pages/
│               ├── Customers/       <- CustomersPage (/clientes), CustomerDetail/ (/clientes/:id, fila arrastar-e-soltar)
│               ├── Machines/        <- MachinesPage (/maquinas), MachineDetail/ (/maquinas/:id)
│               ├── Dashboards/      <- editor e visão do cliente: DashboardWorkspace, widgets/ (registro), SharePanel, DashboardAdminPage (/clientes/:id/dashboard), PublicDashboardPage (/d)
│               └── Backups.tsx / Overview/ (Visão Geral personalizável) / Settings.tsx
├── tools/                       <- Utilitários avulsos (não entram em build nem deploy)
├── archive/legacy_scripts/      <- Código legado, só consulta
├── .agents/rules/               <- Regras lidas pelo Antigravity (agy)
└── .claude/skills/              <- Skills do projeto, só para o Claude Code (o agy não lê esta pasta)
```

---

## 4. Arquitetura do Sistema

```
[Cliente Windows]
    TrilanAgentTray.exe  (UI visual)
    TrilanAgentService.exe (servico Windows)
         |
         |  HTTPS  ->  Headers: X-Client-ID + X-API-Key
         v
[Servidor Dokploy - porta 7001]
    Nginx (reverse proxy)
         |
         +-- /api/* -> FastAPI (porta 8000 interna)
         +-- /*     -> React Dashboard (porta 80 interna)
              |
              +-- PostgreSQL (porta 5432 interna)
```

### Fluxo do Agente

1. Ao iniciar: lê `agent.conf`, chama `GET /api/v1/agent/config` para obter configuração
2. A cada 15 segundos: `POST /api/v1/agent/ping` — heartbeat + recebe flags de controle (long-polling de ate 5s no servidor; `last_seen` e commitado no inicio do ping). Agente considerado online se `last_seen` < 180s
3. No horário agendado (ou quando flag `backup=true` no ping): executa backup completo
4. Após backup: `POST /api/v1/agent/backup/report` + `POST /api/v1/agent/backup/upload/{id}`
5. A cada hora (dentro do ciclo de ping): `GET /api/v1/agent/update-check` — verifica OTA

---

## 5. Banco de Dados

**SGBD:** PostgreSQL 15
**Driver:** psycopg2-binary
**ORM:** SQLAlchemy 2.0 (DeclarativeBase)
**Nome do banco:** `trilan_nvr`

### Tabelas

#### `clients`

| Coluna | Tipo SQL | Tipo Python | Nullable | Padrao |
|---|---|---|---|---|
| id | UUID | uuid.UUID | NOT NULL | gen_random_uuid() |
| name | VARCHAR(255) | str | NOT NULL | — |
| api_key_hash | VARCHAR(255) | str | NOT NULL | — |
| api_key_prefix | VARCHAR(20) | str | NOT NULL | — |
| backup_hour | INTEGER | int | NOT NULL | 2 |
| backup_minute | INTEGER | int | NOT NULL | 0 |
| zip_password | TEXT | str | NULL | — |
| email_to | ARRAY(VARCHAR) | List[str] | NOT NULL | [] |
| active | BOOLEAN | bool | NOT NULL | TRUE |
| last_seen | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NULL | — |
| last_backup_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NULL | — |
| last_backup_status | VARCHAR(20) | str | NULL | — |
| created_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NOT NULL | utcnow() |
| restart_requested | BOOLEAN | bool | NOT NULL | FALSE |
| backup_requested | BOOLEAN | bool | NOT NULL | FALSE |
| telemetry | JSON | dict | NULL | — (CPU/RAM/disco/rede/GPU enviados no ping) |

#### `nvrs` (tabela de equipamentos — nome mantido por compatibilidade)

| Coluna | Tipo SQL | Tipo Python | Nullable | Padrao |
|---|---|---|---|---|
| id | UUID | uuid.UUID | NOT NULL | gen_random_uuid() |
| client_id | UUID | uuid.UUID | NOT NULL | — |
| tipo | VARCHAR(20) | str | NOT NULL | 'NVR' |
| name | VARCHAR(255) | str | NOT NULL | — |
| ip | VARCHAR(50) | str | NOT NULL | — |
| username | VARCHAR(100) | str | NOT NULL | — |
| password | TEXT | str | NOT NULL | — |
| config_extra | JSON | dict | NULL | — |
| last_recording_status | JSON | list | NULL | — |
| last_telemetry_status | JSON | dict | NULL | — |
| active | BOOLEAN | bool | NOT NULL | TRUE |
| updated_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NULL | NOW() |

#### `backups`

| Coluna | Tipo SQL | Tipo Python | Nullable | Notas |
|---|---|---|---|---|
| id | UUID | uuid.UUID | NOT NULL | PK |
| client_id | UUID | uuid.UUID | NOT NULL | FK clients.id |
| started_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NULL | Calculado pelo servidor |
| finished_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NULL | Calculado pelo servidor |
| status | VARCHAR(20) | str | NOT NULL | OK / PARTIAL / ERROR |
| nvr_results | JSON | list | NULL | — |
| zip_filename | VARCHAR(255) | str | NULL | — |
| zip_size | BIGINT | int | NULL | Bytes totais |
| email_sent | BOOLEAN | bool | NOT NULL | FALSE |
| trigger | VARCHAR(50) | str | NOT NULL | scheduled / manual / manual_dashboard |
| created_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NOT NULL | utcnow() |

#### `agent_logs`

| Coluna | Tipo SQL | Tipo Python | Nullable | Notas |
|---|---|---|---|---|
| id | UUID | uuid.UUID | NOT NULL | PK |
| client_id | UUID | uuid.UUID | NOT NULL | FK clients.id CASCADE DELETE |
| event_type | VARCHAR(50) | str | NOT NULL | ping, backup_trigger, ping_recovery... |
| message | TEXT | str | NOT NULL | — |
| created_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NOT NULL | Max 50 logs por cliente |

#### `settings`

| Coluna | Tipo SQL | Nullable |
|---|---|---|
| key | VARCHAR(100) | NOT NULL (PK) |
| value | TEXT | NULL |

**Chaves:** `smtp_server`, `smtp_port`, `smtp_email`, `smtp_password`, `retention_days`, `admin_password_hash`

#### `agent_versions`

| Coluna | Tipo SQL | Tipo Python | Nullable | Notas |
|---|---|---|---|---|
| id | UUID | uuid.UUID | NOT NULL | PK |
| version | VARCHAR(20) | str | NOT NULL UNIQUE | Formato X.Y.Z |
| notes | TEXT | str | NULL | — |
| url_service | TEXT | str | NOT NULL | URL do TrilanAgentService.exe |
| url_tray | TEXT | str | NULL | URL do TrilanAgentTray.exe |
| sha256_service | VARCHAR(64) | str | NOT NULL | Hash lowercase |
| sha256_tray | VARCHAR(64) | str | NULL | Hash lowercase |
| active | BOOLEAN | bool | NOT NULL | FALSE = rollback emergência |
| created_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NOT NULL | utcnow() |

#### `customer_dashboards` (um dashboard por Cliente, `client_groups`)

| Coluna | Tipo SQL | Tipo Python | Nullable | Notas |
|---|---|---|---|---|
| id | UUID | uuid.UUID | NOT NULL | PK |
| customer_id | UUID | uuid.UUID | NOT NULL UNIQUE | FK `client_groups.id` ON DELETE CASCADE |
| layout | JSON | dict | NOT NULL | `{schema_version, filtros:{periodo}, widgets:[{id, tipo, titulo, largura, altura, config}]}` validado por `services/dashboards/layout.py` |
| version | INTEGER | int | NOT NULL | +1 a cada gravação do layout (409 em edição concorrente) |
| share_token_hash | VARCHAR(64) | str | NULL UNIQUE | SHA-256 do token do link; o token em texto puro nunca é gravado |
| share_enabled | BOOLEAN | bool | NOT NULL | Link ativo |
| share_expires_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NULL | Validade (UTC) |
| share_allow_edit | BOOLEAN | bool | NOT NULL | O visitante do link pode salvar o layout |
| share_created_at / last_viewed_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NULL | — |
| created_at / updated_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NOT NULL | utcnow() |

### Estratégia de Migração

> **O projeto NAO usa Alembic.**
> Migracoes sao feitas via `ALTER TABLE` inline no `main.py` na inicializacao,
> protegidas por verificacao de existencia de coluna.

Padrao obrigatorio:
```python
colunas = [col['name'] for col in insp.get_columns('tabela')]
if 'nova_coluna' not in colunas:
    conn.execute(text("ALTER TABLE tabela ADD COLUMN nova_coluna TIPO;"))
```

---

## 6. Regras Protegidas — Contratos Imutáveis

> Estas regras NAO podem ser alteradas sem analise explicita de impacto
> em toda a cadeia: Codigo -> ORM -> Banco -> API -> Frontend -> Agente

---

### REGRA-001 — Datetime Naive (sem timezone) no Banco

**Decisao:** Todas as colunas de data/hora no banco usam `TIMESTAMP WITHOUT TIME ZONE`.

**Tipo ORM:** `Column(DateTime)` — SEM `timezone=True`.

**Tipo Python:** `datetime` naive (sem `tzinfo`).

**Como popular:** Sempre usar `datetime.utcnow()`.

**PROIBIDO:**
```python
datetime.now(timezone.utc)   # retorna datetime AWARE — quebra o banco
datetime.now()               # retorna hora LOCAL — nao UTC
```

**CORRETO:**
```python
datetime.utcnow()            # naive em UTC — compativel com o banco
```

**Excecoes documentadas e permitidas:**
- `auth.py`: JWT usa `datetime.now(timezone.utc)` — nao e persistido no banco; exigido pelo `python-jose`
- `routers/agent.py` (ping_agent): comparacao de horario BRT em memoria apenas, nao persistida diretamente

**Impacto se violado:** Erro de tipo Python↔PostgreSQL ao persistir `datetime` aware em coluna `TIMESTAMP WITHOUT TIME ZONE`.

---

### REGRA-002 — Nome da Tabela de Equipamentos e `nvrs`

**Decisao:** A tabela chama-se `nvrs` no banco, mesmo suportando outros tipos.

**Motivo:** Compatibilidade com instalacoes existentes. Renomear seria migracao destrutiva.

**NAO FAZER:** Renomear para `equipamentos` ou qualquer outro nome no banco.

---

### REGRA-003 — Autenticacao Dupla (Admin vs Agente)

**Admin Dashboard:** JWT Bearer Token
- Header: `Authorization: Bearer <token>`
- Gerado via `POST /api/v1/auth/login` com `ADMIN_PASSWORD`
- Expira em `ACCESS_TOKEN_EXPIRE_HOURS` (padrao 8h), algoritmo `HS256`

**Agente Windows:** API Key + Client ID
- Headers: `X-Client-ID: <uuid>` + `X-API-Key: sk_trilan_<token>`
- Hash SHA-256 armazenado — chave raw nunca salva no banco
- Chave retornada UMA unica vez: na criacao do cliente

**NAO MISTURAR:** Nunca usar JWT para agentes, nem API Key para o dashboard.

---

### REGRA-004 — Criptografia de Senhas com Fernet

Senhas de equipamentos (`nvrs.password`) e senhas de ZIP (`clients.zip_password`)
sao criptografadas com Fernet antes de salvar no banco.

**Chave:** Variavel de ambiente `FERNET_KEY` (Base64-encoded, 32 bytes).

---

### REGRA-005 — Hora do Backup e Calculada pelo Servidor

`backups.started_at` e `backups.finished_at` sao calculados pelo **servidor** no momento
do recebimento do relatorio, nao pelo cliente.

```python
server_finished_at = datetime.utcnow()
duration = body.finished_at - body.started_at  # duracao relatada pelo cliente
server_started_at = server_finished_at - duration
```

**Motivo:** O relogio do cliente Windows pode estar errado.

---

### REGRA-006 — Limite de 50 Logs por Cliente

O sistema mantem no maximo 50 logs por cliente na tabela `agent_logs`.
Ao inserir novo log, os mais antigos sao deletados automaticamente se count > 50.

---

### REGRA-007 — Migracoes Inline (sem Alembic)

Toda nova coluna ou tabela: `ALTER TABLE` / `CREATE TABLE IF NOT EXISTS` no `main.py`,
dentro do bloco protegido por `try/except` e verificacao de existencia previa.

**NAO FAZER:** Introduzir Alembic, migrations automaticas destrutivas, ou `drop_all`.

---

### REGRA-008 — SHA-256 dos EXEs sempre em lowercase

Hash SHA-256 na tabela `agent_versions` e sempre armazenado em **lowercase**.
O agente tambem compara em lowercase. Inconsistencia de case = falha na validacao.

---

### REGRA-009 — Versao do Agente usa formato X.Y.Z

Comparacao de versoes usa `tuple(int(x) for x in v.split("."))`.

**NAO FAZER:** Sufixos (`1.0.6-beta`, `1.0.6.1`), letras, ou qualquer formato diferente de `X.Y.Z`.

---

## 7. Autenticação e Segurança

### Fluxo JWT (Admin)

```
POST /api/v1/auth/login { "password": "..." }
    -> 200 { "access_token": "...", "token_type": "bearer" }

Requisicoes protegidas:
    Authorization: Bearer <access_token>
```

### Fluxo API Key (Agente)

```
X-Client-ID: <uuid-do-cliente>
X-API-Key: sk_trilan_<token>
```

API Key gerada com `secrets.token_urlsafe(32)` prefixada com `sk_trilan_`.

### Fluxo do link público do Dashboard (token de compartilhamento)

```
X-Dashboard-Token: dsh_<token>      (somente nas rotas /api/v1/public/dashboard/*)
```

- Token com `secrets.token_urlsafe(32)` (256 bits) e prefixo `dsh_`; só o hash SHA-256 fica no banco e o token aparece **uma única vez**, ao gerar. Gerar de novo invalida o anterior; revogar apaga.
- O link é `/d#<token>`: o token vai no **fragmento da URL**, que o navegador não envia ao servidor (fora de logs do nginx/proxy). A página `/d` usa um cliente HTTP próprio, sem o JWT do painel, e o nginx do dashboard responde `/d` com `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex` e `Cache-Control: no-store`.
- Token inexistente, desativado, expirado ou de cliente inativo → o mesmo `404` genérico. Limites em memória por IP (válidos para 1 worker uvicorn): 240 requisições/min e 10 tentativas inválidas/5 min (depois `429`).
- Isolamento: o token resolve para um único `customer_id` e todas as consultas são filtradas por ele; ids de máquina/equipamento guardados no layout são validados contra o cliente ao salvar (422) e ignorados na leitura. A resposta pública usa listas brancas de campos: sem IPs, usuários, senhas, `config_extra` ou chaves de API.
- O token **não** abre nenhuma rota administrativa (`verify_admin_token` continua exigindo o JWT). Editar o layout pelo link exige `share_allow_edit` e só altera `layout`/`version`, nunca o compartilhamento.

---

## 8. Contratos de API

**Prefixo base:** `/api/v1`
**Documentacao interativa:** `/api/docs` (Swagger UI)

### Endpoints do Agente (X-Client-ID + X-API-Key)

| Metodo | Path | Descricao |
|---|---|---|
| GET | `/api/v1/agent/config` | Retorna configuracao completa do cliente |
| POST | `/api/v1/agent/ping` | Heartbeat; body opcional `{"telemetry": {...}}`; retorna flags `restart` e `backup` |
| POST | `/api/v1/agent/backup/report` | Agente reporta resultado do backup |
| POST | `/api/v1/agent/backup/upload/{backup_id}` | Agente faz upload do ZIP (limite `MAX_UPLOAD_MB`, 413 acima) |
| GET | `/api/v1/agent/update-check` | Verifica se ha nova versao OTA (maior versao ativa) |
| POST | `/api/v1/agent/rtsp-result` | Agente devolve o resultado da tarefa RTSP do dashboard |
| POST | `/api/v1/agent/nvr-cameras/night-image` | Agente envia a imagem da noite de um canal |

### Endpoints de Admin (Bearer Token)

| Metodo | Path | Descricao |
|---|---|---|
| POST | `/api/v1/auth/login` | Login — retorna JWT |
| GET/POST | `/api/v1/machines` | Listar (filtros `customer_id`, `unassigned`) / criar máquina (`customer_id` opcional) |
| GET/PUT/DELETE | `/api/v1/machines/{id}` | Detalhar/atualizar/deletar máquina |
| POST | `/api/v1/machines/{id}/rotate-key` | Rotacionar API key |
| POST | `/api/v1/machines/{id}/trigger-backup` | Solicitar backup manual |
| POST | `/api/v1/machines/{id}/restart-agent` | Solicitar reinicio do agente |
| POST | `/api/v1/machines/trigger-backup-all` · `/restart-agent-all` | Ação em massa nas máquinas online (`{queued, skipped_offline}`) |
| GET | `/api/v1/machines/{id}/logs` | Listar logs do agente |
| GET/POST | `/api/v1/machines/{id}/equipamentos` | Listar/criar equipamentos da máquina |
| GET/PUT/DELETE | `/api/v1/machines/{id}/equipamentos/{eq_id}` | Gerenciar equipamento |
| POST | `/api/v1/machines/{id}/equipamentos/{eq_id}/test-rtsp` | Tarefa RTSP via agente (409 se já houver uma pendente) |
| GET | `/api/v1/machines/{id}/equipamentos/{nvr_id}/cameras` | Galeria do NVR (une `nvr_cameras` + `last_recording_status`) |
| POST | `/api/v1/machines/{id}/equipamentos/{nvr_id}/cameras/perfect-image` | Salvar imagem de referência |
| GET/POST | `/api/v1/clients` | Listar/criar Clientes (customers.py) |
| GET/PUT/DELETE | `/api/v1/clients/{id}` | Gerenciar Cliente |
| POST | `/api/v1/clients/{id}/trigger-backup` · `/cancel-queue` | Fila sequencial de backup do Cliente |
| POST/DELETE | `/api/v1/clients/{id}/machines/{machine_id}` | Vincular (herda horário) / remover máquina do Cliente (409 com fila ativa) |
| PUT | `/api/v1/clients/{id}/queue-order` | Ordem da fila `{machine_ids:[...]}` (arrastar e soltar; 409 com fila ativa) |
| GET | `/api/v1/clients/{id}/runs` | Rodadas de backup do Cliente (1 e-mail por rodada) |
| GET | `/api/v1/clients/{id}/runs/{run_id}/download` | ZIP unificado da rodada (uma pasta por máquina) |
| POST | `/api/v1/clients/{id}/runs/{run_id}/resend-email` | Reenviar e-mail da rodada (409 se aberta) |
| GET | `/api/v1/clients/{id}/download-latest` | ZIP unificado do último backup do Cliente |
| GET | `/api/v1/dashboards/widgets` | Catálogo dos tipos de widget (rótulo, tamanho padrão, schema da config) |
| GET/PUT | `/api/v1/clients/{id}/dashboard` | Ler (cria o padrão) / salvar o layout `{layout, version}` (409 = versão antiga; 422 = layout ou referência inválida) |
| POST | `/api/v1/clients/{id}/dashboard/restore-default` · `/preview` | Restaurar o layout padrão / dados de um rascunho sem gravar |
| GET | `/api/v1/clients/{id}/dashboard/data` · `/opcoes` | Dados dos widgets do layout salvo / máquinas e equipamentos do cliente para configurar |
| POST/PUT/DELETE | `/api/v1/clients/{id}/dashboard/share` | Gerar/regenerar o link (token devolvido uma vez) / ativar, validade, permissão de edição / revogar |
| GET | `/api/v1/public/dashboard` · `/data` | Dashboard e dados pelo link (`X-Dashboard-Token`; 404 genérico, 429 por limite) |
| GET/POST/PUT | `/api/v1/public/dashboard/opcoes` · `/preview` · `/layout` | Só com permissão de edição do link (403 sem ela) |
| GET | `/api/v1/backups` | Listar backups (paginado; filtros `machine_id`, `customer_id`) |
| GET | `/api/v1/backups/{id}/download` | Download de ZIP (admin) |
| GET | `/api/v1/backups/public-download/{id}` | Download público por link de e-mail (sem auth; ver riscos abertos) |
| GET | `/api/v1/backups/public-run-download/{run_id}` | ZIP unificado da rodada pelo link do e-mail do Cliente (mesmo modelo do public-download) |
| POST | `/api/v1/backups/{id}/resend-email` | Reenviar e-mail do backup |
| GET/PUT | `/api/v1/settings` | Configuracoes do sistema |
| POST | `/api/v1/admin/agent-version` | Registrar nova versao OTA |
| GET | `/api/v1/admin/agent-version` | Listar versoes OTA |
| PUT | `/api/v1/admin/agent-version/{id}/toggle` | Ativar/desativar versao |
| PUT | `/api/v1/admin/agent-version/{id}` | Editar versao |
| DELETE | `/api/v1/admin/agent-version/{id}` | Deletar versao |
| GET | `/api/v1/stats` | Estatisticas do dashboard |
| GET | `/api/health` | Health check |

### Contrato do Response `GET /api/v1/agent/update-check`

**Com update:**
```json
{
  "has_update": true,
  "version": "1.1.4",
  "url_service": "https://github.com/.../TrilanAgentService.exe",
  "url_tray": "https://github.com/.../TrilanAgentTray.exe",
  "sha256_service": "<64 chars hex lowercase>",
  "sha256_tray": "<64 chars hex lowercase>",
  "notes": "..."
}
```

**Sem update:** `{ "has_update": false }`

`url_tray` e `sha256_tray` sao **opcionais** — o agente deve tolerar `null`.

---

## 9. Agente Windows

### Arquivos Compilados

| Arquivo | Fonte | Responsabilidade |
|---|---|---|
| `TrilanAgentService.exe` | `service.py` | Windows Service — executa backups |
| `TrilanAgentTray.exe` | `tray.py` | Icone na bandeja — controle visual |

### Servico Windows

- **Nome:** `TrilanAgentNVR`
- **Display name:** `Trilan — Agente Backup NVR`
- **Diretorio de instalacao:** `C:\Program Files (x86)\Trilan NVR Backup Agent\`
- **Diretorio de logs:** `C:\ProgramData\Trilan NVR Backup Agent\logs\servico.log`
- **Config file:** `agent.conf` (mesmo diretorio do exe)

### Formato de `agent.conf`

```ini
[server]
url = https://servidor.exemplo.com
client_id = <uuid>
api_key = sk_trilan_<token>
```

### Comunicacao Inter-processo (Service <-> Tray)

O Tray dispara backup manual via Win32 Named Event:
- **Nome do evento:** `Global\TrilanAgentNVR_RunNow`
- O Service escuta com `win32event.WaitForMultipleObjects`

### NVR Factory — Ordem de Detecao de Tipo

```
1. buscar_cameras_nvr (Hikvision IP)
2. buscar_cameras_dvr (Hikvision Analogico)
3. Se ambos -> NVR Hibrido (mescla os dois dicionarios) -> tipo "NVR"
4. Se so NVR -> tipo "NVR"
5. Se so DVR -> tipo "DVR"
6. buscar_cameras_motorola -> tipo "MOTOROLA"
7. Nenhum -> tipo "DESCONHECIDO"
```

---

## 10. Sistema OTA (Over The Air Update)

### Fluxo Completo

1. Admin faz build dos novos `.exe` localmente via PyInstaller
2. Admin sobe os `.exe` para GitHub Releases
3. Admin copia SHA-256 e URLs e cadastra no Dashboard (Settings -> Gerenciador OTA)
4. Agentes detectam nova versao na proxima verificacao (a cada hora)
5. Agente baixa `TrilanAgentService.exe` (obrigatorio) e `TrilanAgentTray.exe` (opcional)
6. Agente valida SHA-256
7. Agente executa `.bat` detached que para o servico, mata o Tray (se houver update de Tray), substitui os `.exe` e reinicia

### Campos OTA

| Campo | Obrigatorio | Notas |
|---|---|---|
| `url_service` | Sim | URL do TrilanAgentService.exe |
| `sha256_service` | Sim | Hash SHA-256 em lowercase |
| `url_tray` | Nao | Se null, o Tray nao e atualizado |
| `sha256_tray` | Nao | Obrigatorio se url_tray for preenchido |

### Compatibilidade de Versoes

- Agentes `<=1.0.5`: so atualizam o Service (sem suporte a Tray OTA)
- Agentes `>=1.0.6`: suportam atualizacao de ambos via OTA

---

## 11. Infraestrutura e Deploy

### Producao (Dokploy)

- **Porta exposta:** `7001` (Nginx)
- **Proxy:** `/api/*` -> FastAPI (porta 8000), `/*` -> Dashboard (porta 80)
- **Backups:** Volume bind mount em `/opt/trilan/backups` no host
- **Banco:** PostgreSQL interno via rede Docker `trilan_net`
- **Plataforma:** Dokploy (auto-deploy via git push)

### Branches Git

| Branch | Repositorio | Proposito |
|---|---|---|
| `isaque` | `projetoswmfa/trilan-backup-automation` | Desenvolvimento principal |
| `integracao-equipamentos` | `isaqueschaffer/backup-automation` | Producao (deploy automatico Dokploy) |

### Regra de Push Duplo

Todo commit deve ser propagado para AMBOS os repositorios:
```bash
git push origin isaque
git push https://github.com/isaqueschaffer/backup-automation.git isaque:integracao-equipamentos
```

**Excecao:** Branches de features externas (ex: `helena`) NAO devem ir para `integracao-equipamentos` sem auditoria de merge.

---

## 12. Variáveis de Ambiente

### Obrigatórias

| Variavel | Descricao |
|---|---|
| `DATABASE_URL` | URL de conexao PostgreSQL |
| `SECRET_KEY` | Assinatura JWT (32 bytes hex) |
| `FERNET_KEY` | Criptografia Fernet (base64 32 bytes) |
| `ADMIN_PASSWORD` | Senha do painel admin |
| `POSTGRES_DB` | Nome do banco |
| `POSTGRES_USER` | Usuario do banco |
| `POSTGRES_PASSWORD` | Senha do banco |

### Opcionais

| Variavel | Padrao | Descricao |
|---|---|---|
| `ACCESS_TOKEN_EXPIRE_HOURS` | `8` | Expiracao do JWT |
| `CORS_ORIGINS` | `""` | Origens permitidas (separadas por virgula) |
| `BACKUP_STORAGE_PATH` | `/data/backups` | Diretorio de armazenamento de ZIPs |
| `PUBLIC_URL` | None | URL publica do servidor |
| `SMTP_SERVER` | None | Servidor SMTP |
| `SMTP_PORT` | `587` | Porta SMTP |
| `SMTP_EMAIL` | None | E-mail remetente |
| `SMTP_PASSWORD` | None | Senha do e-mail |

---

## 13. Tipos de Equipamento Suportados

| Tipo | Valor em nvrs.tipo | Integracao | Protocolo |
|---|---|---|---|
| NVR IP (Hikvision) | NVR | src/nvr/hikvision/ | HTTP ISAPI |
| DVR Analogico (Hikvision) | DVR | src/nvr/hikvision/ | HTTP ISAPI |
| NVR Hibrido (Hikvision) | NVR | src/nvr/factory.py | HTTP ISAPI |
| Motorola (NVMS-9000) | MOTOROLA | src/nvr/motorola/ + camera/rtsp_client.py | HTTP + RTSP (`chID=N`); imagem da noite via `queryChlRecLog` |
| OLT (Huawei, UNM2000, V-SOL) | OLT | src/olt/ (huawei_active, unm2000, vsol) | SSH Paramiko |
| ONU | ONU | — | — |
| PABX | PABX | src/pabx/ | — |
| Mikrotik | MIKROTIK | src/mikrotik/routeros.py | SSH/SFTP |
| Digifort | DIGIFORT | src/application/webhook_digifort.py + tools/agente_digifort.py | Webhook/SNMP |
| Intelbras Defense | DEFENSE | src/vms/defense.py | API / HTTP |
| Misto / Custom | MIXED | — | — |
| Câmera IP (Teste RTSP)| CAMERA | server/api/routers/equipamentos.py + agent.py (`/rtsp-result`), agent/src/camera/rtsp_client.py | RTSP (TCP) |

---

## 14. Decisões Arquiteturais (ADRs)

### ADR-001 — Datetime Naive para Banco de Dados

**Data:** 2025 | **Status:** ATIVO E PROTEGIDO

**Decisao:** Usar `datetime.utcnow()` (naive) para todas as datas persistidas no banco.

**Motivo:** PostgreSQL `TIMESTAMP WITHOUT TIME ZONE` e incompativel com `datetime` aware.
A migracao para `TIMESTAMP WITH TIME ZONE` foi tentada, causou erros 500 em producao
(incompatibilidade com dados existentes e lock de banco no Dokploy), e foi revertida.

**Regra:** `datetime.utcnow()` e obrigatorio para insercoes. `datetime.now(timezone.utc)` so
permitido em contextos que nao persistem no banco (JWT em auth.py, comparacoes em memoria).

---

### ADR-002 — Tabela `nvrs` mantem o nome original

**Data:** 2025 | **Status:** ATIVO E PROTEGIDO

**Decisao:** Nao renomear `nvrs` para `equipamentos` no banco.

**Motivo:** Clientes em producao possuem dados na tabela. Migracao destrutiva = risco de perda de dados.

---

### ADR-003 — Migracoes Inline sem Alembic

**Data:** 2025 | **Status:** ATIVO E PROTEGIDO

**Decisao:** `ALTER TABLE` condicional no `main.py` ao inves de Alembic.

**Motivo:** Simplicidade operacional. Sem pipeline CI/CD que execute `alembic upgrade head` antes do deploy.

---

### ADR-004 — OTA via Batch Script Detached

**Data:** Outubro 2026 | **Status:** ATIVO

**Decisao:** Atualizacao OTA usa `.bat` rodando com `DETACHED_PROCESS` para substituir os proprios `.exe`.

**Motivo:** No Windows, um processo nao pode substituir seu proprio executavel enquanto esta rodando.

---

### ADR-005 — Versao 1.0.6 introduz OTA para o Tray

**Data:** 07/10/2026 | **Status:** ATIVO

**Decisao:** A partir da versao 1.0.6, o OTA suporta atualizacao opcional do `TrilanAgentTray.exe`.

**Campos novos:** `url_tray` e `sha256_tray` (ambos opcionais na API).

**Retrocompatibilidade:** Agentes `<=1.0.5` ignoram os novos campos silenciosamente.

---

### ADR-006 — Rollback do Merge com Branch `helena`

**Data:** 07/10/2026 | **Status:** HISTORICO

**Decisao:** Merge da branch `helena` revertido via `git reset --hard da6dc80`.

**Motivo:** A branch introduziu `datetime.now(timezone.utc)` causando erros 500 em producao
por incompatibilidade de tipo com o banco de dados existente.

**Licao:** Qualquer alteracao de tipo de coluna datetime e CRITICA e exige analise
de dados existentes, rollout gradual e plano de rollback.

### ADR-007 — Nomenclatura: Cliente (empresa) e Máquina (computador com agente)

**Data:** 13-14/10/2026 | **Status:** VIGENTE

**Decisao:** Cliente = empresa atendida (`Customer`, tabela `client_groups`, API `/api/v1/clients`, painel `/clientes`).
Máquina = computador com o agente (`Machine`, tabela `clients`, API `/api/v1/machines`, painel `/maquinas`).
Equipamento = NVR/OLT/etc. da máquina. Hierarquia Cliente → Máquinas → Equipamentos; máquina tem no máximo um cliente.
Tabelas e colunas do banco NÃO foram renomeadas (sem migração): o ORM mapeia `customer_id` → coluna `group_id` e
`machine_id` → coluna `client_id`. As rotas `/api/v1/agent/*`, os headers `X-Client-ID`/`X-API-Key` e o JSON trocado com
o agente não mudaram. Termos "Unidade" e "grupo" foram eliminados da interface.

**Regras:** máquina vinculada usa o horário do cliente (copiado ao vincular e quando o cliente muda o horário; PUT da
máquina com outro horário = 400). Vínculo e ordem da fila só pelas rotas do cliente. O painel antigo (`/units`,
`/clients`, `/clients/:id`) redireciona para as rotas novas.

**Licao:** Ao renomear rota, grep por todos os caminhos no dashboard, não só em `api/client.ts`.

---

### ADR-008 — Binários e artefatos não são versionados

**Data:** 13/10/2026 | **Status:** VIGENTE

**Decisao:** `agent/dist/` (EXEs), `__pycache__/`, dumps `*.sql`, `scratch_test/` e `.claude/` ficam fora do git. Os EXEs vão por upload
no OTA Manager (GitHub Release). Utilitários avulsos ficam em `tools/`; código legado em `archive/`.

**Motivo:** Os EXEs (~50 MB cada, várias versões) inflaram o histórico para ~150 MB e o clone do Dokploy levava minutos.
O histórico antigo ainda contém esses blobs e alguns segredos; reescrevê-lo (`git filter-repo` + force-push nos dois remotes)
é decisão pendente do dono.

---

## 15. Incompatibilidades Conhecidas

| ID | Componente | Incompatibilidade | Status |
|---|---|---|---|
| IC-001 | PostgreSQL + SQLAlchemy | datetime aware em coluna TIMESTAMP WITHOUT TIME ZONE | Contornado via REGRA-001 |
| IC-002 | PyInstaller + pystray | SyntaxWarning: return in a finally block | Inofensivo, warning apenas |
| IC-003 | PyInstaller + pycparser | pycparser.lextab e yacctab nao encontrados | Inofensivo, warning apenas |
| IC-004 | OTA Tray em agentes <=1.0.5 | Agentes antigos nao tem logica de download/substituicao do Tray | Conhecido e aceito |
| IC-005 | agent_update.py edit_version | PUT /api/v1/admin/agent-version/{id} nao aceitava url_tray e sha256_tray | Resolvido (schema `AgentVersionUpdate` inclui os campos; `Settings.tsx` usa `editAgentVersion` do `client.ts`) |
| IC-006 | Dashboard `/auth` + JWT | Token em `localStorage` (risco de XSS) | Aceito; mitigação futura: cookie httpOnly |
| IC-007 | `backups/public-download/{id}` | Link público sem expiração enviado por e-mail; o UUID é o único segredo | ABERTO — decisão do dono (token assinado com expiração) |
| IC-008 | OTA (`updater.py`) | Só integridade (SHA-256), sem assinatura do EXE; `https://` é exigido | ABERTO — decisão do dono (Authenticode ou allowlist de host) |
| IC-009 | `api_client.py` | `verify=False` em todas as chamadas ao servidor, inclusive o ping com a API key | ABERTO — decisão do dono |
| IC-010 | `pending_rtsp_tasks` | Estado em memória do processo: exige 1 worker uvicorn | Documentado; multi-worker pede Redis/tabela |
| IC-011 | Rotas `/clients` e `datetime.now(timezone.utc)` | `check_client_online`/`current_server_time` usam datetime aware, sem gravar no banco | Exceção documentada à REGRA-001 (nunca gravar) |
| IC-012 | Credencial padrão `navarro@123` | Ainda usada como fallback em `rtsp_client.py`, `equipamentos.py`, `schemas.py` e no dashboard | ABERTO — decisão do dono (muda o comportamento do teste RTSP) |

---

## 16. Architecture Changelog

### [2026-10-22] — Telemetria de NVR: Tráfego e Interfaces de Rede (Hikvision e Intelbras) e Total de RAM

**Alteração:**
1. **Rede nos Gravadores:** A telemetria de NVR/DVR passa a incluir interfaces de rede (`telemetry.networks`), status (UP/DOWN), MAC, IP, velocidade negociada e consumo de banda em tempo real (Recebimento/Download das câmeras e Envio/Upload para visualização).
   - **Hikvision (ISAPI):** Consulta `ISAPI/System/Network/statistics` (taxa de entrada e saída em kbps/Mbps) e `ISAPI/System/Network/interfaces` (detalhes da NIC, IP, MAC e velocidade).
   - **Intelbras (SNMP):** Consulta a MIB padrão `IF-MIB` (`1.3.6.1.2.1.2.2.1` e `1.3.6.1.2.1.31.1.1.1`) para identificar interfaces ativas, MAC, velocidade (100M/1G) e calcula taxa instantânea de tráfego (Mbps) via amostragem de octetos.
2. **Total de RAM:** Corrigido o cálculo de RAM do Hikvision (ISAPI retorna em MB e não em percentual; agora calcula `(uso / (uso + disp)) * 100`). O total de memória (`ram_total_gb`) e uso (`ram_used_gb`) agora são informados tanto na Hikvision quanto na Intelbras, exibindo no card principal o percentual acompanhado da capacidade física (ex.: `44% de 1,1 GB` e legenda `0,5 GB em uso`).
3. **Modal e Painel:** `NVRTelemetryModal.tsx` exibe os cards das placas de rede com setas de recebimento/envio em Mbps, MAC e badges de status/velocidade, além do total de RAM.
4. **Correções no Agente:** Adicionado `"telemetria": r.get("telemetria")` no payload de `post_report()` em `api_client.py` (antes descartado ao enviar ao servidor) e correção em `gerar_secretkey()` (`crypto.py`) para clientes sem `zip_password`.
**Arquivos:** agent/src/nvr/hikvision/telemetry.py, agent/src/nvr/intelbras/telemetry.py, agent/src/application/api_client.py, agent/src/backup/crypto.py, server/api/services/dashboards/widgets.py, server/dashboard/src/api/types.ts, server/dashboard/src/components/StatusBadge.tsx, server/dashboard/src/pages/Machines/MachineDetail/components/NVRTelemetryModal.tsx, server/dashboard/src/pages/Machines/MachineDetail/components/ServerHealthCard.tsx, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** helena

### [2026-10-23] — Telemetria de NVRs Motorola (CPU, RAM, Discos e Rede)

**Alteração:** Suporte a coleta de telemetria em gravadores Motorola (arquitetura NVMS-9000 / TVT):
1. Script de diagnóstico e dump (`teste backup motorola/dump_motorola_telemetria.py`): baseado no padrão do `dump_motorola_cameras.py`, conecta via NVMS-9000 (`reqLogin`/`doLogin` com SHA-512 ou Base64), testa envelopes gerais e com `requireField` para armazenamento (`queryDiskStatus`, `queryDiskDetailInfo`, `queryStorageCapacity`), CPU/RAM (`queryCpuStatus`, `queryMemoryStatus`, `queryDevStatus`) e rede (`queryNetCfg`, `queryNetStatus`), salvando os XMLs brutos em `respostas_telemetria_<ip>/` e exibindo o resumo consolidado e o JSON formatado.
2. Agente (`agent/src/nvr/motorola/telemetry.py`): novo módulo `coletar_telemetria_motorola` extrai CPU (`%`), RAM (`%`, total e usado em GB), tabela de discos (identificador, status normalizado para o `StatusBadge`, percentual de uso, capacidade total e livre em GB) e interfaces de rede (nome, status UP/DOWN, IP, MAC, velocidade e taxas de envio/recebimento).
3. Despacho no `agent/src/nvr/factory.py`: `coletar_telemetria_nvr()` roteia para `coletar_telemetria_motorola` quando `marca == "MOTOROLA"` ou `tipo_nvr == "MOTOROLA"`, integrando diretamente à tela de telemetria (`NVRTelemetryModal`) e aos widgets de gravadores sem exigir mudanças no backend ou frontend.
**Arquivos:** agent/src/nvr/motorola/telemetry.py, agent/src/nvr/factory.py, teste backup motorola/dump_motorola_telemetria.py, teste backup motorola/dump_motorola_cameras.py, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** helena

### [2026-10-21] — Agente 1.1.18: Telemetria de NVR Intelbras via SNMP

**Alteração:** NVR com `config_extra.marca = "Intelbras"` agora coleta telemetria por SNMPv2c (porta 161, community "Public" por padrão, configurável em `config_extra.snmp_community`) em vez de ISAPI: novo `agent/src/nvr/intelbras/telemetry.py` (`coletar_telemetria_intelbras`, usando `pysnmp.hlapi.asyncio`) lê RAM (`%` de uso, OID da MIB proprietária Intelbras) e a tabela de HDs (dispositivo, status, capacidade e livre em GB), traduzindo o status (Normal/Error/Abnormal/...) para os rótulos do `StatusBadge`. Sem OID de CPU na MIB Intelbras — o card mostra "—" nesse campo, igual a qualquer equipamento sem o dado. `factory.coletar_telemetria_nvr()` passa a receber `marca`/`snmp_community` e rotear para SNMP (Intelbras) ou ISAPI (Hikvision e demais); `buscar_cameras()` trata `marca="Intelbras"` como `"HIKVISION"` (câmeras/gravações continuam via ISAPI, que os NVRs Intelbras também falam). O resultado tem o mesmo formato do Hikvision (`cpu_percent`/`ram_percent`/`disks`), então `NVRTelemetryModal` exibe os dois fabricantes sem nenhuma mudança de frontend. Novo seletor "Intelbras" na Marca do NVR (`EquipamentoFormModal.tsx`, antes agrupado em "Hikvision / Intelbras / Outros"). Build: `pysnmp` no `requirements.txt` e `--collect-all pysnmp`/`--collect-all pyasn1` no `build.ps1` (MIBs e módulos carregados dinamicamente, precisam ser coletados à parte pelo PyInstaller).
Integração (merge em isaque): a dependência foi fixada em `pysnmp>=7.1,<8.0.0` — com a faixa original (`>=6.1.2,<7`) o pip instalava a 6.2.6, que não tem `get_cmd`/`walk_cmd` (`ImportError`), o que derrubaria o processamento de NVRs; o módulo foi validado contra um simulador SNMP (RAM, discos e status; community errada devolve `None`) com pysnmp 7.1.30 em Python 3.12 e 3.14. O import em `factory.py` passou a ser protegido (`try/except`): falha do pysnmp desativa só a telemetria Intelbras e nunca o backup. Versão do agente 1.1.18.
**Arquivos:** agent/src/nvr/intelbras/telemetry.py, agent/src/nvr/intelbras/__init__.py, agent/src/nvr/factory.py, agent/src/application/backup_job.py, agent/requirements.txt, agent/build.ps1, server/dashboard/src/pages/Machines/MachineDetail/components/EquipamentoFormModal.tsx, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** helena, isaque

### [2026-10-21] — Dashboards por Cliente: redimensionar com o mouse e conteúdo adaptável (rodada B)

**Alteração:** Em modo de edição cada componente ganha alças (borda direita, borda inferior e canto) para redimensionar com o mouse como uma janela, com encaixe na grade (colunas de 1/12 da largura e linhas de 50px), tamanho mínimo por tipo de widget, etiqueta "N col × M lin" durante o arrasto e atualização ao vivo do layout; "Largura total" e "Ajustar ao conteúdo" (também por duplo clique no canto) substituem os seletores de ¼/½. O conteúdo dos componentes se reorganiza conforme a área (quebra de linha, grades `auto-fit`, gráfico do histórico desenhado no tamanho real) e, no limite, rola dentro do quadro: nenhuma informação é cortada. O componente "Saúde do servidor" passou a mostrar sempre "Atualizado há …" (o servidor envia `segundos_desde_contato` e o tempo continua envelhecendo no navegador) e "Aguardando a primeira comunicação" quando a máquina nunca se comunicou; `iso()` deixou de gerar datas com fuso duplicado.
**Arquivos:** server/dashboard/src/pages/Dashboards/DashboardCanvas.tsx, WidgetAcoesEdicao.tsx, DashboardWorkspace.tsx, WidgetFrame.tsx, types.ts, widgets/*, server/dashboard/src/index.css, server/api/services/dashboards/widgets.py
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-21] — Dashboards por Cliente: tamanho livre dos componentes e pizza de status dos NVRs (rodada A)

**Alteração:** O tamanho dos componentes deixa de ser fixo: `largura` vale 2 a 12 colunas e `altura` 1 a 40 linhas de 50px (antes 1–4 linhas de 150px). Layouts antigos (`schema_version` 1) são convertidos na leitura (altura × 3) para `schema_version` 2, sem tocar no banco até o próximo salvamento. Cada tipo de widget ganha tamanho mínimo no front (`larguraMin`/`alturaMin`) para o conteúdo não quebrar. Novo widget `status_nvr` ("Status dos NVRs (pizza)"): gráfico de pizza SVG da situação das câmeras de cada NVR (gravando, sem gravação, offline, não verificado) com cores fixas por status, uma pizza por NVR ou uma agregada; reaproveita `last_recording_status` e a lista branca de campos/isolamento por cliente (`ids_referenciados` cobre a chave `equipamentos` do novo tipo).
**Arquivos:** server/api/services/dashboards/layout.py, widgets.py, server/dashboard/src/pages/Dashboards/types.ts, useElementSize.ts, PieChart.tsx, widgets/StatusNvrWidget.tsx, widgets/registry.tsx, server/dashboard/src/index.css
**Breaking Change:** Não (layouts antigos são convertidos na leitura).
**Branch:** isaque

### [2026-10-21] — Dashboards por Cliente: componente "Gravadores" e indicadores de disco no Resumo

**Alteração:** A telemetria dos NVR/DVR Hikvision (`nvrs.last_telemetry_status`: CPU, RAM e discos) passa a alimentar o dashboard do Cliente. Novo tipo de widget `telemetria_equipamentos` ("Gravadores (CPU, RAM e discos)": anéis de CPU/RAM, status e ocupação de cada disco, alerta quando o disco tem status diferente de OK/REPOUSO ou ocupação >= 90%, filtro de gravadores e opção "apenas com problema") e três indicadores novos no Resumo (`gravadores_com_telemetria`, `discos_total`, `discos_com_problema`; os tiles de disco só aparecem se houver telemetria). A resposta usa lista branca de campos (sem IP, usuário, senha ou `config_extra`) e o isolamento por cliente cobre a chave `equipamentos` do novo widget (`ids_referenciados`). Nenhuma mudança no agente nem no banco.
**Arquivos:** server/api/services/dashboards/widgets.py, server/api/services/dashboards/layout.py, server/dashboard/src/pages/Dashboards/types.ts, widgets/TelemetriaEquipamentosWidget.tsx, widgets/registry.tsx, widgets/ResumoWidget.tsx, WidgetConfigModal.tsx
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-21] — Telemetria de NVR Hikvision (CPU/RAM/Discos) e status no painel

**Alteração:** (1) Agente: novo `src/nvr/hikvision/telemetry.py` (`coletar_telemetria_hikvision`) lê `ISAPI/System/status` (CPU/RAM) e `ISAPI/ContentMgmt/Storage/hdd` (discos: capacidade, livre, status) de NVR/DVR Hikvision, convertendo MB→GB e calculando o percentual de uso de cada disco; `factory.py` expõe `coletar_telemetria_nvr()`, que só roda para `tipo_nvr` `NVR`/`DVR` (Motorola retorna `None`). `backup_job.processar_nvr` inclui o resultado em `"telemetria"` no retorno do backup. (2) API: `NVRResult.telemetria` (relatório do agente) grava em `NVR.last_telemetry_status` (coluna JSON nova, migração inline em `main.py`); exposta em `NVRResponse.last_telemetry_status`. (3) Painel: botão "Telemetria" no card de equipamento NVR (`EqCard.tsx`) abre `NVRTelemetryModal.tsx`, reaproveitando `MetricTile`/`PctBar` (CPU, RAM) e `StatusBadge` (status de cada disco: OK, Erro, Não Inicializado, Não Formatado, Repouso, Desconhecido — novas entradas no mapa de `StatusBadge.tsx`) e `fmtGb`/`fmtPct` de `telemetry.ts`. Sem dado (equipamento não-Hikvision ou offline na última coleta): modal mostra "Sem dados de telemetria disponíveis.".
**Arquivos:** agent/src/nvr/hikvision/telemetry.py, agent/src/nvr/factory.py, agent/src/application/backup_job.py, server/api/schemas.py, server/api/models.py, server/api/main.py, server/api/routers/agent.py, server/dashboard/src/api/types.ts, server/dashboard/src/components/StatusBadge.tsx, server/dashboard/src/pages/Machines/MachineDetail/components/NVRTelemetryModal.tsx, server/dashboard/src/pages/Machines/MachineDetail/components/EqCard.tsx, server/dashboard/src/pages/Machines/MachineDetail/index.tsx, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** helena, isaque

### [2026-10-21] — Agente 1.1.17: Suporte Completo a Câmeras IP Motorola / ONVIF (MTIDM022603)

**Alteração:** (1) Agente (`rtsp_client.py`): Diferenciação entre NVRs Motorola multiplexados (NVMS-9000, que usam `/chID=N&streamType=main`) e câmeras IP standalone Motorola / ONVIF Profile S (como a Dome 2MP `MTIDM022603`), que passam a tentar as URLs padrão `/profile1` (stream principal), `/profile2` (sub-stream), `/live/ch0`, `/live/ch1`, `/?chID=1&streamType=main`, `/onvif1` e fallback ONVIF genérico. Evita que câmeras avulsas tentem endpoints exclusivos de NVR ou caiam no padrão Hikvision (`/Streaming/Channels/101`). (2) `_eh_motorola` e `_sem_playback`: câmeras diretas (`direct_camera=True`) ou modelos MTI/ONVIF são identificadas como câmeras avulsas sem playback em NVR, prevenindo tentativas de login NVR via SOAP/NVMS. (3) Frontend: Adicionada detecção de prefixo `MTI`/`MTIDM` e marca `MOTOROLA` como protocolo ONVIF no importador CSV (`useCameraImport.ts`) e opção explícita "Motorola (ONVIF)" nos modais de edição (`NVRCamerasGalleryModal.tsx` e `EquipamentoFormModal.tsx`).
(4) Proteção anti-lockout: no máximo 4 tentativas por captura e parada imediata em `401 Unauthorized`. Na integração (merge em isaque) ficou junto da checagem prévia da porta 554 e das mensagens de erro traduzidas sem usuário/senha, e a parada considera só `401 Unauthorized`.
**Arquivos:** agent/src/camera/rtsp_client.py, server/dashboard/src/pages/Machines/MachineDetail/hooks/useCameraImport.ts, server/dashboard/src/pages/Machines/MachineDetail/components/NVRCamerasGalleryModal.tsx, server/dashboard/src/pages/Machines/MachineDetail/components/EquipamentoFormModal.tsx, agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** helena, isaque

### [2026-10-21] — Dashboards por Cliente (etapa 3: documentação e testes)

**Alteração:** Dashboard por Cliente documentado nas seções 3 (estrutura), 5 (tabela `customer_dashboards`), 7 (fluxo do link público: token com hash, fragmento da URL, 404 genérico, limites por IP, isolamento e listas brancas) e 8 (rotas). Nova skill do Claude `criar-widget-dashboard` (como registrar um tipo de widget no backend e no front). Testes de ponta a ponta no repositório: `tools/teste_dashboards_e2e.py` (API: isolamento entre clientes, token inválido/expirado/revogado/regenerado, limite de tentativas, permissão de edição, token sem acesso a rotas admin, resposta pública sem IP/credenciais) e `tools/dashboards_ui/` (Chromium headless em Docker: página pública e de administração, personalizar, salvar, compartilhar e revogar).
**Arquivos:** PROJECT_SPEC.md, CLAUDE.md, .claude/skills/criar-widget-dashboard/SKILL.md, tools/teste_dashboards_e2e.py, tools/dashboards_ui/*, tools/README.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-21] — Dashboards por Cliente (etapa 2B-2: compartilhamento e personalização pelo cliente)

**Alteração:** Painel "Compartilhar" na página do dashboard (admin): gerar o link (validade: sem validade, 7/30/90 dias ou data; permitir ou não a personalização pelo cliente), copiar o link (mostrado uma única vez — o servidor guarda só o hash), ativar/desativar, alterar a validade e a permissão de edição, gerar novo link (invalida o anterior) e revogar. A página pública `/d` passou a usar o mesmo editor (`DashboardWorkspace`): quando o link tem permissão de edição o cliente vê "Personalizar" (sem "Restaurar padrão" nem "Compartilhar") e o layout é salvo no servidor com controle de versão; sem permissão a página é somente leitura.
**Arquivos:** server/dashboard/src/pages/Dashboards/SharePanel.tsx, DashboardAdminPage.tsx, PublicDashboardPage.tsx
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-21] — Dashboards por Cliente (etapa 2B-1: editor e página de administração)

**Alteração:** Editor de dashboard (`DashboardWorkspace`): adicionar/remover componentes, arrastar para reordenar, largura (¼ a total) e altura por componente, configuração por componente (máquinas, equipamentos, tipos, período, visual) gerada a partir dos `campos` de cada tipo de widget (registro modular), filtro geral de período, prévia com dados reais do rascunho (`POST .../dashboard/preview`, admin e público com permissão de edição), salvar com controle de versão (409 em edição concorrente), descartar e restaurar o padrão. Nova página `/clientes/:id/dashboard` e botão "Dashboard" no detalhe do cliente.
**Arquivos:** server/dashboard/src/pages/Dashboards/*, server/dashboard/src/api/dashboards.ts, server/dashboard/src/App.tsx, server/dashboard/src/pages/Customers/CustomerDetail/*, server/api/routers/dashboards.py, server/api/routers/public_dashboard.py, server/api/services/dashboards/esquemas.py
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-21] — Dashboards por Cliente (etapa 2A: visão pública e widgets)

**Alteração:** Registro de widgets no front (resumo, saúde do servidor, status e histórico de backups, câmeras, equipamentos, texto), grade de 12 colunas (`.dash-grid`) e página pública `/d` (sem menu e sem login) que lê o token do fragmento da URL (`/d#<token>`), envia em `X-Dashboard-Token` por um cliente HTTP separado (sem JWT do painel) e atualiza os dados a cada 30 s. Novas rotas de opções para o editor: `GET /api/v1/clients/{id}/dashboard/opcoes` (admin) e `GET /api/v1/public/dashboard/opcoes` (só com permissão de edição). A rota `/d` do nginx do dashboard envia `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex` e `Cache-Control: no-store`.
**Arquivos:** server/dashboard/src/pages/Dashboards/*, server/dashboard/src/api/dashboards.ts, server/dashboard/src/App.tsx, server/dashboard/src/index.css, server/dashboard/nginx-spa.conf, server/api/routers/dashboards.py, server/api/routers/public_dashboard.py, server/api/services/dashboards/{dados,esquemas}.py
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-21] — Dashboards por Cliente (etapa 1: API)

**Alteração:** Nova tabela `customer_dashboards` (um dashboard por Cliente: layout JSON versionado + compartilhamento por link). Registro de tipos de widget plugáveis (`services/dashboards/`: resumo, saúde do servidor, status e histórico de backups, câmeras/gravação, equipamentos, texto) que montam os dados a partir de telemetria, backups e `last_recording_status` já existentes. Rotas de admin (JWT) em `/api/v1/clients/{id}/dashboard` (layout com controle de versão, link de compartilhamento: gerar/regenerar, ativar, validade, permitir edição, revogar) e catálogo em `/api/v1/dashboards/widgets`. Rotas públicas em `/api/v1/public/dashboard` autenticadas só por `X-Dashboard-Token` (token aleatório de 256 bits, guardado como hash SHA-256, mostrado uma única vez; 404 genérico para inválido/expirado/revogado; limite de requisições e de tentativas inválidas por IP em memória, válido para 1 worker). O servidor filtra tudo pelo cliente do token e a resposta pública omite IPs, credenciais e configurações dos equipamentos.
**Arquivos:** server/api/models.py, server/api/main.py, server/api/services/dashboards/*, server/api/routers/dashboards.py, server/api/routers/public_dashboard.py
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-21] — Agente 1.1.16: Fallback RTSP (TCP/UDP e sub-stream) e pareamento por nome/IP na Galeria VMS

**Alteração:** (1) Agente (`rtsp_client.py`): `test_rtsp_camera` agora utiliza fallback automático entre protocolos de transporte (TCP -> UDP) com `-stimeout 5000000` (5s), além de tentar o stream secundário (`102`) e formato simplificado (`/Streaming/Channels/1`) se o principal estiver saturado. Isso resolve o erro de timeout de 15s no FFmpeg em câmeras Hikvision mais antigas (ex: DS-2CD2012-I e DS-2CD2020-I) que funcionavam no VLC (que usa UDP por padrão) mas travavam no TCP forçado enquanto o VMS gravava. (2) Servidor (`equipamentos.py`): `get_nvr_cameras` para VMS pareia câmeras por nome e por IP (não apenas por número sequencial de canal), garantindo que nomes e IPs não se misturem e que câmeras sem registro prévio no banco utilizem o IP reportado pelo agente (eliminando câmeras "sem IP"). (3) `test_equipamento_rtsp`: recupera o IP do relatório de status e persiste automaticamente se o canal ainda não possuía IP cadastrado na galeria, evitando o erro falso "sem IP configurado". (4) `import_cameras`: casa câmeras existentes por nome/IP antes de casar por canal ao importar CSV/XLSX, preservando referências e imagens ao reimportar. (5) Integração (merge de helena em isaque): a captura ao vivo usa `-timeout` (o `-stimeout` não existe no ffmpeg 7.1 do agente e fazia toda captura falhar com "Unrecognized option"), checa a porta 554 antes das tentativas, limita o total a 20 s e devolve motivo traduzido sem usuário/senha. O pareamento de câmeras (nome, IP e nome parecido único, nunca por canal) foi extraído para `services/galeria_vms.py` e é usado pela Galeria, pela captura do painel e pelo envio da imagem da noite.
**Arquivos:** agent/src/camera/rtsp_client.py, agent/src/backup/file_manager/manager.py, server/api/routers/equipamentos.py, server/dashboard/src/pages/Machines/MachineDetail/hooks/useCameraImport.ts, agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json, server/api/services/galeria_vms.py, server/api/routers/agent.py
**Breaking Change:** Não.
**Branch:** helena, isaque

### [2026-10-21] — Agente 1.1.15: Galeria DIGIFORT/DEFENSE com câmeras casadas pelo nome e erro de captura sem senha

**Alteração:** Em equipamentos DIGIFORT/DEFENSE, o servidor passou a casar relatório, imagem da noite e status de captura pelo **nome** da câmera (antes era pelo canal, e a numeração do agente — ordem do export local — difere da da Galeria, o que trocava nome/IP/imagem entre câmeras). O agente envia o canal da Galeria e deduplica por nome. A captura ao vivo do agente verifica a porta 554 antes do ffmpeg, usa timeout de 20 s e devolve o motivo traduzido (porta inacessível, senha recusada, caminho RTSP não encontrado, tempo esgotado); a URL RTSP com usuário/senha nunca vai na mensagem, e o servidor também mascara credenciais recebidas de agentes antigos (rtsp-result, relatório e leitura da Galeria).
**Arquivos:** server/api/routers/agent.py, server/api/routers/equipamentos.py, agent/src/backup/file_manager/manager.py, agent/src/camera/rtsp_client.py
**Breaking Change:** Não (o servidor já corrige a leitura com agentes atuais; a correção do agente chega às máquinas na 1.1.15).
**Branch:** isaque

### [2026-10-20] — Visão Geral: Saúde do Servidor em destaque e layout personalizável

**Alteração:** Cada máquina da Visão Geral é um card com o nome do **cliente** como título e o nome da máquina pequeno, status do último backup, comunicação ("Atualizado agora/há N s", ou última comunicação quando offline) e a Saúde do Servidor como conteúdo principal em medidores em anel (CPU, RAM, GPU e um anel por disco) e as placas de rede físicas em linhas compactas. A página atualiza a cada 10 s. O botão "Personalizar" liga o modo de edição: arrastar e soltar para reordenar, largura por card (¼, ⅓, ½, ⅔, total, grade de 12 colunas) e escolha de quais máquinas aparecem. A escolha fica no `localStorage` do navegador (chave `trilan.overview.layout.v1`), sem mudança no servidor; máquinas novas aparecem sozinhas no fim. O card é compacto (largura padrão ¼) para ver muitas máquinas de uma vez.
**Arquivos:** server/dashboard/src/pages/Overview/ (index.tsx, layout.ts, MachineHealthCard.tsx, RingGauge.tsx), pages/Machines/MachineDetail/components/ServerHealthCard.tsx (exports), src/index.css
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-20] — Skills: três externas instaladas e as do projeto atualizadas

**Alteração:** (1) Instaladas em `.claude/skills/`, baixadas direto do GitHub e revisadas antes: `fastapi` (fastapi/fastapi@6f28852), `vercel-react-best-practices` (vercel-labs/agent-skills@063bee9) e `docker-compose-patterns` (docker/skills@38df58b). (2) Reescritas com a estrutura atual: `criar-novo-agente` (apontava para `agente_unm.py`, que não existe mais), `criar-endpoint-fastapi` (agora com REGRA-001/002/003/004/005/007 e o fluxo dashboard/PROJECT_SPEC) e `gerenciar-containers` (usa o `docker-compose.local.yml`; o de produção é só do Dokploy; testes em container). (3) `CLAUDE.md` registra como aplicar as externas neste projeto e como instalar novas sem `npx skills`.
**Arquivos:** .claude/skills/*, CLAUDE.md, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-20] — Skills só para o Claude Code

**Alteração:** As skills do projeto saem de `.agents/skills/` (lida automaticamente pelo Antigravity/agy, usado como executor) e passam para `.claude/skills/`, que só o Claude Code lê: `criar-endpoint-fastapi`, `criar-novo-agente`, `gerenciar-containers` e `find-skills`. O `professional-frontend` foi removido. O `.gitignore` versiona só `.claude/skills/`; o resto de `.claude/` (permissões locais) continua fora do git. `.agents/` fica só com `rules/git-deploy.md`.
**Arquivos:** .gitignore, .claude/skills/*, .agents/skills/* (removidos), CLAUDE.md, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-20] — Painel: Saúde do Servidor com resumo e detalhes

**Alteração:** O card "Saúde do Servidor" da página da máquina mostra um status geral (Saudável/Atenção/Crítico, ou Offline), quando os dados foram atualizados, blocos de CPU, RAM e GPU, a lista de todos os discos (usado, livre, total e barra) e todas as placas de rede (físicas em destaque, virtuais atenuadas, com envio e recebimento). O botão "Ver detalhes" abre um modal com cada disco (sistema, usado, livre, total), memória usada/livre, cada placa de rede (física ou virtual) e a GPU com memória. A barra de rede comparada a 1 Gbps fixo saiu. Limites únicos em `telemetry.ts`: atenção acima de 75%, crítico acima de 90%. Sem mudança no agente nem na API: usa a telemetria que já chega no ping.
**Arquivos:** server/dashboard/src/pages/Machines/MachineDetail/telemetry.ts, components/ServerHealthCard.tsx, components/ServerHealthModal.tsx, components/TelemetryBar.tsx, components/MachineInfoCards.tsx, utils.ts, index.tsx
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-20] — Agente 1.1.14: Galeria RTSP para DIGIFORT e DEFENSE

**Alteração:** Equipamentos DIGIFORT e DEFENSE ganham a mesma Galeria de Câmeras do NVR (Referência Ideal + Imagem da Noite via RTSP), já que cada câmera é uma câmera IP própria (ip/usuário/senha/modelo individuais), não um canal do mesmo NVR. (1) `nvr_cameras` ganha `ip`, `username`, `password` (Fernet) e `modelo`, opcionais (NULL em NVR comum). (2) Três formas de popular a galeria: `POST .../cameras/import` (CSV/XLSX exportado do equipamento, ou `sync_from_machine=true` para copiar as câmeras avulsas tipo `CAMERA` da máquina) e `PUT/DELETE .../cameras/{canal}` para editar/remover uma câmera manualmente. (3) `GET .../cameras` resolve o canal "N/A" que DIGIFORT/DEFENSE reportam (casa pelo nome com a galeria ou usa o próximo canal livre) e devolve `ip`/`username`/`modelo`/`has_password`. (4) `POST .../test-rtsp` em equipamento DIGIFORT/DEFENSE exige `canal`, busca a câmera da galeria e monta a tarefa com `direct_camera=True` + `stream_principal=True` (sem canal de NVR); o agente (`executar_tarefa_rtsp`) captura sempre ao vivo nesse caso, para os modos `ao_vivo`/`referencia`/`noite`. (5) `GET /agent/config` envia `cameras_config` (ip/usuário/senha decriptada/modelo) de cada equipamento DIGIFORT/DEFENSE; no backup da madrugada, `capturar_imagens_noite_vms` (novo, em `rtsp_client.py`) captura 1 frame por câmera (stream principal), respeitando um orçamento de 20 min (`LIMITE_IMAGENS_NVR_S`), e envia para `POST /agent/nvr-cameras/night-image` (que agora aceita `ip`/`modelo` opcionais). DIGIFORT cruza isso com `export_cameras.csv` local (`get_detalhes_cameras`, novo); DEFENSE usa só `cameras_config` (o status de queda ainda vem do Webhook CSV). (6) Dashboard: Galeria mostra os botões "Importar CSV/XLSX", "Sincronizar da Máquina" e "+ Câmera" (editar IP/usuário/senha/modelo) quando o equipamento é DIGIFORT/DEFENSE; botões "Galeria" e "Gravações" no card do equipamento passam a aparecer para DEFENSE também (DIGIFORT já tinha).
**Arquivos:** server/api/models.py, server/api/main.py, server/api/schemas.py, server/api/routers/agent.py, server/api/routers/equipamentos.py, agent/src/camera/rtsp_client.py, agent/src/application/webhook_digifort.py, agent/src/backup/file_manager/manager.py, agent/src/olt/unm2000.py, agent/src/application/backup_job.py, agent/src/vms/defense.py, server/dashboard/src/api/types.ts, server/dashboard/src/pages/Machines/MachineDetail/hooks/useCameraImport.ts, server/dashboard/src/pages/Machines/MachineDetail/components/EqCard.tsx, server/dashboard/src/pages/Machines/MachineDetail/components/NVRCamerasGalleryModal.tsx, server/dashboard/src/pages/Machines/MachineDetail/index.tsx, agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json
**Breaking Change:** Não (NVR comum não é afetado; agente antigo em DIGIFORT/DEFENSE simplesmente não recebe `cameras_config` nem captura a imagem da noite, como hoje).
**Branch:** helena

### [2026-10-19] — Publicação de versões: release no repositório público e cadastro sob demanda

**Alteração:** (1) Ao gerar os executáveis, a release (tag = versão, título `v<versão>`, só `TrilanAgentService.exe` e `TrilanAgentTray.exe`) é publicada em `isaqueschaffer/backup-automation` (público; os agentes baixam daqui). (2) O cadastro da versão no painel é sob demanda: só quando o usuário pedir e informar a senha do painel, via `agent/publish_version.ps1`. (3) Servidor: `POST /api/v1/admin/agent-version` passa a aceitar também o header `X-Publish-Token` (variável `PUBLISH_TOKEN`; vazia = desativado), que só serve para registrar versões. Regras fixas registradas em `CLAUDE.md`.
**Arquivos:** CLAUDE.md, agent/publish_version.ps1, server/api/auth.py, server/api/config.py, server/api/routers/agent_update.py, server/.env.example
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-19] — Agente 1.1.13: nome do serviço no Windows

**Alteração:** O nome exibido do serviço em services.msc passa de "Trilan — Agente Backup NVR" para "Trilan — Agente Backup" (`_svc_display_name_` em `service.py`). Máquinas já instaladas recebem o novo nome sozinhas: `_configurar_recuperacao_servico` aplica `sc config TrilanAgentNVR DisplayName=` a cada início. O nome interno do serviço (`TrilanAgentNVR`) não mudou.
**Arquivos:** agent/service.py, agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-16] — Agente 1.1.12: reinício pelo painel e atualização OTA confiáveis

**Problema:** "Reiniciar todos" parava os agentes e eles não voltavam. Causa: o script que religa o serviço era iniciado com `DETACHED_PROCESS`; sem console o PowerShell fecha sem executar nada (1.1.9–1.1.11). Até a 1.1.8, `ping 3s && sc start` tentava uma vez só, cedo demais. No .bat da OTA, `timeout /t` não espera sem console (as pausas fixas nunca aconteceram).
**Alteração:** (1) Scripts auxiliares iniciados com `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP` e stdin/stdout/stderr nulos (nunca `DETACHED_PROCESS`). (2) Reinício por dois caminhos independentes: `SCRIPT_REINICIO` espera o processo do serviço (o bootloader) sair, tenta `Start-Service` até 5x, confere e registra em `logs/reinicio.log`; e o processo termina com `os._exit(1)`, para a recuperação do Windows (`sc failure ... restart/5000/10000/30000`, reaplicada a cada início por `garantir_recuperacao_windows`) religar em 5 s. (3) .bat da OTA: espera o processo antigo sair (até 90 s), copia com novas tentativas, inicia e confere `RUNNING` (até 5x), pausas com `ping`, log em `logs/atualizacao.log`. Uma OTA para a 1.1.12 ainda é aplicada pelo .bat da versão antiga.
**Arquivos:** agent/service.py, agent/src/application/updater.py
**Breaking Change:** Não. Cada reinício pelo painel gera no Visualizador de Eventos um aviso de "serviço terminou inesperadamente" (é o gatilho da recuperação).
**Branch:** isaque

### [2026-10-16] — Agente 1.1.11: backup sem imagem da noite; captura sem imagem cinza; galeria reorganizada

**Alteração:** (1) O backup (manual e agendado) não captura mais a imagem da noite — atrasava muito o backup. A captura é só sob demanda pela Galeria (tarefa RTSP `modo=noite`). (2) Todas as capturas ffmpeg usam `-skip_frame nokey` antes do `-i`: só quadros-chave são decodificados; antes, a conexão que começava entre dois quadros-chave gerava imagem cinza (H.265, intermitente). (3) Servidor: o relatório do agente substitui `last_recording_status`; `_manter_imagem_noite` preserva o `imagem_noite` anterior nos canais sem esse campo; falha da captura da noite pelo painel grava `FALHA`+motivo no canal (`_marcar_imagem_noite`). (4) Galeria: ações em lote no topo por tipo (Referência / Noite) com contador "x/y com imagem", "Capturar faltantes (n)" (padrão) e "Todas", progresso, cancelamento e lista de falhas; lateral com filtros Todas / Sem referência / Sem noite e chips REF/NOITE por câmera; botões de cada imagem abaixo do respectivo painel.
**Arquivos:** agent/src/application/backup_job.py, agent/src/camera/rtsp_client.py, server/api/routers/agent.py, server/api/routers/equipamentos.py, server/dashboard/src/pages/Machines/MachineDetail/components/NVRCamerasGalleryModal.tsx
**Breaking Change:** Não (agentes antigos continuam capturando a noite no backup; o servidor aceita os dois).
**Branch:** isaque

### [2026-10-16] — Agente 1.1.10: instalador, bandeja e reabertura da bandeja após atualização

**Alteração:** (1) Instalador: `--startup=auto` antes da ação (pywin32 usa getopt e ignorava a opção após `install`); `remove` antes do `install`; `PrepareToInstall` para o serviço e fecha a bandeja antes de copiar os arquivos. (2) Bandeja: "Reiniciar serviço" em um único `Restart-Service` elevado; instância única por mutex `Local\TrilanAgentTray` (por sessão). (3) A atualização OTA fecha a bandeja para trocar o arquivo; ao iniciar, o serviço (SYSTEM, sessão 0) a reabre como o usuário de cada sessão ativa/desconectada que não a tem aberta (`WTSQueryUserToken` + `CreateProcessAsUser`), só se o `TrilanAgentTray.exe` foi trocado nos últimos 15 min — não reabre uma bandeja fechada pelo usuário num reinício comum. Na atualização 1.1.9 → 1.1.10 quem aplica é o atualizador antigo; a reabertura funciona porque é feita pelo serviço novo ao iniciar.
**Arquivos:** agent/service.py, agent/tray.py, agent/installer.iss, agent/src/application/updater.py
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-15] — Reinício do agente espera o backup terminar

**Alteração:** No `/agent/ping`, se o agente informa `telemetry.backup_em_andamento` (>= 1.1.8), o servidor não entrega `restart` e mantém `restart_requested` até o ping seguinte sem backup em andamento (evita perder o backup por "Reiniciar"/"Reiniciar todos" no meio). O dashboard mostra "Reinício agendado" no cabeçalho da máquina. Agentes antigos reiniciam como antes. Backup manual não é afetado.
**Arquivos:** server/api/routers/agent.py, server/dashboard/src/pages/Machines/MachineDetail/components/MachineHeader.tsx
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-15] — Imagem da noite: limite de falhas; rodada espera máquina em backup (agente 1.1.8)

**Alteração:** (1) `capture_night_image` (Hikvision) desiste da câmera após 2 falhas de vídeo (`MAX_FALHAS_CAPTURA`) em vez de testar até 40 trechos de 25 s; Motorola testa 1 trecho por modo de horário (local/utc), no máximo 2 falhas. Há também um orçamento de 20 min por NVR para todas as imagens da noite (`LIMITE_IMAGENS_NVR_S`); câmeras restantes ficam com "Tempo limite…". (2) Trecho que atravessa a meia-noite é cortado em 00:00 (a URL usava a data pedida para início e fim, gerando intervalo invertido e 400). (3) O ping do agente informa `telemetry.backup_em_andamento`; passado o prazo (`RUN_DEADLINE_HOURS`), a rodada do Cliente espera a máquina esperada que ainda não reportou e está em backup (ping < 120 s), até `RUN_MAX_HOURS` (6 h) desde o início. Agentes < 1.1.8 mantêm o fechamento no prazo. (4) Log do agente grava só o motivo do ffmpeg, não o banner inteiro.
**Arquivos:** agent/src/camera/rtsp_client.py, agent/src/application/backup_job.py, agent/src/application/api_client.py, agent/src/application/estado.py, agent/service.py, server/api/services/backup_runs.py, server/api/config.py, server/dashboard/src/pages/Customers/CustomerDetail/components/RunDetailsModal.tsx
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-15] — Captura pela gravação: referência de câmera offline e imagem da noite sob demanda (agente 1.1.6)

**Alteração:** `POST .../equipamentos/{id}/test-rtsp` ganhou `modo` (`ao_vivo` padrão | `referencia` | `noite`) e `nome`. A tarefa vai ao agente com `modo`; agentes < 1.1.6 ignoram e capturam ao vivo.
- `referencia`: ao vivo; se falhar (câmera offline), o agente usa o frame do fim do trecho gravado mais recente, buscando do agora para trás até 15 dias (Hikvision: ISAPI em janelas de 6h; Motorola: `queryChlRecLog`).
- `noite`: madrugada (00h–06h) mais recente com gravação, da noite mais nova para a mais antiga, até 15 dias (desiste após 2 falhas de vídeo). O servidor salva em `nvr_cameras.night_image_*` e marca `imagem_noite` OK no `last_recording_status` do canal. Resposta sem `horario` (agente antigo) é recusada.
- `RTSPTestResponse` ganhou `horario` e `origem` ("ao_vivo" | "gravacao"). Espera do servidor: 35s ao vivo, 130s pela gravação (o agente encerra em ~100s); a sessão do banco é liberada durante a espera. Envio do resultado pelo agente: timeout 10s → 60s.
- Galeria: "Capturar referência" (com fallback), "Capturar imagem da noite" e "Enviar imagem"; "Atualizar todas as referências" agora inclui câmeras offline.
**Arquivos:** agent/src/camera/rtsp_client.py, agent/service.py, agent/src/application/api_client.py, agent/src/application/updater.py, agent/installer.iss, server/api/routers/equipamentos.py, server/api/schemas.py, server/dashboard/src/pages/Machines/MachineDetail/components/NVRCamerasGalleryModal.tsx, server/dashboard/package.json
**Breaking Change:** Não (sem `modo` o comportamento é o anterior; agente antigo recebe a tarefa como ao vivo).
**Branch:** isaque

### [2026-10-15] — Upload da imagem de referência; acesso às máquinas pela fila do Cliente

**Alteração:** Na Galeria do NVR, além de "Capturar da câmera" (RTSP pelo agente), o botão "Enviar imagem" sobe um arquivo do computador como referência do canal. O navegador converte para JPEG (qualidade 0,9; lado maior até 3840 px) e usa o mesmo endpoint `POST .../cameras/perfect-image`. `NVRCameraSetPerfect.image_base64` agora é validado: base64 válido, JPEG (`FF D8`), até 10 MB; aceita prefixo `data:`. Na fila do Cliente, a linha da máquina (ou o botão "Abrir") abre `/maquinas/:id`; na máquina, o cabeçalho mostra "Cliente: X › Máquina" e o voltar retorna ao Cliente.
**Arquivos:** server/api/schemas.py, server/dashboard/src/pages/Machines/MachineDetail/components/NVRCamerasGalleryModal.tsx, server/dashboard/src/pages/Machines/MachineDetail/components/MachineHeader.tsx, server/dashboard/src/pages/Machines/MachineDetail/index.tsx, server/dashboard/src/pages/Customers/CustomerDetail/components/QueueSection.tsx
**Breaking Change:** Não (a captura RTSP do agente já envia JPEG).
**Branch:** isaque

### [2026-10-14] — E-mail anexa a imagem de referência das câmeras offline

**Alteração:** O e-mail de relatório (máquina avulsa e rodada do Cliente) anexa a imagem perfeita (`nvr_cameras.perfect_image_base64`) de cada câmera não ONLINE, para o técnico identificar a câmera no local. Sem mudança no agente nem no banco.
**Regras:** só câmeras offline (mesmo critério da seção de câmeras); só a imagem de referência (não a da noite); arquivo `<nome da câmera>.jpg` (caracteres inválidos viram `_`, nomes repetidos ganham ` (2)`); no máximo 10 imagens por e-mail (`MAX_OFFLINE_IMAGES`). O corpo informa quantas foram anexadas, quantas passaram do limite e quantas câmeras offline não têm imagem cadastrada. A câmera é achada pelo NVR (máquina + nome, como no recebimento do relatório) e pelo canal.
**Arquivos:** server/api/services/email_service.py, server/api/services/backup_runs.py, server/api/routers/agent.py, server/api/routers/backups.py, server/api/tests/test_email_offline_images.py
**Breaking Change:** Não (`machine_id` é parâmetro opcional; sem ele o e-mail sai sem imagens).
**Branch:** isaque

### [2026-10-14] — Backup e e-mail por Cliente (rodadas)

**Alteração:** Cliente com várias máquinas recebe 1 e-mail por rodada de backup, com o relatório de todas as máquinas e um ZIP unificado.
**Antes:** 1 e-mail por upload de cada máquina, para os e-mails da máquina (5 máquinas = 5 e-mails); máquina sem ZIP não gerava e-mail.
**Depois:**
- Nova tabela `customer_backup_runs` e `backups.run_id`; `client_groups.email_to` (populado na criação com a união dos e-mails das máquinas). Migração inline idempotente; datetimes naive (REGRA-001).
- Rodada `scheduled` (aberta no 1º relatório agendado), `queue` (aberta no backup em fila do cliente) e `manual_machine` (backup avulso de uma máquina: e-mail só dela). Fecha quando todas as máquinas esperadas reportaram + 90 s para o ZIP chegar (`RUN_UPLOAD_GRACE_SECONDS`), ou no prazo de 2 h (`RUN_DEADLINE_HOURS`); fila que termina pulando máquinas offline fecha logo após o último ZIP. Quem não reportou aparece como "não executou".
- Fechamento por tarefa de fundo a cada 30 s (`services/backup_runs.py`, 1 worker uvicorn) com `UPDATE ... WHERE closed_at IS NULL` para nunca enviar o e-mail duas vezes.
- E-mail do cliente (`send_customer_report`): resumo por máquina, seções de câmeras e backup de cada máquina e link `PUBLIC_URL/api/v1/backups/public-run-download/{run_id}` (sem `PUBLIC_URL`, diz "ZIP disponível no painel"). Máquina sem cliente: e-mail por upload como antes.
- E-mails da máquina com cliente são os do cliente (PUT alterando = 400). Painel: e-mails no cliente, seção "Rodadas de backup" (detalhes, baixar ZIP, reenviar), e-mail travado na máquina.
**Requisito de produção:** definir `PUBLIC_URL` no `.env` para o link do ZIP sair no e-mail automático.
**Verificação:** simulação com SMTP interceptado (rodada completa, máquina faltando, avulso, fila, cancelamento, máquina sem cliente, downloads, reenvio, duplicidade, contrato do agente inalterado) e as 45 chamadas do painel conferidas contra a API.
**Breaking Change:** Não para o agente. A API admin ganhou campos e rotas (o painel foi atualizado junto).
**Branch:** isaque

### [2026-10-14] — Cliente e Máquina reorganizados; fila com arrastar e soltar

**Alteração:** Nomenclatura única (ver ADR-007) em telas, código e API admin; telas planas por entidade.
**Antes:** A lista de máquinas se chamava "Clientes" e criava "Novo Cliente"; clientes apareciam como "Unidade"; a posição na fila era digitada; não havia como remover máquina de um cliente; máquinas de um cliente eram vistas num acordeão.
**Depois:**
- Backend: `Machine`/`Customer` (ORM com colunas antigas), `routers/machines.py` e `routers/customers.py`; novas rotas para vincular/remover máquina e reordenar a fila (409 com fila ativa; fila renumerada ao remover); filtros `customer_id`/`unassigned` em máquinas e `machine_id`/`customer_id` em backups; `BackupResponse` com máquina e cliente; `StatsResponse` com `machines_total`, `machines_active`, `customers_total`; e-mail diz "Máquina:".
- Dashboard: `/clientes`, `/clientes/:id` (fila com arrastar e soltar nativo, adicionar/remover máquina, backups do cliente), `/maquinas`, `/maquinas/:id` (cliente com link; horário travado quando herdado); Backups com colunas e filtros de Cliente e Máquina.
- Contrato JSON admin: `group_id/group_name` → `customer_id/customer_name`; `agents_total/online` e `clients` → `machines_total/online` e `machines`; `client_id/client_name` em backups → `machine_id/machine_name`; NVR e logs usam `machine_id`.
**Verificação:** simulação do app real (SQLite) cobrindo vínculo, fila, horário herdado, filtros e o fluxo do agente; as 42 chamadas do dashboard conferidas contra as 51 rotas do OpenAPI; `tsc` e `vite build` sem erros.
**Breaking Change:** Sim para a API admin (só o dashboard a consome, atualizado junto). Não para o agente.
**Branch:** isaque

### [2026-10-14] — Agente 1.1.5: correções da auditoria

**Alteração:** Versão do agente elevada para 1.1.5 para distribuir, via OTA, as correções da auditoria (todos os clientes estavam na 1.1.4, e o OTA só atualiza para versão maior).
**Inclui:** não loga credenciais de câmera; OTA defensivo (exige https, exceção não derruba o serviço); `buscar_trechos` sem "dummy"; `rtsp_task` não se perde durante backup manual; timeouts em mysqldump/Mikrotik; `ConfigError`; hidden-imports no build.
**Atenção:** Atualizações OTA com URL `http://` passam a ser ignoradas (use https no GitHub Release).
**Arquivos:** agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-13] — Auditoria geral: correções, reestruturação do repositório e do dashboard

**Alteração:** Auditoria por área (API, dashboard, agente, higiene do repositório) seguida das correções seguras.
**Repositório:** `agent/dist`, `__pycache__` e `.claude/settings.json` deixam de ser versionados; removidos `.bat` com API key, `index.xml`, `scratch_test/` (config real de OLT), imagens de teste e arquivos soltos da raiz; scripts avulsos em `tools/`, legado em `archive/legacy_scripts/`; `.gitignore` ampliado. Seção 3 e rotas da seção 8 reescritas conforme o código.
**API:** corrige `UnboundLocalError` do auto-recovery do ping (importava `AgentLog` depois do uso); upload de ZIP sem path traversal, em streaming (`MAX_UPLOAD_MB`) e fora do event loop; ping libera a sessão do banco no long-poll; `test-rtsp` devolve 409 se já houver tarefa; `compare_digest` em senha admin e API key; `backup_hour/minute` validados na entrada (respostas sem limite); `group_id` inexistente = 404; lixeira só após o commit; menos N+1; `update-check` escolhe a maior versão ativa e valida X.Y.Z/SHA-256; migrações inline com um ALTER por transação e logging.
**Agente:** não loga credenciais de `rtsp_task` nem senha da URL RTSP; OTA defensivo (https obrigatório, `tmp_dir` limpo, exceção não derruba o serviço); `buscar_trechos` não devolve mais "dummy" (busca inconclusiva cai nos horários fixos); pings drenados durante backup manual não perdem o `rtsp_task`; timeouts em mysqldump e Mikrotik; `ConfigError` no lugar de `sys.exit`; hidden-imports adicionais no `build.ps1`.
**Dashboard:** `ClientDetail.tsx` (~1580 linhas) dividido em `pages/ClientDetail/` (index, utils, components, hooks); `utils/date.ts`; aliases CSS das variáveis inexistentes; tipos alinhados ao backend; tratamento de erro/corrida nos carregamentos; correção do 422 ao editar máquina sem grupo e da regex `\s` nos nomes de arquivo; `tsc` e `vite build` verificados em cópia fora do projeto.
**Pendente (decisão do dono):** IC-007 a IC-009 e IC-012; rotacionar a API key do agente e a `SECRET_KEY`/senha de dev que estavam versionadas; reescrever o histórico do git para tirar EXEs e segredos.
**Breaking Change:** Não nos contratos de API. Uploads acima de `MAX_UPLOAD_MB` agora recebem 413; atualizações OTA com URL `http://` deixam de ser aplicadas.
**Branch:** isaque

### [2026-10-13] — Ações em massa: reiniciar/backup de todos os clientes e atualizar todas as referências da galeria

**Alteração:** Três botões novos, sem mudança no agente.
**API:** `POST /api/v1/machines/restart-agent-all` e `POST /api/v1/machines/trigger-backup-all` marcam `restart_requested` / `backup_requested` em todos os clientes ativos e online (ping < 180s); offline ficam de fora. Resposta: `{"queued": n, "skipped_offline": m}`. Reaproveitam o fluxo existente de flags consumidas no ping.
**Dashboard:** tela Clientes ganha "Reiniciar todos" e "Backup de todos" (com confirmação). Na galeria do NVR, "Atualizar todas as referências" atualiza uma câmera por vez (todas as não OFFLINE), com progresso, cancelar e resumo de falhas; é sequencial porque `pending_rtsp_tasks` guarda uma única tarefa RTSP por cliente (~15–20s por câmera, limitado pelo ping do agente).
**Arquivos:** server/api/routers/clients.py, server/dashboard/src/api/client.ts, server/dashboard/src/pages/Clients.tsx, server/dashboard/src/pages/ClientDetail.tsx
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-13] — Agente 1.1.4: Galeria/imagem da noite para NVR Motorola (NVMS-9000)

**Alteração:** Captura da imagem da noite e da referência ideal passa a funcionar em NVR Motorola, e a galeria lista as câmeras Motorola.
**Antes:** O backup marcava toda câmera Motorola como `NAO_SUPORTADO`; a referência usava a URL RTSP da Hikvision (404); o canal Motorola era reportado como GUID (`{0000000N-0000-...}`) e o servidor descartava (`int()` falhava), então a galeria ficava vazia.
**Depois:**
- RTSP Motorola: ao vivo `rtsp://.../chID=N&streamType=main`; playback `chID=N&date=AAAA-MM-DD&time=HH:MM:SS&timelen=10&streamType=main`. A rota `test-rtsp` agora envia também `marca` (NVR guarda a marca em `config_extra.marca`, não em `modelo`).
- `factory.py`: o canal Motorola é reportado como inteiro (N do GUID; GUID original em `canal_guid`) e com `dias_com_gravacao`. O servidor também converte GUID de relatórios de agentes antigos (`_canal_int`).
- `motorola/recordings.py`: `buscar_trechos_motorola` usa `queryChlRecLog` (mesmo comando da tela de gravação do NVR; resposta em UTC; erro `noRecord` = sem gravação) para achar o trecho real da madrugada.
- `rtsp_client.capture_night_image_motorola`: 02:00 limitado ao trecho (até 2 trechos por interpretação de horário). Alguns NVRs (ex.: relógio/fuso reconfigurado) exibem/reproduzem no horário UTC cru da busca em vez do fuso local; o agente testa as duas interpretações ("local"/"utc") e lembra a que funcionou por NVR (`_MODO_HORARIO_MOTOROLA`). Sem gravação na madrugada = `SEM_GRAVACAO`; busca falhou = horários fixos como fallback.
- `backup_job.py`: um login Motorola para todas as câmeras; antes das 06h usa o último dia anterior a hoje (a madrugada de hoje ainda não terminou).
**Validação (8 NVRs Motorola, VPN, madrugada de 12/10):** imagem capturada na grande maioria das câmeras com gravação; as restantes são `SEM_GRAVACAO` ou falha com motivo (NVR lista trecho mas não entrega o vídeo em 1–3 canais por NVR).
**Limitação conhecida:** num NVR com fuso divergente e gravação contínua, a interpretação errada do horário poderia devolver um quadro de outro horário; o horário reportado é o solicitado ao NVR.
**Arquivos:** agent/src/camera/rtsp_client.py, agent/src/nvr/factory.py, agent/src/nvr/motorola/recordings.py, agent/src/application/backup_job.py, agent/src/application/updater.py, agent/installer.iss, server/api/routers/equipamentos.py, server/dashboard/package.json
**Breaking Change:** Não. Relatórios Motorola passam a trazer `canal` inteiro; o servidor aceita os dois formatos.
**Branch:** isaque

### [2026-10-09] — Agente 1.1.3: Captura de imagem da noite via histórico ISAPI e Galeria unificada

**Alteração:** Agente busca trechos de gravação na madrugada via ISAPI (`buscar_trechos`) antes de tentar baixar a imagem via RTSP, evitando tentativas cegas (e timeouts) em NVRs que não têm gravação. A galeria do NVR agora une os dados da tabela `nvr_cameras` com `last_recording_status`, listando todas as câmeras gravadas (mesmo as que falharam na imagem).
**Antes:** O ffmpeg tentava baixar 15s de RTSP em horários fixos. Câmeras sem gravação ficavam até 15s bloqueadas. A galeria só mostrava câmeras com imagem capturada com sucesso (`nvr_cameras`).
**Depois:** A galeria lista todas as câmeras. Falhas mostram o motivo (traduzido do log do ffmpeg).
**Arquivos:** `agent/src/nvr/hikvision/recordings.py`, `agent/src/camera/rtsp_client.py`, `agent/src/application/backup_job.py`, `agent/src/application/api_client.py`, `server/api/schemas.py`, `server/api/routers/equipamentos.py`, `server/dashboard/src/pages/ClientDetail.tsx`
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-09] — Agente 1.1.2: ping em cadência fixa + telemetria sem NaN

**Alteracao:** Ping do agente movido para thread própria com cadência fixa de 15s (início a início); telemetria sanitizada; "Próximo contato (estimado)" sincronizado com o ping real.
**Antes:** O ping só era verificado quando o loop principal acordava (espera de até 60s, e bloqueado durante backups), então saía a cada ~60s enquanto o dashboard contava 15s e ficava em 00:00. GPUtil devolvia NaN para campos `[N/A]` do nvidia-smi e o `requests` recusava serializar o JSON, derrubando todos os pings (cliente aparecia offline e não recebia OTA).
**Depois:** `service.py` roda `_ping_loop` em thread (`PING_INTERVAL_S = 15`); as instruções do ping são enfileiradas e executadas no loop principal via evento `hPingResp`. `hWaitStop` virou manual-reset para as duas threads verem a parada. `api_client._json_safe` troca NaN/inf por null e falha de telemetria não impede o ping. Dashboard mostra "aguardando…" ao passar do horário e consulta o cliente a cada 1s por até 30s.
**Imagem de referência (1.1.2):** `rtsp_client.test_rtsp_camera` passa a capturar o stream principal (`{canal}01` / `subtype=0`) quando a tarefa traz `canal` (galeria do NVR), igual à origem da imagem da noite; antes usava o secundário (`{canal}02` / `subtype=1`), com resolução e proporção diferentes. O teste de câmera direta (sem canal) continua no secundário.
**Galeria do NVR (dashboard):** os painéis "Referência Ideal" e "Último backup (noite)" usam o mesmo componente `CameraImagePanel`, com `object-fit: contain` (quadro inteiro, sem corte) e a resolução da imagem ao lado do título. Antes eram dois blocos duplicados com `cover`, que cortava imagens fora de 16:9.
**Arquivos:** agent/service.py, agent/src/application/api_client.py, agent/src/camera/rtsp_client.py, agent/src/application/updater.py, agent/installer.iss, server/dashboard/src/pages/ClientDetail.tsx, server/dashboard/package.json
**Breaking Change:** Não. Clientes na 1.1.1 com GPU que retorna NaN não pingam e portanto não recebem OTA: atualizar manualmente.
**Branch:** isaque

---

### [2026-10-09] — Versão do agente 1.1.1

**Alteracao:** Versão do agente elevada para 1.1.1 (build com telemetria psutil/GPUtil do merge `helena`).
**Antes:** `CURRENT_VERSION = "1.1.0"`, `AppVersion=1.1.0`.
**Depois:** `CURRENT_VERSION = "1.1.1"`, `AppVersion=1.1.1`, dashboard `package.json` 1.1.1.
**Arquivos:** agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json
**Breaking Change:** Não. Requer build (`agent/build.ps1`), GitHub Release v1.1.1 e registro no OTA Manager.
**Branch:** isaque

---

### [2026-10-07] — Merge Seletivo da Branch `helena` (Câmeras RTSP)

**Alteracao:** Adicionado suporte ao tipo `CAMERA` e roteador de testes de preview de imagem RTSP.
**Antes:** A branch `helena` tentou alterar novamente o fuso horário para UTC no banco e alterar as portas/volumes do Docker, violando o ADR-001 e a REGRA-001.
**Depois:** Foi realizado o "cherry-pick" manual focando apenas no Dashboard e nas rotas de teste RTSP. O banco permanece Naive e os Contratos intactos.
**Arquivos Adicionados/Modificados:** `server/api/routers/rtsp_test.py`, `server/api/schemas.py`, `server/api/requirements.txt`, Componentes React (Frontend).
**Breaking Change:** Não.
**Branch:** isaque

---

### [2026-10-07] — Merge Seletivo da Branch `helena` (Intelbras Defense)

**Alteracao:** Adicionado suporte ao Intelbras Defense e scripts acessórios, além da função de Lixeira de clientes.
**Antes:** A branch `helena` possuía quebras de contrato de banco (`docker-compose.yml`) e datetime que impossibilitavam o merge.
**Depois:** Foi realizado um "cherry-pick" manual arquitetural. Arquivos perigosos de infra e modelos foram bloqueados de acordo com a REGRA-001 e a sanidade do Proxy. As features de VMS e Storage (Lixeira) foram incorporadas com segurança.
**Arquivos Adicionados/Modificados:** `agent/src/vms/defense.py`, `server/api/schemas.py`, `server/api/services/storage_service.py`, `server/api/routers/clients.py`
**Breaking Change:** Não.
**Branch:** isaque

---

### [2026-10-07] — OTA do TrilanAgentTray.exe

**Alteracao:** Suporte a atualizacao do Tray via OTA
**Antes:** check_and_apply_update() so baixava TrilanAgentService.exe
**Depois:** Baixa tambem TrilanAgentTray.exe (opcional) se url_tray + sha256_tray forem fornecidos
**Arquivos:** agent/src/application/updater.py, server/api/schemas.py, server/dashboard/src/pages/Settings.tsx
**Breaking Change:** Nao (retrocompativel)
**Branch:** isaque | **Commit:** dcef965

---

### [2026-10-07] — Logs em Tempo Real no Tray

**Alteracao:** Menu do Tray agora abre PowerShell com log em tempo real
**Antes:** Abria servico.log no Notepad (estatico)
**Depois:** Abre janela PowerShell com `Get-Content -Wait -Tail 50`
**Arquivos:** agent/tray.py
**Breaking Change:** Nao
**Branch:** isaque | **Commit:** dcef965

---

### [2026-10-07] — Rollback do merge com a branch `helena`

**Alteracao:** Revertido para commit da6dc80 antes do merge
**Motivo:** Erros 500 em producao por migracao de datetime para TIMESTAMP WITH TIME ZONE
**Antes:** Codigo pos-merge com alteracoes de timezone da helena
**Depois:** Codigo revertido ao estado estavel anterior
**Breaking Change:** Sim (reverteu features da helena)
**Branch:** isaque | **Commit:** da6dc80 (reset)

---

### [2026-10-08] — Galeria de Imagens de Câmeras (NVR) Lado a Lado

**Alteracao:** Implementado sistema completo para salvar "Perfect Image" e extrair automaticamente "Night Image" das câmeras de NVR. Limitado para Hikvision/Intelbras para garantir estabilidade.
**Antes:** As câmeras atreladas aos NVRs apenas recebiam mapeamento em texto dos dias gravados.
**Depois:** Banco de dados recebe tabela `nvr_cameras`. UI do Dashboard agora possui a Galeria (Botão "Galeria" no Card do NVR). Agente extrai a imagem noturna usando o endpoint RTSP de Playback (02:00:00 da última gravação válida) logo após verificar as gravações do NVR.
**Arquivos:** `server/api/models.py`, `server/api/schemas.py`, `server/api/routers/equipamentos.py`, `server/api/routers/agent.py`, `agent/src/camera/rtsp_client.py`, `agent/src/application/backup_job.py`, `server/dashboard/src/pages/ClientDetail.tsx`
**Breaking Change:** Não
**Branch:** isaque

---

### [2026-10-09] — Correcao da edicao de versoes OTA no Dashboard

**Alteracao:** `Settings.tsx` chamava `PUT /api/v1/admin/agent-versions/{id}` (plural, rota inexistente) via `fetch` cru, sem `API_BASE`, exibindo sucesso mesmo com 404.
**Depois:** Usa `editAgentVersion` de `api/client.ts` (`PUT /admin/agent-version/{id}`). IC-005 encerrado.
**Arquivos:** `server/dashboard/src/pages/Settings.tsx`
**Breaking Change:** Nao
**Branch:** isaque

---

### [2026-10-09] — Sincronizacao do "Ultimo contato" com o ping

**Alteracao:** `ping_agent` setava `last_seen` mas o `db.refresh(client)` do long-polling descartava o valor antes do commit; "Ultimo contato" so atualizava em `/agent/config`.
**Depois:** `last_seen` e commitado logo no inicio do ping. Dashboard calcula "Proximo contato" com intervalo de 15s (antes 5 min) e contagem regressiva continua usando o skew do relogio do servidor.
**Arquivos:** `server/api/routers/agent.py`, `server/dashboard/src/pages/ClientDetail.tsx`, `server/dashboard/src/api/types.ts`
**Breaking Change:** Nao
**Branch:** isaque

---

### [2026-10-09] — Merge auditado da branch `helena` (isaque_repo/helena @ 13f066c)

**Tipo:** merge real (`git merge --no-ff`) com resolução seletiva, auditado contra este documento.

**Incorporado:**
- Telemetria do agente (CPU, RAM, disco, rede por placa, GPU) enviada no body do ping; coluna `clients.telemetry` (JSON) via migração inline (REGRA-007); card "Saúde do Servidor" no ClientDetail.
- Importação de câmeras via CSV robusto (aspas, `;`/`,`) e XLSX (`xlsx` 0.18.5), mapeamento dinâmico de colunas, limpeza de `\0`, botão "Apagar Câmeras".
- `service.py`: inicia webhooks Digifort/Defense conforme equipamentos; se iniciou sem servidor, reinicia ao reconectar para buscar config; restart via `ping -n 4` (o `timeout` falha sem console no contexto de serviço).
- `backup_job.py`: equipamentos `CAMERA` ignorados no backup automático.
- `.agents/rules/git-deploy.md`: nome correto do repo secundário.

**Bloqueado / ajustado na resolução:**
- `docker-compose.yml`: porta `7005` e volume `pg_data_local` **rejeitados** (o volume novo apontaria produção para um banco vazio). Mantido `7001` + `pg_data`.
- `datetime.now(timezone.utc).replace(tzinfo=None)` em `models.py`/`agent.py` revertido para `datetime.utcnow()` (REGRA-001 / ADR-001).
- `routers/rtsp_test.py` + `numpy`/`opencv` no servidor: **rejeitados** — sem consumidor no frontend, o container não alcança a LAN do cliente, credencial padrão hardcoded; o teste RTSP já é feito pelo agente.
- `numpy`/`opencv` no agente: removidos (agente usa `imageio-ffmpeg` desde a v1.0.8).
- `webhook_defense.py`: versão de debug (POST não registrava evento) rejeitada.
- `vms/defense_api.py`: esqueleto com TODOs, não referenciado — não incorporado.
- Scripts avulsos/backup (`fix.py`, `resolve.py`, `patch_client_detail*.py`, `insert_cameras.py`, `scratch_test*`, `clientdetail.bak`, `cameras.csv`) não incorporados.
- `service.py`: corrigido mojibake (`â€”`, `Ã£`) inclusive no `_svc_display_name_`; `config_extra` nulo não derruba mais a carga de config (evita restart em loop).
- Ping: `last_seen` e `telemetry` commitados antes do long-polling (5s), preservando a correção anterior.

**Breaking Change:** Não (body do ping é opcional; agentes antigos continuam funcionando).
**Requer:** nova build do agente para enviar telemetria.
**Branch:** isaque

---

## 17. Fluxo de Atualização de Versão (Release)

Quando uma nova versão do Agente Trilan for lançada, certifique-se de atualizar o número da versão nos seguintes arquivos:

1. **`server/dashboard/package.json`**: Propriedade `"version"`.
2. **`agent/src/application/updater.py`**: Variável `CURRENT_VERSION`.
3. **`agent/installer.iss`**: Propriedades `AppVersion` e `OutputBaseFilename` (para controle e nome do executável do InnoSetup).
