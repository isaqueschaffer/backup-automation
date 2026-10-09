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
├── agent/
│   ├── service.py               <- Entry point do serviço Windows
│   ├── tray.py                  <- Entry point do app de bandeja
│   ├── agent.py                 <- Orquestrador de backup
│   ├── agent.conf               <- Configuração local do agente
│   ├── requirements.txt
│   ├── src/
│   │   ├── application/
│   │   │   ├── api_client.py    <- HTTP client para o servidor
│   │   │   └── updater.py       <- Lógica de auto-atualização OTA
│   │   ├── nvr/
│   │   │   ├── factory.py       <- Detecta tipo de NVR e orquestra busca
│   │   │   ├── hikvision/       <- Integração Hikvision (NVR/DVR)
│   │   │   └── motorola/        <- Integração Motorola
│   │   ├── olt/                 <- Integração OLT
│   │   ├── pabx/                <- Integração PABX
│   │   ├── mikrotik/            <- Integração Mikrotik
│   │   └── core/config.py       <- Lê agent.conf
│   └── dist/                    <- EXEs compilados
│       ├── TrilanAgentService.exe
│       └── TrilanAgentTray.exe
├── server/
│   ├── .env                     <- Configuração de produção (NAO versionar)
│   ├── .env.example
│   ├── docker-compose.yml       <- Produção (Dokploy)
│   ├── api/
│   │   ├── main.py              <- FastAPI app + migracoes inline
│   │   ├── models.py            <- ORM SQLAlchemy
│   │   ├── schemas.py           <- Pydantic schemas
│   │   ├── auth.py              <- JWT + API Key auth
│   │   ├── database.py          <- Engine + SessionLocal
│   │   ├── config.py            <- Settings via pydantic-settings
│   │   └── routers/
│   │       ├── agent.py         <- /api/v1/agent/*
│   │       ├── agent_update.py  <- OTA endpoints
│   │       ├── clients.py       <- /api/v1/clients/*
│   │       ├── equipamentos.py  <- /api/v1/equipamentos/*
│   │       ├── nvrs.py          <- /api/v1/nvrs/* (compatibilidade)
│   │       ├── backups.py       <- /api/v1/backups/*
│   │       ├── settings_router.py
│   │       └── auth_router.py
│   └── dashboard/
│       └── src/
│           ├── pages/Settings.tsx   <- Gerenciador OTA
│           └── api/client.ts
└── .agents/                     <- Skills do Antigravity IDE
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
| POST | `/api/v1/agent/backup/upload/{backup_id}` | Agente faz upload do ZIP |
| GET | `/api/v1/agent/update-check` | Verifica se ha nova versao OTA |

### Endpoints de Admin (Bearer Token)

| Metodo | Path | Descricao |
|---|---|---|
| POST | `/api/v1/auth/login` | Login — retorna JWT |
| GET/POST | `/api/v1/clients` | Listar/criar clientes |
| GET/PUT/DELETE | `/api/v1/clients/{id}` | Detalhar/atualizar/deletar |
| POST | `/api/v1/clients/{id}/rotate-key` | Rotacionar API key |
| POST | `/api/v1/clients/{id}/trigger-backup` | Solicitar backup manual |
| POST | `/api/v1/clients/{id}/restart-agent` | Solicitar reinicio do agente |
| GET | `/api/v1/clients/{id}/logs` | Listar logs do agente |
| GET/POST | `/api/v1/equipamentos` | Listar/criar equipamentos |
| GET/PUT/DELETE | `/api/v1/equipamentos/{id}` | Gerenciar equipamento |
| GET | `/api/v1/backups` | Listar backups (paginado) |
| GET | `/api/v1/backups/{id}/download` | Download de ZIP |
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
  "version": "1.0.6",
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
| Motorola | MOTOROLA | src/nvr/motorola/ | HTTP |
| OLT | OLT | src/olt/ | SSH Paramiko |
| ONU | ONU | — | — |
| PABX | PABX | src/pabx/ | — |
| Mikrotik | MIKROTIK | src/mikrotik/ | SSH/API |
| Digifort | DIGIFORT | — | — |
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

---

## 15. Incompatibilidades Conhecidas

| ID | Componente | Incompatibilidade | Status |
|---|---|---|---|
| IC-001 | PostgreSQL + SQLAlchemy | datetime aware em coluna TIMESTAMP WITHOUT TIME ZONE | Contornado via REGRA-001 |
| IC-002 | PyInstaller + pystray | SyntaxWarning: return in a finally block | Inofensivo, warning apenas |
| IC-003 | PyInstaller + pycparser | pycparser.lextab e yacctab nao encontrados | Inofensivo, warning apenas |
| IC-004 | OTA Tray em agentes <=1.0.5 | Agentes antigos nao tem logica de download/substituicao do Tray | Conhecido e aceito |
| IC-005 | agent_update.py edit_version | PUT /api/v1/admin/agent-version/{id} nao aceitava url_tray e sha256_tray | Resolvido (schema `AgentVersionUpdate` inclui os campos; `Settings.tsx` usa `editAgentVersion` do `client.ts`) |

---

## 16. Architecture Changelog

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
