---
name: gerenciar-containers
description: Docker do projeto — ambiente local (server/docker-compose.local.yml), testes em container e cuidados com o compose de produção (Dokploy). Use ao subir, parar, depurar ou testar os containers.
---

# Docker do projeto

| Arquivo | Uso |
|---|---|
| `server/docker-compose.local.yml` | **Desenvolvimento e testes nesta máquina**: painel em http://localhost:7001, Postgres em `localhost:5433` |
| `server/docker-compose.yml` | **Não é a produção.** O Dokploy não lê este arquivo: a produção são Applications separados (Backend `/server/api`, Frontend `/server/dashboard`, build Railpack) e um Postgres do Dokploy. O arquivo fica só como referência do conjunto de serviços. Não subir localmente (bind mount em `/opt/trilan/backups`). O `7005:7001` e o volume `pg_data_local` vieram da máquina da Helena; não alterar sem pedido |

Serviços do compose local: `nginx` (proxy, porta 7001), `api` (FastAPI na 8000 interna), `dashboard` (build do Vite servido por nginx) e `db` (Postgres 15 com healthcheck).
Manter os nomes `docker-compose*.yml`, mesmo que a skill `docker-compose-patterns` recomende `compose.yaml`.

## Primeira vez

Criar `server/.env` a partir de `server/.env.local.example` e gerar `SECRET_KEY` e `FERNET_KEY` como o arquivo explica. O `.env` nunca vai para o git.

## Comandos (da raiz do repositório)

- Subir com build: `docker compose -f server/docker-compose.local.yml up -d --build`
- Situação: `docker compose -f server/docker-compose.local.yml ps`
- Logs: `docker compose -f server/docker-compose.local.yml logs -f api` (ou `db`, `nginx`, `dashboard`)
- Rebuild de um serviço após mudar código: `docker compose -f server/docker-compose.local.yml up -d --build api`
- Parar: `docker compose -f server/docker-compose.local.yml down` (mantém o banco)
- **Apagar dados** (`down -v`, `docker volume rm`): só com confirmação explícita do usuário, dizendo quais volumes se perdem (`pg_data_local`, `trilan_backups_local`).

## Testes

- Só quando o usuário pedir, e sempre em container, nunca no Python ou Node da máquina.
- API (`server/api/tests`): `docker compose -f server/docker-compose.local.yml run --rm --no-deps api sh -c "pip install -q pytest && python -m pytest tests -q"`. O pytest não está no `requirements.txt`; o container descartável instala na hora. Os testes usam SQLite em memória e não precisam do `db`.
- Exceção: o agente Windows (PyInstaller + pywin32) só compila no host, com `agent/build.ps1`, e só quando pedido.

## Produção

Você (Gemini) não tem acesso ao Dokploy: código vai para a produção só por git (push na `isaque` redeploya Backend e Frontend). Configuração da produção (variáveis, serviço novo, volumes) é feita pelo dono no próprio Dokploy, não no compose: se a tarefa exigir isso, diga no relatório o que precisa ser configurado lá. Não rodar o compose de produção nem comandos contra o servidor.
