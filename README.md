# Trilan Backups

Sistema que faz backup automático da configuração de equipamentos de rede e segurança (NVR/DVR, câmeras,
OLTs, Mikrotik, PABX, centrais de alarme, antenas, Digifort e Defense) e monitora o estado deles.

Um **agente** instalado na rede do cliente conversa com os equipamentos, gera os backups e manda tudo para a
**API**; o **painel** web mostra máquinas, equipamentos, backups, câmeras e dashboards por cliente.

```
Equipamentos ── (rede local) ── Agente (Windows ou container no Mikrotik)
                                    │ HTTPS
                                    ▼
                       API FastAPI ── PostgreSQL        Painel React (Vite)
                       (server/api)                     (server/dashboard)
```

Hierarquia dos dados: **Conta** (integrador ou cliente final) › **Cliente/Setor** › **Máquina** (computador
com o agente) › **Equipamento**. Cada rota da API só enxerga a conta do usuário (REGRA-010 no `PROJECT_SPEC.md`).

## Onde está cada coisa

| Pasta | O que é |
|---|---|
| `server/api/` | API FastAPI 0.111, SQLAlchemy 2.0 síncrono, PostgreSQL. Testes em `server/api/tests/` |
| `server/dashboard/` | Painel React 18 + Vite + TypeScript (SPA) |
| `server/docker-compose.local.yml` | Ambiente local completo (nginx, API, painel, Postgres) |
| `server/deploy_producao.ps1` | Leva o código para a produção (ver "Deploy") |
| `agent/` | Agente Python: serviço Windows (`service.py`), ícone da bandeja (`tray.py`), versão Linux para o container do Mikrotik (`service_linux.py`). Testes em `agent/tests/` |
| `tools/` | Scripts de apoio e testes manuais (ver `tools/README.md`) |
| `archive/`, `legacy/` | Código antigo guardado só como referência |
| `PROJECT_SPEC.md` | Especificação: regras (REGRA-xxx), decisões (ADR-xxx), rotas, variáveis e o histórico de mudanças |
| `CLAUDE.md`, `.agents/` | Instruções e skills das IAs que trabalham no projeto (Claude Code e Gemini) |

## Rodar localmente

Requisitos: Docker com Compose.

```bash
cd server
cp .env.local.example .env        # preencha SECRET_KEY, FERNET_KEY e ADMIN_PASSWORD (o arquivo explica como gerar)
docker compose -f docker-compose.local.yml up -d --build
```

O painel abre em `http://localhost:7001` e a API responde em `http://localhost:7001/api/v1/...`
(documentação interativa em `http://localhost:7001/api/docs`). O Postgres local fica em `localhost:5433`.

Nunca rode `docker compose down -v`: o `-v` apaga o banco local.

## Testes

```bash
# Agente (Windows; o venv é criado pelo agent/build.ps1)
cd agent
venv\Scripts\python.exe -m unittest discover -s tests

# API (precisa das dependências de server/api/requirements.txt e do pytest)
cd server/api
python -m pytest tests -q

# Painel: checagem de tipos (o build de produção também roda)
cd server/dashboard
npm install
npm run typecheck
```

O teste de isolamento entre contas (`test_isolamento_contas.py`) só roda no container, contra o Postgres local,
com `TRILAN_TESTE_ISOLAMENTO=1`; fora disso ele aparece como pulado.

## Instalar o agente num cliente

Use o instalador `TrilanAgentSetup.exe` da [última release](https://github.com/isaqueschaffer/backup-automation/releases/latest).
Ele pede a URL do servidor (`https://server.suportetrilan.com.br`), o **Client ID** e a **API Key** da máquina,
que aparecem no painel ao cadastrar a máquina. Depois de instalado, o agente se atualiza sozinho (OTA) quando uma
versão nova é cadastrada no painel.

Para o container no Mikrotik, veja `agent/README_MIKROTIK.md`. Detalhes de funcionamento do agente estão em
`agent/DOCUMENTACAO_AGENTE.md`.

## Ramos e deploy

| Ramo | Repositório | Uso |
|---|---|---|
| `isaque` | privado | Ramo de trabalho do dono e portão de merge |
| `producao` | `isaqueschaffer/backup-automation` | O que está no ar. Protegido: só o dono atualiza |
| `helena`, `integracao-equipamentos` | `isaqueschaffer/backup-automation` | Colaboradores e testadores |

O código de colaboradores só chega à produção por merge auditado na `isaque` (checklist no `CLAUDE.md`).

A produção roda no Dokploy (Backend e Frontend como Applications, build Railpack, Postgres do Dokploy) e **não usa**
o `server/docker-compose.yml`. Não há deploy automático: com a `isaque` já enviada, o dono roda

```powershell
./server/deploy_producao.ps1
```

que atualiza o ramo `producao` e dispara o deploy do Backend e depois do Frontend.

Versões do agente: tag `X.Y.Z` e release no repositório público com `TrilanAgentService.exe`, `TrilanAgentTray.exe`,
`TrilanAgentSetup.exe` e `TrilanAgentLinux.tar.gz`; o passo a passo está no `CLAUDE.md`.

## Segredos

Nenhuma senha, chave ou token entra no repositório, que é espelhado em um repositório público. Variáveis da produção
ficam no Dokploy; credenciais locais ficam em arquivos ignorados pelo git (`*.local.md`, `.env`, `agent.conf`).
