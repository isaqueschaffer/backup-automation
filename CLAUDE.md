# Instruções do projeto

## Publicação de versões do agente (regra fixa)

Sempre que gerar os executáveis do agente (`agent/build.ps1` + Inno Setup), publicar também uma release no
repositório **público** `isaqueschaffer/backup-automation` (as máquinas dos clientes baixam daqui):

- Tag: a versão sem prefixo (ex.: `1.1.13`). Título: `v<versão>` (ex.: `v1.1.13`).
- Anexar **apenas** `TrilanAgentService.exe` e `TrilanAgentTray.exe` (de `agent/dist/`). O `TrilanAgentSetup.exe` só se for pedido.
- Alvo: o commit atual (`--target $(git rev-parse HEAD)`), já enviado aos repositórios.
- Comando: `gh release create <versão> agent/dist/TrilanAgentService.exe agent/dist/TrilanAgentTray.exe -R isaqueschaffer/backup-automation --title "v<versão>" --target "$(git rev-parse HEAD)" --notes "<resumo>"`
- Não usar `isaqueschaffer/trilan-nvr-backup-automation` para releases (não é o repositório público).
- No fim, informar os links de download e os hashes SHA-256 de Service e Tray para o cadastro no painel.

A versão fica em três lugares: `agent/src/application/updater.py` (`CURRENT_VERSION`), `agent/installer.iss` (`AppVersion`) e `server/dashboard/package.json`.

## Cadastro da versão no painel (após a release)

Depois da release, registrar a versão na API com `agent/publish_version.ps1`, usando o token só de publicação
(variável de ambiente `TRILAN_PUBLISH_TOKEN` nesta máquina, nunca no repositório; o servidor lê `PUBLISH_TOKEN`):

`./publish_version.ps1 -Version <versão> -ServerUrl <url do painel> -Notes "<resumo>" -UrlService <url do Service> -UrlTray <url do Tray>`

- Antes, conferir que os links e os hashes SHA-256 batem com os assets da release. Cadastrar libera a versão para todos os agentes.
- O token só vale para `POST /api/v1/admin/agent-version` (header `X-Publish-Token`); não dá acesso ao painel.
- Se `TRILAN_PUBLISH_TOKEN` não estiver definida, não pedir nem armazenar senha: avisar o usuário.
