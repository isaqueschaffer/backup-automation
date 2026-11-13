# Instruções do projeto

## Skills e subagentes (Claude e Antigravity)

Cada ferramenta tem a sua pasta, com cópias separadas (não há link entre elas; ao mudar uma skill de conteúdo comum, atualizar as duas):
- **Claude Code**: skills em `.claude/skills/<nome>/SKILL.md`.
- **Antigravity (`agy`, o Gemini que executa os planos)**: skills em `.agents/skills/<nome>/SKILL.md`, subagentes em `.agents/agents/<nome>/agent.md` e regras em `.agents/rules/`. Desde 23/10/2026 o Gemini enxerga e usa skills e delega a subagentes especializados (`backend-fastapi`, `frontend-dashboard`, `agente-windows`, `revisor`, `depurador`); a regra `.agents/rules/subagentes.md` explica quando usar cada um.
- As skills do Gemini ficam em português e já trazem as regras do projeto; skills externas só entram depois de lidas por inteiro (viram instrução) e com origem e commit anotados no frontmatter.

Skills do Claude (mantidas aqui; atualizar quando a estrutura mudar): `criar-endpoint-fastapi`, `criar-novo-agente`, `gerenciar-containers`, `criar-widget-dashboard`, `tirar-duvidas` (só do Claude: antes de executar um pedido não trivial, tira as dúvidas com o usuário via `AskUserQuestion`; não existe cópia para o Gemini).
Skills do Gemini: as mesmas quatro, mais `fastapi`, `docker-compose-patterns`, `react-vite-boas-praticas` (versão enxuta da `vercel-react-best-practices`), `seguranca-e-endurecimento`, `revisao-de-codigo` e `depuracao-sistematica` (as três últimas adaptadas de `addyosmani/agent-skills`, MIT, commit `aeac41d`).

Skills externas e como aplicá-las aqui (as regras do projeto sempre prevalecem):
- `fastapi` (oficial do FastAPI): o projeto usa FastAPI 0.111, SQLAlchemy 2.0 síncrono e `requests`. Não migrar para SQLModel, HTTPX, uv, Ruff ou ty, e não usar recursos de versões novas (`app.frontend()`, `fastapi.sse`, OpenTelemetry nativo). `Annotated` pode.
- `vercel-react-best-practices` (Vercel): o dashboard é SPA Vite, sem Next.js. Ignorar as regras `server-*` e de hidratação/RSC; no lugar de `next/dynamic`, usar `React.lazy`/`import()`. Não adicionar SWR nem outras dependências sem pedido.
- `docker-compose-patterns` (Docker): manter os nomes `docker-compose.yml` e `docker-compose.local.yml` (o primeiro **não** é lido pelo Dokploy: ver "Produção no Dokploy" abaixo) e nunca rodar `down -v` sem confirmação.
- `find-skills`: para procurar skills novas. Instalar sem `npx skills` (ele grava só em `.agents/skills/` e deixa a decisão fora do nosso controle). Baixar os arquivos do GitHub num commit fixo, ler tudo antes (vira instrução) e salvar em `.claude/skills/<nome>/` (Claude) e/ou `.agents/skills/<nome>/` (Gemini), adaptando para o projeto. Atualizar é repetir o processo.

## Produção no Dokploy (verificado em 09/11/2026; corrige o que se dizia antes)

**A produção NÃO usa `server/docker-compose.yml`.** No Dokploy, o projeto "Sistema de Backup" (ambiente `production`) tem:
- **Backend** (Application): repositório `projetoswmfa/trilan-backup-automation`, branch `isaque`, caminho `/server/api`, build **Railpack**, auto-deploy. Variáveis de ambiente (`DATABASE_URL`, `SECRET_KEY`, `FERNET_KEY`, `ADMIN_PASSWORD`...) ficam na aba Environment do Application, não em `.env` do repositório. Bind mount `/opt/trilan/backups` -> `/data/backups`.
- **Frontend** (Application): mesmo repositório e branch, caminho `/server/dashboard`, Railpack, auto-deploy, variável `VITE_API_URL`.
- Um **Postgres do próprio Dokploy** (serviço `sistema-de-backup-database-…`); o `DATABASE_URL` do Backend aponta para ele pelo nome interno. O nome interno de qualquer serviço do Dokploy é o `appName` dele.
- Cada push na `isaque` redeploya Backend e Frontend. **Alterar `docker-compose.yml` não muda a produção**; um serviço novo precisa ser criado no Dokploy como Application novo, com as variáveis, o volume e o endereço interno ajustados lá. Os compose servem ao ambiente local (`docker-compose.local.yml`) e como referência dos serviços.
- **Acesso (só para o Claude; nunca passar ao Gemini):** o endereço do painel, o modo de login e onde estão as credenciais ficam em `CLAUDE.local.md` (só nesta máquina, fora do git). Consultar (GET) é livre; criar/editar Application, variáveis ou disparar deploy só a pedido do usuário. Nunca imprimir valores de variáveis nem senhas, e nunca copiar credenciais para arquivos versionados (este repositório é espelhado em um público).

