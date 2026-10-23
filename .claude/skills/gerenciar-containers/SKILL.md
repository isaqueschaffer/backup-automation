---
name: gerenciar-containers
description: Docker do projeto — ambiente local (server/docker-compose.local.yml), testes em container e cuidados com o compose de produção (Dokploy). Use ao subir, parar, depurar ou testar os containers.
---

# Docker do projeto

| Arquivo | Uso |
|---|---|
| `server/docker-compose.local.yml` | **Desenvolvimento e testes nesta máquina**: painel em http://localhost:7001, Postgres em `localhost:5433` |
| `server/docker-compose.yml` | **Produção**: o Dokploy faz o deploy a cada push na branch `isaque`. Não subir localmente (bind mount em `/opt/trilan/backups`). A porta de produção é 7001; o `7005:7001` e o volume `pg_data_local` desse arquivo vieram da máquina da Helena e não devem ser tratados como produção nem alterados sem pedido |

Serviços: `nginx` (proxy, porta 7001), `api` (FastAPI na 8000 interna), `dashboard` (build do Vite servido por nginx) e `db` (Postgres 15 com healthcheck).
Manter os nomes `docker-compose*.yml` (o Dokploy usa o de produção), mesmo que a skill `docker-compose-patterns` recomende `compose.yaml`.

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

Não há acesso ao Dokploy: produção só muda por git (push na `isaque`). Não rodar o compose de produção nem comandos contra o servidor.
