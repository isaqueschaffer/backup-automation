# PROJECT_SPEC.md
# Trilan Backups — Especificação Técnica e Fonte de Verdade

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
17. [Fluxo de Atualização de Versão (Release)](#17-fluxo-de-atualização-de-versão-release)

---

## 1. Visão Geral

**Nome:** Trilan NVR Backup Automation
**Propósito:** Sistema de backup automatizado de configurações de equipamentos de rede instalados em clientes (NVRs, DVRs, OLTs, PABXs, Mikrotiks, etc.).
**Modelo:** SaaS multi-tenant — um servidor central recebe dados de múltiplos agentes Windows instalados nos clientes. Desde 27/10/2026 com **multi-contas** (ADR-009): Integradores (Clientes → Máquinas) e Clientes finais (Setores → Máquinas), cada conta com plano e validade, isoladas entre si (REGRA-010).

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
| python-dotenv | 1.0.1 | Leitura do `.env` |
| pyzipper | 0.3.6 | ZIP com senha (ZIP unificado do Cliente) |

### Dashboard (Frontend)

| Dependência | Versão | Uso |
|---|---|---|
| React | 18.x | UI framework |
| TypeScript | 5.x | Tipagem |
| Vite | 5.x | Build tool |

### Agente Windows

| Dependência | Versão | Uso |
|---|---|---|
| Python | 3.14 (`py -3.14` no `build.ps1`; build atual com 3.14.8) via PyInstaller 6.22.3 | Runtime compilado |
| requests | ==2.34.2 | HTTP para API |
| pyzipper | ==0.4.0 | ZIP com senha AES-256 |
| pycryptodome | ==3.24.0 | Criptografia local |
| pywin32 | ==312 | Win32 API (serviço Windows); substitui o `pypiwin32`, que era só um invólucro antigo |
| pystray | ==0.19.5 | Ícone na bandeja do Windows |
| Pillow | ==12.3.0 | Renderização de ícone |
| paramiko | ==3.5.1 | SSH (para OLTs/Mikrotiks) |
| pyftpdlib | ==2.2.0 | FTP (para equipamentos que usam FTP) |
| imageio-ffmpeg | ==0.6.0 | ffmpeg embarcado (captura RTSP / imagem noturna) |
| psutil | ==7.2.2 | Telemetria (CPU, RAM, disco, rede) |
| GPUtil | ==1.4.0 | Telemetria de GPU (opcional, falha silenciosa) |
| pysnmp | ==7.1.30 | SNMPv2c: telemetria de NVR Intelbras (a faixa `<7` não tem `get_cmd`/`walk_cmd`) |
| openpyxl | ==3.1.5 | Planilhas da configuração dos NVR |

Desde a 1.1.34 todas as versões do `agent/requirements.txt` são fixas (`==`); atualizar uma dependência é trocar o número aqui e no arquivo.

---

## 3. Estrutura de Diretórios

```
trilan-nvr-backup-automation/
├── PROJECT_SPEC.md              <- ESTE ARQUIVO (fonte de verdade)
├── README.md                    <- Visão geral, ambiente local, testes, ramos e deploy
├── CLAUDE.md                    <- Regras de trabalho das IAs (merge, versão, deploy)
├── docs/
│   ├── CHANGELOG.md             <- Histórico de mudanças (antes seção 16 deste arquivo)
│   └── CONVENCOES.md            <- Glossário (conceito x código x tabela) e convenções de nomes e pastas
├── .github/workflows/ci.yml     <- CI: testes, tipos, build do painel e regras da auditoria de merge
├── .credenciais/                <- Credenciais locais das IAs (NÃO versionar; ignorada pelo .gitignore)
├── agent/                       <- Agente Windows (PyInstaller) e Linux (MikroTik container)
│   ├── service.py               <- Entry point do serviço Windows (ping em thread + loop principal)
│   ├── service_linux.py         <- Entry point do container no MikroTik
│   ├── tray.py                  <- Entry point do app de bandeja
│   ├── agent.py                 <- Orquestrador de backup (reexporta run_backup)
│   ├── agent.conf               <- Configuração local do agente (NAO versionar)
│   ├── agent.conf.example
│   ├── build.ps1                <- Gera os EXEs em dist/ (confere versão, roda testes; hidden-imports aqui)
│   ├── launcher_linux.py / pacote_linux.py / verificar_imagem.py <- container do MikroTik (OTA Linux, pacote, checagem da imagem)
│   ├── reiniciar_agentes.ps1    <- Pede o reinício de todos os agentes online (após cadastrar versão)
│   ├── ferramentas/             <- Ferramentas avulsas (fotos da facial Intelbras, teste de OLTs); fora do produto
│   ├── publish_version.ps1
│   ├── installer.iss            <- Instalador Inno Setup (versão do agente)
│   ├── requirements.txt
│   ├── requirements-linux.txt
│   ├── Dockerfile.mikrotik      <- Imagem ARMv7 do agente no MikroTik
│   ├── mikrotik/                <- Imagem do container (anexo de release) e scripts RouterOS (setup.rsc)
│   ├── dist/                    <- EXEs compilados (NAO versionados; vão na release do GitHub e são cadastrados no painel)
│   └── src/
│       ├── application/
│       │   ├── api_client.py    <- HTTP client para o servidor (ping, upload, telemetria)
│       │   ├── backup_job.py    <- Orquestra o backup por equipamento + captura da imagem da noite
│       │   ├── updater.py       <- Auto-atualização OTA (CURRENT_VERSION)
│       │   ├── estado.py        <- Flag `backup_em_andamento`, compartilhada entre as threads do backup e do ping
│       │   ├── webhook_defense.py / webhook_digifort.py
│       ├── backup/              <- archiver, crypto, downloader, file_manager/
│       ├── camera/rtsp_client.py<- Teste RTSP, referência ideal e imagem da noite (ffmpeg)
│       ├── core/config.py       <- Lê agent.conf (ConfigError, parse_config_extra)
│       ├── nvr/
│       │   ├── factory.py       <- Detecta tipo de NVR e orquestra busca/gravação
│       │   ├── planilha_comum.py<- Estilo, abas e aba 'Câmeras (completo)' das planilhas de configuração dos NVR
│       │   ├── hikvision/       <- NVR/DVR Hikvision (ISAPI; telemetria CPU/RAM/discos; planilha .xlsx)
│       │   ├── intelbras/       <- NVR Intelbras: telemetria por SNMP; planilha .xlsx pelo CGI Dahua (câmeras e gravações usam o ISAPI de hikvision/)
│       │   └── motorola/        <- NVR Motorola/NVMS-9000 (cameras, recordings, queryChlRecLog, telemetry, planilha .xlsx)
│       ├── olt/                 <- huawei_active, unm2000, vsol
│       ├── pabx/issabel.py
│       ├── mikrotik/routeros.py
│       ├── vms/defense.py       <- Intelbras Defense
│       └── utils/               <- http.py, xml_parser.py
├── server/
│   ├── .env                     <- Configuração de produção (NAO versionar)
│   ├── .env.example / .env.local.example
│   ├── docker-compose.yml       <- Referência dos serviços (NÃO é lido pelo Dokploy; ver seção 11)
│   ├── docker-compose.local.yml <- Desenvolvimento local
│   ├── nginx/nginx.conf
│   ├── deploy_producao.ps1      <- Leva a isaque para a produção (ramo producao + deploy no Dokploy)
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
│   │   │   ├── nvrs.py          <- legado: ativo (JWT) mas oculto do OpenAPI (`include_in_schema=False`), sem chamador no painel nem no agente (candidato a remoção)
│   │   │   ├── backups.py       <- /api/v1/backups/*
│   │   │   ├── dashboards.py    <- /api/v1/clients/{id}/dashboard/* e /api/v1/dashboards/widgets (admin, JWT)
│   │   │   ├── public_dashboard.py <- /api/v1/public/dashboard/* (só X-Dashboard-Token)
│   │   │   ├── settings_router.py / auth_router.py
│   │   ├── services/            <- crypto_service, email_service, storage_service, galeria_vms, backup_runs (rodadas de backup do Cliente: abertura, fechamento, e-mail e ZIP unificado)
│   │   │   └── dashboards/      <- registro, widgets, layout, dados, compartilhamento (token/limitador), esquemas
│   │   └── tests/
│   └── dashboard/               <- React + Vite + TypeScript
│       ├── Dockerfile / nginx-spa.conf
│       └── src/
│           ├── api/             <- client.ts (axios), dashboards.ts (dashboards, inclusive o cliente HTTP do link público) e types.ts
│           ├── components/ / utils/date.ts
│           └── pages/
│               ├── Customers/       <- CustomersPage (/clientes), CustomerDetail/ (/clientes/:id, fila arrastar-e-soltar)
│               ├── Machines/        <- MachinesPage (/maquinas), MachineDetail/ (/maquinas/:id)
│               ├── Dashboards/      <- editor e visão do cliente: DashboardWorkspace, widgets/ (registro), SharePanel, DashboardAdminPage (/clientes/:id/dashboard), PublicDashboardPage (/d)
│               └── Backups.tsx / Overview/ (Visão Geral personalizável) / Settings.tsx
├── tools/                       <- Utilitários avulsos e testes e2e (não entram em build nem deploy); verificar_regras.py roda no CI
├── archive/                     <- Material antigo, só consulta: legacy_scripts/, fiberhome-zabbix/, relatorios/, whatsapp/
├── .agents/                     <- Antigravity (agy): rules/, skills/, agents/
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
[Servidor Dokploy]  (produção: Applications separados, ver seção 11)
    Backend  (/server/api, FastAPI)  --->  Postgres do Dokploy (nome interno)
    Frontend (/server/dashboard, React)
```

No ambiente local (`docker-compose.local.yml`) o layout é outro: Nginx na porta 7001 com `/api/*` -> FastAPI (8000) e `/*` -> Dashboard (80), Postgres na 5432 interna.

### Fluxo do Agente

1. Ao iniciar: lê `agent.conf`, chama `GET /api/v1/agent/config` para obter configuração
2. A cada 15 segundos: `POST /api/v1/agent/ping` — heartbeat + recebe flags de controle (long-polling de ate 5s no servidor; `last_seen` e commitado no inicio do ping). Agente considerado online se `last_seen` < 180s. A tarefa RTSP do painel (`rtsp_task`) e disparada na propria thread de ping (agente >= 1.1.34), para responder mesmo durante um backup. O `servico.log` so registra pings com instrucao, a volta do servidor e as falhas (a primeira e depois no maximo uma linha a cada 10 min)
3. No horário agendado (ou quando flag `backup=true` no ping): executa backup completo
4. Após backup: `POST /api/v1/agent/backup/report` + `POST /api/v1/agent/backup/upload/{id}`
5. A cada hora (dentro do ciclo de ping): `GET /api/v1/agent/update-check` — verifica OTA. O servidor oferece a atualização à mesma máquina no máximo 1 vez por hora (em memória). Depois de baixar, o serviço avisa "parado" ao Windows e sai com `os._exit(0)` (agente >= 1.1.35); o `apply_update.bat` espera até ~45 s o processo antigo sair e, se não sair, encerra `TrilanAgentService.exe` à força (sem `/T`) antes de copiar

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
| api_key_hash | VARCHAR(255) | str | NOT NULL UNIQUE | — |
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
| group_id | UUID | uuid.UUID (ORM: `customer_id`) | NULL | — (FK `client_groups.id` ON DELETE SET NULL; Cliente da máquina) |
| queue_order | INTEGER | int | NOT NULL | 0 (posição na fila de backup do Cliente) |
| conta_id | UUID | uuid.UUID | NULL | — (FK `contas.id` ON DELETE RESTRICT; conta dona; preenchida no startup) |

#### `client_groups` (Clientes — empresas atendidas; model `Customer`, ADR-007)

| Coluna | Tipo SQL | Tipo Python | Nullable | Padrao |
|---|---|---|---|---|
| id | UUID | uuid.UUID | NOT NULL | uuid4 |
| name | VARCHAR(255) | str | NOT NULL | — |
| description | TEXT | str | NULL | — |
| active | BOOLEAN | bool | NOT NULL | TRUE |
| backup_hour / backup_minute | INTEGER | int | NULL | 2 / 0 (horário herdado pelas máquinas vinculadas) |
| queue_active | BOOLEAN | bool | NOT NULL | FALSE (fila sequencial de backup em andamento) |
| queue_current_index | INTEGER | int | NULL | — (posição atual na fila) |
| email_to | ARRAY(VARCHAR) | List[str] | NOT NULL | [] (destinatários do e-mail único por rodada) |
| zip_password | TEXT | str | NULL | — (Fernet; NULL = ZIP do Cliente sem senha) |
| created_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NOT NULL | utcnow() |
| conta_id | UUID | uuid.UUID | NULL | — (FK `contas.id` ON DELETE RESTRICT; conta dona do Cliente/Setor) |

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
| olt_status | JSON | dict | NULL | OLT UNM2000: `{"atualizado_em", "olts": [...]}` enviado pelo agente a cada 5 min (Telnet) |
| olt_notificar | JSON | dict | NULL | OLT: avisos ligados `{"onu_offline": bool, "sinal_critico": bool}` (opt-in; vazio = desligados) |
| olt_alertas | JSON | dict | NULL | OLT: estado dos alertas `{"onu": {chave: desde}, "sinal": {chave: desde}, "avisadas": {categoria: {olt: [chaves]}}}` (chave = `<OLT>|<índice ou slot/pon/onu>`, datas naive em UTC) |
| antena_status | JSON | dict | NULL | ANTENA: `{"atualizado_em", "erro", "mikrotik": {identidade, ip, dispositivos}, "antenas": [...], "descobertas": [...]}` enviado pelo agente a cada 3 min (SSH no MikroTik + ping) |
| conexao_status | JSON | dict | NULL | Último "Testar conexão": `{"ok", "mensagem", "etapas": [{"id", "rotulo", "estado", "detalhe"}], "segundos", "testado_em"}` (`testado_em` naive em UTC) |
| active | BOOLEAN | bool | NOT NULL | TRUE |
| updated_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NULL | NOW() |

#### `nvr_cameras` (galeria de câmeras de um equipamento; model `NVRCamera`)

| Coluna | Tipo SQL | Tipo Python | Nullable | Notas |
|---|---|---|---|---|
| id | UUID | uuid.UUID | NOT NULL | PK |
| nvr_id | UUID | uuid.UUID | NOT NULL | FK `nvrs.id` ON DELETE CASCADE |
| canal | INTEGER | int | NOT NULL | Canal do NVR (em DIGIFORT/DEFENSE, número na galeria) |
| nome | VARCHAR(255) | str | NOT NULL | — |
| ip / username | VARCHAR(50) / VARCHAR(100) | str | NULL | Conexão RTSP individual (DIGIFORT e DEFENSE; NULL em NVR comum) |
| password | TEXT | str | NULL | Fernet quando preenchida (REGRA-004) |
| modelo | VARCHAR(50) | str | NULL | Hikvision, Intelbras, Grandstream, ONVIF, Motorola |
| canal_rtsp | INTEGER | int | NULL | Canal da câmera dentro do equipamento do IP; obrigatório na prática quando o mesmo IP é usado por 2 ou mais câmeras da Galeria (gravador/encoder com vários canais) |
| pasta_gravacao | VARCHAR(255) | str | NULL | DIGIFORT: pasta de gravação da câmera (chave do vínculo; aprendida pelo nome igual no relatório; a câmera pode ser renomeada depois) |
| perfect_image_base64 | TEXT | str | NULL | Imagem de referência |
| night_image_base64 / night_image_date | TEXT / TIMESTAMP WITHOUT TIME ZONE | str / datetime naive | NULL | Imagem da noite e data |
| updated_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NULL | utcnow() |

A tabela nasce por `Base.metadata.create_all` (`main.py`); as colunas `ip`, `username`, `password`, `modelo`, `canal_rtsp` e `pasta_gravacao` vêm da migração inline.

#### `nvr_planilhas` (última planilha importada na Galeria de um equipamento DIGIFORT/DEFENSE; model `NVRPlanilha`)

| Coluna | Tipo SQL | Tipo Python | Nullable | Notas |
|---|---|---|---|---|
| id | UUID | uuid.UUID | NOT NULL | PK |
| nvr_id | UUID | uuid.UUID | NOT NULL | FK `nvrs.id` ON DELETE CASCADE, UNIQUE (1 planilha por equipamento) |
| nome_arquivo | VARCHAR(255) | str | NOT NULL | Nome original do arquivo (CSV/XLSX) |
| linha_cabecalho | INTEGER | int | NOT NULL | Índice da linha do cabeçalho (0-based) |
| total_linhas | INTEGER | int | NOT NULL | Quantidade de linhas na planilha |
| dados | TEXT | str | NOT NULL | Matriz de células em JSON criptografada com Fernet (REGRA-004) |
| importado_em | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NOT NULL | Data/hora de importação (utcnow) |

A tabela nasce por `Base.metadata.create_all` (`main.py`), sem migração inline.

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
| run_id | UUID | uuid.UUID | NULL | FK `customer_backup_runs.id` ON DELETE SET NULL; rodada do Cliente (só máquinas com Cliente) |

#### `customer_backup_runs` (rodadas de backup do Cliente: 1 e-mail por rodada)

| Coluna | Tipo SQL | Tipo Python | Nullable | Notas |
|---|---|---|---|---|
| id | UUID | uuid.UUID | NOT NULL | PK |
| customer_id | UUID | uuid.UUID | NOT NULL | FK `client_groups.id` ON DELETE CASCADE |
| trigger | VARCHAR(30) | str | NOT NULL | scheduled / queue / manual_machine |
| started_at / deadline_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NOT NULL | Início e prazo (`RUN_DEADLINE_HOURS`) |
| closed_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NULL | Preenchido ao fechar a rodada (fechamento por UPDATE condicional) |
| status | VARCHAR(20) | str | NOT NULL | EM_ANDAMENTO / OK / PARCIAL / ERRO |
| expected_machine_ids | JSON | list | NOT NULL | Ids (UUID em texto) das máquinas esperadas |
| email_sent | BOOLEAN | bool | NOT NULL | FALSE |
| created_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NOT NULL | utcnow() |

#### `agent_logs`

| Coluna | Tipo SQL | Tipo Python | Nullable | Notas |
|---|---|---|---|---|
| id | UUID | uuid.UUID | NOT NULL | PK |
| client_id | UUID | uuid.UUID | NOT NULL | FK clients.id CASCADE DELETE |
| event_type | VARCHAR(50) | str | NOT NULL | ping, backup_trigger, ping_recovery, agent_log... |
| message | TEXT | str | NOT NULL | — |
| nivel | VARCHAR(10) | str | NOT NULL | `INFO` (padrão), `WARNING` ou `ERROR` |
| equipamento | VARCHAR(255) | str | NULL | Nome do equipamento a que o log se refere (null = log geral da máquina) |
| created_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NOT NULL | Retenção: ver REGRA-006. Índice `(client_id, created_at)` |

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
| layout | JSON | dict | NOT NULL | `{schema_version: 3, filtros:{periodo}, widgets:[{id, tipo, titulo, x, y, largura, altura, config}]}` (grade de 24 colunas × linhas de 31 px; o schema 2 é migrado ao ler) validado por `services/dashboards/layout.py` |
| version | INTEGER | int | NOT NULL | +1 a cada gravação do layout (409 em edição concorrente) |
| share_token_hash | VARCHAR(64) | str | NULL UNIQUE | SHA-256 do token do link; o token em texto puro nunca é gravado |
| share_enabled | BOOLEAN | bool | NOT NULL | Link ativo |
| share_expires_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NULL | Validade (UTC) |
| share_allow_edit | BOOLEAN | bool | NOT NULL | O visitante do link pode salvar o layout |
| share_created_at / last_viewed_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NULL | — |
| created_at / updated_at | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NOT NULL | utcnow() |

#### `planos`

| Coluna | Tipo SQL | Tipo Python | Nullable | Padrao |
|---|---|---|---|---|
| id | UUID | uuid.UUID | NOT NULL | gen_random_uuid() |
| nome | VARCHAR(60) | str | NOT NULL UNIQUE | — |
| duracao_dias | INTEGER | int | NOT NULL | — (CheckConstraint: `duracao_dias > 0`) |
| ativo | BOOLEAN | bool | NOT NULL | TRUE |
| criado_em | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NOT NULL | utcnow() |

#### `contas` (inquilinos — model `Conta`)

| Coluna | Tipo SQL | Tipo Python | Nullable | Padrao |
|---|---|---|---|---|
| id | UUID | uuid.UUID | NOT NULL | gen_random_uuid() |
| nome | VARCHAR(255) | str | NOT NULL | — |
| tipo | VARCHAR(20) | str | NOT NULL | — (CheckConstraint: `tipo IN ('INTEGRADOR', 'CLIENTE_FINAL')`) |
| documento | VARCHAR(20) | str | NULL | — (CNPJ/CPF, só dígitos) |
| email_contato | VARCHAR(255) | str | NULL | — |
| telefone | VARCHAR(30) | str | NULL | — |
| plano_id | UUID | uuid.UUID | NULL | — (FK `planos.id` ON DELETE SET NULL) |
| expira_em | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NULL | — (UTC; NULL = sem validade) |
| ativo | BOOLEAN | bool | NOT NULL | TRUE (False = suspensa pela Trilan) |
| avisos_enviados | JSON | list | NOT NULL | [] (marcos de e-mail já enviados; zera ao renovar) |
| observacoes | TEXT | str | NULL | — |
| criado_em | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NOT NULL | utcnow() |

#### `conta_renovacoes`

| Coluna | Tipo SQL | Tipo Python | Nullable | Padrao |
|---|---|---|---|---|
| id | UUID | uuid.UUID | NOT NULL | gen_random_uuid() |
| conta_id | UUID | uuid.UUID | NOT NULL | — (FK `contas.id` ON DELETE CASCADE) |
| plano_id | UUID | uuid.UUID | NULL | — (FK `planos.id` ON DELETE SET NULL) |
| plano_nome | VARCHAR(60) | str | NOT NULL | — (cópia imutável do nome do plano) |
| dias | INTEGER | int | NOT NULL | — (dias adicionados/redefinidos) |
| expira_em_anterior | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NULL | — |
| expira_em_nova | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NOT NULL | — |
| feito_por | VARCHAR(255) | str | NULL | — (e-mail do usuário ou "admin") |
| criado_em | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NOT NULL | utcnow() |

#### `usuarios` (usuários do painel)

| Coluna | Tipo SQL | Tipo Python | Nullable | Padrao |
|---|---|---|---|---|
| id | UUID | uuid.UUID | NOT NULL | gen_random_uuid() |
| conta_id | UUID | uuid.UUID | NULL | — (FK `contas.id` ON DELETE CASCADE; NULL ⇔ SUPER_ADMIN) |
| nome | VARCHAR(255) | str | NOT NULL | — |
| email | VARCHAR(255) | str | NOT NULL UNIQUE | — (sempre minúsculo) |
| senha_hash | VARCHAR(255) | str | NOT NULL | — (bcrypt) |
| papel | VARCHAR(20) | str | NOT NULL | — (CheckConstraint: `papel IN ('SUPER_ADMIN', 'ADMIN', 'VISUALIZADOR', 'LEITURA')`) |
| ativo | BOOLEAN | bool | NOT NULL | TRUE |
| token_versao | INTEGER | int | NOT NULL | 1 (incrementa ao trocar senha/papel) |
| ultimo_login | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NULL | — |
| criado_em | TIMESTAMP WITHOUT TIME ZONE | datetime naive | NOT NULL | utcnow() |

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
- (Removida em 29/10/2026, agente 1.1.34) `routers/agent.py` (ping_agent) usava `timezone(timedelta(hours=-3))` na recuperacao de backup perdido; agora e tudo naive: `datetime.utcnow()` + `utc_offset_min` da maquina

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
- Gerado via `POST /api/v1/auth/login`: com `{email, password}` para usuário (`usuarios`, senha bcrypt) → JWT `{sub: <uuid do usuário>, tv: <token_versao>}`; com só `{password}` (`ADMIN_PASSWORD` ou `settings.admin_password_hash`) → administrador da plataforma legado, JWT `{sub: "admin"}` (usado pelo `agent/publish_version.ps1`; não remover)
- Expira em `ACCESS_TOKEN_EXPIRE_HOURS` (padrao 8h), algoritmo `HS256`
- Cada requisição recarrega o usuário (`get_contexto`, `auth.py`): inativo ou `tv` diferente de `token_versao` → 401 (trocar senha, papel ou desativar derruba os tokens já emitidos)
- Papéis: `SUPER_ADMIN` (plataforma, sem conta própria; escolhe a conta pelo header `X-Conta-ID`, sem ele fica na conta da plataforma — não existe visão "todas as contas" desde 29/10/2026), `ADMIN`, `VISUALIZADOR` (vê e roda testes, não altera) e `LEITURA` (de uma conta; `X-Conta-ID` é ignorado). Isolamento por conta: REGRA-010

**Agente Windows:** API Key + Client ID
- Headers: `X-Client-ID: <uuid>` + `X-API-Key: sk_trilan_<token>`
- Hash SHA-256 armazenado — chave raw nunca salva no banco
- Chave retornada UMA unica vez por geracao: na criacao da maquina e em cada `POST /api/v1/machines/{id}/rotate-key` (a nova chave invalida a anterior)

**NAO MISTURAR:** Nunca usar JWT para agentes, nem API Key para o dashboard.

**Dois esquemas restritos a rotas especificas** (o contrato dos dois acima nao muda):
- `X-Publish-Token` (`auth.py`, `verify_publish_or_admin`): so em `POST /api/v1/admin/agent-version`. E aceito no lugar do JWT quando `PUBLISH_TOKEN` esta definido no servidor (vazio = desativado; comparacao em tempo constante); sem o header, vale o JWT do admin. Nao da acesso ao painel nem as demais rotas admin.
- `X-Dashboard-Token` (`dsh_<token>`): so em `/api/v1/public/dashboard/*` (secao 7). Nao abre nenhuma rota administrativa.

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

### REGRA-006 — Retenção dos Logs do Agente (alterada em 29/10/2026)

A tabela `agent_logs` e podada por maquina (`services/agent_logs.py`, `podar_logs`), no ping e ao receber logs do agente:
- **Pings:** no maximo os 50 mais recentes (o ping nao conta no limite dos demais eventos).
- **Demais eventos** (`agent_log`, `ping_recovery`, filas, e-mails...): 30 dias, e no maximo 5000 por maquina.

Antes, o limite era de 50 logs por maquina incluindo ping, e um erro sumia em ~12 minutos (ping a cada 15 s).

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

### REGRA-010 — Isolamento por Conta (multi-contas)

**Decisao:** toda rota do painel enxerga só a conta de quem chama (ADR-009).

**Como fazer (rota nova ou alterada):**
- Receber `ctx: Contexto = Depends(get_contexto)` (`auth.py`). Rota só da plataforma: `Depends(exigir_super_admin)`; gestão de usuários da conta: `Depends(exigir_admin_conta)`.
- Buscar Cliente/Setor e Máquina por `obter_cliente(db, ctx, id)` e `obter_maquina(db, ctx, id)`; listas com `filtrar_por_conta(consulta, Model.conta_id, ctx)` (`services/escopo.py`). Equipamento, backup, rodada e dashboard chegam pela máquina ou pelo Cliente já validados.
- Recurso de outra conta = **404** com a mesma mensagem de "não encontrado" (nunca 403, para não revelar que existe).
- Todo `Customer(...)` e `Machine(...)` novo recebe `conta_id` (`conta_para_criacao(db, ctx)`, ou a conta do Cliente da máquina). Máquina e Cliente vinculados são sempre da mesma conta (409 se não forem).
- O bloqueio de escrita (conta vencida/suspensa ou usuário LEITURA/VISUALIZADOR → 403 em POST/PUT/PATCH/DELETE) já acontece dentro do `get_contexto`: não repetir nas rotas. Rota de **teste** que o VISUALIZADOR pode usar (não altera cadastro) usa `get_contexto_teste` no lugar.
- Rotas do agente continuam com `get_current_machine` (REGRA-003); a conta bloqueada é tratada por `maquina_bloqueada(machine)` (`services/contas.py`).

**NAO FAZER:** `db.query(Customer|Machine|Backup|NVR)` sem filtro de conta em rota do painel; usar `verify_admin_token` em rota nova de dados de conta (ele aceita só o super admin e existe por compatibilidade).

**Verificacao:** `server/api/tests/test_isolamento_contas.py` (Postgres local, `TRILAN_TESTE_ISOLAMENTO=1`). Acrescentar um caso a ele ao criar rota que exponha dados de conta.

---

## 7. Autenticação e Segurança

### Fluxo JWT (Admin)

```
POST /api/v1/auth/login { "email": "...", "password": "..." }   # usuário de conta ou super admin nomeado
POST /api/v1/auth/login { "password": "..." }                   # administrador da plataforma (senha única)
    -> 200 { "access_token": "...", "token_type": "bearer" }
    -> 401 "E-mail ou senha incorretos" | 429 depois de 10 erros por IP em 5 min

Requisicoes protegidas:
    Authorization: Bearer <access_token>
    X-Conta-ID: <uuid>      # opcional, só o super admin: conta em uso
GET /api/v1/auth/me -> { usuario, conta (status, validade, dias_restantes), somente_leitura, rotulos }
```

Senhas de usuários: bcrypt (`services/senhas.py`, `bcrypt==4.2.1` direto, sem `passlib`), de 10 a 72 bytes. Conta vencida pode entrar (fica somente leitura). Validade da conta e avisos: ADR-009.

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
| GET | `/api/v1/agent/config` | Retorna configuracao completa do cliente (`client_name` = nome da máquina; `customer_name` = nome do Cliente da máquina, opcional) |
| POST | `/api/v1/agent/ping` | Heartbeat; body opcional `{"telemetry": {...}}`; retorna flags `restart` e `backup`. A telemetria do agente >= 1.1.34 traz `utc_offset_min` (fuso local em minutos, ex.: -180), usado na recuperação de backup perdido (inteiro de -720 a 840; ausente ou inválido = -180). O agente >= 1.1.49 manda `versao` (ex.: `"1.1.49"`), gravada em `clients.agent_version` (cortada em 20 caracteres; ausente = mantém a anterior) e devolvida como `agent_version` nas respostas de máquina |
| POST | `/api/v1/agent/logs` | Agente envia lote (até 100) do seu log: `{"logs": [{"nivel": "INFO\|WARNING\|ERROR", "mensagem", "equipamento", "segundos_atras", "detalhe"}]}`; avisos, erros e marcos viram `agent_log`; linhas INFO comuns (`detalhe: true`) viram `agent_log_detalhe` (7 dias, até 20.000 por máquina); o servidor calcula `created_at` (REGRA-005); aceita também conta bloqueada |
| POST | `/api/v1/agent/backup/report` | Agente reporta resultado do backup. Equipamento com `status` ERRO e `cameras` nulo ou vazio (agente >= 1.1.34 manda `null` quando o equipamento não informou câmeras; os antigos mandam `[]`) não apaga `last_recording_status`: as câmeras conhecidas ficam com `status_comunicacao`/`status_gravacao` = `NAO_VERIFICADO` e `online` nulo |
| POST | `/api/v1/agent/backup/upload/{backup_id}` | Agente faz upload do ZIP (limite `MAX_UPLOAD_MB`, 413 acima) |
| PUT | `/api/v1/agent/backup/upload-stream/{backup_id}` | Agente do Mikrotik envia o ZIP em pedaços (túnel, sem arquivo no agente); mesmas regras do upload; conexão caída não grava nada |
| POST | `/api/v1/agent/backup/{backup_id}/resultado` | Agente do Mikrotik corrige o status de um equipamento do relatório (o envio em túnel sai depois dele) |
| GET | `/api/v1/agent/update-check` | Verifica se ha nova versao OTA (maior versao ativa). A mesma máquina recebe `has_update: true` no máximo 1 vez por hora (`INTERVALO_OFERTA_ATUALIZACAO`, em memória; reiniciar a API zera). Com `OTA_PILOTO_MAQUINAS` preenchido, só essas máquinas recebem. Para `current_version` < 1.1.35, `version` leva também os comandos que encerram o processo antigo (ver changelog de 30/10/2026). `plataforma=linux` (agente do Mikrotik, >= 1.1.52): só versões com `url_linux`/`sha256_linux`, e a resposta traz só esses campos |
| POST | `/api/v1/agent/rtsp-result` | Agente devolve o resultado da tarefa RTSP do dashboard |
| POST | `/api/v1/agent/conexao-progresso` | Agente (>= 1.1.44) envia o estado inteiro do "Testar conexão" a cada etapa: `{"task_id", "etapas": [...], "concluido", "ok", "mensagem"}`; ao concluir grava `nvrs.conexao_status` (só equipamento DA máquina). O pedido chega no ping como `conexao_task` (o equipamento como em `/agent/config` + `task_id`) e só para o agente que manda `"recursos": ["teste_conexao"]` no corpo do ping |
| POST | `/api/v1/agent/nvr-cameras/night-image` | Agente envia a imagem da noite de um canal |
| POST | `/api/v1/agent/defense/alarmes/comando-resultado` | Agente (>= 1.1.44) devolve o resultado do `alarme_task` recebido no ping: `{"sucesso", "mensagem"}` |
| POST | `/api/v1/agent/defense/alarmes/status` | Agente envia o status das centrais de alarme dos DEFENSE da máquina: `{"equipamentos": [{"nome", "ip", "erro", "alarmes": [...]}]}`; grava `nvrs.last_alarm_status` e já verifica as notificações ALARME; 403 com conta bloqueada |
| POST | `/api/v1/agent/olt/status` | Agente (>= 1.1.38) envia o status das OLTs das UNM2000 da máquina: `{"equipamentos": [{"nome", "olts": [...]}]}` (até 50 equipamentos e 100 OLTs); grava `nvrs.olt_status` só em equipamento OLT ativo DA máquina; 403 com conta bloqueada |

### Endpoints de Admin (Bearer Token)

Todas as rotas de dados abaixo (máquinas, equipamentos, Clientes/Setores, dashboards, backups, `/stats`) são isoladas pela conta do usuário (REGRA-010); as marcadas **(plataforma)** aceitam só o super admin.

| Metodo | Path | Descricao |
|---|---|---|
| POST | `/api/v1/auth/login` | Login — retorna JWT (`{email, password}` ou só `{password}` para o administrador da plataforma) |
| GET | `/api/v1/auth/me` | Usuário, conta (status, validade), `somente_leitura` e rótulos ("Cliente" ou "Setor") |
| POST | `/api/v1/auth/trocar-senha` | Troca a própria senha (devolve token novo; vale com a conta bloqueada) |
| GET | `/api/v1/conta` | Minha conta: plano, validade e histórico de renovações |
| GET/POST/PUT | `/api/v1/conta/usuarios` · `/{id}` | Usuários da conta (só ADMIN da conta ou super admin com `X-Conta-ID`; 409 ao tirar o último ADMIN ativo) |
| GET/POST/PUT | `/api/v1/admin/planos` · `/{id}` | **(plataforma)** Planos (nome + dias); sem DELETE, desativar com `ativo=false` |
| GET/POST | `/api/v1/admin/contas` | **(plataforma)** Listar contas (com status e totais) / criar conta com o primeiro ADMIN (validade = hoje + dias do plano) |
| GET/PUT | `/api/v1/admin/contas/{id}` | **(plataforma)** Detalhe com histórico / editar dados e ajustar `expira_em` à mão |
| POST | `/api/v1/admin/contas/{id}/renovar` · `/suspender` · `/reativar` | **(plataforma)** Renovar (maior entre agora e a validade atual + dias do plano) / suspender / reativar; 409 na conta da plataforma |
| POST | `/api/v1/admin/clientes/{id}/mover-conta` | **(plataforma)** Move o Cliente/Setor e as máquinas dele para outra conta (409 com fila ativa) |
| GET/POST/PUT | `/api/v1/admin/super-admins` · `/{id}` | **(plataforma)** Administradores da plataforma com e-mail e senha |
| GET/POST | `/api/v1/machines` | Listar (filtros `customer_id`, `unassigned`) / criar máquina (`customer_id` opcional) |
| GET/PUT/DELETE | `/api/v1/machines/{id}` | Detalhar/atualizar/deletar máquina |
| POST | `/api/v1/machines/{id}/rotate-key` | Rotacionar API key |
| POST | `/api/v1/machines/{id}/trigger-backup` | Solicitar backup manual |
| POST | `/api/v1/machines/{id}/restart-agent` | Solicitar reinicio do agente |
| POST | `/api/v1/machines/trigger-backup-all` · `/restart-agent-all` | Ação em massa nas máquinas online (`{queued, skipped_offline}`) |
| GET | `/api/v1/machines/{id}/logs` | Listar logs do agente (`incluir_pings=false` oculta os eventos `ping`; `nivel` = lista de `INFO,WARNING,ERROR`; `q` = busca no texto; `equipamento` = nome exato; `limit` 1 a 500, padrão 50) |
| GET/POST | `/api/v1/machines/{id}/equipamentos` | Listar/criar equipamentos da máquina |
| GET/PUT/DELETE | `/api/v1/machines/{id}/equipamentos/{eq_id}` | Gerenciar equipamento |
| POST | `/api/v1/machines/{id}/equipamentos/{eq_id}/test-rtsp` | Tarefa RTSP via agente (409 se já houver uma pendente) |
| POST | `/api/v1/machines/{id}/equipamentos/{eq_id}/testar-conexao` | "Testar conexão": volta na hora com `{task_id, etapas, concluido, ok, mensagem, segundos}`; máquina offline = `concluido` com erro e `task_id` nulo; teste em andamento do mesmo equipamento é reaproveitado |
| GET | `/api/v1/machines/{id}/equipamentos/{eq_id}/testar-conexao/{task_id}` | Andamento do teste (o painel consulta a cada 1 s); 404 se expirou (10 min) ou a API reiniciou. Prazos: 45 s para o agente buscar o pedido, 25 s para a primeira resposta, 5 min no total |
| GET | `/api/v1/machines/{id}/equipamentos/{nvr_id}/cameras` | Galeria do NVR (une `nvr_cameras` + `last_recording_status`) |
| POST | `/api/v1/machines/{id}/equipamentos/{nvr_id}/alarmes/comando` | Arma/desarma uma central de alarme do DEFENSE pelo agente (`{"central_id", "acao": "ARMAR"|"DESARMAR"}` → `{"sucesso", "mensagem"}`; espera até 75 s; 409 com agente offline ou outro comando em andamento; ADMIN/super admin; registrado nos logs da máquina) |
| GET | `/api/v1/machines/{id}/equipamentos/{nvr_id}/alarmes` | Último status das centrais de alarme de um DEFENSE (`last_alarm_status`; vazio `{"atualizado_em": null, "alarmes": []}` se ainda não chegou) |
| GET | `/api/v1/machines/{id}/equipamentos/{nvr_id}/olt-status` | Último status das OLTs/ONUs de uma UNM2000 (`olt_status`; vazio `{"atualizado_em": null, "olts": []}` se ainda não chegou) |
| POST | `/api/v1/machines/{id}/equipamentos/{nvr_id}/cameras/perfect-image` | Salvar imagem de referência |
| POST | `/api/v1/machines/{id}/equipamentos/{nvr_id}/cameras/import` | Importar câmeras para a galeria (lista `cameras` lida do CSV/XLSX pelo painel) ou, com `sync_from_machine=true`, copiar as câmeras avulsas (tipo `CAMERA`) da máquina |
| PUT/DELETE | `/api/v1/machines/{id}/equipamentos/{nvr_id}/cameras/{canal}` | Editar / remover uma câmera da galeria (DIGIFORT e DEFENSE) |
| PUT/GET/DELETE | `/api/v1/machines/{id}/equipamentos/{nvr_id}/planilha` | Salvar / obter / remover a planilha importada na galeria (admin, só DIGIFORT e DEFENSE; GET mascara colunas de senha por padrão, salvo `mostrar_senhas=true`) |
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
| GET | `/api/v1/backups/{id}` | Detalhar um backup |
| GET | `/api/v1/backups/{id}/download` | Download de ZIP (admin) |
| GET | `/api/v1/backups/public-download/{id}` | Download público por link de e-mail (sem auth; ver riscos abertos) |
| GET | `/api/v1/backups/public-run-download/{run_id}` | ZIP unificado da rodada pelo link do e-mail do Cliente (mesmo modelo do public-download) |
| POST | `/api/v1/backups/{id}/resend-email` | Reenviar e-mail do backup |
| GET/PUT | `/api/v1/settings` | **(plataforma)** Configuracoes do sistema |
| POST | `/api/v1/admin/storage/reorganizar` | **(plataforma)** Move as pastas de backup para a estrutura Cliente > Maquina (admin; `aplicar=false` so simula, `true` executa; caminhos relativos ao armazenamento) |
| POST | `/api/v1/admin/agent-version` | Registrar nova versao OTA (JWT do admin ou `X-Publish-Token`; ver REGRA-003) |
| GET | `/api/v1/admin/agent-version` | Listar versoes OTA |
| PUT | `/api/v1/admin/agent-version/{id}/toggle` | Ativar/desativar versao |
| PUT | `/api/v1/admin/agent-version/{id}` | Editar versao |
| DELETE | `/api/v1/admin/agent-version/{id}` | Deletar versao |
| GET | `/api/v1/stats` | Estatisticas do dashboard |
| GET | `/api/v1/notificacoes` | Notificações da conta (licença UNM2000 vencendo, backup com falha, agente offline); `apenas_abertas=false` traz também as resolvidas; isolada por conta (REGRA-010) |
| GET | `/api/v1/notificacoes/config` | Preferência (ativo/inativo) da conta para cada tipo (ausente = ativo) |
| PUT | `/api/v1/notificacoes/config/{tipo}` | Liga/desliga um tipo para a conta (ADMIN da conta ou super admin) |
| GET | `/api/v1/notificacoes/personalizadas` | Definições de notificação personalizada da conta (qualquer papel vê) |
| POST | `/api/v1/notificacoes/personalizadas` | Cria uma notificação personalizada (ADMIN da conta ou super admin): título/mensagem, canais (`enviar_email`, `mostrar_popup`) e frequência — `modo=RECORRENTE` (`intervalo_dias`) ou `modo=DATA` (`data_alvo` + `dias_antes`) |
| PUT/DELETE | `/api/v1/notificacoes/personalizadas/{id}` | Editar / apagar (ADMIN da conta ou super admin); apagar fecha o alerta aberto vinculado |
| GET | `/api/v1/notificacoes/cameras` | Equipamentos ativos com câmeras (NVR, DIGIFORT, DEFENSE), estado atual e `notificar_offline` (isolada por conta) |
| PUT | `/api/v1/notificacoes/cameras/{camera_id}` | Liga/desliga a notificação de offline de uma câmera (ADMIN da conta ou super admin) |
| GET | `/api/v1/notificacoes/alarmes` | DEFENSE ativos com as centrais de alarme do último status (conectada, disparo, partições desarmadas) e `notificar` (isolada por conta) |
| PUT | `/api/v1/notificacoes/alarmes/{nvr_id}/{central_id}` | Liga/desliga a notificação ALARME de uma central (`{"notificar": bool}`; ADMIN da conta ou super admin); já reavalia os alertas do equipamento |
| GET/POST/PUT/DELETE | `/api/v1/clients/{machine_id}/nvrs` · `/{nvr_id}` | **Legado** (`routers/nvrs.py`): ativo e com JWT **(plataforma)**, oculto do OpenAPI/Swagger (`include_in_schema=False`) e sem chamador no painel nem no agente. Aqui `{machine_id}` é o id da **Máquina**, embora o prefixo seja `/clients` (ADR-007); não colide com nenhuma rota do Cliente |
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
- **Display name:** `Trilan — Agente Backup`
- **Diretorio de instalacao:** `C:\Program Files (x86)\Trilan NVR Backup Agent\`
- **Diretorio de logs:** `C:\ProgramData\Trilan NVR Backup Agent\logs\servico.log` (cp1252, lido pela bandeja com `Get-Content`). Na inicializacao, acima de 10 MB vira `servico.1.log` (substitui o anterior); sem `RotatingFileHandler`, porque a bandeja mantem o arquivo aberto. No Log de Eventos do Windows so vao os erros e as marcas de inicio/parada do servico (agente >= 1.1.34)
- **Config file:** `agent.conf` (mesmo diretorio do exe)
- **Threads:** ping (15 s), presenca das cameras (5 min) e envio de logs (20 s) sao iniciadas uma unica vez por processo; o laco de resiliencia do `SvcDoRun` so reinicia o laco principal. O horario de backup recebido do servidor e validado (hora 0-23, minuto 0-59; invalido = erro no log e 02:00)
- **Presenca das cameras** (`src/application/presenca_cameras.py`, a cada 5 min, pulada com backup em andamento): NVR por `buscar_cameras` (so cameras com online True/False); DIGIFORT pelo ping ICMP em memoria; DEFENSE pela API do Defense IA (so handshake, login e arvore de dispositivos, com os mesmos nomes do backup; nao le mais o CSV). Equipamento NVR/DEFENSE sem resposta entra em espera crescente por (nome, ip): pula 5, 10, 20, 40 e depois 60 min a cada falha seguida (evita manter a conta ou o IP bloqueado no NVR com senha errada) e zera na primeira leitura com sucesso

### Formato de `agent.conf`

```ini
[server]
url = https://servidor.exemplo.com

[auth]
client_id = <uuid>
api_key = sk_trilan_<token>
```

### Comunicacao Inter-processo (Service <-> Tray)

O Tray dispara backup manual via Win32 Named Event:
- **Nome do evento:** `Global\TrilanAgentNVR_RunNow`
- O Service escuta com `win32event.WaitForMultipleObjects`

### NVR Factory — Ordem de Detecao de Tipo

Quando `config_extra.marca` está definida, ela decide primeiro: `Motorola` vai direto ao passo 6; `Hikvision` usa só a sonda Hikvision (passos 1 a 5); `Intelbras` usa o CGI Dahua (`src/nvr/intelbras/cameras.py`) e, se ele não achar câmeras, a sonda Hikvision (modelos antigos com ISAPI). Sem `marca`, vale a ordem abaixo. A telemetria de NVR `Intelbras` é lida por SNMP (`src/nvr/intelbras/`); a dos demais, por ISAPI.

**NVR fora do ar ou senha errada nunca sai como OK (agente >= 1.1.34):** Motorola com login falho → `DESCONHECIDO` (logou e não achou câmeras → `MOTOROLA` sem câmeras); Intelbras sem resposta HTTP 200 em nenhuma das consultas CGI (ChannelTitle e RemoteDevice) e sem câmeras pelo ISAPI → `DESCONHECIDO` (respondeu sem câmeras → `INTELBRAS` sem câmeras). `DESCONHECIDO` sem câmeras faz o `processar_nvr` devolver ERRO ("NVR INACESSIVEL ou falha no login") sem tentar telemetria nem planilha, e o relatório leva `cameras: null` (o servidor mantém a lista anterior como `NAO_VERIFICADO`).

**Estado online das câmeras Intelbras:** `GET /cgi-bin/LogicDeviceManager.cgi?action=getCameraState&uniqueChannels[0]=-1` (Digest), linhas `states[N].channel` (base 0) e `states[N].connectionState`: `Connected` = online, `Disconnected` = offline, outro valor, canal ausente ou erro = desconhecido (`None`; o `factory.py` usa as gravações e a presença não envia). Canal analógico (fallback ChannelTitle) = desconhecido. **Não validado em equipamento Intelbras real.**

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
| `url_linux` | Nao | `TrilanAgentLinux.tar.gz` (código do agente Linux/Mikrotik, >= 1.1.52). Sem ele o agente Linux não recebe a versão |
| `sha256_linux` | Nao | Obrigatorio se url_linux for preenchido |

### OTA do agente Linux (Mikrotik, >= 1.1.52)

O container roda `launcher_linux.py` (só na imagem), que sobe o `service_linux.py` da pasta da OTA
(`/app/data/code/atual`) quando ela é mais nova que a imagem, ou o da imagem. O agente consulta
`update-check?plataforma=linux` 2 min após subir e depois a cada hora, baixa o pacote, confere SHA-256, recusa
caminho absoluto/`..`/links, confere que a versão do pacote é a oferecida, que o `requirements-linux.txt` é igual ao da
imagem (biblioteca nova exige imagem nova) e a sintaxe; troca `atual` -> `anterior`, `novo` -> `atual`, grava
`pendente` e encerra. O launcher sobe o código novo; o 1º ping bem-sucedido apaga `pendente`. Versão que cai 3 vezes
(ou não pinga em 10 min) é desfeita para a anterior (ou a imagem) e fica bloqueada 24 h (`falhou`). O "Reiniciar
agente" do painel passa a funcionar (o launcher religa o processo). Detalhes em `agent/README_MIKROTIK.md`.

### Compatibilidade de Versoes

- Agentes `<=1.0.5`: so atualizam o Service (sem suporte a Tray OTA)
- Agentes `>=1.0.6`: suportam atualizacao de ambos via OTA

---

## 11. Infraestrutura e Deploy

### Producao (Dokploy) — verificado no painel em 09/11/2026

A produção **não** usa `server/docker-compose.yml`. No Dokploy, o projeto "Sistema de Backup" (ambiente `production`) tem:

| Serviço | Tipo no Dokploy | Origem | Build | Observações |
|---|---|---|---|---|
| Backend | Application | Git `https://github.com/isaqueschaffer/backup-automation.git`, ramo `producao`, caminho `/server/api` (desde 25/11/2026; antes GitHub App em `projetoswmfa/trilan-backup-automation`, ramo `isaque`) | Railpack | Sem auto-deploy (deploy pelo `server/deploy_producao.ps1`). Variáveis na aba Environment do Application (`DATABASE_URL`, `SECRET_KEY`, `FERNET_KEY`, `ADMIN_PASSWORD`, `RAILPACK_PYTHON_VERSION`...). Bind mount `/opt/trilan/backups` -> `/data/backups` |
| Frontend | Application | mesma origem e ramo, caminho `/server/dashboard` | Railpack | Sem auto-deploy. Variável `VITE_API_URL` |
| Banco | Postgres do Dokploy | — | — | O `DATABASE_URL` do Backend aponta para ele pelo nome interno (`appName` do serviço) |

- **Deploy:** `./server/deploy_producao.ps1` (na raiz, ramo `isaque` já enviado): empurra `isaque` -> `producao` e dispara pela API do Dokploy o deploy do Backend e depois o do Frontend, esperando cada um. Não há webhook. O ramo `producao` tem o ruleset `producao-somente-admin` (só o administrador do repositório cria/atualiza/apaga).
- **Serviço novo:** precisa ser criado no Dokploy como Application (variáveis, volume e endereço interno configurados lá); alterar o compose não tem efeito em produção. O nome interno de um serviço, usado por outro, é o `appName` dele.
- **WhatsApp:** retirado em 10/11/2026 (solução arquivada em `archive/whatsapp/README.md`). O Application "WhatsApp" do Dokploy e as variáveis `WHATSAPP_*` do Backend foram removidos (ver o changelog de 10/11/2026).

### Branches Git

| Branch | Repositorio | Proposito |
|---|---|---|
| `isaque` | `projetoswmfa/trilan-backup-automation` (privado) | Ramo de trabalho do dono e portao de merge; so o dono faz merge aqui (nao dispara deploy desde 25/11/2026) |
| `producao` | `isaqueschaffer/backup-automation` (publico) | **Producao**: copia de `isaque` que o Dokploy poe no ar; protegido (so o dono atualiza, pelo `server/deploy_producao.ps1`) |
| `integracao-equipamentos` | `isaqueschaffer/backup-automation` (publico) | Colaboradores e testadores; sem acesso direto a `isaque`; recebe o espelho do push duplo |
| `helena` | `isaqueschaffer/backup-automation` (publico) | Colaboradora; sem acesso direto a `isaque`; o codigo so chega a producao por merge auditado feito pelo dono |

### Regra de Push Duplo

Todo commit deve ser propagado para AMBOS os repositorios:
```bash
git push origin isaque
git push https://github.com/isaqueschaffer/backup-automation.git isaque:integracao-equipamentos
```

**Excecao:** Branches de features externas (ex: `helena`) NAO devem ir para `integracao-equipamentos` sem auditoria de merge.

Para ir ao ar (servidor/painel), depois do push duplo: `./server/deploy_producao.ps1` (faz o terceiro push, `isaque:producao`, e o deploy). Mudanca so no agente: `git push isaque_repo isaque:producao` basta, para manter `producao` igual a `isaque`.

### Auditoria de merge de ramos de colaboradores

O merge de `helena` ou `integracao-equipamentos` em `isaque` e o unico portao da producao. Antes de concluir:
1. Ver o que entra (`git log isaque..<ramo>`, `git diff --stat isaque...<ramo>`).
2. Revisar os arquivos sensiveis: `server/docker-compose*.yml` (nao regem a producao, mas manter coerentes; local em `7001:7001`), `server/nginx/nginx.conf`, `server/api/models.py`, migracoes do `server/api/main.py`, `requirements*.txt`, `agent/build.ps1`, `agent/installer.iss`, `.env*`, arquivos novos na raiz e binarios.
3. Procurar data com fuso nas linhas adicionadas (REGRA-001): `git diff isaque...<ramo> | grep -nE '^\+.*(datetime\.now|timezone)'`.
4. Procurar segredos nas linhas adicionadas.
5. Registrar na secao 16 o que foi incorporado e o que foi bloqueado.

Historico: o merge de 06/10 (`538600f`) levou datas com fuso (ADR-006), compose `7005`/`pg_data_local` e arquivos soltos; o compose voltou em 13/10 (`7ec3cc4`) sem auditoria registrada (IC-015). Obs. (09/11/2026): a producao nao le esse compose, entao a troca de volume nunca afetou o banco de producao.

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
| `BACKUP_STORAGE_PATH` | `/data/backups` | Raiz do armazenamento de ZIPs: `<CLIENTE>_<uuid>/<MAQUINA>_<uuid>/` (maquina sem Cliente em `_sem_cliente/`; `lixeira/` para maquinas excluidas). Ver o changelog de 23/10/2026 |
| `PUBLIC_URL` | None | URL publica do servidor |
| `SMTP_SERVER` | None | Servidor SMTP |
| `SMTP_PORT` | `587` | Porta SMTP |
| `SMTP_EMAIL` | None | E-mail remetente |
| `SMTP_PASSWORD` | None | Senha do e-mail |
| `PUBLISH_TOKEN` | `""` (desativado) | Token só para registrar versões do agente (`POST /api/v1/admin/agent-version`), enviado em `X-Publish-Token`; não dá acesso ao painel (REGRA-003) |
| `MAX_UPLOAD_MB` | `1024` | Tamanho máximo do ZIP enviado pelo agente (413 acima) |
| `RUN_DEADLINE_HOURS` | `2` | Prazo da rodada de backup do Cliente, a partir do início (horas) |
| `RUN_MAX_HOURS` | `6` | Limite absoluto: passado o prazo, a rodada espera até este total as máquinas que ainda estão em backup (agente >= 1.1.8 informa `backup_em_andamento` no ping) |
| `RUN_UPLOAD_GRACE_SECONDS` | `90` | Espera após o último relatório antes de fechar a rodada (tempo para o ZIP chegar) |

`MAX_UPLOAD_MB` e `RUN_*` não estão no `.env.example` (usam o padrão acima).

---

## 13. Tipos de Equipamento Suportados

| Tipo | Valor em nvrs.tipo | Integracao | Protocolo |
|---|---|---|---|
| NVR IP (Hikvision) | NVR | src/nvr/hikvision/ | HTTP ISAPI |
| DVR Analogico (Hikvision) | NVR (o agente o detecta como `DVR`) | src/nvr/hikvision/ | HTTP ISAPI |
| NVR Hibrido (Hikvision) | NVR | src/nvr/factory.py | HTTP ISAPI |
| NVR Intelbras | NVR com `config_extra.marca = "Intelbras"` | src/nvr/intelbras/ (câmeras e estado online pelo CGI Dahua, gravações, planilha, telemetria) + src/nvr/hikvision/ (fallback ISAPI) | HTTP CGI Dahua, SNMPv2c (porta 161) e HTTP ISAPI |
| Motorola (NVMS-9000) | NVR com `config_extra.marca = "Motorola"` (o agente o detecta como `MOTOROLA`) | src/nvr/motorola/ + camera/rtsp_client.py | HTTP + RTSP (`chID=N`); imagem da noite via `queryChlRecLog` |
| OLT (Huawei, UNM2000, V-SOL) | OLT | src/olt/ (huawei_active, unm2000, vsol) | SSH Paramiko; UNM2000: cópia da pasta de exportação e, no backup manual (`manual` da bandeja ou `manual_dashboard` do painel/fila do Cliente), uma exportação nova pela API local antes de copiar |
| ONU | ONU | — | — |
| PABX | PABX | src/pabx/ | — |
| Mikrotik | MIKROTIK | src/mikrotik/routeros.py | SSH/SFTP |
| Antenas (Wi-Fi) | ANTENA | src/mikrotik/antenas.py + src/application/status_antena.py (server: services/antenas.py) | SSH no MikroTik (só leitura: vizinhos, ARP, DHCP, bridge) + ping ICMP do agente |
| Digifort | DIGIFORT | src/application/webhook_digifort.py (ping ICMP) + src/vms/digifort_gravacoes.py (tempo gravado pelos índices `.dix`) | Ping + leitura dos arquivos de gravação |
| Intelbras Defense | DEFENSE | src/vms/defense.py (+ src/application/webhook_defense.py, plano B) | API REST do Defense IA (HTTPS, porta `config_extra.porta_api`, padrão 4433): estado das câmeras e gravações no backup; só o estado (sem gravações e sem RTSP) na presença a cada 5 min. Gravação `COM_GRAVACAO` só se gravou hoje (como no NVR); sem dado da API = `NAO_VERIFICADO`. API sem resposta: estado pelo CSV do webhook (`config_extra.caminho_log_csv` ou o padrão), câmera sem informação = `ERRO_COMUNICACAO`. O webhook escuta só em `127.0.0.1:8181` |
| HikCentral (VSM) | HIKCENTRAL | `HikCentralParser` (`src/backup/file_manager/parsers.py`) + `processar_hikcentral` (`backup_job.py`) | Backup pela pasta, como o UNM2000: `config_extra.pasta_origem` (local, SMB ou SFTP) com subpastas `VSM_V<versão>_BACKUP_<AAAAMMDDHHMMSS>_<n>`; copia a mais recente (pasta inteira, nome original), válida se for do dia ou das últimas 24 h. Sem câmeras nem status periódico |
| Misto / Custom | MIXED | — | — |
| Câmera IP (Teste RTSP)| CAMERA | server/api/routers/equipamentos.py + agent.py (`/rtsp-result`), agent/src/camera/rtsp_client.py | RTSP (TCP) |

Os valores válidos de `nvrs.tipo` são os de `TIPOS_EQUIPAMENTO` (`server/api/schemas.py`): NVR, OLT, ONU, PABX, MIKROTIK, DIGIFORT, MIXED, DEFENSE, CAMERA, ANTENA e HIKCENTRAL (outro valor: 400). `DVR` e `MOTOROLA` são tipos detectados pelo agente em tempo de execução, nunca gravados em `nvrs.tipo`; a marca do NVR fica em `config_extra.marca` (Hikvision / Intelbras / Motorola).

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

**Decisao:** `agent/dist/` (EXEs), `__pycache__/`, dumps `*.sql`, `scratch_test/` e `.claude/` (exceto `.claude/skills/`, que é versionada) ficam fora do git. Os EXEs vão por upload
no OTA Manager (GitHub Release). Utilitários avulsos ficam em `tools/`; código legado em `archive/`.

**Motivo:** Os EXEs (~50 MB cada, várias versões) inflaram o histórico para ~150 MB e o clone do Dokploy levava minutos.
O histórico antigo ainda contém esses blobs e alguns segredos; reescrevê-lo (`git filter-repo` + force-push nos dois remotes)
é decisão pendente do dono.

---

### ADR-009 — Multi-contas: Integrador e Cliente final, com plano e validade

**Data:** 27/10/2026 | **Status:** VIGENTE

**Decisao:** o sistema atende várias **Contas** (tabela `contas`, inquilinos) de dois tipos: **Integrador** (tem Clientes, e cada Cliente tem Máquinas) e **Cliente final** (organiza as Máquinas em **Setores**). Setor e Cliente são a mesma tabela `client_groups` (fila, rodadas, e-mail único, dashboard e armazenamento iguais); só o rótulo muda no painel (`/auth/me` → `rotulos`). Hierarquia: Conta → Cliente/Setor → Máquina → Equipamento; `client_groups.conta_id` e `clients.conta_id` são NOT NULL (RESTRICT).

**Validade:** toda conta tem um plano (`planos`: nome + dias) e `expira_em` (UTC naive). A renovação é manual pela Trilan (super admin): nova validade = maior entre agora e a validade atual + dias do plano; cada renovação ou ajuste manual fica em `conta_renovacoes`. Status (`services/contas.py`): OK, AVISO (≤ 15 dias, faixa amarela no painel), CRITICO (≤ 3 dias, vermelha), VENCIDA, SUSPENSA (desativada pela Trilan) e VITALICIA (`expira_em` nulo, só a conta da plataforma). E-mail ao contato e aos ADMIN da conta a 7, 3 e 1 dia e no vencimento (`services/avisos_conta.py`, de hora em hora).

**Conta vencida ou suspensa (bloqueio imediato, decisão do dono):** painel somente leitura (403 em escrita), `/agent/config` sem equipamentos (o agente encerra o backup sem erro de rede), ping sem backup nem recuperação, `report`/upload 403 e link público do dashboard 404. Nada é apagado; ao renovar volta tudo na hora. O agente instalado não precisa de versão nova.

**Conta da plataforma:** "Trilan" (INTEGRADOR, sem validade; id em `settings.conta_plataforma_id`) recebeu todos os dados anteriores. O super admin sem conta escolhida fica nela (vê e cria só os itens dela; para ver outra conta escolhe no seletor); não pode ser suspensa nem ganhar validade.

**Fora do escopo (27/10/2026):** cobrança automática, limite de máquinas por plano, login para os clientes do integrador, exclusão de conta (só suspender) e RLS no Postgres (o isolamento é na aplicação, REGRA-010).

**Motivo:** vender o sistema a integradores e a clientes finais com prazo de uso, sem mexer no agente instalado e reaproveitando toda a lógica de Cliente.

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
| IC-013 | Repositório `isaqueschaffer/backup-automation` (antes `trilan-nvr-backup-automation`; é o mesmo repositório) | É **público**, recebe pelo push duplo todo o código de produção e guarda todo o histórico, que a ADR-008 admite conter segredos. Reescrever o histórico (`git filter-repo` + force-push) não basta: quem já clonou ou baixou continua com os valores, então **os segredos expostos precisam ser trocados**. Inventário do histórico pendente | ABERTO — **CRÍTICA** — decisão do dono |
| IC-014 | `routers/dashboards.py` (geração do link, linha 226) | O link é `PUBLIC_URL` + `/d#<token>`, e `PUBLIC_URL` é a URL pública do servidor (usada nos links de e-mail). A API e o painel ficam em hosts diferentes (`server.` e `backups.suportetrilan.com.br`), então o link pode apontar para um host que não serve a página `/d` (não confirmado). A resposta também traz `caminho` (`/d#<token>`) | ABERTO — código não alterado |
| IC-015 | `server/docker-compose.yml` | O arquivo versionado traz `7005:7001` e o volume `pg_data_local`, valores da máquina de uma colaboradora que entraram no ramo `isaque` pelo merge `7ec3cc4` (13/10/2026) sem auditoria do compose, depois de rejeitados em 09/10 (ver changelog). A produção usa a porta 7001; o volume em uso no Dokploy precisa ser conferido. Risco: um deploy que siga o arquivo aponta o PostgreSQL para outro volume (banco vazio) | ABERTO — arquivo não alterado; confirmar no Dokploy antes de reverter |
| IC-016 | `server/nginx/nginx.conf` | Traz `error_log ... debug`, o `/health` e o `proxy_pass` direto (sem `upstream`) vindos do commit `f73fc38` de uma colaboradora (30/09/2026), que nenhuma auditoria reverteu. O binário padrão da imagem `nginx` não tem suporte a debug, então provavelmente é inócuo (não confirmado), mas é configuração de depuração em produção | ABERTO — baixa; arquivo não alterado |

---

## 16. Architecture Changelog

O histórico de mudanças fica em **[`docs/CHANGELOG.md`](docs/CHANGELOG.md)** (desde 26/11/2026; antes ficava aqui e era 60% deste arquivo). Toda mudança de arquitetura, banco, API, agente ou deploy ganha uma entrada nova no topo de lá.

## 17. Fluxo de Atualização de Versão (Release)

O passo a passo (versão nos três lugares, build, release, hashes, cadastro e reinício dos agentes) está no `CLAUDE.md`, seções "Publicação de versões do agente" e "Checklist de uma nova versão do agente". O `agent/build.ps1` confere sozinho se a versão bate nos três lugares.