## Publicação de versões do agente (regra fixa)

Sempre que gerar os executáveis do agente (`agent/build.ps1` + Inno Setup), publicar também uma release no
repositório **público** `isaqueschaffer/backup-automation` (as máquinas dos clientes baixam daqui):

- Tag: a versão sem prefixo (ex.: `1.1.13`). Título: `v<versão>` (ex.: `v1.1.13`).
- Anexar os três executáveis de `agent/dist/`: `TrilanAgentService.exe`, `TrilanAgentTray.exe` e `TrilanAgentSetup.exe` (o instalador, para máquinas novas; desde 05/11/2026), mais o `TrilanAgentLinux.tar.gz` (código do agente do Mikrotik, gerado pelo `build.ps1`; desde 12/11/2026, 1.1.52). Service, Tray e Linux são cadastrados no painel (OTA; o Linux com `-UrlLinux` no `publish_version.ps1`); o Setup não.
- Alvo: o commit atual (`--target $(git rev-parse HEAD)`), já enviado aos repositórios.
- Comando: `gh release create <versão> agent/dist/TrilanAgentService.exe agent/dist/TrilanAgentTray.exe agent/dist/TrilanAgentSetup.exe agent/dist/TrilanAgentLinux.tar.gz -R isaqueschaffer/backup-automation --title "v<versão>" --target "$(git rev-parse HEAD)" --notes "<resumo>"`
- Não usar o nome antigo `isaqueschaffer/trilan-nvr-backup-automation` nas releases: é o mesmo repositório (foi renomeado); o nome correto é `backup-automation`.
- Ramos: `isaque` em `projetoswmfa/trilan-backup-automation` (privado) é a produção e dispara o deploy no Dokploy. `helena` e `integracao-equipamentos` (repositório público `isaqueschaffer/backup-automation`) são de colaboradores e testadores, sem acesso direto à `isaque`; o código deles só entra na produção por merge feito pelo dono.
- No fim, informar os links de download e os hashes SHA-256 de Service e Tray (para o cadastro no painel) e também o link e o hash do Setup.

A versão fica em três lugares: `agent/src/application/updater.py` (`CURRENT_VERSION`), `agent/installer.iss` (`AppVersion`) e `server/dashboard/package.json`.

## Cadastro da versão no painel (sob demanda)

O cadastro da versão no painel NÃO é automático: libera a versão para todos os agentes de uma vez.
Depois da release, informar os links e os hashes e esperar o usuário dizer "publique" e passar a senha do painel na hora.

- Então rodar, em `agent/`: `./publish_version.ps1 -Version <versão> -ServerUrl https://server.suportetrilan.com.br -AdminPassword <senha> -Notes "<resumo>" -UrlService <url do Service> -UrlTray <url do Tray> -UrlLinux <url do TrilanAgentLinux.tar.gz>` (sem `-UrlLinux` o agente do Mikrotik não recebe a versão)
- Antes, conferir que os links e os hashes SHA-256 batem com os assets da release.
- Nunca gravar a senha em arquivo, memória, commit ou log; usá-la só nesse comando e informar o resultado.
- O servidor também aceita um token só de publicação (`PUBLISH_TOKEN` no servidor, `TRILAN_PUBLISH_TOKEN` na máquina), mas ele está desativado por padrão e não é usado hoje.

## Checklist de uma nova versão do agente (fazer sempre, nesta ordem)

1. Subir a versão nos três lugares (updater.py, installer.iss, package.json) e registrar no changelog do `PROJECT_SPEC.md`.
2. Commit e push para `origin isaque` e `isaque_repo isaque:integracao-equipamentos`.
3. Gerar os executáveis: `agent/build.ps1` e depois `ISCC.exe installer.iss` (Inno Setup 7). Encerrar antes processos `TrilanAgent*` abertos.
4. Calcular os SHA-256 de `TrilanAgentService.exe`, `TrilanAgentTray.exe`, `TrilanAgentSetup.exe` e `TrilanAgentLinux.tar.gz`.
5. Criar a release em `isaqueschaffer/backup-automation` (tag = versão, título `v<versão>`) com os quatro arquivos (Service, Tray, Setup e Linux) e conferir que os `digest` dos assets batem com os hashes. Se o `requirements-linux.txt` mudou, gerar também a imagem nova do Mikrotik (`agent/README_MIKROTIK.md`), porque a OTA do Linux recusa essa versão.
6. Informar ao usuário os links de download e os hashes e **parar**. Cadastrar só quando ele disser "publique" e passar a senha na hora.
7. Cadastrar com `agent/publish_version.ps1` (API em `https://server.suportetrilan.com.br`; o painel `backups.suportetrilan.com.br` é só a tela e não atende `/api`). Depois conferir via `GET /api/v1/admin/agent-version` que links e hashes ficaram corretos.
8. **Reiniciar todos os agentes logo depois do cadastro** (etapa fixa desde 12/11/2026, a pedido do usuário): rodar, em `agent/`, `./reiniciar_agentes.ps1 -AdminPassword <senha>`. Ele percorre cada conta (`GET /api/v1/admin/contas`) e chama `POST /api/v1/machines/restart-agent-all` com `X-Conta-ID` (o endpoint age só na conta do contexto). Reinicia só máquinas online (offline pegam a versão pela OTA ao voltar); o reinício vale no próximo ping (~15 s) e, com backup em andamento, espera ele terminar. Informar quantas máquinas receberam o pedido. Vale também no fluxo "merge com a Helena" (passo 3) quando houver cadastro de versão; sem cadastro (só servidor/painel), não reiniciar.
9. Lembrar o usuário: o cadastro libera a versão a todos os agentes (atualizam em até 1 h, ou logo após o reinício do passo 8); a senha do painel deve ser forte.

