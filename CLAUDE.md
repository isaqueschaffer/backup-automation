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
