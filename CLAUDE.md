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

## Cadastro da versão no painel (sob demanda)

O cadastro da versão no painel NÃO é automático: libera a versão para todos os agentes de uma vez.
Depois da release, informar os links e os hashes e esperar o usuário dizer "publique" e passar a senha do painel na hora.

- Então rodar, em `agent/`: `./publish_version.ps1 -Version <versão> -ServerUrl https://server.suportetrilan.com.br -AdminPassword <senha> -Notes "<resumo>" -UrlService <url do Service> -UrlTray <url do Tray>`
- Antes, conferir que os links e os hashes SHA-256 batem com os assets da release.
- Nunca gravar a senha em arquivo, memória, commit ou log; usá-la só nesse comando e informar o resultado.
- O servidor também aceita um token só de publicação (`PUBLISH_TOKEN` no servidor, `TRILAN_PUBLISH_TOKEN` na máquina), mas ele está desativado por padrão e não é usado hoje.

## Checklist de uma nova versão do agente (fazer sempre, nesta ordem)

1. Subir a versão nos três lugares (updater.py, installer.iss, package.json) e registrar no changelog do `PROJECT_SPEC.md`.
2. Commit e push para `origin isaque` e `isaque_repo isaque:integracao-equipamentos`.
3. Gerar os executáveis: `agent/build.ps1` e depois `ISCC.exe installer.iss` (Inno Setup 7). Encerrar antes processos `TrilanAgent*` abertos.
4. Calcular os SHA-256 de `TrilanAgentService.exe` e `TrilanAgentTray.exe`.
5. Criar a release em `isaqueschaffer/backup-automation` (tag = versão, título `v<versão>`) com os dois executáveis e conferir que os `digest` dos assets batem com os hashes.
6. Informar ao usuário os links de download e os hashes e **parar**. Cadastrar só quando ele disser "publique" e passar a senha na hora.
7. Cadastrar com `agent/publish_version.ps1` (API em `https://server.suportetrilan.com.br`; o painel `backups.suportetrilan.com.br` é só a tela e não atende `/api`). Depois conferir via `GET /api/v1/admin/agent-version` que links e hashes ficaram corretos.
8. Lembrar o usuário: o cadastro libera a versão a todos os agentes (atualizam em até 1 h); a senha do painel deve ser forte.