## Merge de ramos de colaboradores (`helena`, `integracao-equipamentos`) em `isaque`

O merge em `isaque` é o único portão da produção (cada push dispara o deploy). Antes de concluir o merge, fazer sempre:

1. `git fetch` e ver o que entra: `git log isaque..<ramo> --oneline` e `git diff --stat isaque...<ramo>`.
2. Olhar com atenção os arquivos sensíveis: `server/docker-compose*.yml` (não regem a produção, mas manter coerentes: local em `7001:7001`), `server/nginx/nginx.conf`, `server/api/models.py`, a parte de migrações do `server/api/main.py`, `requirements*.txt`, `agent/build.ps1`, `agent/installer.iss`, `.env*`, além de arquivos novos na raiz e binários.
3. Procurar data com fuso nas linhas adicionadas (REGRA-001): `git diff isaque...<ramo> | grep -nE '^\+.*(datetime\.now|timezone)'`.
4. Procurar segredos nas linhas adicionadas (chaves `sk_trilan_`, senhas, tokens, credenciais de equipamentos).
5. Isolamento por conta (REGRA-010): toda rota nova ou alterada em `server/api/routers` recebe `ctx` (`get_contexto`) e busca Cliente/Máquina por `obter_cliente`/`obter_maquina`/`filtrar_por_conta`; procurar `verify_admin_token` e `db.query(Customer|Machine|NVR|Backup)` sem filtro de conta nas linhas adicionadas: `git diff isaque...<ramo> -- server/api/routers | grep -nE '^\+.*(verify_admin_token|db\.query\((Customer|Machine|NVR|Backup)\))'`.
6. Se algo violar uma REGRA ou o compose, resolver no merge (manter a versão de `isaque`) e registrar no changelog do `PROJECT_SPEC.md` o que foi incorporado e o que foi bloqueado.

### Pedido "faça um merge com a Helena" = merge + versão + build + release + cadastro (regra permanente, desde 29/10/2026)

O usuário não quer pedir cada etapa de novo. Quando ele pedir o merge com a Helena (ou com outro colaborador) e o ramo trouxer mudança no agente, fazer a sequência inteira, sem perguntar entre as etapas:

1. Auditar e fazer o merge (`git merge --no-ff isaque_repo/helena`, depois da auditoria acima), resolver conflitos mantendo os dois lados quando forem só texto/campos, e registrar o merge no changelog do `PROJECT_SPEC.md`.
2. Se o ramo mexeu em `agent/`, subir a versão (três lugares) e seguir o "Checklist de uma nova versão do agente": commit e push duplo, `agent/build.ps1` + `ISCC.exe installer.iss`, SHA-256, release em `isaqueschaffer/backup-automation` com Service, Tray e Setup, conferência dos `digest`.
3. **Cadastrar a versão no painel na mesma rodada** (`agent/publish_version.ps1`), sem esperar o "publique": neste fluxo o pedido de merge com a Helena já é a autorização. Depois conferir via `GET /api/v1/admin/agent-version` (login em `/api/v1/auth/login` com `{"password": ...}`) que links e hashes batem, e rodar o passo 8 do checklist (`agent/reiniciar_agentes.ps1`, reinício de todos os agentes).
4. Se o ramo só mexeu em servidor/painel (sem `agent/`), não gerar executável nem cadastrar versão: só merge, changelog e push.
5. A senha do painel NÃO fica neste arquivo nem em nada versionado (o repositório é espelhado em um público). Ela está em `CLAUDE.local.md`, só nesta máquina, e o usuário autorizou usá-la neste fluxo sem perguntar. Se esse arquivo não existir (outra máquina), pedir a senha só no momento do passo 3. Nunca passá-la ao Gemini.
6. No fim, informar o resumo: o que entrou, o que foi bloqueado, links e hashes, e lembrar que o cadastro libera a versão a todos os agentes (atualizam em até 1 h) e que a senha do painel deve ser forte.


Lição: o merge de 06/10 (`538600f`) levou `datetime.now(timezone.utc)`, compose `7005`/`pg_data_local` e arquivos soltos; o compose voltou em 13/10 (`7ec3cc4`) sem auditoria. (Obs. de 09/11/2026: a produção não lê esse arquivo, então o risco de "banco vazio" descrito na época não se aplicava; o cuidado com datas e arquivos soltos continua valendo.)
