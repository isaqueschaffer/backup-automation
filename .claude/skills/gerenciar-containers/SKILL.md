---
name: gerenciar-containers
description: Comandos e fluxos para gerenciar o ambiente Docker local do projeto de NVR Backup.
---

# Gerenciamento do Docker Compose

Sempre que a tarefa envolver iniciar, parar ou debugar containers, utilize estas referências:

- **Arquivo Principal**: `server/docker-compose.yml`
- **Subir os serviços em background**: `docker compose -f server/docker-compose.yml up -d`
- **Derrubar os serviços**: `docker compose -f server/docker-compose.yml down`
- **Visualizar logs de um serviço (ex: api)**: `docker compose -f server/docker-compose.yml logs -f <nome-do-servico>`
- **Reconstruir a imagem (quando houver mudança em requirements/Dockerfile)**: `docker compose -f server/docker-compose.yml build`

Ao executar comandos no terminal em nome do usuário, prefira sempre apontar o caminho completo do docker-compose se não estivermos no diretório `server/`.
