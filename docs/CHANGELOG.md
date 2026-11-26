# Histórico de mudanças (changelog)

Registro do que mudou no sistema, mais recente primeiro: data, problema, correção, arquivos e versão.
Até 26/11/2026 ficava na seção 16 do `PROJECT_SPEC.md`; foi movido para cá sem alterar o texto das entradas.

Regras: **só acrescentar** (nova entrada no topo, logo abaixo desta linha); não reescrever nem apagar entradas
antigas (o git guarda o texto, mas só este arquivo guarda os porquês). Corrigir algo dito numa entrada antiga =
nova entrada que cite a antiga.

---

### [2026-11-26] — OLT Huawei: uma sessão SSH por vez, nova tentativa quando a OLT fecha o login e mensagem certa no backup

- **Corrige a entrada "Backup de pasta (UNM2000/Huawei/Digifort) aceita o arquivo das últimas 24 h"** (abaixo): Georgina e Recanto Real não usam a mesma OLT, e a senha do `root` não mudou.
- **Origem**: o backup das OLTs Huawei da Recanto Real e da Georgina (OLTs diferentes, com o mesmo IP `10.11.104.2` em redes distintas) falhou em 26/11 às 02:00 com "Usuario ou senha incorretos", e o "Testar conexão" da Recanto Real às 13:55 com "A OLT fechou a conexão durante o login". A coleta de status entrou nas duas às 13:56 com o mesmo `root`: a senha está certa. A OLT recusa sessões quando já há outra do usuário aberta (a coleta de status do agente abre SSH a cada 5 min; o backup das 02:00 e o teste caíam em cima dela). Desde 23/11 a coleta da Recanto Real já registrava esse EOF umas 5 vezes por dia.
- **Mensagem errada**: `huawei_active` tratava toda `paramiko.AuthenticationException` como senha incorreta, mas o EOF ("transport shut down or saw EOF") é a mesma exceção. Agora usa `explicar_erro_ssh`, como o teste de conexão.
- **Correção**: novo `agent/src/olt/huawei_sessao.py`. `sessao_exclusiva(ip)` é uma trava por IP: coleta de status, teste e backup (Windows e Mikrotik) esperam um ao outro, até 600 s (depois disso, `OltOcupada` com explicação própria). `conectar_com_novas_tentativas` repete o login, com 30 s de pausa, só quando a OLT fechou a conexão sem avaliar a senha: 3 vezes no backup, 2 na coleta e no teste. Senha recusada de verdade não é repetida, para não bloquear o usuário. `huawei_status.abrir_ssh_huawei` cria um cliente novo a cada tentativa. `sftp_origem.abrir_ssh` (Mikrotik) mantém o texto original do paramiko e separa "fechou a conexão durante o login" de "usuário/senha recusados".
- **Limite**: a trava vale dentro de um agente. Sessões de fora (outra máquina ou alguém do provedor logado como `root`) continuam podendo esgotar as sessões; a nova tentativa cobre a maior parte desses casos.
- **Testes**: `agent/tests/test_huawei_sessao.py` (11; os 2 do backup Windows pulam sem o `pyftpdlib` e passam com ele); `test_huawei_status.py` sem a pausa real. Suíte do agente 363 OK.
- **Versão**: muda `agent/`; precisa de versão nova do agente no merge do dono.

### [2026-11-26] — Backup de pasta (UNM2000/Huawei/Digifort) aceita o arquivo das últimas 24 h

- **Origem**: investigação das OLTs com falha em 26/11. O teste-mk-maquina (agenda 02:00) e um backup manual do Chiquinho (00:58) deram `BACKUP_ANTIGO` porque o UNM2000 só exporta às 03:00: depois da meia-noite o agente exigia o arquivo do dia novo e achava o de ontem, com menos de 24 h.
- **Correção**: `Validator.is_expected_date` (`agent/src/backup/file_manager/validators.py`) aceita o grupo do mesmo dia ou feito até `JANELA_BACKUP_RECENTE` (24 h) antes da hora do agente; mais velho continua `BACKUP_ANTIGO` (ex.: Hot Beach Resort, parado em 15/11). O log "Data esperada" passa a dizer "(ou backup das últimas 24 h)". Teste: `agent/tests/test_validador_data_backup.py`; suíte do agente 352 OK.
- **Painel (sem código)**: horário do cliente teste-mk de 02:00 para 04:00 (depois da exportação do UNM).
- **Achados sem correção no código** (dependem do cliente): Georgina e Recanto Real usam a mesma OLT Huawei `10.11.104.2` e as duas recusaram o login do `root` a partir de 26/11 02:00 (senha trocada ou usuário bloqueado); Hot Beach Resort sem exportação do UNM2000 desde 15/11; Server Defense Trilan com `STATUS_ACCESS_DENIED` para a conta `unm2000` em `\\192.168.91.6\emsback` (falta permissão de compartilhamento/NTFS).
- **Versão**: muda `agent/`; precisa de versão nova do agente no merge do dono.

### [2026-11-26] — Agente 1.1.68: merge da Helena (Digifort pela pasta de cada câmera, NVR Hikvision com novas tentativas)

- **Versão**: 1.1.68 em `updater.py`, `installer.iss`, `server/dashboard/package.json` e `package-lock.json`, levando o merge abaixo. `requirements-linux.txt` intacto. Testes: agente OK, API 188 aprovados, tipos do painel OK.

### [2026-11-26] — Merge `helena`: Digifort pela pasta de cada câmera e NVR Hikvision com novas tentativas

- **Entrou** (helenaoc-dotcom, 25-26/11: `e2a22ce` conserto NVR Horizontes, `9e417e7` e `f629db5` Digifort): ver a entrada abaixo, escrita pela Helena.
- **Auditoria**: 20 arquivos (agente, servidor, painel); sem data com fuso no servidor, sem segredos, sem rota nova (só o campo `pasta_gravacao` na resposta de câmeras, já dentro da rota com `ctx`), sem compose/nginx/models/migrações/requirements. `tools/verificar_regras.py`: 0 erro, 0 aviso. Atenção operacional: com o NVR Hikvision sem responder, as novas tentativas (3 × 60 s no status, no `.bin` e no `.xls`) somam até ~6 min ao backup daquele equipamento (dentro do limite de 2 h).
- **Conflito**: só no `PROJECT_SPEC.md` (a Helena registrou no changelog antigo, que foi movido para este arquivo em 26/11): a entrada dela veio para cá sem mudança de texto.

### [2026-11-26] — Digifort: pasta de gravação de cada câmera lida direto da planilha; NVR Hikvision com nova tentativa da configuração

- **Origem (Digifort)**: na CFTV 03 do Navarro, a câmera "4° ANDAR A FUNDO CORREDOR" aparecia sem gravação nenhuma, mas os arquivos existiam. O equipamento não tinha "Local de gravação", então o agente deduzia a gravação do ping (câmera offline = 15 dias sem gravar). O export do Digifort já traz a coluna "Diretório de gravação" com o caminho de cada câmera (`D:\17\`, `D:\18\`...).
- **Painel**: `pastaGravacaoDoCaminho` guarda o caminho completo quando a célula tem unidade ou é UNC (`D:\17`, sem a barra final); sem unidade, continua o último trecho. Saíram `raizComumCaminhos`/`raizGravacaoDaPlanilha` e o preenchimento automático do "Local de gravação" (Galeria e formulário): com câmeras em discos diferentes não há raiz comum, e no caso da CFTV 03 a raiz saía `D:`, que no Windows é a pasta atual do disco, não `D:\`. O formulário do Digifort mostra "Pastas de gravação: lidas da planilha (N de M)" no lugar do campo; o campo continua para planilha sem a coluna ou para completar as câmeras sem caminho.
- **Servidor**: `NVRCameraResponse` e `GET .../cameras` (VMS) devolvem `pasta_gravacao`; `NVRCameraConfigItem.pasta_gravacao` com `max_length=255` (tamanho da coluna); `com_nomes_da_galeria` mostra o caminho completo como está (só o nome da subpasta continua virando o nome da Galeria). Sem migração.
- **Agente**: `digifort_gravacoes.pastas_das_cameras` / `calcular_gravacoes_pastas` leem direto a pasta de cada câmera da Galeria com caminho completo; `_resumos_gravacao_digifort` junta essas pastas com as subpastas do "Local de gravação" (a mesma pasta entra uma vez só) e o vínculo volta à câmera pela chave igual ao texto da Galeria. `normalizar_raiz` corrige "D:" digitado no campo. Câmeras só com o nome da subpasta (importações antigas) seguem como antes.
- **Origem (NVR)**: o NVR 03 da Horizontes (Hikvision DS-7616NI-K2) ficou PARCIAL em 23 e 25/11: o serviço web travou no meio da verificação de gravação (canais 9 a 14 `NAO_VERIFICADO`) e a configuração não baixou. `factory.WORKERS_GRAVACAO_HIKVISION` passa de 10 para 4 buscas simultâneas; `downloader.com_novas_tentativas` (3 tentativas, 60 s de pausa) e `isapi_responde` envolvem o status ISAPI e os downloads do `.bin`/`.xls`, no Windows (`backup_job`) e no Mikrotik (`tunel_preparo`).
- **Testes**: agente 338 OK (novos: `test_novas_tentativas_nvr.py`, `TestPastaCompletaDaPlanilha` e `normalizar_raiz` em `test_digifort_gravacoes.py`); servidor `test_galeria_pasta_gravacao.py` + `test_planilha_vms.py` + `test_galeria_sync_defense.py` 28 OK; painel `tsc --noEmit` limpo. Não testado no navegador nem numa máquina Digifort real.
- **Versão**: muda `agent/`; precisa de versão nova do agente no merge do dono.

### [2026-11-26] — Organização de pastas, documentos e nomes (sem mudança de comportamento)

- **Changelog**: saiu da seção 16 do `PROJECT_SPEC.md` para `docs/CHANGELOG.md` (178 entradas, texto intacto); o spec caiu de 2.879 para 1.137 linhas e a seção 17 passou a apontar para o checklist do `CLAUDE.md`. Referências atualizadas no `CLAUDE.md` e nas skills (Claude e Gemini) que mandavam registrar "no changelog do PROJECT_SPEC". Título do spec: "Trilan Backups".
- **`docs/CONVENCOES.md`** (novo): glossário conceito × modelo × tabela × rota (Cliente = `Customer`/`client_groups`, Máquina = `Machine`/`clients`, Equipamento = `NVR`/`nvrs` de qualquer tipo, `X-Client-ID` = id da Máquina), convenções de nomes para código novo (português sem acento, sem renomear o que existe) e onde cada tipo de arquivo fica.
- **`legacy/` juntado a `archive/`**: `archive/fiberhome-zabbix/` (templates Zabbix, scripts FiberHome/UNM, protótipos `dash-kpi/` e `lista-onus/`, nomes sem espaço) e `archive/relatorios/2026-10-27-sincronizacao-onedrive.md`. Removidos o `Template OLT FH.rar` (cópia da pasta já extraída) e a cópia repetida de `fiberhome_onu_discovery_name.py`. A cópia que ficou tinha a senha do banco do UNM escrita no código (repositório público): passou a ler `UNM_DB_USER`/`UNM_DB_PASS`; **a senha continua no histórico do git e deve ser trocada no banco do UNM**.
- **`agent/ferramentas/`** (novo): `baixar_fotos_facial*.py`, `build_baixar_fotos.ps1` e `testar_olt_loop.py` saíram da raiz de `agent/` (que fica só com o produto e o build); `testar_olt_loop.py` acha o código e o `agent.conf` pelo próprio caminho.
- **Credenciais locais** (fora do git): os três `.md` da raiz com nomes inconsistentes foram para `.credenciais/` (`servidor-windows-hyperv.md`, `vm-linux-dokploy.md`, `dokploy-painel.md`), ignorada pelo `.gitignore`; `server/deploy_producao.ps1`, `CLAUDE.local.md` e a skill `conciliar-backups-onedrive` apontam para lá.
- **Outros**: `skills-lock.json` removido (era do `npx skills`, que o projeto não usa; a origem foi para o frontmatter da skill `find-skills`); `tools/README.md` reescrito (tinha dois títulos e não listava o `verificar_regras.py`); `archive/README.md` e `agent/ferramentas/README.md`; README da raiz e árvore da seção 3 do spec atualizados; pastas vazias soltas removidas (`mikrotik/`, `teste backup motorola/`, `agent/src/camera;C`).

### [2026-11-25] — Agente 1.1.67: Fase 1 da auditoria (CI, TLS do agente, API sem bloquear o laço, senha do admin com bcrypt)

- **CI (DOC-02)**: `.github/workflows/ci.yml` roda em push (`isaque`, `producao`, `integracao-equipamentos`, `helena`) e PR: regras da auditoria de merge (`tools/verificar_regras.py`: segredo, arquivo de credencial ou binário >5 MB nas linhas/arquivos adicionados reprovam; REGRA-001, REGRA-010, `verify=False` novo no agente e senha padrão em lugar novo geram aviso), pytest da API (Python 3.11, como a produção), unittest do agente (Windows, Python 3.14, como o build) e `npm ci` + `npm run build` do painel. Não faz deploy.
- **Testes da API**: `server/api/requirements-dev.txt` (pytest, httpx) e `tests/conftest.py` comum. A suíte ficou 100% verde pela primeira vez: as "8 falhas antigas" eram a chave Fernet de teste inválida (corrigida em 32 arquivos), 3 testes de `test_storage.py` ainda na estrutura de pastas abandonada em out/2026 (reescritos para `_sem_cliente/<NOME>_<UUID>`), um teste com data fixa que "venceu" em 18/11 (`test_dashboard_status_equipamentos`) e o nome curto 8.3 da pasta temporária no Windows (resolvido no conftest).
- **API-01**: `test_equipamento_rtsp`, `comandar_central_alarme` (`routers/equipamentos.py`) e as rotas do OAuth do MCP (`mcp_server/oauth.py`) não consultam mais o banco nem rodam bcrypt no laço de eventos (trabalho síncrono em `asyncio.to_thread`, como o ping; o OAuth continua async só para ler o corpo). Mesmo padrão que derrubou a API em 23/11. Testes: `tests/test_rotas_async_sem_bloquear.py`.
- **API-05**: senha do login legado (só senha) em bcrypt. `conferir_senha_admin` aceita o valor antigo em texto puro uma vez e o regrava como hash; sem valor gravado vale `ADMIN_PASSWORD`. `PUT /settings` trata `admin_password_hash` como senha nova (mín. 10 caracteres, grava hash, recusa valor com formato de hash) e o GET não a devolve; a tela de Configurações mostra o motivo da recusa. Testes: `tests/test_senha_admin.py`.
- **AGT-02**: `api_client` com `requests.Session` única e cabeçalhos num lugar só; as 15 chamadas ao servidor passam a validar o certificado. Plano B: falha de **verificação** do certificado liga o modo antigo (`verify=False`) até o processo reiniciar e manda um aviso `[TLS]` ao painel uma vez; outros erros de TLS sobem como antes; `http://` continua funcionando com aviso `[TLS]`. Antes de tornar a validação obrigatória, procurar `[TLS]` nos logs. Equipamentos da LAN (NVR, câmeras, OLT, PABX, Defense) continuam `verify=False`. O update-check do Windows já validava (agora explícito, sem plano B). `installer.iss` sugere `https://server.suportetrilan.com.br`. Testes: `tests/test_api_client_tls.py`.
- **AGT-09**: `agent/requirements.txt` com versões fixas (`==`, do venv validado); `pypiwin32` trocado por `pywin32==312` (só Windows).
- **AGT-10**: `build.ps1` para no primeiro erro (confere o código de saída de pip/PyInstaller/python), confere a versão nos três lugares, roda a suíte de testes antes do PyInstaller e não recria o venv; salvo em UTF-8 com BOM.
- **Versão**: 1.1.67 em `updater.py`, `installer.iss`, `server/dashboard/package.json` (e `package-lock.json`). `requirements-linux.txt` intacto.

### [2026-11-25] — Agente 1.1.66: Fase 0 da auditoria (OTA Linux com certificado, segredo fora do log, README, .gitignore)

- **Origem**: auditoria de organização, padronização e documentação de 25/11/2026 (relatório no claude.ai, IDs AGT/API/WEB/DOC). Esta rodada aplica a Fase 0, exceto a senha padrão de câmera no código (AGT-03/API-06), que o dono decidiu manter por ora.
- **AGT-01**: `updater_linux.verificar_e_instalar` deixou de usar `verify=False` no `update-check`. A resposta escolhe a URL e o SHA-256 do pacote executado no container; sem validar o certificado, quem interceptasse a conexão trocaria os dois. O agente Linux já exige `https://server.suportetrilan.com.br` (certificado público). Teste: `test_update_check_valida_o_certificado`.
- **AGT-12**: `backup/downloader.py` ganhou `sem_query()`: os logs de HTTP de erro e de exceção não levam mais a query da URL. A URL do backup Hikvision traz `secretkey=...&iv=...` (dá para recuperar a senha do ZIP) e as mensagens do `requests` repetem a URL, o que o `split('?')` antigo não cobria. Teste: `agent/tests/test_downloader_log.py`.
- **API-03**: `test_isolamento_contas.py` usa `pytest.skip` sem `TRILAN_TESTE_ISOLAMENTO=1` (antes fazia `return` e aparecia como aprovado sem verificar nada).
- **WEB-02**: `npm run build` do painel passa a ser `tsc --noEmit && vite build` (erro de tipo derruba o build em vez de ir para a produção); novo script `typecheck`.
- **DOC-04**: `.gitignore` versionado com padrões de segredo (`*.local.md`, `.env.*` exceto os exemplos, `*.pem`, `*.key`, `id_rsa*`, `acesso*.md`, `chave api*.md`, `.pytest_cache/`); antes só o `.git/info/exclude` local protegia as credenciais da raiz.
- **DOC-01**: `README.md` da raiz reescrito (estava corrompido e falava só do agente de setembro): arquitetura, pastas, ambiente local, testes, instalação do agente, ramos e deploy pelo `server/deploy_producao.ps1`.
- **DOC-09/10**: skill `especialista-dashboard` com a regra de deploy nova; cópia do Gemini de `criar-novo-agente` com a linha da planilha `.xlsx` (nunca grava usuário/senha).
- **Versão**: 1.1.66 em `updater.py`, `installer.iss` e `server/dashboard/package.json`. `requirements-linux.txt` intacto. Suíte do agente: 328 testes OK.

### [2026-11-25] — Merge helena: Defense (planilha manda no acesso dos canais de gravador) e usuário SSH padrão `trilan_backup`

- **Entrou** (commits `17ddfd8` e `d87cfb6` da Helena, 13 arquivos, +231/−21, só servidor e painel): `services/planilha_vms.py` (`gravadores_da_planilha` traz `usuario`/`senha` da linha do gravador; `casar_cameras_por_ip` compara nomes sem pontuação), `services/galeria_vms.py` (`cameras_do_relatorio_sem_par` cria o canal com o acesso do gravador; novo `credenciais_dos_gravadores`), `PUT /machines/{id}/equipamentos/{id}/planilha` (Defense: atualiza usuário e senha cifrada dos canais de gravador já na Galeria), painel (coluna de usuário na importação da planilha, campo Usuário SSH com padrão `trilan_backup` e aviso) e o script `server/dashboard/public/preparar_acesso_ssh.ps1`, mais testes novos em `test_planilha_vms.py` e `test_galeria_sync_defense.py`.
- **Auditoria**: sem data com fuso (a rota segue com `datetime.utcnow()`), sem segredos (só valores fictícios nos testes; o script pede a senha na hora e não grava), rota alterada continua com `ctx` (`get_contexto`) e `_get_machine_or_404` com a conta e o equipamento filtrado pela máquina; a senha é gravada com `encrypt`. Nenhum arquivo sensível (compose, nginx, `models.py`, migrações, `requirements*`, `build.ps1`, `installer.iss`, `.env*`), nenhum arquivo na raiz nem binário. Nada bloqueado.
- **Testes**: `server/api/tests` com as mesmas 8 falhas antigas de antes do merge (`test_storage*`, `test_dashboard_status_equipamentos`); os testes novos passam. Sem mudança em `agent/`: sem versão nova do agente, sem build, release ou cadastro; deploy de Backend e Frontend pelo `server/deploy_producao.ps1`.

### [2026-11-25] — Usuário SSH padrão "trilan_backup" e script de preparo da máquina do cliente

- **Problema**: no Defense da `teste-mk-maquina` (agente no MikroTik), o backup falhava com `Connection reset by peer` no SSH de 192.168.75.41. Teste direto mostrou que o OpenSSH for Windows 9.5 derruba a conexão já no pedido de login do usuário `Administrator` (antes da senha); `Administrador`, `SERVIDOR-DEFENSE` e até um usuário inexistente recebiam a lista de métodos normalmente. Em Windows em português a conta interna é `Administrador` (e vem desativada); com `SERVIDOR-DEFENSE` o backup passou. Não existe nome de administrador comum a todos os Windows.
- **Solução** (escolhida pelo usuário): conta padrão `trilan_backup`, criada por um script. `server/dashboard/public/preparar_acesso_ssh.ps1` (baixável no painel em `/preparar_acesso_ssh.ps1`, idempotente): instala e liga o OpenSSH Server, libera a porta 22, cria ou redefine a conta `trilan_backup` (senha digitada na hora, nunca gravada) e a põe no grupo Administradores achado pelo SID `S-1-5-32-544` (vale em qualquer idioma); mostra o IP e a impressão digital da chave SSH. No formulário do equipamento (seção de acesso remoto, só agente MikroTik) o campo de usuário SSH vem preenchido com `trilan_backup` (`USUARIO_SSH_PADRAO` em `MachineDetail/utils.ts`), editável, com o link do script e o aviso sobre `Administrator`. Cadastros existentes com usuário preenchido não mudam.
- **Testes**: `tsc --noEmit` limpo; sintaxe do script conferida pelo parser do PowerShell e a busca do grupo pelo SID ("Administradores" neste Windows). O script não foi executado numa máquina de cliente.

### [2026-11-25] — Defense: a planilha manda no que a Galeria pegou sozinha

- **Problema**: a Galeria do Defense recebe câmeras sozinha (IP e marca do relatório do agente, senha padrão `navarro@123`) e a planilha exportada do Defense (com usuário e senha de cada dispositivo) só atualizava o que casava por IP ou nome exato, ignorava a coluna de usuário (o painel mandava sempre `admin`) e deixava os canais de DVR/NVR criados pelo relatório com a senha padrão, embora a linha do gravador na planilha traga a senha real.
- **Regra** (escolhida pelo usuário): a planilha manda nos casos casados; nada é apagado (câmeras que a planilha não traz, como canais de DVR do relatório, ficam com as imagens).
- **Servidor**: `casar_cameras_por_ip` compara nomes sem pontuação, espaços e maiúsculas ("1 ANDAR- ACESSO" = "1 andar - acesso"), para a câmera criada sozinha ser atualizada em vez de duplicada. `gravadores_da_planilha` passa a trazer `usuario` e `senha` da linha do gravador (quando as colunas existem). `cameras_do_relatorio_sem_par` (Sincronizar da Máquina) cria o canal de gravador já com esse usuário e senha. Novo `credenciais_dos_gravadores`: ao guardar a planilha (`PUT /{id}/planilha`) de um DEFENSE, os canais de gravador que já estão na Galeria passam a usar o usuário e a senha da linha do gravador (o log de alterações informa quantos).
- **Painel**: `rowsToCameras` lê a coluna "Nome de usuário"/"Usuário"/"User" e o usuário vai em `username` na importação (Galeria e formulário do Digifort); sem a coluna segue `admin`. A coluna de usuário não é mais confundida com a de nome da câmera.
- **Testes**: `test_planilha_vms.py` e `test_galeria_sync_defense.py` (casos novos); `tsc --noEmit` do painel limpo. Não testado contra o servidor real nem com a planilha de verdade do Defense; versão do agente não alterada (mudança só em servidor e painel).

### [2026-11-25] — Produção passa a vir do ramo `producao` do repositório público (deploy pelo script)

- **Problema**: desde 24/11 à tarde nenhum deploy entrava: o GitHub App do Dokploy (`dokploy-2026-08-12-thuirh`, ligado a `projetoswmfa/trilan-backup-automation`) passou a responder "Bad credentials" e não existe mais no GitHub; o deploy do Frontend da 1.1.65 ficou "running" por 14 h e travou a fila. O backend seguiu com o código das 13:42 de 24/11 e o pool do banco esgotou de novo na madrugada (API fora do ar até o reinício do serviço às 09:21). Recriar o App exigiria o login da conta `projetoswmfa` (dono do repositório; o nosso acesso é de colaborador, sem admin).
- **Mudança**: Backend e Frontend no Dokploy passaram para a fonte Git `https://github.com/isaqueschaffer/backup-automation.git`, ramo `producao` (público, sem credencial; caminhos `/server/api` e `/server/dashboard` mantidos; o GitHub App continua configurado mas fora de uso). O ramo `producao` tem o ruleset `producao-somente-admin` (update/creation/deletion/non-fast-forward bloqueados, com passe livre só para o administrador do repositório): Helena e `projetoswmfa` têm escrita no repositório público mas não atualizam `producao`. Sem webhook (o `gh` não tem `admin:repo_hook`), então o deploy é disparado pelo novo `server/deploy_producao.ps1` (push `isaque` -> `producao`, `application.deploy` do Backend e depois do Frontend pela API do Dokploy, espera cada um; credenciais lidas do arquivo local fora do git). Regras atualizadas em `CLAUDE.md` (produção, checklist da versão, merge), `.agents/rules/git-deploy.md` (o Gemini não empurra em `producao` nem faz deploy), skills `gerenciar-containers` (Claude e Gemini) e seção 11 deste arquivo.
- **Também**: o primeiro build pelo novo caminho falhou no `apt` (`OpenPGP signature verification failed`) porque o relógio da VM estava 48 min atrasado (chrony sem `makestep` depois de a VM ficar pausada); corrigido com `chronyc makestep` (autorizado pelo usuário). A fila travada foi limpa com `application.cleanQueues` (`cancelDeployment` não existe no Dokploy self-hosted) e o serviço `dokploy` foi reiniciado a pedido do usuário.

### [2026-11-24] — Servidor: pool do banco esgotado (API fora do ar de 16:35 a ~17:30)

- **Problema**: às 16:35 a API parou de atender toda rota com banco, inclusive o login (`QueuePool limit of size 5 overflow 10 reached`, 2.811 erros até 17:21). No Postgres havia 15 conexões `idle in transaction` (10 s a 13 min) esperando o backend: sessões abertas que não voltavam ao pool. Pouco antes: `Falha ao fechar a rodada … can't subtract offset-naive and offset-aware datetimes` e `Falha geral ao verificar licenças da UNM2000`. O disco da VM lento (iowait 48–72%) piorava. Voltou com o redeploy (container novo, pool vazio).
- **Causas encontradas no código**: (1) colunas `timestamptz` em produção devolvem data com fuso, e o fechamento das rodadas (`backup_runs._is_due/_still_running/finish_queue_run`) e `verificar_agentes_offline` comparavam com `datetime.utcnow()`; (2) `verificar_notificacoes` seguia para as próximas etapas sem `rollback` depois de uma falha, com a sessão em erro; (3) a sessão ficava numa transação aberta durante esperas longas sem banco: SMTP (até ~100 s), upload do ZIP (minutos, túnel do Mikrotik) e montagem do ZIP do Cliente no disco lento; (4) no ping, ler `machine.id` depois do commit fazia um SELECT síncrono no laço de eventos.
- **Correção**: `services/datas.para_utc_naive` (REGRA-001) aplicada nessas comparações; `verificar_notificacoes` grava cada etapa e desfaz só a que falhar; `database.encerrar_transacao` grava e devolve a conexão antes do SMTP (`email_service`, `notificacoes`, `avisos_conta`), do upload (`routers/agent._preparar_upload`, comum aos dois endpoints de upload) e da montagem dos ZIPs (`backup_runs._montar_zip`, que também unifica as três montagens); `get_db` faz rollback em erro; `sincronizar_imagens_existentes` fecha a transação por lote; `machine.id` lido antes do commit no ping. Rede de segurança no engine (Postgres): `pool_timeout` 10 s, `pool_recycle` 1800 s e `idle_in_transaction_session_timeout` 120 s (o banco encerra a sessão esquecida), configuráveis por `DB_*` em `config.py`; SQLite (testes) só `pool_pre_ping`. Diagnóstico no início: o log avisa quais colunas são `timestamptz` (só leitura).
- **Testes**: `server/api/tests/test_pool_e_datas.py` (4 novos). Suíte: 162 OK; 8 falhas em `test_storage*`/`test_dashboard_status_equipamentos` já existiam antes da mudança (mesmas 8 com o código anterior, nesta máquina Windows).
- **Sem versão do agente** (só servidor). Trabalho iniciado por um subagente que foi interrompido; revisado e concluído na sessão principal.

### [2026-11-24] — Merge `helena` + Agente 1.1.65: backup restaurável dos NVR Motorola

- **Entrou** (commit `e1390a4` da Helena): `agent/src/nvr/motorola/backup.py` (exportação da configuração sem plugin, pelo protocolo binário da porta de serviço ou pelo WebSocket H5; entrada abaixo), integração em `backup_job.processar_nvr` (Windows) e `tunel_preparo.preparar_nvr` (Mikrotik, em memória), `sessionId` do `reqLogin` em `motorola/cameras.py`, testes `test_motorola_backup.py` e ajuste em `test_tunel_sftp.py`, docs (`DOCUMENTACAO_AGENTE.md`, `README_MIKROTIK.md`).
- **Auditoria**: só `agent/` e docs (9 arquivos, +736/−10); sem data com fuso, sem segredos (a senha só vai no login da porta de serviço do NVR e não aparece em log), sem rotas do servidor, compose, nginx, models ou requirements; sem dependência nova. Conflito apenas no changelog (mantidas as duas entradas). Nada bloqueado. Suíte do agente: 324 testes OK.
- **Versão**: 1.1.65 em `updater.py`, `installer.iss` e `server/dashboard/package.json` (a 1.1.64 foi publicada no GitHub mas não chegou a ser cadastrada no painel; a 1.1.65 a substitui). `requirements-linux.txt` intacto.

### [2026-11-24] — Backup restaurável da configuração dos NVR Motorola, sem plugin

- **Problema**: a exportação da configuração dos NVR Motorola (OEM TVT, NVMS-9000) só existia pela tela web com o plugin ActiveX no Internet Explorer; o agente só verificava gravações e o backup ficava `SEM_ARQUIVOS`.
- **Investigação**: com um relay TCP entre o plugin e o NVR, a captura mostrou que o plugin não cifra nada: o arquivo já sai cifrado do NVR e os bytes da rede são exatamente o arquivo salvo (SHA-256 igual). O plugin só faz login e transporte na porta de serviço.
- **Implementação** (`agent/src/nvr/motorola/backup.py`, Python puro, sem dependência nova): `exportConfig` (HTTP, com a configuração de rede) e então um de dois caminhos: (1) protocolo binário da porta de serviço (`queryUPnPCfg`, item SERVICE; 6036 por padrão), pacotes `1111` + tamanho: login (usuário/senha), info, abertura `EXPORT_CONFIG_FILE` (a resposta traz o tamanho), blocos de 4 KB com ACK, fim e fechamento; (2) modo H5 dos firmwares 1.4.x (plugin v5): WebSocket `/requestWebsocketConnection?sessionID=<sessionId do reqLogin>` com `/device/file/download/start|step|stop` (cliente WebSocket mínimo próprio, RFC 6455). O caminho é escolhido sem tentar login (o firmware H5 serve `js/lib/websocket.download.js`); se falhar por protocolo, o outro é tentado; os dois falhando, uma 2ª rodada após 10 s (o TD-3316B2-A1 fechou a conexão uma vez). Login HTTP recusado não insiste (evita bloquear o usuário). Prazo total de 300 s; tamanho conferido com o anunciado pelo NVR. `abrir_sessao_motorola` guarda o `sessionId` do `reqLogin` em `tvt_session_id`.
- **Integração**: `processar_nvr` (Windows) grava `CONFIG_MOTOROLA_<data>.bin`; `preparar_nvr` (túnel do Mikrotik) leva o arquivo em memória (`LIMITE_MEMORIA`). Status `OK`, ou `PARCIAL` se a exportação falhar. No túnel o container precisa alcançar também a porta de serviço do NVR.
- **Validação** (24/11/2026, 192.168.124.2 a .10): TD-3116B2 1.3.3 e TD-3316B2-A1 1.3.4 (plugin v2), TD-2008NS-HL 1.3.7 e TD-2116NS-HL 1.3.8 (plugin v3) pelo protocolo binário; TD-3316B2-A1 1.4.8 (plugin v5) pelo WebSocket. Arquivos de 88 a 169 KB em 3 a 7 s, todos com o mesmo cabeçalho de arquivo do NVR; o do .2 é idêntico ao exportado pelo plugin. Testes: `agent/tests/test_motorola_backup.py` (NVR falso local com os dois protocolos). Não testado: restaurar um desses arquivos (reinicia o NVR) e senha errada num NVR real.
- **Versão**: não alterada (entra na próxima). `requirements-linux.txt` intacto.

### [2026-11-24] — Merge `helena` + Agente 1.1.64: marca da câmera do Defense na captura noturna RTSP

- **Entrou** (commit `3775bc6` da Helena, pelo merge `808e2b4`): `agent/src/vms/defense.py` lê a marca do dispositivo na árvore do Defense pelo campo `protocol` (1 = Intelbras/Dahua, 2 = Hikvision, 99 = ONVIF, caso das Motorola MTI/DIH), com `manufacturer` de reserva, e grava `marca` em cada câmera de `extrair_cameras_defense_tree`. Nova `completar_marca_cameras_defense` preenche a marca das câmeras da Galeria sem marca (casa por IP; sem IP, pelo nome) antes da captura noturna (`captura_noite_vms.py`, só tipo DEFENSE; falha na API só registra aviso e a captura segue deduzindo pelo modelo). `rtsp_client.capturar_imagens_noite_vms` passa `marca` à tarefa RTSP. Testes em `test_defense_api.py` e `test_captura_noite_vms.py`.
- **Auditoria**: só `agent/` (5 arquivos, +144); sem data com fuso, sem segredos, sem rotas do servidor, compose, nginx, models ou requirements. Nada bloqueado. Suíte do agente: 307 testes OK.
- **Versão**: 1.1.64 em `updater.py`, `installer.iss` e `server/dashboard/package.json`. `requirements-linux.txt` intacto.

### [2026-11-23] — Agente 1.1.63: foto pela API HTTP da Hikvision quando o RTSP não entrega imagem

- **Problema**: no Digifort do CFTV 01 - Navarro, 12 câmeras de elevador (Hikvision DS-2CD1101-I, 2º ao 13º andar) nunca tiveram imagem ideal nem da noite: todos os caminhos RTSP (Hikvision, Intelbras, ONVIF, Grandstream), em TCP e UDP, davam "Tempo esgotado". Não era modelo (o 1º andar, que funciona, é o mesmo DS-2CD1101-I), caminho (seria 404) nem senha (seria 401; as credenciais vieram todas da mesma importação de 11/11). Com o `-timeout` de 5 s do ffmpeg, câmera muda daria erro em 5 s: estourar os 18 s indica que o RTSP troca dados mas não sai quadro (provável taxa de quadros baixa ou intervalo de quadro-chave longo, com `-skip_frame nokey`). O tempo esgotado descartava a saída do ffmpeg, e o diagnóstico ficava cego.
- **Correção** (`agent/src/camera/rtsp_client.py`): (1) o tempo esgotado do ffmpeg leva a última linha da saída dele (`[ffmpeg: ...]`, sem credenciais); (2) em câmera Hikvision/genérica, se o RTSP falhar sem 401, `test_rtsp_camera` pede a foto pela API HTTP (`/ISAPI/Streaming/channels/<ch>01/picture`, depois `/Streaming/channels/<ch>01/picture`), com autenticação digest e a mesma senha. Vale para ao vivo, referência e imagem da noite de VMS. 401/403 no HTTP para na hora (bloqueio de usuário); 401 no RTSP nem tenta o HTTP. Testes: `agent/tests/test_foto_hikvision.py`.
- **Versão**: 1.1.63 em `updater.py`, `installer.iss` e `server/dashboard/package.json`. `requirements-linux.txt` intacto.

### [2026-11-23] — Agente 1.1.62: câmeras do Defense no backup em túnel do MikroTik

- **Problema**: na máquina do MikroTik, o teste de conexão do Defense listava as 20 câmeras, mas a Galeria e a Gravação do equipamento ficavam vazias. O `preparar_defense` do túnel (`agent/src/backup/tunel_preparo.py`) só achava o arquivo de backup e mandava `cameras: None` no relatório; no Windows, `realizar_backup_defense` também monta o status das câmeras pela API.
- **Correção**: `preparar_defense` chama `_montar_status_cameras_defense` (mesma função do Windows: online e gravações pela API do Defense, nada gravado no roteador) e põe as câmeras no relatório em qualquer desfecho do arquivo (inclusive ERRO por falta de `pasta_origem`). Falha na API só deixa `cameras` vazio. A busca do arquivo virou `_preparar_arquivo_defense`, sem mudança. Teste: `agent/tests/test_tunel_defense_cameras.py`.
- **Versão**: 1.1.62 em `updater.py`, `installer.iss` e `server/dashboard/package.json`. `requirements-linux.txt` intacto. Vai junto a correção do ping da API (entrada abaixo).

### [2026-11-23] — API: ping do agente sem consulta síncrona no laço de eventos (impasse que derrubou a produção)

- **Incidente**: a VM 192.168.75.112 reiniciou às 02:35 UTC e o `dokploy-postgres` subiu sem IP na `dokploy-network` ("invalid IP"); o Dokploy reiniciava a cada 2 min ("Postgres not reachable") e `dokploy.suportetrilan.com.br` dava 502. Corrigido com `docker service update --force dokploy-postgres`. O push da 1.1.61 tinha se perdido nesse intervalo; o redeploy manual subiu um container novo do Backend que travou: as 15 conexões do pool (5 + 10) ficaram em "idle in transaction", toda requisição esperava 30 s e falhava (`QueuePool limit … reached`), e até um 404 demorava 25 s.
- **Causa**: `POST /agent/ping` é `async def`, mas fazia `commit`, `_read_request_flags` (5x no long-poll), `db.get` e a poda de logs direto no laço de eventos. Com o pool cheio, o laço parava 30 s esperando conexão; as conexões presas eram de outros pings, que pegaram a conexão na resolução das dependências (thread) e só a devolveriam quando o laço voltasse a rodar. Na subida de um container novo os 18 agentes chegam juntos e o impasse se instala.
- **Correção** (`server/api/routers/agent.py`): a parte síncrona do ping foi para `_iniciar_ping` e `_concluir_ping`, chamadas com `asyncio.to_thread`, assim como `db.close()` e `_read_request_flags`. O laço só faz a espera e aciona os `asyncio.Event` das tarefas RTSP/alarme. Teste: `server/api/tests/test_ping_sem_bloquear.py`.
- **Pendente**: os erros "can't compare offset-naive and offset-aware datetimes" em `services/notificacoes.py:228` (`verificar_agentes_offline`) e `services/backup_runs.py:266` (`_is_due`) aparecem no log (capturados, não derrubam a API), contrariando a REGRA-001; tratar à parte.

### [2026-11-23] — Agente 1.1.61: imagem da noite e de referência pela gravação em NVR Intelbras

- **Problema**: na Galeria do NVR Intelbras 192.168.75.6 (iNVD 3016), "Capturar imagem da noite" respondia "NVR não entregou o trecho gravado" em todas as câmeras. A captura pela gravação (modos `noite` e `referencia` da tarefa RTSP) só tinha playback Hikvision e Motorola; sem marca Motorola, caía no playback Hikvision (`/Streaming/tracks/<canal>01`) e o NVR Dahua respondia 404. Não era do túnel do MikroTik: o agente Windows faria o mesmo.
- **Correção** (`agent/src/camera/rtsp_client.py`, `agent/src/nvr/intelbras/recordings.py`): playback Dahua `rtsp://…:554/cam/playback?channel=N&subtype=0&starttime=AAAA_MM_DD_HH_MM_SS&endtime=…` (horário do relógio do NVR). Trechos pela busca `mediaFileFind.cgi` (`buscar_trechos_intelbras`: lista de (início, fim), `[]` sem gravação, `None` se a busca falhou). Noite: 02:00 limitado ao trecho, como no Hikvision; sem busca, horários fixos com tempo curto; desiste após `MAX_FALHAS_CAPTURA`. Referência: fim do trecho mais recente, em janelas de 6 h até `DIAS_BUSCA`.
- **Escolha da marca** (`_eh_intelbras`): "Intelbras"/"Dahua" na marca ou no modelo do equipamento decide; "Motorola"/"Hikvision" exclui; marca vazia sonda `magicBox.cgi?action=getDeviceType` uma vez por tarefa. Câmera direta (VMS) segue só ao vivo. "INTELBRAS" saiu de `_sem_playback` (antes um NVR com "Intelbras" no modelo recebia "captura pela gravação não suportada").
- **Testes**: `agent/tests/test_playback_intelbras.py` (8, com o CGI e o ffmpeg simulados). Não testado contra o NVR real antes da release.
- **Versão**: 1.1.61 em `updater.py`, `installer.iss` e `server/dashboard/package.json`. `requirements-linux.txt` intacto (a OTA do MikroTik aceita).

### [2026-11-19] — Agente 1.1.60: backup de todos os tipos no túnel do MikroTik (SFTP, memória, nada em disco)

- **Versão**: 1.1.60 em `updater.py`, `installer.iss` e `server/dashboard/package.json` (este estava em 1.1.59 e foi corrigido). Sem biblioteca nova (`requirements-linux.txt` intacto: paramiko 3.4 já traz SFTP).
- **Alarmes do Defense — correção revertida**: a 1.1.60 inicial (`33735f0`) trocou o token CSRF de `gerar_token_csrf()` para HMAC-SHA1. Conferido no Defense IA real (192.168.75.41:3001) em 19/11: SHA1 simples é aceito (login com senha errada → 401 "credenciais inválidas") e HMAC é recusado (403 "Token CSRF inválido"). Voltou o SHA1 simples (o teste `test_formato_do_pacote_csrf` já esperava isso); sem a reversão, a 1.1.60 quebraria status e armar/desarmar das centrais em todos os agentes.
- **Regra central**: o MikroTik é ponte; nenhum dado de backup é gravado no roteador, nem temporário (a 1.1.60 inicial gravava o NVR Intelbras em `data/tmp_nvr`; removido). Tudo passa por `backup/tunel.py` (ZIP AES em fluxo -> `PUT /agent/backup/upload-stream/{id}`). Origens do ZIP: SMB, **SFTP**, **memória** (configs pequenas, até `LIMITE_MEMORIA` = 64 MB; acima disso o equipamento vira ERRO com mensagem clara) e **fluxo HTTP** (PABX grande/sem Content-Length). Planilhas do NVR entram no ZIP global em `NVR/PLANILHA/` (mesmos nomes do Windows).
- **Origem SFTP** (`agent/src/backup/sftp_origem.py`): para UNM2000, Digifort e Defense o agente entra por SSH na máquina do cliente (OpenSSH Server do Windows ou Linux) e lê por SFTP em blocos; nada é criado no cliente (sem usuário novo, share ou porta 445). Somente leitura (`PastaSftp` só tem listar/stat/tamanho/abrir) e todo caminho é conferido contra a `pasta_origem` (`..` e fora da pasta são recusados); `D:UNM2000/emsback` vira `/D:/UNM2000/emsback`. A seleção do backup é a do Windows (`UNM2000Parser._find_backups_sftp`, mesmas regras de data esperada, completude e estabilidade; Digifort `DIGIFORT_DIR` pasta inteira).
- **Método**: `config_extra.acesso_remoto` = `sftp` | `smb`. Ausente = comportamento anterior (SMB provisionado por SSH), para não quebrar cadastros que já funcionam; o formulário novo grava `sftp` por padrão (cadastro antigo sem o campo aparece como `smb`). O agente Windows ignora o campo.
- **Segurança SSH**: fim do `AutoAddPolicy` nos caminhos do túnel. TOFU como o OpenSSH: a 1ª conexão grava a impressão digital em `/app/data/known_hosts_trilan` (e registra no log do painel), chave diferente depois = recusa "a chave SSH de <host> mudou" (status ERRO). `ssh_fingerprint` (SHA256:...) no cadastro prevalece e é exigida. Autenticação por senha ou por chave privada (`ssh_chave`, só em memória). Senha e chave nunca vão ao log. O provisionamento SMB por SSH (`smb_ssh_provisioner`) também passa a verificar a chave quando roda no Linux; no Windows segue como antes.
- **Servidor/painel**: `ssh_chave` entra em `SEGREDOS` (`services/segredos_config.py`): cifrada em `ssh_chave_enc`, o painel só recebe `ssh_chave_definida`, vazio mantém, só o agente recebe o texto (igual à `ssh_senha`). `validar_acesso_remoto` (criar e editar equipamento) valida `acesso_remoto`, chave privada, `ssh_fingerprint` e `ssh_porta`. `config_extra` é JSON: sem migração de banco. Formulário (`SmbConfigSection`, só com `agenteTipo === "MIKROTIK"`; UNM2000, Digifort e Defense): IP da máquina, método, usuário/senha/porta SSH, chave privada (textarea) e impressão digital. Corrigido: o payload do Defense não enviava os campos de acesso remoto.
- **Equipamentos de rede, tudo em memória**: NVR Intelbras (CGI) e Hikvision (`.bin` com secretkey da senha do ZIP + `.xls`), Motorola = SEM_ARQUIVOS, com `cameras` (status de gravação), `telemetria` e planilha como no Windows (planilha que falha não muda o status); PABX Issabel (memória se Content-Length <= limite, senão HTTP em fluxo); OLT VSOL (HTTP em memória, mantendo `_parece_config/_parece_html`); MIKROTIK (SSH no roteador-alvo, `/system backup save` + `/export`, SFTP em blocos, depois remove os dois arquivos do alvo; eles ficam transitoriamente na flash do alvo, inevitável porque o RouterOS só gera backup em arquivo); OLT Huawei: sem FTP efêmero (exigiria porta 21 e NAT no roteador), o agente lê `display current-configuration` por SSH (paginação tratada) e envia `current-configuration_<nome>_<data>.txt`: é a config em texto (restaurável colando no terminal), diferente do binário `backup configuration`/`backup data` do Windows. CAMERA e ANTENA seguem sem backup. Defense sem `pasta_origem` = ERRO ("configure a pasta de backup do Defense"; sem dump de banco).
- **Windows**: o agente Windows continua gravando em disco como antes (as funções ganharam variantes em memória: `baixar_configuracao_intelbras_memoria`, `baixar_bytes`, `realizar_backup_vsol(em_memoria=True)`, planilhas aceitam `BytesIO`).
- **Testes**: `agent/tests/test_tunel_sftp.py` (servidor SSH/SFTP real em 127.0.0.1: conversão de caminho, `..`/fora da pasta, TOFU, fingerprint, chave privada, leitura em blocos, ZIP com origens SFTP + memória + HTTP, nenhum arquivo criado fora do known_hosts, seleção UNM2000/Digifort, NVR, PABX, Huawei) e `server/api/tests/test_segredos_config.py`.
- **Arquivos**: agent/src/backup/{sftp_origem,tunel,tunel_preparo,downloader,smb_ssh_provisioner}.py, agent/src/backup/file_manager/{models,parsers,manager,validators}.py, agent/src/application/backup_job.py, agent/src/olt/{huawei_texto,vsol}.py, agent/src/pabx/issabel.py, agent/src/mikrotik/routeros.py, agent/src/nvr/*/planilha.py, agent/src/nvr/intelbras/backup.py, agent/README_MIKROTIK.md, server/api/services/segredos_config.py, server/api/routers/equipamentos.py, server/dashboard/src/{api/types.ts,pages/Machines/MachineDetail/utils.ts,.../components/EquipamentoFormModal.tsx}, server/dashboard/package.json.

### [2026-11-19] — Agente 1.1.59: compatibilização de comandos e script de provisionamento RouterOS

- **Versão**: bumped para 1.1.59 em `updater.py` (`CURRENT_VERSION`), `installer.iss` (`AppVersion`) e `server/dashboard/package.json`.
- **Conteúdo da versão**: incorpora script `agent/mikrotik/setup.rsc` para provisionamento no RouterOS e alinhamento do schema `PingResponse` (`alarme_task`).
- **Arquivos**: agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json, PROJECT_SPEC.md.

### [2026-11-19] — Merge do ramo `helena` — alarme_task no schema PingResponse

- **Schema da API (`server/api/schemas.py`)**: adicionado `alarme_task: Optional[dict] = None` ao schema `PingResponse`. O endpoint de ping (`routers/agent.py`) já retornava `alarme_task=comando["task"]` para despachar comandos de armar/desarmar central do DEFENSE (agente >= 1.1.50), e agora o campo está explicitamente declarado no modelo de resposta Pydantic.
- **Auditoria**: sem datas com fuso, sem segredos ou credenciais, sem impacto em regras de isolamento.
- **Sem alteração em código executável do agente ou painel**: nenhuma nova versão do agente foi gerada.
- **Arquivos**: server/api/schemas.py, PROJECT_SPEC.md.

### [2026-11-19] — Merge do ramo `helena` — script `setup.rsc` e provisionamento de rede/firewall no MikroTik

- **Provisionamento MikroTik (`agent/mikrotik/setup.rsc`)**: script idempotente para RouterOS v7 que provisiona as regras de firewall e encaminhamento necessárias quando o container do agente roda no próprio MikroTik:
  - Libera entrada SSH (TCP/22) vindo da bridge do container (`br-trilan`, sub-rede `172.30.250.0/30`) antes do primeiro drop da chain input (`TRILAN-SSH-ANTENAS`);
  - Inclui a sub-rede no `available-from` do serviço `/ip service ssh` se houver restrição configurada;
  - Libera encaminhamento (`forward`) da bridge para alcançar antenas e equipamentos em outras sub-redes (`TRILAN-FORWARD-CONTAINER`);
  - Aplica regra de NAT `masquerade` para a sub-rede do container alcançar a rede das antenas (`TRILAN-NAT-CONTAINER`).
- **Documentação (`agent/README_MIKROTIK.md`)**: adicionada seção detalhada "Regras de rede e firewall (SSH e Antenas)" instruindo a execução do script `/import setup.rsc`.
- **Auditoria**: sem datas com fuso, sem segredos ou credenciais, sem conflitos com regras do projeto.
- **Sem alteração em código executável do agente, servidor ou painel**: nenhuma nova versão do agente foi gerada.
- **Arquivos**: agent/mikrotik/setup.rsc (novo), agent/README_MIKROTIK.md, PROJECT_SPEC.md.

### [2026-11-18] — Painel: trocar "onde o agente roda" (Windows/MikroTik) de uma máquina já criada

**Problema:** o tipo do agente (`clients.agente_tipo`, WINDOWS | MIKROTIK) só era escolhido na criação da máquina; se o cliente trocasse (ex.: tirou o Windows e passou a usar o MikroTik, ou o contrário), era preciso criar outra máquina e perder o histórico. O backend já aceitava o campo no `PUT /api/v1/machines/{id}` (`MachineUpdate.agente_tipo`) e já o registrava nos Eventos do Agente ("onde o agente roda"), mas o modal "Editar Máquina" não mostrava o campo.
**Alteração (painel):** `EditMachineModal` ganha o seletor "Onde o agente roda" (mesmos textos da criação) e, quando o valor muda, um aviso do que fazer: instalar o agente no novo lugar com o mesmo Client ID/API Key da máquina (histórico preservado), revisar os equipamentos (IP de cada um; UNM2000/Digifort com o IP da máquina da pasta) e, no MikroTik, que só o backup em túnel de UNM2000/Digifort roda. `MachineDetail` envia `agente_tipo` no salvar.
**Testes:** `server/api/tests/test_agente_tipo_edicao.py` (novo, 3: troca nos dois sentidos com registro do evento, editar outro campo não muda o tipo, valor inválido recusado); `tsc` e build do painel OK.
**Arquivos:** server/dashboard/src/pages/Machines/MachineDetail/{index.tsx,components/EditMachineModal.tsx}, server/api/tests/test_agente_tipo_edicao.py (novo), PROJECT_SPEC.md.

### [2026-11-18] — Agente 1.1.58: Mikrotik como túnel (backup em fluxo, nada gravado no roteador), coletas e OTA que instala biblioteca nova

**Decisão:** o Mikrotik é **ponte** até o servidor: pouco processamento e nada gravado no roteador. Faz backup só **em túnel** (lê do cliente por SMB e envia ao servidor em fluxo, sem arquivo no roteador; decisão de 18/11, ver abaixo), não roda os webhooks Defense/Digifort (gravam CSV que só o relatório do backup lê) e a imagem da noite só sai quando pedida na Galeria (o ciclo automático da madrugada liga só com `TRILAN_NOITE_AUTOMATICA=true`).
**Problema:** o agente Linux não tinha as coletas do Windows; cada versão que mudava o `requirements-linux.txt` (a 1.1.57 trouxe `smbprotocol`) exigia gerar e trocar a imagem à mão. A imagem usava Python 3.11 e o build do Windows usa 3.14: o `smb_storage.py` da 1.1.57 não compilava no 3.11, e a OTA do Linux (que confere a sintaxe) recusaria o pacote. Faltava `ping`, e sem `TZ` o container rodava em UTC. O ffmpeg do Debian deixava a imagem com ~482 MB (o RB4011 tem ~479 MB livres).
**Alteração (agente):** `service_linux.py` ganha as rotinas do `service.py` que cabem numa ponte: presença das câmeras, status das OLTs, antenas, alarmes do Defense (coleta e `alarme_task` armar/desarmar, com `recursos_extra=("comando_alarme",)` no ping) e vigia de backup travado. `updater_linux.garantir_requisitos`: em vez de recusar qualquer mudança no `requirements-linux.txt`, confere cada linha com `importlib.metadata` + `packaging` e instala as que faltam com `pip install --user --only-binary=:all:` em `PYTHONUSERBASE=/app/data/pyuser` (o `service_linux.py` põe essa pasta no `sys.path` também em imagens antigas); só recusa se o pip falhar. `smb_storage.py` (linha 252) sem `\\` dentro de f-string (compatível com Python < 3.12). Windows: sem mudança de comportamento.
**Alteração (imagem, `Dockerfile.mikrotik`):** base `python:3.14-slim-trixie`; ffmpeg 7.1.1 compilado no build só com RTSP/RTP, H.264/H.265/MJPEG/MPEG-4 e saída JPEG (hash do código-fonte conferido); `iputils-ping`; `TZ=America/Sao_Paulo`; sem `mysqldump` (o túnel só lê pasta de rede); `smbprotocol` no `requirements-linux.txt` (backup em túnel); imagem sem o SMB: 193 MB instalada, 60 MB no `docker save`, captura ao vivo e referência OK no NVR Intelbras (~4 s por foto no emulador); `verificar_imagem.py` roda no fim do build e reprova a imagem se faltar programa, fuso, biblioteca ou se algum módulo não compilar/importar. Precisa de uma troca manual da imagem no RouterOS (ver `agent/README_MIKROTIK.md`).
**Backup em túnel (18/11):** o Mikrotik é ponte também no backup: `agent/src/backup/tunel.py` lê o backup do UNM2000/Digifort por SMB e o envia ao servidor **em fluxo**, sem arquivo temporário no roteador. Antes (e ainda no Windows) o `backup_job` copia para `tmp_backup_work`, faz o ZIP interno, o ZIP global com senha em `tmp_backup_final` e só então envia. Agora o ZIP global (AES, senha da máquina) e o `backup.zip` de cada equipamento são montados com `pyzipper`/`zipfile` num destino só-escrita (data descriptors), uma fila de ~2 MB faz a contrapressão e o corpo vai num `PUT` em pedaços; memória em poucos MB, qualquer tamanho. Estrutura do ZIP idêntica à do Windows. Conferência pelo tamanho lido contra o `stat` do cliente (não há cópia local para comparar hash); divergência = `CORROMPIDO`, o envio aborta, o servidor descarta o `.part` e o ZIP é refeito sem aquele equipamento. Compressão desligada por padrão (`TRILAN_TUNEL_COMPRESSAO=deflate` liga). Só UNM2000 e Digifort por pasta de rede; NVR, PABX, VSOL, Huawei, Mikrotik e Defense respondem `TIPO_NAO_SUPORTADO` (gravam em disco: ficam com o agente Windows); o status de gravação das câmeras do Digifort (lido dos arquivos copiados) não sai pelo túnel. `FileManager.process_equipment(..., somente_preparar=True)` (e `processar_olt`/`realizar_backup_olt`) reaproveita a busca, a validação e a espera de estabilidade e devolve `PRONTO` com os arquivos de origem em vez de copiar.
**Servidor (18/11):** `PUT /api/v1/agent/backup/upload-stream/{backup_id}` (corpo em pedaços, mesmas regras do upload comum; `save_zip_async_stream` grava em `.part` e só então substitui; o resto saiu para `_registrar_zip_recebido`, comum aos dois envios) e `POST /api/v1/agent/backup/{backup_id}/resultado` (corrige o status de um equipamento depois do relatório, que sai antes do envio com os prontos como OK provisório; recalcula `backup.status` e, se for o último backup, `machine.last_backup_status`). Sem mudança no envio do Windows, em rotas existentes ou em migrações.
**Testes (18/11):** agente `test_tunel_linux.py` (novo, 11: ZIP com senha confere conteúdo e não cria arquivo, tamanho divergente, falha do SMB, pasta recursiva, memória limitada com 40 MB, desistência do envio, refazer sem o equipamento, falha de rede); servidor `test_upload_tunel.py` (novo, 6). Verificado com HTTP de verdade (60 MB em pedaços, direto no uvicorn e também pelo `nginx.conf` do projeto): conteúdo idêntico, divergência não deixa arquivo. `verificar_imagem.py` ganhou um autoteste do túnel. Não validado ainda: backup real de um UNM2000 pelo Mikrotik e o caminho do Traefik/Dokploy em produção (corpo em pedaços; o limite de 200 MB do nginx vale igual ao envio comum).
**Testes:** `agent/tests/test_rotinas_linux.py` (novo, 6), `agent/tests/test_ota_linux.py` (regra nova de bibliotecas, 4).
**Arquivos:** agent/{service_linux.py,src/backup/tunel.py (novo),src/backup/file_manager/manager.py,src/olt/unm2000.py,src/application/{backup_job.py,api_client.py},tests/test_tunel_linux.py (novo),verificar_imagem.py (novo),Dockerfile.mikrotik,requirements-linux.txt,pacote_linux.py,README_MIKROTIK.md}, agent/src/application/{updater_linux.py,updater.py}, agent/src/backup/smb_storage.py, agent/tests/{test_rotinas_linux.py,test_ota_linux.py}, agent/installer.iss, server/dashboard/package.json, server/api/{routers/agent.py,services/storage_service.py,tests/test_upload_tunel.py (novo)}, PROJECT_SPEC.md.

### [2026-11-17] — Agente no MikroTik: captura RTSP, leitura de pastas por SSH/SMB e escolha "onde o agente roda"

- **Máquina**: nova coluna `clients.agente_tipo` (`WINDOWS` padrão | `MIKROTIK`, migração inline em `main.py`); `MachineCreate/Update/Response` ganham `agente_tipo`. Na criação da máquina o painel pergunta onde o agente roda; com `MIKROTIK`, o formulário de UNM2000/Digifort mostra o acesso remoto e exige o IP da máquina (`smb_host`).
- **Agente Linux** (`service_linux.py`, `rtsp_client.py`, `Dockerfile.mikrotik`): `rtsp_task` do ping e laço da imagem da noite (DIGIFORT/DEFENSE) agora rodam no Linux, sequenciais (`RTSP_LOCK`); ffmpeg do sistema no container, `-update 1` nas saídas.
- **Pastas remotas** (`smb_storage.py`, `smb_ssh_provisioner.py`): leitura por SMB; com `config_extra.ssh_usuario/ssh_senha/ssh_porta` o agente entra por SSH, cria o usuário somente leitura `trilan_leitura` e um share oculto por pasta, guarda a credencial em `data/smb_leitura.json` e recria sozinho se o acesso falhar (backup e teste de conexão). `ssh_senha` entra em `SEGREDOS` (Fernet).
- Breaking change: nenhum (campos opcionais; agentes antigos ignoram). Branch: `helena`.

### [2026-11-17] — Merge do ramo `helena` — agente 1.1.57 (SMB, Defense/ONVIF por canal, captura no Mikrotik, notificações por usuário)

- Reúne o que dependia de agente novo: **coleta de ANTENAS** (`_antena_loop`, leitura SSH do MikroTik, ping, marca detectada), **Defense**: gravadores DVR/NVR com `dispositivo` no relatório e captura **ONVIF com o canal** (`rtsp_client`, tarefa com `gravador`). Versão em `updater.py`, `installer.iss` e `package.json`.
- **Backup em pasta de rede (SMB)**: `agent/src/backup/smb_storage.py` (`smbprotocol`), usado pelo copiador, validadores, parsers e pelo teste de conexão; `smb_senha`/`smb_password` entram em `segredos_config.SEGREDOS` (cifrados no banco).
- **Agente Linux (Mikrotik)**: atende `rtsp_task` da Galeria (uma captura por vez, `RTSP_LOCK`) e roda a imagem da noite das câmeras Digifort/Defense (`noite_loop`); `rtsp_client._ffmpeg_exe()` usa o ffmpeg do sistema fora do Windows; `Dockerfile.mikrotik` instala `ffmpeg`. **Precisa de imagem nova do container** (ffmpeg e `smbprotocol` em `requirements-linux.txt`: a OTA do Linux recusa a versão até a troca). Teste local em ARMv7: ao vivo e referência OK; a imagem com o ffmpeg do Debian ocupa ~482 MB, acima do livre no RB4011 (~479 MB), a reduzir antes da troca.
- **Auditoria**: mostra o nome do usuário (`usuario_nome`, `UsuarioAuditoriaOpcao`); no merge, a busca dos nomes passou a filtrar pela conta (REGRA-010).
- No merge, as entradas 1.1.55 e 1.1.56 abaixo (que o ramo tinha sobrescrito) foram restauradas.

### [2026-11-16] — Notificações por e-mail escolhidas por usuário; botão "Ativar/Desativar todas" por máquina

- **Quem recebe** (`services/notificacoes.destinatarios_notificacao(db, conta, tipo, machine_id)`): o e-mail de contato da conta (sempre) + os usuários **ativos** da conta com `usuarios.notif_email` ligado, que aceitam o tipo (`usuarios.notif_tipos`: lista, `NULL` = todos) e enxergam a máquina (ADMIN vê todas; VISUALIZADOR/LEITURA sem máquinas marcadas veem todas; notificação personalizada não tem máquina). Antes saía sempre para o contato + todos os admins. Tipos: `LICENCA_UNM2000`, `CAMERA_OFFLINE`, `ALARME`, `ANTENA_OFFLINE`, `ONU_OFFLINE`, `SINAL_OPTICO`, `PERSONALIZADA` (`schemas.TIPOS_EMAIL_NOTIFICACAO`; `BACKUP_FALHOU` e `AGENTE_OFFLINE` só aparecem no painel). O aviso de vencimento da conta (`services/avisos_conta.destinatarios`) não mudou (contato + admins).
- **E-mail de backup continua separado**: usa só as listas `email_to` da máquina/cliente. Decisão: **não** incluir o admin automaticamente (mandaria um relatório por máquina/rodada a quem não pediu, e as listas podem ter contatos do cliente); o admin que quiser coloca o próprio e-mail na lista. Um opt-in "receber relatório de backup" por usuário fica como evolução possível.
- **Migração**: colunas `usuarios.notif_email BOOLEAN NOT NULL DEFAULT FALSE` e `usuarios.notif_tipos JSON`; na criação da coluna, os admins atuais ficam ligados (nada muda no primeiro dia) e os demais desligados. Usuário novo: ADMIN liga por padrão, os outros não.
- **API/painel**: `UsuarioCreate/Update/Response` ganham `notif_email` e `notif_tipos` (em `PUT`, `notif_tipos: null` = todos e ausente = não mexe; tipo inválido = 422). Tela Usuários: coluna "Notificações" e o campo `NotificacoesUsuarioCampo` (liga/desliga, "todos os tipos" ou só os marcados).
- **Notificações (painel)**: em cada máquina das seções Câmeras offline, OLTs e Alarmes, botão **Ativar todas / Desativar todas** (só os itens que mudam são enviados; some para somente leitura/visualizador).
- **Testes**: `server/api/tests/test_destinatarios_notificacao.py` (6). **Arquivos:** server/api/{models.py,main.py,schemas.py,routers/conta.py,services/notificacoes.py}, server/dashboard/src/{api/types.ts,api/contas.ts,pages/Contas/{UsuariosSection.tsx,NotificacoesUsuarioCampo.tsx},pages/Notificacoes/NotificacoesPage.tsx}.

### [2026-11-16] — Agente 1.1.56: log do agente do Mikrotik (Linux) no painel

**Problema:** o agente Linux (`service_linux.py`) só escrevia o log na saída do processo, dentro do Mikrotik; a teste-mk-maquina não tinha nenhum evento do agente no painel. Os pedidos de backup com `TRILAN_ENABLE_BACKUPS` desligado eram ignorados sem aviso visível (e o servidor dispara todo dia um backup de recuperação pelo das 02:00 que não rodou).
**Alteração:** `service_linux.py` instala o `log_remoto` logo após carregar a configuração e roda `logs_loop` (envio a cada 20 s, mesma rotina do Windows, log completo da 1.1.55); ao parar (reinício, OTA) faz um último envio. O aviso de backup desativado passa a dizer em português que o pedido foi ignorado. Sem mudança em `requirements-linux.txt` (a OTA do Linux aceita a versão). Agentes Windows: sem mudança de comportamento.
**Arquivos:** agent/service_linux.py, agent/tests/test_log_linux.py (novo), agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json, PROJECT_SPEC.md.

### [2026-11-16] — Agente 1.1.55: log completo do agente no painel

**Problema:** o agente só mandava ao servidor avisos, erros e marcos do backup; para saber o passo a passo (o que o backup fez antes de falhar, testes, OLT, alarmes) era preciso abrir o `servico.log` no cliente.
**Alteração (agente 1.1.55):** `log_remoto.ManipuladorLogRemoto` passa a enfileirar todas as linhas de INFO para cima; as INFO comuns vão com `detalhe: true`. `extra={"enviar_servidor": False}` (em `service.log(..., remoto=False)`) deixa a linha só no arquivo local: usado no ping de 15 em 15 s, que o servidor já registra. Fila local de 500 para 5.000 itens; deduplicação de 10 min e ocultação de segredos continuam valendo para todas as linhas.
**Servidor:** `LogAgenteItem.detalhe` (padrão `false`; agentes antigos seguem iguais). Linhas de detalhe gravadas como `agent_log_detalhe` e podadas à parte em `podar_logs` (7 dias, até 20.000 por máquina), sem contar no teto de 5.000 dos eventos principais. `GET /machines/{id}/logs` ganha `incluir_detalhe` (padrão `true`) e `limit` até 1.000.
**Painel:** Eventos do Agente ganham o filtro "Log completo" (marcado por padrão) e o rótulo cinza "Log" para essas linhas; "Ver mais" de 200 em 200 até 1.000.
**Arquivos:** agent/src/application/log_remoto.py, agent/service.py, agent/tests/test_log_remoto.py (novo), server/api/{schemas.py,routers/agent.py,routers/machines.py,services/agent_logs.py}, server/api/tests/test_log_completo_agente.py (novo), server/dashboard/src/api/client.ts, server/dashboard/src/pages/Machines/MachineDetail/{index.tsx,components/AgentLogs.tsx}, agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json, PROJECT_SPEC.md.

### [2026-11-13] — Merge do ramo `helena` (perfil Visualizador, isolamento por máquina e avisos de OLT)

**Incorporado:** `7595a31` (Notificações: seção "OLTs" com avisos de ONU offline e de sinal óptico crítico, tipos `ONU_OFFLINE`/`SINAL_OPTICO`) e `532fe4a` (perfil `VISUALIZADOR` e isolamento por máquina para Visualizador/Somente leitura, tabela `usuario_maquinas`). Detalhes nas entradas abaixo.
**Auditoria:** nenhuma data com fuso nas linhas adicionadas (REGRA-001 ok); nenhum segredo (só fixtures de teste); rotas novas/alteradas com `ctx` e `filtrar_por_conta`/`filtrar_maquinas`/`obter_maquina` (REGRA-010 ok, `GET/PUT /notificacoes/olts` filtrados pela conta); migração inline só acrescenta `nvrs.olt_notificar`/`nvrs.olt_alertas` (JSON anuláveis) e recria `ck_usuarios_papel` e `ck_notificacoes_tipo` de forma idempotente; `usuario_maquinas` nasce pelo `create_all`. Compose, nginx, `requirements*.txt`, `agent/`, `build.ps1` e `installer.iss` não foram tocados.
**Bloqueado:** nada. Conflito só no changelog, resolvido mantendo os dois lados.
**Versão:** nenhuma (o ramo não mexeu em `agent/`; só deploy do servidor e do painel).

### [2026-11-13] — Dashboard por Cliente: grade livre (posição x/y, 24 colunas), desfazer/refazer e rolagem do mouse corrigida

**Alteração:** a edição do Dashboard por Cliente deixa de ser uma lista em ordem (CSS grid de 12 colunas × 50 px) e passa a ser uma grade livre como a do Grafana.
- **Layout schema 3:** cada widget ganha `x`/`y`; a grade tem 24 colunas e linhas de 31 px. Cada linha já inclui o respiro entre cartões, então duas linhas novas equivalem a uma antiga. `services/dashboards/layout.py` migra o schema 2 ao validar: refaz o posicionamento automático do CSS grid antigo para achar x/y e dobra largura e altura, então a aparência fica igual. A migração também cobre uma aba aberta antes do deploy que salve no formato antigo. Ao validar, o servidor também limita `x`, põe no primeiro lugar livre o widget sem posição, desfaz sobreposições e sobe os widgets para não deixar buracos. Os tamanhos padrão dos tipos foram dobrados (`widgets.py` e `registry.tsx`); os mínimos ficaram com o mesmo número, então dá para deixar o widget com metade do tamanho mínimo de antes.
- **Editor** (`DashboardCanvas.tsx` + `gradeLayout.ts`): arrastar pelo cabeçalho inteiro para qualquer ponto da grade, com um contorno mostrando onde o widget vai cair. Os outros abrem espaço e sobem. Ao arrastar perto da borda da janela, a página rola. Alças nos quatro lados e nos quatro cantos; dois cliques na borda de cima ou de baixo ajustam a altura ao conteúdo. O redimensionamento não encolhe mais o widget sozinho ao soltar. Em telas de até 1000 px os widgets ficam empilhados na ordem de leitura, sem arrastar.
- **Desfazer/refazer** (`useDashboardDraft.ts`): até 100 passos, com botões na barra de edição e Ctrl+Z / Ctrl+Y (ou Ctrl+Shift+Z). Arrastar e redimensionar contam como um passo cada, gravado ao soltar.
- **Rolagem:** o corpo do widget tinha `overscroll-behavior: contain`, que prendia a roda do mouse no widget mesmo sem nada para rolar. Agora o widget rola só quando o conteúdo passa da caixa; sem rolagem, ou no fim dela, a página rola.
**Testes:** `server/api/tests/test_dashboard_grade.py` (migração do schema 2, lugar livre, sobreposição, limite de `x`, layout padrão).
**Breaking change:** não (os layouts salvos são migrados ao ler e ao salvar). **Requer:** deploy do servidor e do painel juntos; sem mudança no agente.

### [2026-11-13] — Dashboard por Cliente: widgets de antenas, OLT e centrais de alarme; skill `especialista-dashboard`

**Alteração:** três tipos de widget novos em `services/dashboards/widgets.py`, cada um com a sua lista branca e com nível de cor (`critico`/`atencao`/`ok`) calculado no servidor:
- `antenas` ("Antenas Wi-Fi", lê `antena_status`): "X/Y online" por equipamento e lista das antenas com o pior estado no topo. Vermelha quando está fora do ar ou com erro há mais de 10 min (mesmo limiar da notificação ANTENA_OFFLINE); amarela quando caiu há menos tempo ou está sem registro. A latência é opcional. O `resumo` ganha `antenas_total`/`antenas_online` (cartão "Antenas online" aparece só quando há antenas).
- `status_olt` ("OLTs e ONUs", lê `olt_status`): totais de ONUs por OLT (online, offline, falha, sem energia, sinal ruim), PONs com problema e licença da UNM2000. Vermelho com falha de leitura ou mais de 5% das ONUs fora; amarelo com qualquer ONU fora ou com sinal ruim. A licença fica amarela a 10 dias do vencimento e vermelha depois de vencida. Só contagens: nome de assinante, serial, MAC e IP das ONUs não saem.
- `alarmes_defense` ("Centrais de alarme", lê `last_alarm_status`): centrais com disparo (vermelho), desconectadas (amarelo) e partições. Desarmada é estado normal (cinza). **No link público o estado armada/desarmada não é enviado** (só disparo e desconexão): o `ContextoDados` ganhou `publico` (preenchido por `montar_dados(..., publico=True)` em `routers/public_dashboard.py`). As centrais de incêndio aparecem só pelo nome, porque o significado do `status` delas não foi confirmado.

Nos três, os dados com mais de 20 min (antenas e alarmes) ou 15 min (OLT) aparecem como "Sem atualização". `ids_referenciados` (`layout.py`) passa a cobrir a chave `equipamentos` dos três tipos, para manter o 422 de isolamento. Front: `AntenasWidget`, `StatusOltWidget`, `AlarmesDefenseWidget` e as peças comuns em `widgets/statusComum.tsx`. Testes em `server/api/tests/test_dashboard_status_equipamentos.py` (lista branca, níveis, filtro, link público, isolamento) e em `tools/teste_dashboards_e2e.py` (422 com equipamento de outro cliente). Nenhum histórico novo: os três tipos continuam guardando só o último status.
**Skill:** nova skill do Claude `especialista-dashboard` (`.claude/skills/`). Ela descobre o que um equipamento novo envia, pergunta ao usuário o que mostrar e mantém a tabela de cobertura por tipo. A `criar-novo-agente` passou a apontar para ela.

### [2026-11-13] — Merge do ramo `helena` (antenas Wi-Fi via MikroTik e galeria do Defense) — agente 1.1.54

**Incorporado:** `bd3b3bc` (galeria do Defense: "Sincronizar da máquina" passa a trazer as câmeras que o Defense lista e a Galeria não tem, a partir do relatório do agente; `cameras_do_relatorio_sem_par` em `services/galeria_vms.py`), `914fcc5` (merge de `integracao-equipamentos` em `helena`) e `727c770` (equipamento tipo ANTENA, entrada abaixo).
**Auditoria:** datas novas em `datetime.utcnow()` naive (REGRA-001 ok); nenhum segredo nas linhas adicionadas (só fixtures de teste); rota nova do painel (`GET .../antena-status`) com `ctx` via `_get_machine_or_404` e a do agente com `get_current_machine` (REGRA-010 ok); migração inline só acrescenta `nvrs.antena_status` e o tipo `ANTENA_OFFLINE` no `ck_notificacoes_tipo`; compose, nginx, `requirements*.txt`, `build.ps1` e `installer.iss` não foram tocados.
**Bloqueado:** nada. Conflito só no changelog, resolvido mantendo os dois lados.
**Versão:** agente 1.1.54 (o ramo mexeu em `agent/`; é a versão que leva o `_antena_loop` às máquinas).

### [2026-11-13] — Gravação do Digifort: verde acima de 10% e vermelho só sem nenhum registro (agente 1.1.53)

**Problema:** uma câmera aparecia como falha no sistema e tinha gravação no próprio Digifort. Em `segundos_por_dia`
(`agent/src/vms/digifort_gravacoes.py`), um trecho de um registro só (início == fim: quadro isolado, clipe curto de
movimento) somava 0 s, e o dia ficava vermelho mesmo com registro no índice.
**Correção:** `LIMIAR_GRAVOU` passou de `0.20` para `0.10` (acima de 10% = verde; acima de 0% até 10% = amarelo).
Vermelho continua sendo 0%, mas agora 0% quer dizer **nenhum registro no índice do dia**: um trecho de um registro só
conta `MINIMO_TRECHO_S = 1` s no seu dia (fica amarelo e conta como "gravou hoje", `COM_GRAVACAO`). O cache dos índices
guarda os trechos, não os segundos, então não precisa ser invalidado.
**Arquivos:** agent/src/vms/digifort_gravacoes.py, agent/tests/test_digifort_gravacoes.py,
server/dashboard/src/pages/Machines/MachineDetail/components/MiniCalendar.tsx (legenda), versão nos três lugares.
**Breaking Change:** Não. Nenhuma rota nem migração.

### [2026-11-13] — Recuperação de backup perdido passa a olhar o último horário agendado (e não só o de hoje)

**Problema:** os backups das 23:00 de 11/11 e 12/11 não existem para as 12 máquinas agendadas nesse horário. Nas duas noites o servidor estava fora do ar: em 11/11 o host Windows desligou sem shutdown limpo às 21:09; em 12/11 a VM ficou lenta a partir de ~22:40, foi pausada pelo Hyper-V às 02:43 por **disco C: do host cheio** (VHDX dinâmico e `.VMRS` no C:), desligada às 03:13 e só voltou às 08:41. O agente rodou no horário, não conseguiu `GET /agent/config` (timeout) e abortou sem ZIP nem registro. A recuperação no ping (`routers/agent.py`) comparava só com o horário agendado de **hoje**: depois da meia-noite as 23:00 "de hoje" ainda estavam no futuro, então a recuperação nunca disparava para agendamentos noturnos.
**Correção:** `_ultimo_horario_agendado(agora_local, hora, minuto)` devolve o último horário que já passou há mais de 30 min (o de hoje ou o de ontem). Há backup a recuperar quando `last_backup_at` (hora local) é anterior a esse horário, não houve backup nas últimas 2 h e não houve `ping_recovery` desde esse horário. Logo após o deploy, as máquinas sem backup desde a última janela recebem um backup de recuperação no próximo ping.
**Conciliação feita:** a sincronização com o OneDrive estava correta (VM `/opt/trilan/backups` e a pasta do OneDrive no servidor Windows idênticas por cliente). Procedimento e comandos na skill `.claude/skills/conciliar-backups-onedrive` (só do Claude).
**Arquivos:** server/api/routers/agent.py, server/api/tests/test_recuperacao_backup.py, .claude/skills/conciliar-backups-onedrive/SKILL.md, CLAUDE.md, PROJECT_SPEC.md
**Breaking Change:** Não. **Requer:** só o deploy do servidor (sem versão nova do agente).
### [2026-11-13] — Isolamento por máquina para Visualizador e Somente leitura (editado pelo admin)

- **Regra** (decisões do usuário): o admin da conta escolhe, na edição do usuário, quais máquinas um **VISUALIZADOR** ou **LEITURA** vê. **Nenhuma marcada = todas** (os usuários atuais não mudam). O **ADMIN sempre vê todas** (a lista dele fica vazia). Escolha por máquina, agrupada por Cliente, com "marcar todas do cliente"; máquina nova não entra sozinha.
- **Banco**: tabela nova `usuario_maquinas` (`usuario_id` → usuarios ON DELETE CASCADE, `machine_id` → clients ON DELETE CASCADE, PK nos dois; criada pelo `create_all`). Model `UsuarioMaquina` e `Usuario.maquinas` (lista de ids).
- **Contexto** (`auth.py`): `Contexto.maquinas_permitidas` (frozenset; None = todas), lido a cada requisição (mudança do admin vale na hora, sem novo login).
- **Onde vale** (`services/escopo.py`): `obter_maquina` devolve 404 para máquina fora da lista (cobre detalhe da máquina, equipamentos, Galeria, logs, testes); `obter_cliente` 404 para cliente sem nenhuma máquina liberada; `filtrar_maquinas` nas listas de máquinas, backups (também detalhe/download/reenvio de backup) e nas listas da tela de Notificações (câmeras, alarmes, OLTs); a lista de alertas mostra só os das máquinas liberadas e os que não são de máquina (personalizadas). Clientes: a lista e o detalhe mostram só as máquinas liberadas (totais e saúde contam só elas). **O que junta o cliente inteiro exige todas as máquinas dele** (`exigir_cliente_inteiro`): ZIP do cliente e ZIP de rodada (403), dashboard do cliente (403); a lista de rodadas volta vazia.
- **Regra para rota nova** (extensão da REGRA-010): buscar máquina por `obter_maquina` e filtrar listas com `filtrar_maquinas(consulta, <coluna machine_id>, ctx)` além do `filtrar_por_conta`; dado que junta várias máquinas de um cliente passa por `exigir_cliente_inteiro`.
- **API**: `UsuarioCreate`/`UsuarioUpdate` aceitam `maquinas` (lista de ids da conta; outra conta = 400; `[]` = todas; ausente no update = não muda); `UsuarioResponse.maquinas`.
- **Painel**: tela de usuários com a coluna "Máquinas" ("Todas" ou "N máquina(s)") e, para Visualizador/Somente leitura, o campo "Máquinas que o usuário vê" (`pages/Contas/MaquinasUsuarioCampo.tsx`: "Todas as máquinas da conta" ou "Só as máquinas marcadas", agrupadas por cliente).
- **Testes**: `server/api/tests/test_isolamento_maquina.py` (6). Teste real no local: Visualizador limitado a "Teste PABX" vê 1 de 6 máquinas, outra máquina e os equipamentos dela 404, backups só da liberada, cliente "Central" com 1 de 3 máquinas, ZIP do cliente 403, rodadas vazias, cliente "Segunda" 404, 1 de 6 alertas; máquina de outra conta recusada (400). Usuário de teste voltou a "todas" e foi desativado. Sem mudança no agente.
- **Arquivos:** server/api/{models.py,auth.py,schemas.py,services/escopo.py,routers/{conta.py,machines.py,backups.py,customers.py,dashboards.py,notificacoes.py},tests/test_isolamento_maquina.py}, server/dashboard/src/{api/{types.ts,contas.ts},pages/Contas/{UsuariosSection.tsx,MaquinasUsuarioCampo.tsx}}, PROJECT_SPEC.md.

### [2026-11-13] — Perfil de usuário VISUALIZADOR (vê tudo e roda testes, não altera nada)

- **Papéis**: `usuarios.papel` passa a aceitar `VISUALIZADOR` (além de SUPER_ADMIN, ADMIN e LEITURA); `ck_usuarios_papel` recriado na migração inline. Criado e editado na tela de usuários da conta ("Visualizador (vê e testa, não altera)").
- **O que pode**: tudo que o LEITURA vê, mais os **testes**: "Testar conexão" de qualquer equipamento (o "Atualizar" do modal de ONUs usa o mesmo teste) e, na Galeria, o novo **"Testar ao vivo"**, que pede um quadro ao vivo da câmera e só mostra na tela (**nada é salvo**: nem referência, nem noite, nem a câmera recuperada do relatório do agente).
- **O que não pode** (decisões do usuário): capturar/salvar referência ou imagem da noite (a da noite só se vê), disparar backup manual (só admin), armar/desarmar centrais de alarme (só vê o status), cadastrar/editar/pausar/remover qualquer coisa, ligar avisos de notificação, ver a Auditoria.
- **Como é aplicado** (`auth.py`): o VISUALIZADOR é `somente_leitura` (o `_bloquear_escrita` barra POST/PUT/DELETE como no LEITURA). Nova dependência **`get_contexto_teste`**, usada só nas rotas de teste (`POST .../test-rtsp` e `POST .../testar-conexao`), deixa passar quem tem `Contexto.pode_testar` (todos menos LEITURA; ninguém com a conta vencida/suspensa). No `test-rtsp`, o VISUALIZADOR só pode `modo=ao_vivo` (403 nos outros). Rota nova de escrita continua bloqueada por padrão: só entra na lista de teste quem usar `get_contexto_teste`. `/auth/me` devolve `pode_testar` (painel: hook `usePodeTestar()`).
- **Auditoria**: os testes passam a ser registrados para qualquer usuário ("testou a conexão do equipamento X", "testou a captura ao vivo da câmera Y do equipamento X (sem salvar)").
- **Painel**: faixa própria ("Seu acesso é de visualizador..."); Auditoria escondida (como no LEITURA); na Galeria, os botões de importar/limpar planilha, sincronizar, editar RTSP, capturas em lote, capturar/enviar referência e capturar noite somem para LEITURA e VISUALIZADOR; o botão "Testar" do card e o "Atualizar" das ONUs aparecem para quem pode testar.
- **Testes**: `server/api/tests/test_visualizador.py` (6). Teste real no servidor local: usuário VISUALIZADOR criado, `testar-conexao` 200, editar equipamento/capturar noite/referência/backup manual/Auditoria 403, teste registrado na Auditoria; usuário de teste desativado (não há rota para apagar usuário). Sem mudança no agente.
- **Arquivos:** server/api/{auth.py,models.py,main.py,schemas.py,services/contas.py,routers/{auth_router.py,conta.py,auditoria.py,equipamentos.py},tests/test_visualizador.py}, server/dashboard/src/{App.tsx,api/{types.ts,contas.ts},contexts/AuthContext.tsx,components/{Sidebar.tsx,AvisoConta.tsx},pages/Contas/{contaUi.tsx,UsuariosSection.tsx},pages/Machines/MachineDetail/{index.tsx,components/{EqCard.tsx,NVRCamerasGalleryModal.tsx,OltStatusModal.tsx}}}, PROJECT_SPEC.md.

### [2026-11-13] — Notificações: seção "OLTs" com aviso de ONU offline e de sinal óptico crítico

- **Tela** (Notificações): nova seção **OLTs**, no mesmo formato das de câmeras e alarmes (máquina → OLT → opções). Em cada OLT, dois avisos independentes, ligados/desligados separadamente: **ONU offline** (sem energia, fibra desconectada ou offline) e **Sinal óptico crítico** (ONU online com qualidade `RUIM`, -27 dBm ou pior, a mesma classificação do modal de ONUs). Mostra o que está acontecendo agora (contagem por causa) e quando foi a última leitura. Começam desativados (opt-in); perfil LEITURA só vê.
- **Regra** (`services/notificacoes.verificar_olt_equipamento`, chamada ao receber o status da OLT e no ciclo de 10 min): a ONU entra no aviso depois de **10 min** no problema (`LIMIAR_OLT_MIN`; o momento em que entrou fica em `nvrs.olt_alertas`). **Um alerta por OLT** (`referencia` = nome da OLT), com a contagem por causa e a lista das ONUs (até 15, depois "+N outras"); fecha sozinho quando nenhuma ONU está mais no problema. **E-mail** quando o alerta abre e quando entram ONUs ainda não avisadas (não repete todo dia); se o envio falhar, tenta na leitura seguinte; ONU que volta e cai de novo é avisada de novo. OLT que não respondeu na leitura mantém o alerta e as contagens como estavam; status com mais de 20 min não abre nem fecha nada. Desligar o aviso fecha o alerta aberto.
- **Tipos novos** `ONU_OFFLINE` e `SINAL_OPTICO` em `notificacoes.tipo` (`ck_notificacoes_tipo` recriado na migração). **Colunas** `nvrs.olt_notificar` e `nvrs.olt_alertas` (migração inline). **API**: `GET /api/v1/notificacoes/olts` e `PUT /api/v1/notificacoes/olts/{nvr_id}` (`{onu_offline?, sinal_critico?}`, admin da conta), filtradas pela conta (REGRA-010).
- **Sem versão nova do agente**: usa o `olt_status` que UNM2000, Huawei e VSOL já enviam (`estado` e `qualidade` de cada ONU).
- **Testes**: `server/api/tests/test_olt_notificacao.py` (7). **Arquivos:** server/api/{models.py,main.py,schemas.py,routers/{agent.py,notificacoes.py},services/notificacoes.py,tests/test_olt_notificacao.py}, server/dashboard/src/{api/{types.ts,client.ts},utils/notificacoes.ts,pages/Notificacoes/NotificacoesPage.tsx}, PROJECT_SPEC.md.

### [2026-11-13] — Equipamento tipo ANTENA: status das antenas Wi-Fi (Ruijie etc.) lido pelo MikroTik

- **Motivo**: acompanhar antenas sem depender da API da Ruijie (o `appid`/`secret` só sai por pedido à Ruijie). O agente entra por SSH no MikroTik da rede e vê as antenas pelo ponto de vista dele. Testado no MikroTik da sede (RouterOS 7.25): a antena Ruijie `9C:2B:A6:71:6A:CF` aparece com o MAC `...6A:D0` (+1), IP 192.168.75.123, sem LLDP: só DHCP, ARP e tabela da bridge a enxergam.
- **Cadastro** (`nvrs.tipo = 'ANTENA'`): `ip`/`username`/`password` são o acesso SSH ao MikroTik (senha criptografada como nos outros; recomendado usuário só de leitura, `policy=ssh,read,test`); `config_extra`: `porta_ssh` (22), `prefixos_mac` (OUI da busca automática, ex.: `9C:2B:A6, 54:16:51`) e `antenas` (`[{nome, mac, ip?, marca?, notificar}]`, até 200; `marca` com até 40 caracteres, opcional). `services/antenas.normalizar_config` valida e normaliza no POST/PUT (MAC em `AA:BB:CC:DD:EE:FF`, sem repetição; erro vira 400 com a mensagem).
- **MAC com tolerância**: a antena é cadastrada por um MAC e vale qualquer MAC do **mesmo fabricante (3 primeiros bytes) a até 32 endereços de diferença** (`TOLERANCIA_MAC`), porque porta e rádios têm MACs consecutivos. O painel recusa cadastrar um MAC já coberto por outra antena.
- **Agente** (`src/mikrotik/antenas.py`, `src/application/status_antena.py`; laço `_antena_loop` no `service.py`, a cada 3 min, `INTERVALO_ANTENA_S`): lê `/ip neighbor`, `/ip arp`, `/ip dhcp-server lease` e `/interface bridge host` (só `print`, nada é alterado no MikroTik), junta por MAC e avalia cada antena: **ONLINE** (respondeu ao ping, ou ARP `reachable`/`delay`/`probe`, ou foi vista na bridge sem IP), **OFFLINE** (IP conhecido que não responde), **SEM_REGISTRO** (nenhum MAC dela no MikroTik e sem IP). Ping ICMP em paralelo (até 8) com a latência. **Busca automática** (`descobertas`): vizinhos com capacidade `wlan-ap` ou nome Ruijie/Reyee e MACs com prefixo de `prefixos_mac`, fora das já cadastradas; MACs próximos viram um só. "Testar conexão" do tipo ANTENA: rede (SSH), leitura, conferência das antenas e envio. O backup diário ignora o tipo (`backup_job.py`, como a câmera avulsa).
- **Servidor**: coluna `nvrs.antena_status` (migração inline); `POST /api/v1/agent/antenas/status` (agente) grava via `services/antenas.mesclar_status` (guarda `ultimo_online`, `offline_desde` na primeira queda e o último IP/hostname quando a antena some; erro de leitura do MikroTik mantém o estado anterior); `GET /api/v1/machines/{id}/equipamentos/{id}/antena-status` (painel). As antenas são editadas pelo `PUT` do equipamento (lista inteira em `config_extra.antenas`), então cada mudança entra na Auditoria.
- **Marca da antena**: o agente detecta a marca pelo que o vizinho (LLDP/CDP/MNDP) e o DHCP anunciam (`marca_do_texto` em `src/mikrotik/antenas.py`; por enquanto só **Ruijie** (palavras `ruijie`, `reyee`), **Aruba** e **Xixian**, uma lista de palavras, não de MACs; outras marcas ficam sem detecção até serem acrescentadas aqui e em `MARCAS` de `AntenasModal.tsx`). Cada antena traz `marca` (a do cadastro, que vale sobre a detectada, ou, sem ela, a detectada) e `marca_detectada`; a busca automática também traz `marca`. Quando o LLDP não identifica (caso da antena Ruijie testada, que não anuncia LLDP), o usuário escolhe a marca no formulário "Adicionar pelo MAC" ou no seletor Marca da linha da antena (lista fechada Ruijie/Aruba/Xixian; uma marca já gravada fora da lista continua aparecendo; o servidor aceita qualquer texto até 40 caracteres). A marca é só informação: não muda a busca nem o cruzamento de MACs.
- **Notificação `ANTENA_OFFLINE`** (nova no `ck_notificacoes_tipo`, recriado na migração; `services/notificacoes.py`): uma por antena (`referencia` = MAC), aberta quando a antena marcada para notificar fica fora do ar há mais de 10 min (`LIMIAR_ANTENA_OFFLINE_MIN`) e resolvida sozinha quando volta; "FALHA" quando o agente não consegue ler o MikroTik. E-mail no máximo 1 por dia por alerta e, se o alerta já tinha e-mail, outro "voltou" ao resolver (não avisa "voltou" se a antena foi removida). Relatório com mais de 20 min não abre nem fecha alerta (a queda do agente tem notificação própria).
- **Painel**: novo tipo "Antenas" no formulário (IP/porta SSH/usuário/senha do MikroTik e prefixos de MAC); botão **Antenas** no card abre `AntenasModal` (status, IP, MAC cadastrado e "visto como", ping, offline desde, sino por antena, remover), a **busca automática** com "Adicionar" e o formulário **Adicionar pelo MAC** (aceita `9C:2B:A6:71:6A:CF`, `9c2b.a671.6acf` e `9c-2b-...`).
- **Limites**: precisa de agente novo (**versão a publicar pelo dono**: sem ela o `_antena_loop` não existe na máquina e o status não chega); o agente precisa alcançar o MikroTik pelo SSH, e o ping parte da máquina do agente (se ela estiver em outra rede e bloquear ICMP, vale o ARP do MikroTik). Antena que some do ARP/DHCP/bridge sem IP fixo no cadastro fica "Não encontrada" (o IP opcional da antena serve de reserva). Não usa a API da Ruijie Cloud (sem `appid`/`secret` ainda).
- **Testes**: `agent/tests/test_antenas.py` (27) e `server/api/tests/test_antenas.py` (18). **Arquivos:** agent/{service.py,src/mikrotik/antenas.py,src/application/{status_antena.py,api_client.py,teste_conexao.py,backup_job.py}}, server/api/{models.py,main.py,schemas.py,routers/{agent.py,equipamentos.py},services/{antenas.py,notificacoes.py}}, server/dashboard/src/{api/types.ts,utils/notificacoes.ts,pages/Machines/MachineDetail/{index.tsx,utils.ts,components/{AntenasModal.tsx,EqCard.tsx,EquipamentoFormModal.tsx,eqTipos.tsx}},pages/Notificacoes/NotificacoesPage.tsx}, PROJECT_SPEC.md.

### [2026-11-13] — Avisos de confirmação no padrão do sistema (dashboard)

Os 28 `confirm()` do navegador foram trocados por um diálogo próprio: `components/ConfirmDialog.tsx` (`ConfirmProvider` no `App.tsx` e hook `useConfirm()`, que devolve `Promise<boolean>`). Opções: `title`, `message`, `confirmLabel`, `cancelLabel` e `variant` (`danger` vermelho, `warning` âmbar, `info` roxo). Esc e clique fora cancelam. Regra: não usar `alert/confirm/prompt` nativos; usar `useConfirm()` (confirmações) e `useToast()` (avisos). Só dashboard, sem mudança no agente nem na API.

### [2026-11-12] — Atualização automática (OTA) do agente Linux no Mikrotik (agente 1.1.52)

O agente Linux do container RouterOS não tinha OTA (o do Windows troca `.exe` com `.bat`/`sc`), então ficava na
versão da imagem; o painel mostrava "— (agente anterior à 1.1.49)" para a máquina `teste-mk-maquina`. Agora a OTA
troca só o código Python (`dist/TrilanAgentLinux.tar.gz`, gerado por `agent/pacote_linux.py` no `build.ps1` e anexado à
release); as bibliotecas compiladas para ARM ficam na imagem. Novo `agent/launcher_linux.py` (CMD da imagem: escolhe o
código, religa o agente ao encerrar, desfaz versão que não sobe) e `agent/src/application/updater_linux.py`
(verificação, download, SHA-256, extração segura, checagens, troca de pastas). `service_linux.py` verifica a OTA a cada
hora, confirma a versão no 1º ping e sai com código 3 se a versão nova não pingar em 10 min. `src/core/config.py`:
`DIR_AGENT` aceita `TRILAN_AGENT_DIR` (a imagem define `/app`, onde ficam `agent.conf`, logs e temporários).
**Servidor:** colunas `agent_versions.url_linux` (TEXT) e `sha256_linux` (VARCHAR(64)), migração inline; schemas de
criar/editar/listar versão e `UpdateCheckResponse` com os dois campos; `GET /agent/update-check` aceita
`plataforma=linux` (só versões com pacote Linux; resposta só com `url_linux`/`sha256_linux`). Painel (Configurações ->
OTA) mostra hash e link do pacote Linux. `publish_version.ps1` ganhou `-UrlLinux`. Testes: `agent/tests/test_ota_linux.py`.
**Limite:** a imagem precisa ser trocada à mão uma vez (a anterior não tem launcher nem OTA); depois, só quando o
`requirements-linux.txt` mudar. Sem breaking change (Windows segue igual; campos opcionais). Branch `isaque`.

### [2026-11-12] — Merge com a Helena (5ª rodada): tela de Auditoria

**Incorporado (ramo `helena`, `611267e`):** tela `/auditoria` e `GET /api/v1/auditoria` (+ `/usuarios`), que registram quem
alterou o quê pelo painel (equipamentos, câmeras, planilhas, máquinas, pedidos de backup/reinício e comandos de alarme)
em `agent_logs`, com a coluna nova `usuario` (migração inline `VARCHAR(255)` nula e índice parcial
`ix_agent_logs_usuario_created`). Eventos de usuário ficam 365 dias fora da poda comum. Detalhes na entrada "Tela de
Auditoria na barra lateral" abaixo. **Auditoria:** sem data com fuso, sem segredo (os eventos guardam só os nomes dos
campos, nunca os valores), rota nova com `ctx` e `filtrar_por_conta` (REGRA-010), sem mudança em compose, nginx,
requirements, agente, build ou instalador. Conflito só nos imports de `server/dashboard/src/api/client.ts` (mantidos
`ConexaoTeste` e `PaginatedAuditoria`). `tsc` sem erro; testes da API com o mesmo resultado antes e depois do merge.
**Bloqueado:** nada. **Versão:** sem mudança no agente; segue a 1.1.51.

### [2026-11-12] — Gravação do Digifort: novas faixas para câmeras por movimento (agente 1.1.51)

Caso real: no CFTV 01 do Navarro, a maioria das câmeras grava por movimento e ficava amarela nos dias úteis e vermelha
nos fins de semana e feriados. A "CATRACA (A) - SUBSOLO 3", com pouco movimento, mostrava 12 dias cinza ("sem
histórico") mesmo tendo gravação, porque nenhum dia passava de 11%. Novas faixas em `resumir_camera`
(`agent/src/vms/digifort_gravacoes.py`): acima de 20% = gravou (`█`); acima de 0% até 20% = parcial (`▒`); 0% (nenhum
segundo gravado) = não gravou (`░`). Qualquer gravação no dia agora entra em `dias_com_gravacao`/`total_dias` e conta
como "gravou hoje". O cinza `·` fica só para dias sem nenhuma gravação antes da primeira gravação da janela (retenção ou
câmera nova). `LIMIAR_GRAVOU = 0.20` e `LIMIAR_PARCIAL = 0.0`, os dois com comparação "acima de". Textos do
`MiniCalendar` atualizados. Só agente e texto do painel; nenhuma rota nem migração.

### [2026-11-12] — Merge com a Helena (4ª rodada): alarmes do DEFENSE, notificação ALARME e versão 1.1.50 do agente

**Incorporado (ramo `helena`, `2af33d4` e `4d8e355`):** alarmes das centrais Intelbras do DEFENSE reativados (saem de
`legacy/defense_alarmes/`), com login no painel de alarmes, centrais de incêndio, armar/desarmar central pelo painel e a
notificação `ALARME` opt-in por central (detalhes na entrada da Helena abaixo). Migrações: `nvrs.alarmes_notificar`,
`notificacoes.referencia` e `ck_notificacoes_tipo` com `ALARME`. **Auditoria:** sem data com fuso, sem segredo (só
`password="x"` em fixture de teste); rotas novas isoladas por conta (`_get_machine_or_404`/`filtrar_por_conta`, caso novo
em `test_isolamento_contas.py`); compose, nginx, requirements, build.ps1 e `.env` intocados. **Corrigido no merge:** o
`alarme_task` do ping leva a senha do DEFENSE e era entregue a qualquer agente; os agentes até 1.1.49 só tiram
`rtsp_task`/`conexao_task` do log do ping (que vai também ao painel), então gravariam a senha. Agora o serviço do Windows
declara `"comando_alarme"` em `recursos` (`ping_server(conf, recursos_extra=...)`; o `service_linux.py` não declara, pois
não executa o comando) e o servidor só entrega a quem declara; os demais recebem na hora "agente anterior à 1.1.50".
**Conflitos:** `models.py`, `schemas.py`, `routers/{agent,equipamentos}.py`, `test_isolamento_contas.py`, `service.py`,
`client.ts`, `EqCard.tsx` e `MachineDetail/index.tsx` (resolvidos mantendo "Testar conexão" e "Alarmes" lado a lado) e
este changelog; versões mantidas as da `isaque` (o ramo trazia 1.1.44). **Bloqueado:** nada. **Versão:** agente 1.1.50.

### [2026-11-12] — Versão do agente no ping e no painel (agente 1.1.49)

O agente passa a mandar `versao` (`CURRENT_VERSION`) no corpo do `POST /api/v1/agent/ping` (`api_client.ping_server`).
O servidor grava em `clients.agent_version` (coluna nova `VARCHAR(20)`, migração inline em `main.py`) e o
`MachineResponse` devolve `agent_version`. O card "Configuração da Máquina" (`MachineInfoCards.tsx`) ganhou a linha
"Versão" (`v1.1.49`; sem valor: "— (agente anterior à 1.1.49)"). Campo opcional: agentes antigos continuam pingando
sem ele e a versão gravada não é apagada. Arquivos: `server/api/{models,schemas,main}.py`, `server/api/routers/agent.py`,
`server/dashboard/src/api/types.ts`, `agent/src/application/api_client.py`. Sem breaking change. Branch `isaque`.

### [2026-11-12] — Gravação do Digifort por faixas de cobertura (agente 1.1.48)

`resumir_camera` (`agent/src/vms/digifort_gravacoes.py`) deixou de tratar qualquer gravação abaixo de 90% como parcial.
Cobertura do dia (hoje: do tempo já decorrido): 40% a 100% = gravou (`█`, verde); 11% a 39% = parcial (`▒`, amarelo);
0% a 10% = não gravou (`░`, vermelho). Dia com 10% ou menos não entra em `dias_com_gravacao`/`total_dias` e não conta como
"gravou hoje" (`status_gravacao`), o que também corrige o e-mail e o `RecordingModal`. Novo campo `percentual_hoje` no
resumo da câmera (ainda sem uso no painel). Textos do `MiniCalendar` atualizados. Constantes `LIMIAR_GRAVOU` e
`LIMIAR_PARCIAL`. Só agente e texto do painel; nenhuma rota nem migração.

### [2026-11-12] — Merge com a Helena (3ª rodada): login da OLT VSOL e versão 1.1.47 do agente

**Incorporado (ramo `helena`, `e1e7126`):** `_parece_tela_login` em `agent/src/olt/vsol.py` reconhece a tela de login da
VSOL em qualquer idioma (algumas só têm o texto em inglês, sem "senha") e o redirect de sessão inválida
(`location.href="login.html"`); o status (`vsol_status._pedir`) passa a falhar com o motivo "sessão não autenticada" em
vez de devolver 0 ONUs sem explicação. Testes em `agent/tests/test_vsol_login.py`. **Auditoria:** sem data com fuso, sem
segredo, nenhuma rota de servidor, compose, nginx, models, migrações, requirements, build.ps1, installer.iss ou `.env`
tocados. **Bloqueado:** `fiberhome_out.txt` (despejo binário de depuração da tela do Telnet da FiberHome, solto na
raiz do repositório). **Conflitos:** nenhum. **Versão:** agente 1.1.47.

### [2026-11-12] — Erro de SSH da OLT Huawei explicado no painel (agente 1.1.46)

**Problema:** a falha do login SSH chegava ao painel com o texto cru do paramiko ("Authentication failed: transport
shut down or saw EOF"), que parece senha errada mas significa que a OLT fechou a conexão durante o login. **Alteração:**
`explicar_erro_ssh` (`agent/src/olt/huawei_status.py`) classifica a falha e diz o que fazer: OLT fechou a conexão
(sessões SSH ocupadas, usuário bloqueado ou sem serviço SSH), senha/usuário recusados, algoritmo SSH incompatível
(firmware antigo), tempo esgotado e conexão recusada (SSH desligado ou porta errada). Vale no "Testar conexão", no
"Atualizar" do modal de ONUs e no status das OLTs. O agente passou a aceitar mensagens de até 700 caracteres no teste
(antes 300). **Arquivos:** `agent/src/olt/huawei_status.py`, `agent/src/application/teste_conexao.py`,
`agent/tests/test_huawei_status.py`. **Breaking change:** nenhum. **Branch:** `isaque`. **Versão:** agente 1.1.46.

### [2026-11-12] — Botão "Atualizar" do modal de ONUs da OLT passa a ler a OLT e mostrar o andamento

**Problema:** o "Atualizar" só relia do servidor o último status salvo (instantâneo e, sem mudança, a tela ficava igual:
nenhum sinal de que algo aconteceu). **Alteração:** o botão pede ao agente uma leitura nova da OLT pelo mesmo fluxo do
"Testar conexão" (`POST .../testar-conexao`, exige agente >= 1.1.44) e mostra barra de progresso, etapa atual e
cronômetro; ao terminar recarrega os dados e avisa por toast ("Status atualizado em N s." ou o motivo da falha); em
falha o motivo fica na tela. Sem clique, o modal mostra "Última leitura: data (há N min) · próxima automática em mm:ss".
Fechar a janela não interrompe a leitura. A lógica de acompanhar o teste virou o hook `MachineDetail/useTesteConexao.ts`,
usado também por `ConexaoTesteModal.tsx`. **Arquivos:** `server/dashboard/src/pages/Machines/MachineDetail/{useTesteConexao.ts,
components/{OltStatusModal,ConexaoTesteModal}.tsx}`. **Breaking change:** nenhum; só painel (sem versão nova do agente).

### [2026-11-12] — Merge com a Helena (2ª rodada): limpar planilha e importação por IP, sem versão nova do agente

**Incorporado (ramo `helena`, `bff8c37`):** botão "Limpar planilha" da Galeria e do formulário do Digifort
(`DELETE /machines/{id}/equipamentos/{nvr_id}/cameras`, só DIGIFORT/DEFENSE) e importação que substitui a câmera de mesmo
IP (`casar_cameras_por_ip`); detalhes na entrada de 12/11 da Helena abaixo. **Auditoria:** sem data com fuso, sem
segredo, rota nova isolada por conta (`obter_maquina` e equipamento filtrado pela máquina), sem alteração em compose,
nginx, models, migrações, requirements, build.ps1, installer.iss, `.env` ou `agent/`. **Conflitos:** nenhum.
**Bloqueado:** nada. **Versão:** o ramo não mexeu em `agent/`; nenhum executável novo, a 1.1.45 continua a vigente e
não houve cadastro no painel. Só o servidor e o painel mudam, via deploy do push na `isaque`.

### [2026-11-12] — Merge com a Helena e versão 1.1.45 do agente

**Incorporado (ramo `helena`, `52d3610`):** notificação de câmera offline (`CAMERA_OFFLINE`, opt-in por câmera:
`nvr_cameras.notificar_offline`, `notificacoes.camera_id`, rotas `GET/PUT /notificacoes/cameras`) e a captura RTSP que só
confere a porta 554 depois da 1ª falha (Hikvision antigas davam timeout). **Auditoria:** sem data com fuso, sem segredo
novo (o `navarro@123` está só numa fixture de teste, IC-012), rotas novas isoladas por conta (`filtrar_por_conta`),
migrações idempotentes; compose, nginx, requirements, build.ps1, installer.iss e `.env` intocados. **Conflitos:**
`main.py` (migrações: mantidas as duas colunas novas), `client.ts` (imports) e este changelog, resolvidos mantendo os dois
lados. **Bloqueado:** nada. **Versão:** agente 1.1.45 (`rtsp_client.py`); inclui o "Testar conexão" da 1.1.44, que não
chegou a ser cadastrada no painel.

### [2026-11-12] — "Testar conexão" dos equipamentos com barra de progresso (agente 1.1.44)

**Contexto:** depois de cadastrar um equipamento não havia como saber se o IP e as credenciais estavam certos antes do
backup da madrugada (na OLT, o painel só dizia que as ONUs podiam levar 5 min). **Alteração:** (1) Ao salvar um
equipamento (cadastro ou edição), o painel abre o modal "Testando conexão" (`ConexaoTesteModal.tsx`): barra de
progresso por etapa, cronômetro, lista de etapas (✓/girando/✗ com detalhe) e a mensagem final; o card ganha o botão
"Testar" e o selo do último teste (Conectado / Falha na conexão / Conexão não testada + data), guardado em
`nvrs.conexao_status` (migração inline). (2) Rotas `POST .../testar-conexao` e `GET .../testar-conexao/{task_id}`
(isoladas por conta, `obter_maquina`) e `POST /agent/conexao-progresso`. Estado em memória em
`services/teste_conexao.py` (mesma limitação de 1 worker do teste RTSP). (3) Agente (`src/application/teste_conexao.py`):
roda na thread do ping (funciona durante um backup) com as mesmas rotinas do backup: NVR (porta HTTP, login
Hikvision ISAPI / Intelbras CGI / Motorola NVMS, contagem de câmeras), OLT (pasta de origem da UNM2000, porta de cada
OLT, login e leitura das ONUs pelo `coletar_status_olts` e **envio imediato** do status ao painel, sem esperar o ciclo
de 5 min), PABX Issabel (login e acesso ao backup), Mikrotik (SSH e identidade), Defense IA (API e câmeras), Digifort
(pasta de origem) e demais tipos (porta TCP). A senha é mascarada nas mensagens e o pedido não aparece no log do ping.
(4) **Segurança com agentes antigos:** o pedido leva a senha do equipamento e os agentes até 1.1.43 gravam a resposta
do ping no log; por isso o agente novo declara `"recursos": ["teste_conexao"]` no ping e o servidor só entrega a quem
declara (os demais recebem na hora "agente anterior à 1.1.44"). **Arquivos:** `server/api/{models,main,schemas}.py`,
`routers/{agent,equipamentos}.py`, `services/teste_conexao.py`, `tests/test_teste_conexao.py`,
`tests/test_isolamento_contas.py`; `agent/service.py`, `service_linux.py`, `src/application/{api_client,teste_conexao}.py`,
`tests/test_teste_conexao.py`; dashboard `api/{client,types}.ts`, `index.css`, `MachineDetail/index.tsx`,
`components/{EqCard,ConexaoTesteModal,EquipamentoFormModal,OltStatusModal}.tsx`. **Breaking change:** nenhum (campos
novos opcionais). **Branch:** `isaque`. **Versão:** agente 1.1.44.

### [2026-11-12] — Alarmes do DEFENSE reativados com o login do painel de alarmes, e notificação de alarmes (tipo ALARME)

**Alteração:** a função retirada em 11/11 (`legacy/defense_alarmes/`) voltou aos caminhos originais, agora com a
autenticação certa. O painel de alarmes (Next.js, porta padrão 3001) não aceita HTTP Basic Auth: o agente
reproduz o login do navegador — gera o token CSRF no formato do pacote npm `csrf`, assinado com o segredo padrão
`"secret-key"` (lido no JavaScript do painel), manda no cookie `csrfToken` junto do `POST /api/auth/login`
(`{username, password}`) e leva o `token.token` recebido no cookie `token` em `GET /api/alarm-centrals` (o header
`Authorization` é recusado com 400). Credenciais: as mesmas do equipamento DEFENSE; só a porta é configurável
(`config_extra.porta_alarme`, padrão 3001). `parse_alarmes` passou a copiar `id` da central e `id`/`disparada`
(`alarm`) das partições, e continua sem copiar `Bridge.private_key`/`access_key`, que a resposta do painel traz.
Religados: `_alarmes_loop` (5 min) em `agent/service.py`, `send_status_alarmes`, `POST /agent/defense/alarmes/status`,
`GET /machines/{id}/equipamentos/{nvr_id}/alarmes`, botão "Alarmes" no card do DEFENSE (`AlarmesModal`, agora com a
coluna de disparo) e o campo "Porta dos Alarmes" no formulário.
Notificação nova `ALARME`, opt-in por central (coluna nova `nvrs.alarmes_notificar`, JSON com os ids das centrais
marcadas; vazio até o usuário marcar). Uma notificação por situação, separadas pela coluna nova
`notificacoes.referencia`: `<central>:<partição>:DISPARO`, `<central>:DESCONECTADA` (status diferente de 1),
`<central>:<partição>:DESARMADA` e `FALHA` (agente não conseguiu consultar o painel; enquanto falha, as outras
ficam como estavam). Status com mais de 20 min (`LIMIAR_ALARME_SEM_DADOS_MIN`) não abre nem fecha alerta. A
verificação roda ao receber o relatório do agente (o disparo aparece na hora), ao ligar/desligar uma central e no
ciclo de 10 min; e-mail 1x por dia corrido por alerta aberto. Endpoints novos: `GET /notificacoes/alarmes` e
`PUT /notificacoes/alarmes/{nvr_id}/{central_id}` (isolados por conta). Painel: card "Alarmes" na página
Notificações, por máquina (recolhível, como o de câmeras), com as centrais de cada DEFENSE e o botão por central.
Migração inline: `nvrs.alarmes_notificar`, `notificacoes.referencia` e `ck_notificacoes_tipo` com `ALARME`.
Centrais de incêndio (tela `/central-incendio` do painel): o agente também lê `GET /api/firestations` na mesma sessão
e manda `incendio: [{id, nome, modelo, status}]` (sem o `hmac` nem a bridge); falha só nessa consulta vira lista
vazia. Fica em `last_alarm_status.incendio` e aparece numa seção do modal "Alarmes"; ainda não gera notificação.
Armar/desarmar central (botões no modal "Alarmes", com caixa de confirmação; só ADMIN da conta e super admin, pois o
`get_contexto` barra POST de LEITURA e conta vencida): `POST /machines/{id}/equipamentos/{nvr_id}/alarmes/comando`
(`{central_id, acao: ARMAR|DESARMAR}`) cria a tarefa em `pending_alarme_tasks` (memória, 1 por máquina, mesma
limitação de 1 worker do teste RTSP), entregue no long-poll do ping como `alarme_task`; o agente (thread disparada no
próprio ping, para não esperar o loop principal durante backup) faz login, confirma o modelo da central em
`/api/alarm-centrals` e manda o que a tela `/arm-disarm` do painel manda: `PATCH /api/commands/AMT8000/Arm|Desarm`
com `{"station_id"}` para AMT 8000, ou `PATCH /api/commands/arm-disarm` com `{station_id, command: 1|0,
partitionsState}` (4010: partições A-D; demais: A e B). Devolve em `POST /agent/defense/alarmes/comando-resultado`
e, se deu certo, reenvia o status da central 8 s depois. O servidor espera até 75 s, recusa máquina offline (409) e
grava pedido e resultado nos logs da máquina (`event_type="alarme_comando"`, com o e-mail de quem pediu). Arme
parcial, bypass e restauração do painel (`/api/commands/AMT8000/{ArmParcial,Bypass,Restore}`) ficaram de fora.
**Arquivos:** agent/{service.py,src/application/{api_client.py,status_alarmes_defense.py},src/vms/defense_alarmes.py,tests/test_defense_alarmes.py}, server/api/{models.py,main.py,schemas.py,routers/{agent.py,equipamentos.py,notificacoes.py},services/notificacoes.py,tests/test_alarmes_notificacao.py}, server/dashboard/src/{api/{client.ts,types.ts},utils/notificacoes.ts,pages/Notificacoes/NotificacoesPage.tsx,pages/Machines/MachineDetail/{index.tsx,utils.ts,components/{AlarmesModal.tsx,EqCard.tsx,EquipamentoFormModal.tsx}}}, legacy/defense_alarmes (removido), PROJECT_SPEC.md.
**Breaking change:** não (colunas novas são opcionais; agente antigo só não envia alarmes).
**Versão do agente:** 1.1.44 (updater.py, installer.iss, package.json). Inclui também a correção do login da VSOL
(`e1e7126`). Gerada em 12/11 só para teste local na máquina da Helena (venv Python 3.13, sem Inno Setup); a
release oficial fica para o merge na `isaque`.
**Branch:** helena.


### [2026-11-12] — Notificação de câmera offline (tipo CAMERA_OFFLINE), para NVR, DIGIFORT e DEFENSE

**Alteração:** novo tipo de alerta `CAMERA_OFFLINE`, opt-in por câmera (não por conta, ao contrário dos 3
tipos automáticos existentes): o usuário escolhe quais câmeras quer acompanhar na aba Notificações, e cada
câmera nova já cadastrada começa com a notificação desativada. `NVRCamera` ganhou a coluna
`notificar_offline` (BOOLEAN, default FALSE) e `Notificacao` ganhou `camera_id` (FK para `nvr_cameras`, `ON
DELETE CASCADE`) — migração inline em `main.py` (`_MIGRACOES_COLUNAS` + recriação de `ck_notificacoes_tipo`
com o valor `CAMERA_OFFLINE`). `services/notificacoes.py` ganhou `verificar_cameras_offline`, para
equipamentos `tipo IN ('NVR', 'DIGIFORT', 'DEFENSE')` (testado primeiro só com DEFENSE, depois estendido aos
outros dois, a pedido do usuário); o pareamento de cada `NVRCamera` com o `last_recording_status` do agente
usa a mesma regra de cada tipo — função nova e compartilhada `services/galeria_vms.status_por_camera`
(pasta/nome via `parear_cameras` para DIGIFORT/DEFENSE; canal físico, via `canal_int`, para NVR tradicional
— a mesma distinção que `routers/equipamentos.py:get_nvr_cameras` já fazia pra Galeria). Usa
`services/camera_offline.segundos_offline` para medir o tempo offline; limiar de 15 min
(`LIMIAR_CAMERA_OFFLINE_MIN`, igual ao de agente offline) antes de abrir o alerta, com e-mail diário (1x/dia
corrido enquanto continuar offline, mesmo padrão da licença/personalizada). Endpoints novos em
`routers/notificacoes.py`: `GET /notificacoes/cameras` (lista os equipamentos com câmeras da conta, de
qualquer um dos 3 tipos, com estado atual e a flag; cada item já vem com `machine_id`/`nvr_id`/`nvr_tipo`
pra agrupar no painel) e `PUT /notificacoes/cameras/{camera_id}` (liga/desliga, ADMIN da conta ou super
admin), ambos isolados por conta (REGRA-010) via `Machine.conta_id`. Painel: nova seção "Câmeras offline"
em `NotificacoesPage.tsx`, agrupada primeiro por Máquina e depois por equipamento (ícone/cor/rótulo do tipo
vindos de `eqTipos.tsx`, o mesmo usado nos cards de equipamento), com um botão ativar/desativar por câmera
(mesmo padrão visual dos 3 tipos automáticos); ícone/cor do tipo de notificação em `utils/notificacoes.ts`
(`VideoOff`, vermelho). Testes de unidade com SQLite em memória em
`server/api/tests/test_cameras_offline_notificacao.py` (sem Postgres): opt-in por câmera, limiar de tempo,
volta a ficar online, e o pareamento por canal físico (NVR tradicional) separado do pareamento por nome.
**Arquivos:** server/api/{models.py,main.py,schemas.py,routers/notificacoes.py,services/{notificacoes.py,galeria_vms.py},tests/test_cameras_offline_notificacao.py}, server/dashboard/src/{api/{client.ts,types.ts},utils/notificacoes.ts,pages/Notificacoes/NotificacoesPage.tsx}, PROJECT_SPEC.md.

### [2026-11-13] — Defense: câmeras de DVR/NVR voltam à Galeria ("Sincronizar da Máquina" traz tudo que o Defense lista)

- **Sintoma** (Defense Trilan): a Galeria tinha só as 10 câmeras de IP próprio; os 5 canais do DVR-CATANDUVA, os 3 do ESTOQUE CATANDUVA, o canal do NVR INTELBRAS e a LATERAL TERRENO (10 de 20) não apareciam, sem estado, gravação nem imagem.
- **Causa**: (1) a importação da planilha só aceita linhas do tipo "câmera" (`d0e682e`, 26/10) e a planilha do Defense não traz os canais dos gravadores; (2) desde 29/10 (`248d255`) o agente, havendo câmeras na Galeria, reporta só as câmeras da Galeria (antes inventava estado para o que não achava); (3) câmeras de IP compartilhado precisam de `canal_rtsp` para a captura (`7cc188e`). A API do Defense sempre devolveu as 20 câmeras, com estado e gravação.
- **Agente** (`src/vms/defense.py`): `_casar_cameras_defense` acrescenta ao relatório as câmeras que o Defense lista e a Galeria não tem (por nome, nome do canal ou, em câmera de IP próprio, IP); essas entradas levam `modelo` e `canal_rtsp`. `canal_rtsp` sai do código do canal (`1000079$1$0$3` = canal 4 do gravador) e só existe para canais de DVR/NVR. Entradas da Galeria não mudam. Testes: `agent/tests/test_defense_cameras_fora_da_galeria.py`. **Precisa de versão nova do agente.**
- **Servidor**: `POST .../cameras/import` com `sync_from_machine` num DEFENSE cria também as câmeras do relatório sem par na Galeria (`cameras_do_relatorio_sem_par` e `marca_pelo_modelo` em `services/galeria_vms.py`): nome e IP do Defense, `canal_rtsp` do gravador, marca pelo modelo (DS-=Hikvision, MTI/DIH=ONVIF, MHDX/VIP/iNVD=Intelbras) e a senha padrão do projeto (a do gravador não vem do Defense: editar na câmera se for outra). Sem nada para trazer responde 400 com o motivo. Testes: `server/api/tests/test_galeria_sync_defense.py`.
- **Painel**: mesma tela e botão "Sincronizar da Máquina" (só o texto da dica muda no DEFENSE). Depois do agente novo, as câmeras de gravador já aparecem na Galeria (só com estado e gravação); o botão as cadastra para a captura das imagens.
- **Suposição não testada**: o canal físico do gravador é o último número do código + 1 (ESTOQUE CATANDUVA, MHDX 1108-C de 8 canais, tem os canais 6, 7 e 8). Conferir a primeira captura de cada gravador.

### [2026-11-12] — Tela de Auditoria na barra lateral

- **Tela**: `/auditoria` ("Auditoria", ícone de relógio, entre Notificações e Minha conta). Tabela com data/hora, usuário, máquina (com o cliente) e o que mudou, filtros por cliente, máquina, usuário, período e texto, paginada de 30 em 30. Só ADMIN da conta e super admin veem; o perfil LEITURA não vê o item e a API responde 403.
- **Dados**: lê os eventos de `agent_logs` com `usuario` preenchido (nova coluna `agent_logs.usuario`, migração inline em `main.py`, índice parcial por data). `registrar_alteracao()` grava o `usuario`; o pedido de armar/desarmar central de alarme também (o resultado do comando, que vem do agente, não). Eventos anteriores a esta versão não têm `usuario` e não aparecem na tela (continuam em "Eventos do Agente").
- **API**: `GET /api/v1/auditoria` (filtros `machine_id`, `customer_id`, `usuario`, `q`, `date_from`, `date_to`, `page`, `size`) e `GET /api/v1/auditoria/usuarios`. Sempre limitada às máquinas da conta do contexto (REGRA-010). O filtro de datas usa o dia no horário do Brasil (UTC-3), como a lista de Backups.
- **Retenção**: eventos com `usuario` não entram na poda de 30 dias / 5000 por máquina; ficam 365 dias (`DIAS_RETENCAO_AUDITORIA` em `services/agent_logs.py`, podados junto com os pings da máquina).
- **Fora do escopo**: o histórico é por máquina; alterações de Cliente, usuários, contas e dashboards (sem máquina) não entram. E apagar a máquina apaga os eventos dela.

### [2026-11-12] — Eventos do Agente: alterações feitas por usuários e admins no painel

- **O que**: toda alteração feita pelo painel numa máquina ou nos equipamentos dela vira um evento `alteracao_usuario` (etiqueta roxa "Alteração") em "Eventos do Agente", como já era feito com os comandos de alarme (`alarme_comando`). A mensagem traz quem fez (`ctx.feito_por`: e-mail do usuário ou "admin") e o horário é o `created_at` do evento, mostrado na linha.
- **Onde**: `registrar_alteracao()` em `services/agent_logs.py`, chamada na mesma sessão da alteração (o evento só existe se a alteração foi gravada). Cobre: cadastro/alteração/remoção de equipamento; importação, edição, remoção e imagem de referência de câmeras da Galeria; planilha importada, removida ou limpa; cadastro e alteração da máquina; nova chave de API; pedido de backup e de reinício do agente (um a um e "em todas as máquinas online").
- **Alterar mostra só os nomes dos campos** ("nome, IP, senha, configurações (pasta_gravacoes)"), nunca os valores, para não gravar senha nem segredo no evento. Salvar sem mudar nada não gera evento.
- **Fora do escopo**: o evento pertence a uma máquina (`agent_logs.client_id`), então alterações de Cliente, usuários, contas e dashboards não aparecem aqui; remover a máquina apaga os eventos dela junto. A retenção é a dos outros eventos (30 dias / 5000 por máquina).

### [2026-11-12] — Digifort/Defense: botão "Limpar planilha" e câmera de mesmo IP é substituída na importação

- **Limpar planilha**: botão na Galeria (DIGIFORT/DEFENSE) e no campo "Planilha das câmeras" do formulário do Digifort. Pede confirmação e chama `DELETE /machines/{id}/equipamentos/{nvr_id}/cameras`, que apaga todas as câmeras da Galeria (com as imagens de referência e da noite) e a planilha guardada. No formulário, se há planilha carregada e ainda não salva, o botão só a descarta.
- **Mesmo IP substitui**: `POST .../cameras/import` casava pelo nome antes do IP; se o nome da planilha nova era de uma câmera e o IP era de outra, a primeira recebia o IP da segunda e as duas ficavam com o mesmo IP (câmeras em dobro). Agora `casar_cameras_por_ip` (`services/planilha_vms.py`) dá prioridade ao IP: IP que aparece uma só vez na planilha e em uma só câmera da Galeria é a mesma câmera (renomeia e atualiza, preservando as imagens). IP repetido (equipamento com vários canais) continua casando pelo nome. Cada câmera antiga casa com no máximo uma linha.
- Câmera nova não toma mais o canal de uma câmera que continua na Galeria (antes podia haver dois itens com o mesmo canal).
- Testes em `server/api/tests/test_planilha_vms.py`.

### [2026-11-11] — Captura RTSP: porta 554 conferida só depois da 1ª falha (Hikvision antigas davam timeout)

- **Sintoma**: na CFTV 01 - Navarro, as câmeras Hikvision DS-2CD2012-I (e a 2 ANDAR, DS-2CD2020-I) falhavam na captura do painel com "Tempo esgotado (18s) via TCP" em todas as URLs, com IP, usuário e senha certos; Grandstream e a DS-2CD1001-I funcionavam.
- **Causa** (medida na própria máquina): `test_rtsp_camera` abria e fechava uma conexão TCP na porta 554, sem requisição, antes de chamar o ffmpeg (sonda de 21/10, `0b49f0c`). Esses firmwares ficam ~18 s sem atender o RTSP depois disso: o ffmpeg levou 18,4 s com a sonda e 0,06 s sem ela (ffmpeg 7.1, o mesmo do agente, e o 9.0.2 deram o mesmo resultado). O agente encerrava a 1ª URL aos 18 s e as seguintes também esbarravam na câmera ocupada.
- **Correção** (`agent/src/camera/rtsp_client.py`): a sonda virou `_porta_rtsp_aberta()` e roda só depois que a 1ª tentativa TCP falha (exceto 401). Câmera que responde não recebe conexão extra; câmera desligada ou IP errado continua parando na 1ª falha com "Porta RTSP 554 inacessível". Testes em `agent/tests/test_rtsp_sonda_porta.py`.
- Vale para a captura pelo painel e para a imagem da noite dos VMS (mesma função). Precisa de versão nova do agente para chegar às máquinas.

### [2026-11-11] — Piloto do agente MikroTik (ARMv7): build corrigido, imagem no GHCR e documentação do agente

**Contexto:** avaliar rodar o agente como container no MikroTik RB4011 do cliente (RouterOS 7, ARMv7) em vez de um PC
Windows. O colega adicionou ao `isaque` (merge `762dd99`) `service_linux.py`, `requirements-linux.txt`,
`Dockerfile.mikrotik` e `README_MIKROTIK.md`; a versão Windows não mudou. **Build:** o `Dockerfile.mikrotik` original
falhava no `pip install` (sem `gcc` e sem `make`: o PyPI não tem wheel ARMv7 de `pynacl`, `pycryptodome(x)`, `psutil`,
`Pillow` e `cffi`). Passou a ter dois estágios (compilação no `builder`, imagem final só com o resultado e
`libffi8`/`libjpeg62-turbo`/`zlib1g`) e ganhou `agent/.dockerignore`. **Resultado:** imagem `linux/arm/v7` de ~60 MB;
teste emulado (`armv7l`) importa todas as dependências e os módulos do agente. Build sem cache leva ~1h40 sob QEMU.
**Imagem:** `agent/mikrotik/trilan-agent-armv7.tar` (60,2 MB, SHA-256 `35fbdde5…3433f`), versionada no repositório
para o colega subir no RB4011 de teste. **Não
validado:** execução contra o servidor, importação no RouterOS, desempenho no roteador, SSH do `paramiko` 3.4.0 com as
OLTs Huawei antigas. **Docs:** `agent/DOCUMENTACAO_AGENTE.md` (funcionamento completo do agente Windows e do piloto) e
seção em português no `agent/README_MIKROTIK.md` (build, como gerar a imagem e configuração do teste).

### [2026-11-11] — Merge com a Helena e versão 1.1.43 do agente

**Incorporado (ramo `helena`, `f7cca54`):** importação do Digifort com pasta de gravação por câmera e raiz automática; alarmes do Defense movidos para `legacy/defense_alarmes/` (retirada pedida na entrada da Helena; a coluna `nvrs.last_alarm_status` permanece sem uso); OLT Huawei: campo `fabricante` no status e ONT sem estado de `DESCONHECIDO` para `OFFLINE`. **Auditoria:** sem data com fuso, sem segredo novo, nenhuma rota nova sem `ctx`/filtro de conta; compose, nginx, models, migrações, requirements, build.ps1, installer.iss e `.env` intocados. **Bloqueado:** nada. **Observação:** o dashboard continua usando `navarro@123` como senha padrão de câmera (IC-012, já aberto). **Versão:** agente 1.1.43 (agente mexeu em `service.py`, `api_client.py`, `status_olt.py`, `huawei_status.py`).

### [2026-11-11] — Importação do Digifort: pasta de gravação por câmera e raiz automática

**Alteração:** a importação da planilha do Digifort (Galeria e formulário do equipamento, mesma função
`rowsToCameras`) agora lê a coluna "Diretório de gravação" / "pasta de gravação" quando presente. Para cada
câmera, o último trecho do caminho (qualquer nome: número como "34" ou texto longo como "1 ANDAR - ELEVADOR
B") é gravado como vínculo explícito (`pasta_gravacao` da `NVRCamera`, enviado por `cameras/import` no campo
`pasta_gravacao` do item) — assim o agente casa a pasta de gravação com a câmera mesmo que o nome dela não
tenha nada a ver com o nome da pasta (ex.: câmera "44" com pasta "SALA ADM"), sem depender do
aprendizado automático por nome igual (`aprender_pastas` em `galeria_vms.py`, que só generaliza quando
nome da câmera == nome da pasta). A raiz comum dos caminhos da coluna (ex.: "F:\GRAVACAO DIGIFORT") passa a
preencher sozinho o campo "Local de gravação das câmeras" do formulário do Digifort quando o usuário
confirma a planilha ("Usar esta planilha" no campo, ou "Importar câmeras" na Galeria de um equipamento
existente): não precisa mais digitar o caminho manualmente quando a planilha já trouxer essa informação.
**Arquivos:** server/api/schemas.py (`NVRCameraConfigItem.pasta_gravacao`), server/api/routers/equipamentos.py
(`import_cameras` grava `pasta_gravacao` quando enviado), server/dashboard/.../hooks/useCameraImport.ts
(`raizGravacaoDaPlanilha`, `pastaGravacaoDoCaminho`, `raizComumCaminhos`, coluna detectada em
`rowsToCameras`), server/dashboard/.../planilhaVms.ts, server/dashboard/.../components/
PlanilhaCamerasCampo.tsx, server/dashboard/.../components/NVRCamerasGalleryModal.tsx, server/dashboard/.../
index.tsx (`onPastaGravacoesDetectada` grava a raiz no `config_extra` do equipamento ao confirmar import).
**Breaking Change:** Não (campo novo opcional; comportamento antigo mantido quando a planilha não tem a
coluna).
**Branch:** helena

### [2026-11-11] — Alarmes do Defense (Intelbras) movidos para legacy/

**Alteração:** retirada "por enquanto" da funcionalidade que lia as centrais de alarme Intelbras de um
equipamento DEFENSE (`/api/alarm-centrals`) e mostrava status/partições num modal do dashboard. Os quatro
arquivos (`status_alarmes_defense.py`, `defense_alarmes.py`, `test_defense_alarmes.py`, `AlarmesModal.tsx`)
foram movidos sem alteração para `legacy/defense_alarmes/` (com um README explicando como reativar); os
pontos de ligação que continuavam ativos foram apenas removidos (não movidos): a thread `_alarmes_loop` e
seu start em `agent/service.py`, `send_status_alarmes` em `api_client.py`, a rota `POST
/defense/alarmes/status` (e o import de `StatusAlarmeReport`) em `routers/agent.py`, a rota `GET
/{id}/alarmes` em `routers/equipamentos.py`, os schemas `EquipamentoStatusAlarme`/`StatusAlarmeReport`, e no
dashboard o botão "Alarmes" do `EqCard`, o campo "Porta dos Alarmes" do `EquipamentoFormModal` e os tipos
`AlarmPartition`/`AlarmCentral`/`AlarmeStatusResponse`/`porta_alarme`. A coluna `last_alarm_status` em `NVR`
fica no banco sem uso (migração só é aditiva). O cadastro e o backup de equipamentos DEFENSE continuam
normais; só a tela/coleta de alarmes saiu.
**Arquivos:** legacy/defense_alarmes/ (novo), agent/service.py, agent/src/application/api_client.py,
server/api/routers/agent.py, server/api/routers/equipamentos.py, server/api/schemas.py,
server/dashboard/src/pages/Machines/MachineDetail/components/EqCard.tsx, index.tsx,
EquipamentoFormModal.tsx, server/dashboard/src/pages/Machines/MachineDetail/utils.ts,
server/dashboard/src/api/types.ts, PROJECT_SPEC.md
**Breaking Change:** Não (a coluna do banco é mantida; agentes antigos que ainda enviarem o status antigo
recebem 404 na rota removida, sem afetar o resto do ping/backup).
**Branch:** helena

### [2026-11-10] — WhatsApp retirado (solução arquivada)

**Decisão do usuário:** tirar tudo o que foi feito para o WhatsApp e guardar a solução documentada, para uso futuro. **Feito:** revertido o commit `9804e4c`: ponte `server/whatsapp/`, `whatsapp_service`, `whatsapp_relatorios`, `whatsapp_numero`, `routers/whatsapp_router.py`, `tests/test_whatsapp.py`; campos `whatsapp_to`/`whatsapp_contato` nos models, schemas e rotas; envios por WhatsApp em `agent.py`, `backups.py`, `backup_runs.py`, `notificacoes.py` e `avisos_conta.py`; variáveis `WHATSAPP_*` no `config.py` e nos `.env*.example`; serviço e volume nos dois compose; cartão em Configurações e campos do painel. O e-mail volta a ser o único canal, como antes de 09/11. **Mantido:** `server/dashboard/.dockerignore` (correção do build, sem relação com o WhatsApp). **Documentação:** `archive/whatsapp/README.md` (como funcionava, decisões, riscos e como trazer de volta).

**Banco:** as colunas `client_groups.whatsapp_to`, `clients.whatsapp_to` (`TEXT[] NOT NULL DEFAULT '{}'`) e `contas.whatsapp_contato` (`VARCHAR(30)`) foram **apagadas** (`DROP COLUMN IF EXISTS`, rodado no startup de um deploy único, commit `3723b7b`, e depois retirado do código). Os números cadastrados se perderam. Motivo: sem o campo no model, a coluna NOT NULL sem default (criada pelo `create_all`) fazia o cadastro de Cliente falhar com "null value in column whatsapp_to", reproduzido no banco local. Conta, Cliente e Máquina são criados normalmente depois do DROP (testado no banco local). Nenhuma rota do agente mudou (o agente não sabia do WhatsApp). **Dokploy:** o Application "WhatsApp" (criado em 09/11, Dockerfile `server/whatsapp/Dockerfile`, volume `whatsapp-auth`) foi **excluído** e as variáveis `WHATSAPP_BRIDGE_URL`/`WHATSAPP_BRIDGE_KEY` foram removidas da aba Environment do Backend, a pedido do usuário. Também foram removidos o container e o volume locais e a linha do `server/.env`.

### [2026-11-10] — Versão 1.1.42: merge `helena` (detecção de GPON na OLT Huawei)

**Incorporado** (`5d23696`, `d5ab86b`, merge `f0c1ea5`):
- `agent/src/olt/huawei_status.py`: o `interface gpon 0/<slot>` que dá certo não imprime nada além do eco e do prompt novo, e o `comando()` cortava justamente a última linha (o prompt); por isso toda placa era tratada como "sem GPON" e a coleta voltava sem ONUs. Agora o teste é feito contra o prompt guardado em `prompt_atual`.
- `agent/tests/test_huawei_status.py`: teste de regressão com o diálogo real da MA5800 (eco + prompt).
- `agent/requirements.txt`: `paramiko` fixado em `3.4.0` (antes `>=3.4.0,<4.0.0`), para manter `ssh-rsa`/`ssh-dss` com OLTs Huawei antigas. Conferido no venv do build: funciona com `cryptography` 50.0.2 (só avisos de depreciação do TripleDES).

**Auditoria:** sem datas com fuso, sem segredos, sem mudança em compose, nginx, models, migrações, build ou instalador. **Bloqueado:** nada.

### [2026-11-09] — Correção da documentação: a produção são Applications do Dokploy, não o `docker-compose.yml`

**Descoberta:** o WhatsApp em produção respondia "container não está respondendo" e o log do Backend mostrava `Failed to resolve 'whatsapp'`. Consultando o Dokploy (só leitura), o projeto "Sistema de Backup" não tem Compose: são os Applications **Backend** (`/server/api`) e **Frontend** (`/server/dashboard`), ambos com build Railpack a partir da `isaque`, mais um Postgres do próprio Dokploy. O `server/docker-compose.yml` nunca foi lido pela produção; por isso o serviço `whatsapp` adicionado nele (entrada "WhatsApp só por QR code", acima) não foi criado.

**Corrigido:** seção 11 (tabela dos serviços reais), estrutura de pastas e diagrama da seção 2, auditoria de merge (o compose não rege a produção), `CLAUDE.md` (nova seção "Produção no Dokploy"; acesso do Claude descrito em `CLAUDE.local.md`, fora do git), skill `gerenciar-containers` (cópias do Claude e do Gemini), `.agents/rules/git-deploy.md` e um aviso no topo do `server/docker-compose.yml`. A IC-015 e o incidente de 06/10 perdem a gravidade de "banco vazio": a troca de volume nunca atingiu a produção.

**Pendente para o WhatsApp funcionar em produção (no Dokploy, a pedido do usuário):** criar um Application "WhatsApp" (`/server/whatsapp`, build pelo Dockerfile, volume em `/data`, `API_KEY` igual à `WHATSAPP_BRIDGE_KEY` do Backend, `INSTANCE_NAME=trilan`, sem domínio) e no Backend definir `WHATSAPP_BRIDGE_URL=http://<appName do WhatsApp>:3000`. Atenção: o Backend tem **duas** linhas `WHATSAPP_BRIDGE_KEY` com valores diferentes; deixar só uma.

### [2026-11-09] — WhatsApp só por QR code: removida a opção de Evolution API externa

**Decisão do usuário:** o WhatsApp passa a funcionar apenas pelo container `whatsapp` com QR code; sem Evolution. **Esta entrada substitui o que as duas entradas de WhatsApp de 09/11/2026 dizem sobre `evolution_*`/`EVOLUTION_*`.**

**Removido:** as chaves `evolution_url`/`evolution_instance`/`evolution_apikey` da tabela `settings` e do `GET/PUT /api/v1/settings` (e os campos de URL/instância/chave no painel); `POST /api/v1/settings/whatsapp/teste`; as variáveis `EVOLUTION_*`; o `environment` do compose local. **Como fica a configuração:** `config.py` ganhou `WHATSAPP_BRIDGE_KEY` (sem ela o WhatsApp fica desligado), `WHATSAPP_BRIDGE_URL` (padrão `http://whatsapp:3000`) e `WHATSAPP_INSTANCE` (padrão `trilan`); a API recebe a chave pelo `env_file` (`server/.env`), sem bloco `environment`. `whatsapp_service.whatsapp_config()` não consulta mais o banco. Rotas, todas só do admin global em `routers/whatsapp_router.py`: `GET /api/v1/whatsapp/conexao` (`configurado`, `disponivel`, `connected`, `numero`, `qr`), `POST /api/v1/whatsapp/desconectar` e `POST /api/v1/whatsapp/teste` (antes em `/settings`). **Painel:** Configurações mostra só o cartão WhatsApp (QR, número conectado, Desconectar e envio de teste, que aparece depois de conectar); avisa quando falta a chave ou o container não responde. As rotas de envio da ponte (`/message/sendText|sendMedia/:instance`) mantêm o formato antigo só por conveniência; o Trilan não depende da Evolution.

**Testado:** 26 testes (WhatsApp, e-mail com imagens e avisos da conta) passam em container; `tsc --noEmit` do painel limpo; com a API recriada, a sessão já conectada seguiu ativa (conferido só em leitura). 

**Produção (mesma data):** `server/docker-compose.yml` ganhou o serviço `whatsapp` (build de `./whatsapp`, sem porta publicada, volume nomeado `whatsapp_auth` para a sessão, `API_KEY: ${WHATSAPP_BRIDGE_KEY:-}`). Nada mais do arquivo foi tocado (nginx `7005:7001` e `pg_data_local` ficaram como estavam). A chave usa `:-`, e não `:?`, para o deploy nunca falhar por falta dela; sem a chave o container `whatsapp` fica ocioso com um aviso no log (em vez de reiniciar em loop) e o WhatsApp fica desligado, sem afetar o resto. A API lê a mesma `WHATSAPP_BRIDGE_KEY` do `.env`.

**Breaking Change:** Não. **Requer, depois do deploy:** definir `WHATSAPP_BRIDGE_KEY` (aleatória, mínimo 16 caracteres) nas variáveis de ambiente do Dokploy, reimplantar, e ler o QR code em Configurações > WhatsApp (a sessão local não vai para o servidor).

### [2026-11-09] — WhatsApp sem servidor externo: container `whatsapp` (Baileys) com conexão por QR code no painel

**Motivo:** o usuário não quer instalar/manter uma Evolution API. Modelo tirado do repositório `isaqueschaffer/BotMercadolivre` (Baileys direto no processo, sessão em volume, QR no dashboard).

**Novo serviço `server/whatsapp/`** (Node 22 + `@whiskeysockets/baileys` ^6.7.16 + express): mantém uma sessão do WhatsApp Web e expõe, só na rede interna do Docker (sem porta publicada), as **mesmas rotas de envio da Evolution v2** (`POST /message/sendText|sendMedia/:instance`, header `apikey`), então `services/whatsapp_service.py` não mudou. Extras: `GET /status`, `GET /qr` (PNG em data URL), `POST /logout` (apaga a sessão e volta a gerar QR) e `GET /health`. Resolve o número com `onWhatsApp` (cobre o 9º dígito dos celulares BR; número sem WhatsApp = 404), usa `fetchLatestBaileysVersion` (o WhatsApp recusa versões antigas do protocolo) e reconecta sozinho (inclusive o reinício que o WhatsApp pede logo após ler o QR). A chave `API_KEY` (≥16 caracteres) é obrigatória e comparada em tempo constante. A sessão fica no volume `whatsapp_auth_local` (`/data/auth`): sem volume, pede QR a cada recriação.

**API:** `routers/whatsapp_router.py`, só admin global: `GET /api/v1/whatsapp/conexao` (`configurado`, `suportado`, `connected`, `numero`, `qr`; `suportado=false` quando o envio usa uma Evolution externa, que não tem `/status`/`/qr`) e `POST /api/v1/whatsapp/desconectar`. **Painel:** o cartão de WhatsApp em Configurações mostra o QR (atualiza a cada 3 s), o número conectado e o botão Desconectar; os campos URL/instância/chave só são preenchidos para usar uma Evolution externa (têm prioridade sobre as variáveis `EVOLUTION_*`).

**Compose:** só `server/docker-compose.local.yml` foi alterado (serviço `whatsapp`, volume `whatsapp_auth_local`, e a API recebe `EVOLUTION_API_URL=http://whatsapp:3000`, `EVOLUTION_INSTANCE=trilan`, `EVOLUTION_API_KEY=${WHATSAPP_BRIDGE_KEY}`). A chave `WHATSAPP_BRIDGE_KEY` fica em `server/.env` (exemplo em `.env.local.example`). **`server/docker-compose.yml` (produção) NÃO foi alterado**: para usar em produção é preciso replicar o serviço, o volume e a variável lá (o push na `isaque` dispara o deploy no Dokploy). Também foi criado `server/dashboard/.dockerignore` (o build do painel tentava copiar `node_modules` da pasta do OneDrive).

**Riscos:** a biblioteca não é oficial; o número pode ser bloqueado pelo WhatsApp e a versão do Baileys pode precisar de atualização quando o protocolo mudar. **Testado:** ponte rodando no compose local (gera QR; 401 sem chave, 503 sem conexão, 404 instância errada), ligação API → ponte e rota `/whatsapp/conexao` conferidas por dentro do container da API, `tsc --noEmit` do painel sem erros. **Não testado:** envio real (depende de ler o QR com um celular).

**Breaking Change:** Não. **Requer:** build do novo container no deploy (quando for levado à produção).

### [2026-11-09] — WhatsApp: os mesmos relatórios e avisos do e-mail, pela Evolution API

**Pedido:** poder cadastrar números de WhatsApp para receber o que hoje sai por e-mail. **Decisões (perguntadas ao usuário):** provedor = Evolution API própria; vão por WhatsApp o relatório de backup, as notificações da conta e os avisos da conta; o número é cadastrado ao lado dos e-mails; formato = texto resumido + imagens das câmeras offline.

**Banco (migração inline em `_MIGRACOES_COLUNAS`, idempotente):** `client_groups.whatsapp_to TEXT[]` (Cliente) e `clients.whatsapp_to TEXT[]` (Máquina), ambos `NOT NULL DEFAULT '{}'`; `contas.whatsapp_contato VARCHAR(30)`. Números guardados só com dígitos e DDI (`5511999998888`): `server/api/whatsapp_numero.py` normaliza e valida (10/11 dígitos sem `+` = Brasil, ganha o 55; com `+` ou `00` vale o DDI informado, 8 a 15 dígitos) e é usado nos validadores Pydantic (`whatsapp_to` em Cliente/Máquina, `whatsapp_contato` em Conta). Número inválido = 422.

**Servidor:** `services/whatsapp_service.py` (config em `settings` com fallback para `EVOLUTION_*`; `POST {url}/message/sendText|sendMedia/{instância}` com header `apikey`; 3 tentativas só em falha de rede/5xx; pausas entre mensagens; nunca levanta exceção) e `services/whatsapp_relatorios.py` (monta o texto resumido reaproveitando os helpers do e-mail: status geral, contagens, só os equipamentos com falha, contagem de câmeras, link de download; envia depois as imagens de referência das câmeras offline, no máximo `MAX_OFFLINE_IMAGES`=10; `disparar_em_segundo_plano` roda numa thread com sessão própria e grava `AgentLog` `whatsapp_sent`/`whatsapp_error`). Pontos de envio: upload do ZIP de máquina sem Cliente (`routers/agent.py`), reenvio do relatório (`routers/backups.py`), fechamento/reenvio da rodada do Cliente (`services/backup_runs.send_run_email`, números do Cliente), notificações de licença e personalizadas (`services/notificacoes._enviar_email`) e avisos de vencimento (`services/avisos_conta.enviar_aviso`), estes dois para o `whatsapp_contato` da conta. O e-mail continua igual: falha ou ausência de WhatsApp nunca afeta o e-mail, e o aviso conta como enviado se saiu por pelo menos um canal. Máquina com Cliente herda os números do Cliente (como os e-mails; `PUT /machines` recusa mudar `whatsapp_to` de máquina vinculada). Rotas novas: `GET/PUT /api/v1/settings` ganham `evolution_url`, `evolution_instance`, `evolution_apikey` (a chave não volta; só `evolution_apikey_configurada`) e `POST /api/v1/settings/whatsapp/teste` (admin global; manda uma mensagem de teste).

**Painel:** Configurações ganha o cartão "WhatsApp (Evolution API)" com botão de teste; campo "WhatsApp do relatório" nos formulários de Cliente e de Máquina (travado na máquina vinculada) e no cartão da Máquina; "WhatsApp de contato" no formulário e no detalhe da Conta; o log da máquina mostra "WhatsApp enviado"/"Erro de WhatsApp".

**Atenção:** as notificações personalizadas continuam com a caixa "enviar e-mail"; o WhatsApp acompanha essa caixa (sai para o número da conta se ele existir). Pré-requisito de operação: servidor Evolution API v2 próprio, com uma instância conectada (QR code) ao número remetente; número não oficial pode ser bloqueado pelo WhatsApp. **Testado:** `tests/test_whatsapp.py` (18 testes: normalização, configuração, envio com retentativas, montagem das mensagens e limite de imagens) e as demais suítes da API rodadas uma a uma em container Python 3.12 (todas passam, exceto `test_storage.py` e `test_galeria_pasta_gravacao.py`, que já falham por variável de ambiente ausente nos próprios testes: `ADMIN_PASSWORD`, `DATABASE_URL`, `SECRET_KEY`); `tsc --noEmit` do painel sem erros. **Não testado contra uma Evolution API real.**

**Breaking Change:** Não (colunas novas com padrão vazio). **Requer:** deploy do servidor e do painel; sem mudança no agente nem no compose.

### [2026-11-09] — Merge auditado do ramo `helena` (39a028a): OLT Huawei e alarmes do DEFENSE (agente 1.1.41)

**Tipo:** merge real (`git merge --no-ff`), sem conflitos; mexeu em `agent/`, então nova versão **1.1.41** (updater.py, installer.iss, package.json), build, release e cadastro (fluxo "merge com a Helena").

**Incorporado:** status das OLTs Huawei (`agent/src/olt/huawei_status.py`, integrado a `status_olt.py`); alarmes das centrais Intelbras cadastradas no DEFENSE (`agent/src/vms/defense_alarmes.py`, `status_alarmes_defense.py`, laço no `service.py`, envio no `api_client.py`); servidor: coluna `nvrs.last_alarm_status` (JSON; modelo `NVR` e migração inline em `_MIGRACOES_COLUNAS`), schemas `StatusAlarmeReport`/`EquipamentoStatusAlarme`, rota do agente `POST /api/v1/agent/defense/alarmes/status` e rota do painel `GET /api/v1/machines/{machine_id}/equipamentos/{id}/alarmes`; painel: `AlarmesModal.tsx`, `EqCard.tsx`, formulário de equipamento, tipos; testes `test_huawei_status.py` e `test_defense_alarmes.py`.
**Verificado e sem problema:** rota do agente filtra pela própria máquina (`machine.id`) e bloqueia conta suspensa; rota do painel recebe `ctx` e usa `_get_machine_or_404` (REGRA-010); `last_alarm_status` gravado em UTC naive (REGRA-001); migração idempotente; compose, nginx, requirements, build.ps1, installer.iss e `.env` intocados; nenhum segredo (só a leitura de `api_key` da configuração do equipamento).
**Bloqueado:** nada.

**Breaking Change:** Não. **Requer:** deploy do servidor e do painel (push em `isaque` dispara o Dokploy; a coluna nova é criada na subida) e atualização OTA do agente.

### [2026-11-09] — Merge auditado do ramo `helena` (04a3f9e): status de OLT VSOL e UNM2000 (agente 1.1.40)

**Tipo:** merge real (`git merge --no-ff`), sem conflitos; mexeu em `agent/`, então nova versão **1.1.40** (updater.py, installer.iss, package.json), build, release e cadastro no painel (fluxo "merge com a Helena").

**Incorporado:** monitoramento de status de OLT da VSOL (novo `agent/src/olt/vsol_status.py`, por HTTP, usando IP/usuário/senha do cadastro do equipamento) e ajustes no status das ONUs da UNM2000 em `status_olt.py`; testes `agent/tests/test_vsol_status.py`; painel: `OltStatusModal.tsx`, `StatusBadge.tsx` e `api/types.ts`.
**Verificado e sem problema:** nenhum arquivo sensível (compose, nginx, models, main.py, requirements, build.ps1, installer.iss, .env) nem rota do servidor no diff; nenhuma data com fuso (REGRA-001); sem segredos reais (só credenciais fictícias nos testes).
**Bloqueado:** nada.

**Breaking Change:** Não. **Requer:** deploy do painel (push em `isaque`) e atualização OTA do agente.

### [2026-11-06] — Merge auditado do ramo `helena` (66c1dc3): notificações do painel

**Tipo:** merge real (`git merge --no-ff`), sem conflitos; só servidor e painel (nenhum arquivo em `agent/`), então sem nova versão do agente, build ou cadastro.

**Incorporado:** sistema de notificações (licença da UNM2000, backup com falha, agente offline e personalizadas recorrentes ou por data): tabelas `notificacoes`, `configuracoes_notificacao` e `notificacoes_personalizadas`, router `/api/v1/notificacoes`, `services/notificacoes.py` (tarefa de fundo a cada 10 min, com e-mail pelos destinatários da Conta), pop-up ao logar e aba Notificações no painel (detalhes nas duas entradas da Helena abaixo).
**Verificado e sem problema:** toda rota nova recebe `ctx` e usa `filtrar_por_conta` (REGRA-010); escrita só com `exigir_admin_conta`; nenhuma data com fuso (REGRA-001); migração inline idempotente (coluna `definicao_id` em `_MIGRACOES_COLUNAS` e recriação de `ck_notificacoes_tipo`), sem alterar `docker-compose`, `nginx`, `requirements` ou `.env`; nenhum segredo.
**Bloqueado:** nada.

**Breaking Change:** Não. **Requer:** deploy do servidor e do painel (o push em `isaque` dispara o Dokploy).

### [2026-11-06] — Notificações: cor por tipo e notificação personalizada (recorrente ou por data)

**Alteração:** tabela nova `notificacoes_personalizadas` (modelo `NotificacaoPersonalizada`: título/mensagem, `enviar_email`, `mostrar_popup`, `ativo`, `modo` RECORRENTE/DATA, `intervalo_dias`, `data_alvo`, `dias_antes`, `ultimo_disparo_em`) e coluna `notificacoes.definicao_id` (FK para ela, `ON DELETE SET NULL`) — migração inline em `main.py` (`_MIGRACOES_COLUNAS` + recriação de `ck_notificacoes_tipo` com o valor `PERSONALIZADA`, já que a tabela `notificacoes` já existia). `services/notificacoes.py` ganhou `verificar_personalizadas`: no modo DATA funciona como a licença (1 notificação aberta, atualizada a cada ciclo; depois que a data passa continua "venceu há N dias" até desativar/apagar — decisão do usuário); no modo RECORRENTE, a cada `intervalo_dias` fecha o alerta anterior e cria um novo (fica histórico). `enviar_email`/`mostrar_popup` não mudam o que é gravado — só o que o router filtra: `GET /notificacoes?apenas_popup=true` (usado pelo pop-up) tira as personalizadas com `mostrar_popup=false`; a aba Notificações sempre mostra todas. CRUD em `routers/notificacoes.py` (`/notificacoes/personalizadas`, ADMIN da conta ou super admin; schemas com validação cruzada por `modo` em `schemas.py`). Painel: cor e ícone por tipo (`utils/notificacoes.ts`: licença=âmbar, backup=vermelho, agente offline=roxo, personalizada=verde — tokens `--warn/--err/--accent/--ok` já existentes), usados no pop-up e na lista; seção "Notificações personalizadas" e `NotificacaoPersonalizadaFormModal.tsx` em `NotificacoesPage.tsx`.
**Decisão (perguntada ao usuário):** depois que a data de uma personalizada por data passa, continua avisando "venceu" (não some sozinha); no modo recorrente cada disparo cria um alerta novo (histórico, não só atualiza um existente); só ADMIN da conta cria/edita/apaga (LEITURA só vê).
**Testado:** no container local — `tests/test_isolamento_contas.py` (11 asserções, sem regressão) + CRUD e os dois modos exercitados via `TestClient` direto contra o Postgres local (criação, validação 422 sem campo obrigatório, disparo do modo DATA na hora, disparo do modo RECORRENTE simulando `agora` adiantado — confirmado o fechamento do alerta anterior e a criação do novo no 2º disparo —, filtro `apenas_popup` excluindo a personalizada com `mostrar_popup=false` da lista do pop-up mas não da aba, e `DELETE` fechando o alerta aberto); dados de teste removidos ao final.
**Breaking Change:** Não. Requer o deploy do servidor (tabela nova + migração da coluna/constraint, ambas idempotentes) e o build novo do dashboard.

### [2026-11-06] — Notificações (licença UNM2000, backup com falha, agente offline): pop-up ao logar + aba configurável

**Alteração:** tabelas `notificacoes` (uma linha aberta por conta/tipo/equipamento; `resolvido_em` fecha sozinha quando a condição deixa de valer) e `configuracoes_notificacao` (liga/desliga por conta e tipo; ausente = ativo), modelos `Notificacao`/`ConfiguracaoNotificacao` (`models.py`) — criadas pelo próprio `create_all` (tabelas novas). Serviço `services/notificacoes.py`: `verificar_licencas_unm2000` (usa `licenca_da_config`; abre/atualiza a notificação enquanto faltar <= 10 dias ou já vencida, e manda 1 e-mail por dia corrido — dedup em `notificacoes.ultimo_email_em` — reaproveitando `services/avisos_conta.destinatarios` e o SMTP de `email_service.py`), `verificar_backups_falhos` (pelo `Machine.last_backup_status`) e `verificar_agentes_offline` (`Machine.last_seen` > 15 min; ignora máquina que nunca conectou). As três rodam a cada 10 min numa tarefa de fundo (`main.py`, mesmo padrão do laço de vencimentos das Contas) chamadas por `verificar_notificacoes`, cada uma isolada por `try/except`. Rotas novas em `routers/notificacoes.py` (tabela na seção 8); painel: `pages/Notificacoes/NotificacoesPage.tsx` (lista + toggle de preferências), `components/NotificacoesPopup.tsx` (pop-up com as notificações abertas, 1 vez por login — `sessionStorage`, limpo em `AuthContext.login`), link "Notificações" no `Sidebar.tsx`.
**Decisão (perguntada ao usuário):** e-mail da licença vai para os mesmos destinatários dos avisos de vencimento da Conta (não um campo novo no equipamento); isolamento por conta igual ao resto do painel — super admin sem conta escolhida fica na conta da plataforma (não vê "todas as contas juntas"; para ver uma conta específica, troca pelo seletor existente, igual Clientes/Máquinas); primeira entrega já cobre os três tipos (licença + backup com falha + agente offline); pop-up aparece a cada login, sem "não mostrar de novo".
**Testado:** `tests/test_isolamento_contas.py` (11ª asserção: conta A vê a sua, conta B não vê, super admin sem conta não vê/ com `X-Conta-ID` vê, `PUT config` exige admin) rodado de ponta a ponta no container local; `services/notificacoes.verificar_notificacoes` chamado contra um OLT real (licença a 5 dias) e confirmada a notificação com o texto certo (e-mail só não saiu por falta de SMTP configurado no ambiente local — tratado sem erro).
**Breaking Change:** Não. Requer o deploy do servidor (tabelas novas, criadas automaticamente) e o build novo do dashboard.

### [2026-11-05] — Merge auditado do ramo `helena` (27670b1) e agente 1.1.39

**Tipo:** merge real (`git merge --no-ff`), sem conflitos; auditado pelo checklist do CLAUDE.md.

**Incorporado:** FiberHome UNM2000 (resolução dos nomes das ONUs, leitura óptica/sinal por PON no modo clássico, status das OLTs), licença da UNM2000 no cadastro (`services/licenca_unm.py`, `licenca` na resposta de `GET .../olt-status`), `EquipamentoFormModal` e `OltStatusModal` do painel, utilitário `baixar_fotos_facial` (script + tela + `build_baixar_fotos.ps1`, para fotos da facial Intelbras), `.gitignore` das pastas de build das ferramentas, material de referência em `legacy/Template OLT FH`.
**Bloqueado/ajustado:** `server/docker-compose.local.yml` voltou a `7001:7001` (a Helena trazia `7005`); `datetime.now(timezone.utc).replace(tzinfo=None)` em `agent/src/olt/unm_telnet.py` virou `datetime.utcnow()` (REGRA-001). O `legacy/Template OLT FH.rar` (binário) entrou junto com a pasta extraída.

**Verificado e sem problema:** nenhuma rota nova (a alteração em `equipamentos.py` só acrescenta `licenca` ao retorno de uma rota que já usa `obter_maquina`; REGRA-010 mantida), nenhum `nginx`/`models`/migração/`requirements`/`.env` alterado.
**Atenção (não bloqueado):** o código do agente traz credenciais padrão da UNM2000 (`SENHA_PADRAO` do MySQL e `ROOT_SENHA`), ambas trocáveis por `TRILAN_UNM_DB_PASS` e `TRILAN_UNM_ROOT_PASS`; já estavam públicas no ramo da Helena.

**Breaking Change:** Não. **Requer:** nova build do agente (1.1.39 em `updater.py`, `installer.iss` e `package.json`).

### [2026-11-04] — Agente 1.1.38: merge com a Helena (status das OLTs UNM2000, backup travado, Digifort por pasta, Defense, imagem da noite dos VMS)

**Incorporado (ramo `helena`, até `a0a5577`):**
1. **Status das OLTs FiberHome da UNM2000 (agente e painel):** nova thread `_olt_loop` (a cada 300 s) consulta por Telnet (porta 23) cada OLT listada em `config_extra.olts` (um IP por linha ou `Nome=IP`) com `telnet_usuario`/`telnet_senha`/`telnet_enable` (`agent/src/olt/unm_telnet.py`). Só comandos de leitura (`dir`, `show version`, `show onu_state`, `show authorization`, `show optic_module`, `show onu active-state all`, `show onu optical-info`, `show card`; `config`/`interface pon`/`exit` só navegam): estado de cada ONU, totais por PON, placas/firmware e sinal óptico (rodízio de até 150 s por ciclo; BOM acima de -25,9 dBm, mesmo corte do Zabbix). Duas famílias de CLI (clássica V104 / AN5516 e `config` V105 / AN6000-AN6001). Nomes das ONUs lidos (só `SELECT`) do MySQL da UNM2000 (`t_ontdevice`, `nomes_db_*` no `config_extra`; nova dependência `pymysql`). Envio por `POST /api/v1/agent/olt/status` → `nvrs.olt_status` (migração inline); painel: `GET .../equipamentos/{id}/olt-status` e `OltStatusModal`.
2. **Senhas dentro do `config_extra` (`services/segredos_config.py`):** `telnet_senha`, `telnet_enable` e `nomes_db_senha` ficam em Fernet (`<campo>_enc`); o painel recebe só `<campo>_definida` (o `NVRResponse` mascara) e campo em branco ao editar mantém a senha; o agente recebe em texto pelo `/agent/config` (`config_extra_para_agente`).
3. **Backup travado:** cada equipamento roda com limite de 2 h (`_executar_com_limite`; passado o limite vira ERRO e o backup segue); o vigia (`_vigia_backup_loop`) reinicia o serviço com backup em andamento há 6 h; o ping passa `backup_ha_min` e o servidor deixa o reinício pelo painel passar quando o backup está há 120 min ou mais (`BACKUP_TRAVADO_MIN`), e o agente então se reinicia à força. `threads_iniciadas` impede threads duplicadas quando o `_run_loop` roda de novo. Equipamento com exceção inesperada vira ERRO em vez de derrubar o backup.
4. **Digifort:** `nvr_cameras.pasta_gravacao` (migração inline) é a chave do vínculo câmera × pasta: aprendida no relatório quando o nome é igual (`aprender_pastas`), passada ao agente em `cameras_config` e usada primeiro no pareamento; a câmera pode ser renomeada na Galeria sem perder o histórico, e o painel mostra o nome da Galeria. Câmera sem IP para o ping sai com comunicação `NAO_VERIFICADO` (não é queda).
5. **Defense:** gravações pela API (`/brms/api/v1.0/SS/Record/QueryRecords`, só consulta); sem câmeras na Galeria o agente descobre todas pela API (o servidor não manda mais as câmeras avulsas da máquina como fallback para DEFENSE).
6. **Imagem da noite das câmeras DIGIFORT/DEFENSE:** thread `_noite_loop` captura ao vivo (RTSP) na janela 19h30–4h, uma vez por noite e por câmera, repetindo as falhas a cada 30 min; o horário da captura ao vivo vai em UTC naive (antes ia a hora local e o painel deslocava).
7. Bandeja: o monitor do serviço é encerrado e recriado junto com o ícone ao reiniciar após erro. SHA-256 em blocos de 1 MB. `legacy/fiberhome_onu_discovery_name.py` (script original do Zabbix) entra e `legacy/digifort_snmp.py` sai.
**Bloqueado/ajustado no merge:**
- `legacy/fiberhome_onu_discovery_name.py` trazia usuário e senha do MySQL da UNM2000 fixos no código: passam a vir de `UNM_DB_USER`/`UNM_DB_PASS`. **A senha continua no histórico do ramo `helena` do repositório público: trocar a senha do usuário `zabbix_reader`.**
- REGRA-001: `datetime.now(timezone.utc).replace(tzinfo=None)` em `unm_telnet.py` e `rtsp_client.py` virou `datetime.utcnow()` (mesmo valor, padrão do projeto).
- O limite de tempo roda o equipamento em outra thread e o nome do equipamento do log remoto é por thread: `_executar_com_limite` repassa o contexto (senão os logs do backup perdiam o equipamento no painel).
- E-mail: com a regra nova de `NAO_VERIFICADO`, o "Resultado do Serviço" e os anexos de câmeras offline passam a seguir o mesmo critério da seção de câmeras (não conta como queda; só a falta de gravação conta).
- Restaurado um comentário apagado em `tray.py`.
**Atenção:** o `NVRResponse` de equipamento DIGIFORT carrega as câmeras da Galeria (com as imagens base64) para trocar os nomes; a listagem de equipamentos de máquina com Digifort grande fica mais pesada. A coleta das OLTs consulta o `/agent/config` a cada 5 min em toda máquina (mesmo sem OLT).
**Arquivos:** agent/service.py, agent/tray.py, agent/requirements.txt, agent/src/application/{api_client.py, backup_job.py, captura_noite_vms.py, estado.py, status_olt.py, webhook_digifort.py, updater.py}, agent/src/olt/{unm_telnet.py, unm_nomes.py}, agent/src/vms/{defense.py, digifort_gravacoes.py}, agent/src/backup/file_manager/{manager.py, copier.py}, agent/src/camera/rtsp_client.py, agent/installer.iss, agent/tests/*, server/api/{main.py, models.py, schemas.py}, server/api/routers/{agent.py, equipamentos.py}, server/api/services/{email_service.py, galeria_vms.py, segredos_config.py}, server/api/tests/*, server/dashboard/src/**, server/dashboard/package.json, legacy/*, PROJECT_SPEC.md.
**Breaking Change:** Não (colunas novas anuláveis; agentes antigos não enviam `backup_ha_min` nem status de OLT).
**Branch:** isaque

### [2026-11-04] — E-mail do relatório seletivo: só os equipamentos que o cliente possui

**Problema:** o e-mail de backup era igual para todos: sempre trazia a seção "Verificação de Câmeras dos CFTVs" (com "Nenhum equipamento do tipo CFTV verificado"), o título fixo "Backup de Equipamentos (NVR, PABX, Mikrotik...)", as linhas "Monitoramento (Câmeras/Gravações): Sem dados" e o assunto "Verificação de câmeras e Backup dos equipamentos", mesmo para cliente sem câmeras.
**Alteração (`services/email_service.py`, decisões do dono):**
1. **Assunto e cabeçalho dinâmicos:** com equipamento de câmeras (`NVR`, `DIGIFORT`, `DEFENSE`, `CAMERA`) continua "Verificação de câmeras e Backup dos equipamentos"; sem, vira "Backup dos equipamentos". O "Serviço executado" cita só os tipos presentes (ex.: "Backup das configurações dos equipamentos (Mikrotik, OLT)."). Os tipos vêm dos resultados da rodada somados aos equipamentos ativos cadastrados nas máquinas (`_tipos_cadastrados`), para o assunto não mudar quando a máquina das câmeras não reporta. Rodapé "Trilan CFTV" → "Trilan" (inclusive nas respostas encadeadas com imagens).
2. **Backup em lista única:** igual a antes, mas o título cita só os tipos presentes, na ordem do painel: `Backup de Equipamentos (NVR/DVR, Mikrotik, PABX)`.
3. **Por máquina:** a seção de câmeras (e a nota das imagens offline, no e-mail da máquina sem Cliente) só aparece se aquela máquina tiver equipamento de câmeras; as linhas "Monitoramento (Câmeras/Gravações)" do "Resultado do Serviço" seguem a mesma regra. A numeração das seções é sequencial (sem câmeras: 1 Backup, 2 Resultado).
4. **Câmeras não verificadas:** equipamento de câmeras em `ERRO` sem lista de câmeras ganha a linha "❌ Câmeras não verificadas (equipamento sem resposta ou falha no login)" e deixa o monitoramento como "Concluída com problemas" (antes contava como zero câmeras e saía "Concluída"). O total da seção passa a ser "Total de equipamentos com câmeras" (antes a conta misturava todos os equipamentos).
Resultado antigo sem `tipo` (reenvio de backup antigo): vale como `NVR` se trouxe câmeras; senão, tipo desconhecido (não entra no título).
**Arquivos:** server/api/services/email_service.py, server/api/tests/test_email_offline_images.py (NVR falso ganha `tipo` e `active`), PROJECT_SPEC.md.
**Breaking Change:** Não (só o texto do e-mail). **Atenção:** o assunto muda para clientes sem câmeras; regras/filtros de e-mail dos clientes baseados no assunto antigo deixam de casar. Só servidor; versão do agente não muda.
**Branch:** isaque

### [2026-10-30] — Agente 1.1.35: laço de atualização OTA (a 1.1.32 não trocava o executável)

**Problema:** publicada a 1.1.34, agentes 1.1.32 baixavam a versão, o `apply_update.bat` trocava a bandeja mas não o serviço, e o serviço voltava na 1.1.32 cerca de 2 min 15 s depois e baixava tudo de novo (~78 MB e ~2 min parado a cada 2,5 min). O processo antigo do `TrilanAgentService.exe` não saía: na OTA o `SvcDoRun` retornava normalmente e o Python esperava threads/pools pendentes; o .bat esperava 90 s, a cópia falhava 15 vezes (arquivo em uso) e o serviço religava a versão antiga. Mitigação na hora: 1.1.33 e 1.1.34 desativadas no painel (só a 1.1.32 ativa).
**Alteração:**
1. **Servidor:** `GET /agent/update-check` oferece a atualização à mesma máquina no máximo 1 vez por hora (dicionário em memória; a API roda com um worker). Vale para os agentes antigos, que pedem a atualização logo ao iniciar.
2. **Agente (`service.py`):** depois de baixar a atualização, o serviço avisa `SERVICE_STOPPED` ao Windows e sai com `os._exit(0)`, sem esperar threads e pools (avisar antes evita a recuperação do Windows religar a versão antiga).
3. **Agente (`updater.py`):** o `.bat` espera até ~45 s o processo antigo sair e, se não sair, roda `taskkill /F /IM TrilanAgentService.exe` (sem `/T`, porque o .bat é filho do serviço) antes de copiar. A versão recebida do servidor entra no `.bat` só com `[0-9A-Za-z._-]` (até a 1.1.34 entrava sem filtro e virava comando).
4. **Passagem 1.1.32 → 1.1.35 sem ir às máquinas (servidor):** o `.bat` dos agentes < 1.1.35 é gerado pela versão instalada e grava a versão sem filtro na 2ª linha. Para eles o `update-check` devolve `version` = `1.1.35` + `COMANDOS_ENCERRAR_PROCESSO_ANTIGO` (espera 25 s, `sc stop`, `taskkill /F /IM TrilanAgentService.exe`, registra no `atualizacao.log`), que encerra o processo preso antes da cópia. Agentes >= 1.1.35 recebem a versão pura. Linha testada no `cmd` com os comandos neutralizados.
5. **Piloto:** `OTA_PILOTO_MAQUINAS` com o ID da máquina do log do laço; com IDs no conjunto, só elas recebiam atualização. Confirmado em 30/10/2026 11:27–11:28: a máquina saiu da 1.1.32, executou os comandos do item 4 (sem laço, sem erro) e chegou em "Versão atual (1.1.35) está atualizada." Conjunto esvaziado no mesmo dia, liberando para as 122 máquinas.
**Arquivos:** `server/api/routers/agent_update.py`, `agent/service.py`, `agent/src/application/updater.py`, `agent/installer.iss`, `server/dashboard/package.json`, `PROJECT_SPEC.md`.
**Breaking Change:** Não. **Atenção:** o .bat é gerado pela versão instalada, então as correções 2 e 3 só valem a partir da 1.1.35; a passagem 1.1.32 → 1.1.35 depende do item 4 (com o limite do servidor, no máximo uma tentativa por hora por máquina).
**Branch:** isaque

### [2026-11-03] — Agente 1.1.37: travamento do serviço pelo log remoto (causa real do "offline")

**Problema:** desde a 1.1.32 o serviço travava por inteiro: ping, presença, backup, OTA, comandos da bandeja e a própria parada do serviço. Em `log_remoto.ManipuladorLogRemoto.__init__`, `self.lock = threading.Lock()` substituía o lock reentrante (`RLock`) do `logging.Handler`, que o `handle()` já segura durante o `emit()`; o `emit()` fazia `with self.lock:` de novo e a thread travava para sempre. Gatilho: a primeira linha de aviso/erro, ou marcada `enviar_servidor` (ex.: "INICIANDO BACKUP"), depois que a thread de logs instala o handler. Cada thread que registrasse log depois gravava a linha no `servico.log` (o FileHandler vem antes) e travava em seguida — por isso o log terminava com uma última linha de cada thread e sem "ENCERRADO" após "Parada solicitada.". O laço de OTA (1.1.32→1.1.34) reiniciava as máquinas a cada 2,5 min e escondia o problema; com a 1.1.35 elas travaram no backup agendado das 23:00 de 30/10. Na 1.1.35 o ping de rotina não gera log, então a thread de ping seguia pingando até receber uma instrução (por isso parte das máquinas continuava online). A suspeita de rede/DNS registrada na 1.1.36 estava errada: a falha de conexão na porta 7001 era só mais um gatilho (linha de erro).
**Alteração:** `agent/src/application/log_remoto.py`: a fila e a deduplicação usam um lock próprio (`trava_fila`); o `self.lock` do handler não é mais sobrescrito. Base da 1.1.36 mantida (sem as correções da auditoria 1.1.34).
**Arquivos:** agent/src/application/log_remoto.py, agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json, PROJECT_SPEC.md.
**Breaking Change:** Não. **Atenção:** máquinas travadas na 1.1.32–1.1.36 não verificam atualização (a thread principal está presa) e só recebem a 1.1.37 depois que o serviço for reiniciado (reinício do Windows ou `taskkill /F /IM TrilanAgentService.exe` + `sc.exe start TrilanAgentNVR` como administrador); depois disso, a verificação de atualização logo no início pega a 1.1.37 antes do primeiro gatilho, a não ser que uma linha de erro venha antes.
**Branch:** isaque

### [2026-11-03] — Agente 1.1.36: volta à base da 1.1.33, reaplicando só o fix do laço OTA

**Problema:** depois da 1.1.35 ir para as 122 máquinas, várias passaram a aparecer offline no painel por horas/dias (ping, presença e backup silenciosos ao mesmo tempo). Revisado o diff 1.1.33→1.1.35 inteiro: nenhuma regressão óbvia de travamento foi encontrada (as mudanças da auditoria 1.1.34 são majoritariamente correções de robustez, não causas de travamento) — o padrão de silêncio em todas as threads juntas é mais consistente com instabilidade de rede/DNS do hostname `publico.suportetrilan.com.br:7001` (usado por parte das máquinas, as com `agent.conf` mais antigo) do que com o código do agente. Mesmo assim, a decisão foi voltar a um ponto de partida mais simples.
**Alteração:** `agent/` revertido ao estado da 1.1.33 (commit `53dbaa2`), perdendo portanto as 19 correções da auditoria (changelog de 2026-10-29) e os ajustes posteriores de telemetria/codificação/dependências fixas. Reaplicado por cima, isoladamente:
1. **Laço de atualização OTA** (changelog de 2026-10-30, itens 2 e 3): `service.py` sai com `os._exit(0)` após `SERVICE_STOPPED` ao aplicar a atualização; `updater.py` espera ~45 s o processo antigo encerrar e, se não encerrar, mata à força antes de copiar.
2. **Versão filtrada no `.bat`** (changelog de 2026-10-30, item do `2696570`): a string de versão recebida do servidor só entra no `.bat` com `[0-9A-Za-z._-]`, mesmo não sendo mais estritamente necessário para agentes >= 1.1.35 (o servidor já não envia o payload de comandos para eles) — mantido como segurança em profundidade.
3. **URL padrão do instalador:** mantida `http://publico.suportetrilan.com.br:7001` (valor original da 1.1.33). Cheguei a trocar para `https://server.suportetrilan.com.br` por suspeitar dessa URL na instabilidade observada, mas o usuário confirmou que o servidor está na mesma rede de quem testa e que a URL funciona normalmente de fora da rede — revertido a pedido dele.
4. **Build:** mantido `py -3.14` fixo e `pyinstaller==6.22.3`/`pywin32==312` pinados em `build.ps1` (só infraestrutura de build, sem efeito no comportamento do agente).
**Arquivos:** agent/service.py, agent/src/application/updater.py, agent/installer.iss, agent/build.ps1, e os demais arquivos de `agent/` revertidos ao estado da 1.1.33 (ver changelog de 2026-10-29 para a lista completa do que se perde).
**Breaking Change:** Sim, comportamental: volta a perder as 19 correções da auditoria 1.1.34 (status de NVR/Intelbras, resiliência por equipamento, Defense IA via API, telemetria, etc. — ver changelog de 2026-10-29). **Pendente:** a causa real do "offline" (suspeita de rede/DNS em `publico.suportetrilan.com.br:7001`) não foi investigada a fundo nem corrigida nesta entrega; se o problema persistir na 1.1.36, a causa não é o código revertido.
**Branch:** isaque

### [2026-10-29] — Agente 1.1.34: correções da auditoria do agente 1.1.33 (19 itens)

**Alteração:** correções dos 19 problemas encontrados na auditoria do agente 1.1.33.
1. **NVR fora do ar/senha errada não aparece mais como OK.** `motorola/cameras.py`: login falho = `(None, None)`; logou e não achou câmeras = `({}, sessão)`. `intelbras/cameras.py`: `None` quando nenhuma das consultas CGI (ChannelTitle, RemoteDevice) respondeu HTTP 200; `{}` quando respondeu sem câmeras. `factory.py`: Motorola sem sessão e Intelbras sem CGI nem ISAPI viram `DESCONHECIDO`, e o `processar_nvr` devolve ERRO "NVR INACESSIVEL ou falha no login" (antes: Motorola `SEM_ARQUIVOS`, verde no painel; Intelbras `PARCIAL`). `api_client.post_report` manda `cameras: null` quando o equipamento não informou câmeras (antes `[]`, que apagava a lista no servidor). Servidor (`routers/agent.py`, `receive_backup_report`): ERRO com `cameras` nulo ou vazio (cobre agentes antigos) e lista anterior não vazia grava uma cópia com `status_comunicacao`/`status_gravacao` = `NAO_VERIFICADO` e `online` nulo, mantendo os demais campos (`offline_desde`, `offline_desde_aprox`, `imagem_noite`, `mapa`...); o `nvr_results` do backup (base do e-mail) não muda e segue sem câmeras para esse equipamento. `camera_offline.py` trata `NAO_VERIFICADO` como estado incerto (mantém a marca `offline_desde`; a presença seguinte volta a ONLINE/OFFLINE) e os widgets do dashboard o contam como "não online", como já faziam com `ERRO_COMUNICACAO`; o `StatusBadge` já o mostra como "Não Verificado".
2. **Um equipamento com erro não derruba mais o backup da máquina.** `backup_job.run_backup`: exceção no processamento de um equipamento (inclusive pasta final e ZIP interno) vira `{"status": "ERRO", "cameras": None}` com o traceback no log, e o backup segue. `copier.copy_file`: a limpeza do temporário funciona para pasta (Digifort) e arquivo e nunca levanta exceção. `file_manager/manager.py`: `parse_config_extra` no lugar de `equipamento.get("config_extra", {})` (quebrava com `None`) e saiu o ramo morto do DEFENSE, que lia a `pasta_origem` como CSV. `vms/defense.py`: leitura da pasta de origem (`exists`/`iterdir`/`stat`) protegida (erro = ERRO com as câmeras já montadas).
3. e 11. **Defense IA: status real, gravação com o significado do NVR e presença pela API.** Com a API sem resposta, o plano B lê o CSV do webhook (`config_extra.caminho_log_csv` ou o padrão `C:\Relatorios_Defense\status_cameras.csv`), nunca a `pasta_origem` (pasta dos backups); câmera sem informação fica `online: null`, `ERRO_COMUNICACAO` (antes todas viravam online com 15 dias de gravação inventados). Sem dado de gravação da API, a câmera fica `NAO_VERIFICADO` (total 0, mapa vazio), nada é deduzido do estado online. `consultar_gravacoes_defense_api`: HTTP diferente de 200, JSON inválido, resposta sem `data`, erro de rede ou canal sem código = `NAO_VERIFICADO`; resposta válida sem registros = `SEM_GRAVACAO`; `COM_GRAVACAO` só se HOJE tem gravação (como no `factory.py`), com mapa, total e dias cobrindo os 15 dias. Se a página de 1000 registros vier cheia e sem hoje, consulta só o dia de hoje (falha nessa consulta = `NAO_VERIFICADO`). Presença: nova `coletar_presenca_defense` (só handshake, login e árvore de dispositivos, `incluir_gravacoes=False`, sem RTSP), com o mesmo casamento de nomes do backup (`_casar_cameras_defense`: Galeria primeiro, senão as câmeras da API), só câmeras com online True/False; API sem resposta não envia nada; a presença não lê mais o CSV.
4. **UNM2000:** a exportação na hora aceita `trigger` `manual` (bandeja) e `manual_dashboard` ("backup agora" do painel e "Iniciar fila" do Cliente); o agendado continua sem exportação.
5. **Mikrotik e OLT Huawei** devolvem o nome original do equipamento no resultado (o sanitizado fica só nos arquivos); antes o servidor não achava o equipamento e gravava tipo "NVR".
6. **Status geral do backup:** `SEM_ARQUIVOS` conta como OK (mesmo `_OK_STATUSES` de `backup_runs.py`); máquina só com OK e Motorola deixa de sair PARTIAL. ERROR continua sendo "todos ERRO".
7. **Threads únicas:** ping, presença e envio de logs são iniciadas uma vez por processo (o laço de resiliência do `SvcDoRun` criava mais três a cada erro). O horário recebido do servidor é validado (hora 0-23, minuto 0-59) na leitura inicial e na ressincronização; inválido = erro no log e 02:00.
8. **Teste RTSP durante o backup:** a `rtsp_task` é disparada direto na thread de ping (`_ping_loop`), ao receber a resposta; saíram os disparos do `_process_ping_responses` (inclusive o da drenagem), que só rodavam com o laço principal livre (o servidor desiste em 55 s).
9. **RTSP ao vivo do canal 1 de NVR Motorola** (`rtsp_client.test_rtsp_camera`): o ramo de NVR (`/chID={canal}&streamType=main` primeiro) vale para Motorola sem `direct_camera`, com canal e (sem `stream_principal` OU canal > 1); antes o canal 1 caía no ramo de câmera avulsa e o limite de 4 URLs cortava o `chID=1`. No ramo de câmera avulsa, com canal, `/chID={ch}&streamType=main` entra logo após `/profile1`. Canal não numérico não levanta exceção.
10. **Intelbras: estado real das câmeras** pela CGI `LogicDeviceManager.cgi?action=getCameraState&uniqueChannels[0]=-1` (Digest; `Connected` = online, `Disconnected` = offline, outro valor/erro/canal ausente = desconhecido); antes toda câmera habilitada era "online". Canal analógico (ChannelTitle) = desconhecido. A consulta só é feita quando há câmeras IP. **Precisa de validação num NVR Intelbras real** (formato da resposta não conferido em equipamento). Nota da planilha ajustada ("A configuração lida pelo CGI não informa...").
12. **Log:** ping sem instrução não é mais registrado (só com restart/backup/rtsp_task, pelo `_resumo_ping`, e a volta do servidor); falhas seguidas de ping registram a primeira e depois no máximo uma linha a cada 10 min com a contagem. `log()` só manda ao Log de Eventos do Windows os erros e as marcas de início/parada do serviço. Rotação simples na inicialização: `servico.log` acima de 10 MB vira `servico.1.log`.
13. **OTA:** falha de certificado (SSL) no `update-check` vira `logger.error` com mensagem clara (certificado inválido na URL do servidor; atualização automática desativada até corrigir a URL em `agent.conf`), que chega aos logs do painel; a verificação do certificado continua ligada. As outras falhas seguem como aviso.
14. **Instalador:** URL padrão `https://server.suportetrilan.com.br` (antes `http://publico.suportetrilan.com.br:7001`).
15. **Webhook do Defense:** escuta só em `127.0.0.1:8181` (antes `0.0.0.0`, sem autenticação) e interpreta o `status` por comparação exata, sem maiúsculas/minúsculas (`ok`, `online`, `normal`, `restaurada`, `restaurado`, `restore`, `restored` ou começando com `restaura`); antes "broken" virava OK por conter "ok". **Atenção:** o Defense IA precisa chamar o webhook na mesma máquina do agente.
16. **Senha errada não mantém o NVR bloqueado:** a presença põe em espera crescente (por nome + IP) o NVR/DEFENSE sem resposta: pula 5, 10, 20, 40 e depois 60 min a cada falha seguida e zera na primeira leitura com sucesso. DEFENSE sem senha da API não é consultado.
17. **Fuso da recuperação de backup:** o agente manda `utc_offset_min` na telemetria (`time.localtime().tm_gmtoff // 60`); o servidor usa o do ping ou, se ausente, o de `machine.telemetry` (inteiro de -720 a 840; senão -180) e calcula tudo naive (`datetime.utcnow()` + deslocamento) para "agora", o horário agendado de hoje e a data do `last_backup_at`. Saiu o `timezone(timedelta(hours=-3))` (REGRA-001: a exceção documentada do `ping_agent` foi removida). Máquina em outro fuso deixa de receber dois backups por noite.
18. **Codificação explícita** (Python 3.15 muda o padrão): `servico.log` em `cp1252` com `errors="replace"` (formato que a bandeja lê); saída do `sc.exe` na bandeja e o `apply_update.bat` do OTA em `oem` com `errors="replace"`.
19. **Dependências fixas:** `agent/requirements.txt` com `==` (requests 2.34.2, pyzipper 0.4.0, pycryptodome 3.24.0, pywin32 312 no lugar de `pypiwin32>=223`, pystray 0.19.5, Pillow 12.3.0, paramiko 3.5.1, pyftpdlib 2.2.0, imageio-ffmpeg 0.6.0, psutil 7.2.2, GPUtil 1.4.0, pysnmp 7.1.30, openpyxl 3.1.5); `build.ps1` cria o venv com `py -3.14` e instala `pyinstaller==6.22.3` e `pywin32==312`.

Testes do Defense ajustados ao comportamento novo (`agent/tests/test_defense_api.py`: gravou ontem e não hoje = `SEM_GRAVACAO`; câmera sem dado de gravação = `NAO_VERIFICADO`). Nenhuma suíte foi executada nesta entrega (só `py_compile` dos arquivos alterados).
**Precisa de teste em equipamento real:** item 9 (canal 1 de NVR Motorola ao vivo pelo painel), item 10 (`getCameraState` num Intelbras), presença do Defense pela API (itens 3 e 11) e o plano B pelo CSV, a espera crescente da presença com senha errada (item 16) e a recuperação de backup com `utc_offset_min` (item 17).
**Arquivos:** agent/service.py, agent/tray.py, agent/build.ps1, agent/installer.iss, agent/requirements.txt, agent/src/application/{api_client.py,backup_job.py,presenca_cameras.py,updater.py,webhook_defense.py}, agent/src/backup/file_manager/{copier.py,manager.py}, agent/src/camera/rtsp_client.py, agent/src/mikrotik/routeros.py, agent/src/nvr/{factory.py,intelbras/cameras.py,intelbras/planilha.py,motorola/cameras.py}, agent/src/olt/{huawei_active.py,unm2000.py}, agent/src/vms/defense.py, agent/tests/test_defense_api.py, server/api/routers/agent.py, server/dashboard/package.json, PROJECT_SPEC.md

**Breaking Change:** Não. Os campos novos são opcionais: o servidor aceita `cameras: null` e `[]` e, sem `utc_offset_min`, usa -180 como antes; agentes < 1.1.34 seguem funcionando (e passam a ter a lista de câmeras preservada no ERRO). **Atenção:** webhook do Defense só local (item 15). **Requer:** deploy do servidor e a versão 1.1.34 do agente (build, release e cadastro no painel, fora desta entrega).
**Branch:** claude/auditoria-agente-1.1.34

### [2026-10-29] — Agente 1.1.33: merge com a Helena (Intelbras Defense IA via API REST)

**Incorporado (commit `42271ff` do ramo `helena`):** o status e o histórico de gravações das câmeras do DEFENSE passam a vir da API REST do Defense IA (`agent/src/vms/defense.py`: login com assinatura MD5 em duas etapas, `X-Subject-Token`, árvore de câmeras e gravações dos últimos 15 dias; porta em `config_extra.porta_api`, padrão 4433), com o CSV do webhook como plano B quando a API não responde. O backup em si segue igual (copia o arquivo mais recente de `pasta_origem`; sem pasta, cai no dump MySQL). Testes novos em `agent/tests/test_defense_api.py`. No painel, o formulário do DEFENSE pede IP/host, usuário (padrão `system`), senha da API e porta (`EquipamentoFormModal.tsx`, `utils.ts`, `types.ts`); na edição, senha em branco é descartada (a salva é mantida).
**Atenção:** o usuário e a senha do equipamento DEFENSE passam a ser os da API; no modo 2 (dump MySQL, sem `pasta_origem`) o agente reaproveita esse mesmo usuário/senha como credencial do MySQL, que antes era o par fixo `defense`/`defense`. Quem usar o dump precisa de `pasta_origem` ou de ajuste.
**Auditoria:** sem alteração em compose, nginx, models, migrações, requirements, build.ps1, installer.iss ou `.env`; sem rotas de servidor (REGRA-010 não se aplica); só `datetime.now()` sem fuso (REGRA-001 ok); sem segredos (senha e IPs fictícios só nos testes). Nada foi bloqueado. Merge automático, sem conflito.
**Arquivos:** agent/src/vms/defense.py, agent/tests/test_defense_api.py, server/dashboard/src/{api/types.ts,pages/Machines/MachineDetail/utils.ts,pages/Machines/MachineDetail/components/EquipamentoFormModal.tsx}, updater.py, installer.iss, server/dashboard/package.json

**Breaking Change:** Não para DEFENSE com `pasta_origem` (a maioria); equipamentos antigos sem senha de API continuam só com o CSV. **Requer:** a versão 1.1.33 cadastrada no painel; DEFENSE novo precisa de IP, usuário e senha da API.

### [2026-10-29] — Agente 1.1.32: log do agente visível no painel, por máquina

**Alteração:** o log do agente deixa de existir só no cliente (`C:\ProgramData\Trilan NVR Backup Agent\logs\servico.log`). Um handler no logger raiz (`agent/src/application/log_remoto.py`, instalado pela thread `_logs_loop` em `service.py`) enfileira os avisos e erros (WARNING/ERROR, com traceback) e os marcos do backup (início, fim, resultado de cada equipamento, marcados com `extra={"enviar_servidor": True}`) e os envia em lote a cada 20 s para `POST /api/v1/agent/logs`. Fila local de 500 itens (servidor fora do ar não perde o recente), deduplicação de 10 min para o mesmo aviso, equipamento atribuído por contexto de thread (`equipamento_atual`) ou por `extra`. Segredos são ocultados antes do envio (senha em URL, `password=`/`senha`/`token`/`api_key`..., e a `api_key` do agente). O envio nunca chama `logging.error` (evita laço).
**Servidor:** `agent_logs` ganha `nivel` e `equipamento` (migração inline e índice `(client_id, created_at)`). Nova rota `POST /api/v1/agent/logs` (autenticada como máquina, só grava na própria máquina; o horário vem de `segundos_atras`, REGRA-005; aceita conta bloqueada). `GET /machines/{id}/logs` ganha filtros `nivel`, `q`, `equipamento` e `limit` até 500 (isolamento por conta inalterado, REGRA-010). `email_error` passa a nível `ERROR`.
**Retenção (REGRA-006 alterada, a pedido do usuário):** 30 dias por máquina e o ping não conta no limite (ping: 50 mais recentes; demais eventos: 30 dias e no máximo 5000). Antes eram 50 logs incluindo ping, e um erro sumia em ~12 min. Nova função `podar_logs` em `services/agent_logs.py`.
**Painel:** o card "Eventos do Agente" da Máquina ganha filtro por nível (todos / só erros / avisos e erros), por equipamento e busca por texto (debounce de 400 ms), badge de nível, chip do equipamento, "Ver mais" (de 100 até 500), e a linha expande para mostrar a mensagem completa com botão Copiar.
**Fora do escopo:** tela geral de erros de todas as máquinas e alerta por e-mail.
**Arquivos:** server/api/{models.py,main.py,schemas.py}, server/api/services/agent_logs.py (novo), server/api/routers/{agent.py,machines.py,backups.py}, server/api/services/backup_runs.py, server/dashboard/src/api/{client.ts,types.ts}, server/dashboard/src/pages/Machines/MachineDetail/{index.tsx,components/AgentLogs.tsx}, agent/src/application/{log_remoto.py (novo),api_client.py,backup_job.py,presenca_cameras.py}, agent/service.py, updater.py, installer.iss, server/dashboard/package.json, PROJECT_SPEC.md

**Breaking Change:** Não (colunas novas com padrão; agentes antigos continuam funcionando, só não enviam log). **Requer:** deploy do servidor/painel e a versão 1.1.32 do agente cadastrada no painel para os logs começarem a chegar.

### [2026-10-29] — Agente 1.1.31: tempo que cada câmera está offline ("offline há 3h", "offline há 5 dias")

**Alteração:** o agente passa a avisar o servidor, a cada 5 minutos, se cada câmera está online ou offline (`agent/src/application/presenca_cameras.py`, thread `_presenca_loop` em `service.py`, `send_presenca_cameras` em `api_client.py`). NVR (Hikvision/Intelbras/Motorola): `buscar_cameras`, só câmeras com estado conhecido; NVR inacessível não é reportado (estado desconhecido não é offline). DIGIFORT: lê `_ultimo_status_cameras` (ping ICMP a cada 60 s). DEFENSE: CSV do webhook. Pula o ciclo com backup em andamento; espera inicial de 90 s.
**Servidor:** nova rota `POST /api/v1/agent/cameras/status` (autenticada como máquina; só toca equipamentos DA máquina; 403 com conta bloqueada; limites de 200 equipamentos e 1000 câmeras no schema). Novo `services/camera_offline.py`: guarda `offline_desde` (UTC naive, `AAAA-MM-DDTHH:MM:SS`) e `offline_desde_aprox` por câmera dentro de `nvr.last_recording_status` (sem coluna nova); a marca nasce na queda, some ao voltar ONLINE e é mantida em estado incerto. Câmera que já estava offline sem marca (dado anterior) ganha `offline_desde` = agora − 1 dia com `offline_desde_aprox` (aparece como "há mais de 1 dia" e segue contando). O relatório de backup (`receive_backup_report`) aplica a mesma lógica e leva `offline_desde` para o `nvr_results` do e-mail. Efeito colateral útil: `status_comunicacao` e os contadores online/offline do widget passam a atualizar a cada ~5 min, não só no backup diário.
**Onde aparece (só nas offline):** widget Câmeras do dashboard (`offline_segundos`/`offline_aprox` em `construir_cameras`, vale no link público), galeria de câmeras do NVR (`NVRCameraResponse`) e linha da câmera offline no e-mail ("— offline há 3h"). Texto idêntico em `formatar_offline_ha` (Python) e `fmtOfflineHa` (`utils/date.ts`): `há 40 min`, `há 3h`, `há 5 dias`, `há mais de 1 dia`.
**Atenção:** o NVR Motorola faz login a cada 5 minutos para ler o estado das câmeras (o backup já faz isso uma vez por dia); observar se o equipamento aceita. A versão do agente precisa ser cadastrada no painel para chegar às máquinas.
**Arquivos:** server/api/services/camera_offline.py (novo), schemas.py, routers/agent.py, routers/equipamentos.py, services/dashboards/widgets.py, services/email_service.py, server/dashboard/src/utils/date.ts, pages/Dashboards/types.ts, pages/Dashboards/widgets/CamerasWidget.tsx, api/types.ts, pages/Machines/MachineDetail/components/NVRCamerasGalleryModal.tsx, agent/src/application/presenca_cameras.py (novo), api_client.py, service.py, updater.py, installer.iss, server/dashboard/package.json, PROJECT_SPEC.md

**Breaking Change:** Não. **Requer:** deploy do servidor/painel e nova versão do agente (1.1.31) cadastrada para o tempo ficar em horas; sem ela o tempo só avança a cada backup diário.

### [2026-10-29] — Imagens de referência das câmeras também em arquivo, na pasta de backup do Cliente

**Alteração:** a imagem de referência (`nvr_cameras.perfect_image_base64`) passa a ser gravada também em arquivo, FORA da pasta das máquinas: `BACKUP_STORAGE_PATH/<CLIENTE>_<uuid>/imagens das câmeras/<MÁQUINA>/<NVR>/<CÂMERA>.jpg` (Máquina sem Cliente: `_sem_cliente/imagens das câmeras/...`). Nomes legíveis, sem UUID (`_nome_legivel` mantém espaços e acentos); duas câmeras com o mesmo nome no NVR viram `<nome> (canal N)`; extensão pela assinatura dos bytes (`.jpg`, `.png`, `.webp`).
**Regras:** só a referência vai para arquivo (a imagem da noite não); o banco continua com o base64, então e-mail de câmera offline, galeria e API não mudam. Na subida do servidor, `sincronizar_imagens_existentes` grava as imagens que já estão no banco (em segundo plano, em lotes, sem regravar arquivo idêntico). Gravação atômica (`.part` + `replace`).
**Acompanham renomeação/troca:** renomear a Máquina, o NVR ou a câmera move a pasta/arquivo; vincular/desvincular a Máquina de um Cliente e excluir o Cliente movem a pasta de imagens da Máquina para a pasta do novo Cliente (ou `_sem_cliente`); excluir a Máquina move as imagens para `lixeira/imagens das câmeras/`. Excluir câmera ou NVR NÃO apaga os arquivos (ficam como cópia de backup). Renomear o Cliente já renomeia a pasta inteira.
**Limites conhecidos:** a câmera de NVR comum renomeada só pelo relatório do agente (`routers/agent.py`) reflete o nome novo no arquivo na próxima gravação da referência ou na próxima subida do servidor; a sincronização do OneDrive (`robocopy /XO`) não apaga na nuvem o que foi renomeado aqui.
**Arquivos:** server/api/services/storage_service.py, main.py, routers/equipamentos.py, routers/machines.py, routers/customers.py, PROJECT_SPEC.md

**Breaking Change:** Não. **Requer:** só o deploy do servidor (sem nova versão do agente nem do painel).

### [2026-10-27] — Infraestrutura: limpeza, Samba e sincronização dos backups com o OneDrive (registro, sem código)

**Tipo:** operação de infraestrutura feita fora do repositório (servidor Linux do Dokploy e máquinas Windows); registrada aqui para referência. Nenhum arquivo de código foi alterado.

- **Limpeza:** 7 pastas órfãs de teste (`Teste_*`, UUIDs sem registro em `clients`) removidas de `/opt/trilan/backups` (bind-mount de `/data/backups` da API), com confirmação do usuário; as pastas dos clientes reais foram mantidas.
- **Samba:** a seção `[backups]` do `/etc/samba/smb.conf` passou a usar `force user = root`, `force group = root`, `create mask = 0777` e `directory mask = 0777`, e a pasta recebeu `chmod -R 777`. Causa: a API roda como `root` no container e grava `root:root` (755), o que impedia o usuário `trilan` do compartilhamento de apagar pelo Windows. Backup do arquivo original em `smb.conf.bak`.
- **OneDrive:** o `rclone` direto no Linux foi descartado (o Entra ID da Trilan exige consentimento de administrador para apps de terceiros); foi revertido por completo. A sincronização roda no Windows: tarefa agendada `Trilan_Sync_Backups_OneDrive` (de hora em hora) executa `C:\TrilanSync\sync_backups_onedrive.ps1`, que copia `\\<servidor>\backups` com `robocopy /E /XO /R:3 /W:5` para a pasta `Arquivos de Admin - Backups Clientes` do OneDrive da Trilan; o cliente oficial do OneDrive envia para a nuvem. Carga inicial: 447 arquivos, 4,835 GB, 0 falhas.
- **Servidor Windows 24h:** o erro 1219 do `net use` (conexão anterior ao mesmo IP com outro usuário) foi resolvido com `net use * /delete /y` antes de reconectar.
- **Pendências conhecidas (decisão do dono: manter como está):** os scripts `sync_backups_onedrive.ps1` e `instalar_no_outro_servidor.ps1` citados no relatório não estão em `tools/` do repositório; a credencial do compartilhamento aparece em texto puro nesses scripts; o Samba com `force user = root` e `777` dá escrita total a quem autentica. O relatório completo (`RELATORIO_SINCRONIZACAO_BACKUPS.md`) fica só na máquina local, fora do git, por conter essa credencial e o repositório ser espelhado em um público.

**Breaking Change:** Não. **Requer:** nada no código; nova build do agente não é necessária.

### [2026-10-29] — Merge auditado do ramo `helena` (4198296) e agente 1.1.30

**Tipo:** merge real (`git merge --no-ff`), com 3 conflitos de texto resolvidos mantendo os dois lados; auditado pelo checklist do CLAUDE.md.

**Incorporado:** leitura de gravações do Digifort pelos índices `.dix` (`agent/src/vms/digifort_gravacoes.py`, mapa com `▒` e `·`), monitoramento por ping ICMP, status das câmeras em qualquer desfecho do backup, planilha das câmeras obrigatória no formulário do Digifort, coluna "Pasta de gravação" no modal de Gravação e `▒` como "gravou hoje" no e-mail (detalhes nas entradas da Helena abaixo).
**Conflitos:** `PROJECT_SPEC.md` (entradas dos dois lados mantidas), `types.ts` (`dias_gravados` e `pasta_gravacao` juntos) e `RecordingModal.tsx` (coluna "Pasta de gravação" + "Dias gravados" reais da 1.1.29; o Digifort, sem `dias_gravados`, continua com `N/15`).

**Verificado e sem problema:** nenhuma rota nova (REGRA-010 não afetada), nenhum `compose`/`nginx`/`models`/migração/`requirements`/`.env`/binário alterado, nenhum segredo; os únicos `datetime.now()` são naive e só do agente (REGRA-001).

**Breaking Change:** Não. **Requer:** nova build do agente (1.1.30 em `updater.py`, `installer.iss` e `package.json`).
**Branch:** isaque

---

### [2026-10-29] — Digifort: o status das câmeras e a gravação saem em qualquer desfecho do backup

**Alteração:** o bloco que calcula o status das câmeras do Digifort (ping, tempo de gravação pelos índices e pasta usada) ficava dentro do caminho "backup da configuração copiado agora" de `FileManager.process_equipment`. Quando o backup era `BACKUP_ANTIGO`, `JA_PROCESSADO` ou `NAO_ENCONTRADO` (o normal em testes repetidos e sempre que o Digifort não gerou backup novo no dia), o resultado voltava com `cameras: None`; o agente envia `r.get("cameras") or []` e o servidor, ao receber lista vazia, **substituía o `last_recording_status`** e o modal de Gravação ficava sem dados (relato: "após o backup o campo de gravações não aparece"; no log de 29/10 10:02 o desfecho foi `BACKUP_ANTIGO`). Agora `process_equipment` é um invólucro: roda `_processar_backup` (o fluxo de antes) e, se o equipamento é DIGIFORT e `cameras` veio vazio, chama o novo `_status_cameras_digifort` (o bloco extraído, sem mudança de regra). A imagem da noite via RTSP continua só no backup novo (`capturar_imagens=False` no invólucro: capturar todas as câmeras a cada execução seria pesado), e o `quedas_cameras.csv` é copiado para a pasta do equipamento nos dois casos. O status do backup (`BACKUP_ANTIGO` etc.) não muda. Para a pasta de gravações vale o que está na entrada anterior: raiz com uma subpasta por câmera (cada uma com `Dados` e `Indices`) ou pasta de uma câmera só, que leva o nome da pasta; um exemplo de configuração errada é apontar para uma pasta acima da raiz, que vira "uma câmera" com o nome da própria pasta. **Validação:** 3 testes novos (backup antigo, backup não encontrado e outros tipos sem câmeras) e reprodução com a configuração real (`C:\dbbackup` com backup de 27/10 e raiz `...\OneDrive - Trilan\Cliente`): status `BACKUP_ANTIGO`, câmera "Cliente" `ONLINE`, `COM_GRAVACAO`, pasta `Cliente`. O agente instalado precisa ser reiniciado para carregar o código novo. **Arquivos:** agent/src/backup/file_manager/manager.py, agent/tests/test_digifort_gravacoes.py, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** helena

### [2026-10-29] — Digifort: formulário com a planilha das câmeras (obrigatória) e pasta usada por câmera no relatório

**Alteração:** o formulário de equipamento DIGIFORT (`EquipamentoFormModal`) fica com **Local de backup do Digifort** (obrigatório), **Local de gravação das câmeras** (opcional; sem ele o agente só usa o ping) e **Planilha das câmeras** (obrigatória), no formato e com a prévia da Galeria. Os campos de CSV e de LOG já tinham saído do formulário (valores antigos continuam no `config_extra` e são reenviados ao salvar). **Planilha:** novo `PlanilhaCamerasCampo` lê o CSV/XLSX com o mesmo parser da Galeria (`useCameraImport`: Nome ou Descrição, senhas ocultas na prévia), mostra a prévia (`PlanilhaVmsModal`, em portal; o `Esc` fecha só a prévia) e guarda o resultado em `EqForm.planilhaNova`. Ao salvar, `handleSaveEquipamento` cria/atualiza o equipamento e só então chama `enviarPlanilhaVms` (novo `planilhaVms.ts`): `POST /equipamentos/{id}/cameras/import` e `PUT /equipamentos/{id}/planilha`, os mesmos endpoints da Galeria; se a importação falhar, o equipamento fica salvo e o aviso manda importar pela Galeria. Ao editar, o campo consulta a Galeria (`GET cameras` e `GET planilha`): equipamento que já tem câmeras ou planilha guardada cumpre a exigência sem novo envio (`EqForm.planilhaSalva`), e "Trocar planilha" reimporta (câmeras de mesmo nome ou IP são atualizadas). `buildEqPayload` recusa DIGIFORT sem planilha nova nem salva. **Associação câmera × pasta:** continua automática pelo nome normalizado (a planilha dá os nomes). O relatório do agente passa a trazer `pasta_gravacao` em cada câmera DIGIFORT quando a pasta de gravações está configurada (nome da pasta usada, ou `null` = nenhuma pasta com o nome da câmera; ausente quando não configurada). O servidor guarda o relatório como está (`cameras: List[Dict]`), sem mudança; o modal de **Gravação** mostra a coluna "Pasta de gravação" (e "Sem pasta" em destaque) só quando o agente informa o campo. **Validação:** 26 verificações do painel em Node (renderização do formulário e do modal, validação, leitura de CSV no formato Digifort, envio à Galeria com a API simulada), `tsc --noEmit` e `vite build`; 29 testes do agente. Não testado em navegador: interação real (escolher arquivo, prévia sobre o formulário, salvar contra a API). **Arquivos:** server/dashboard/src/api/types.ts, server/dashboard/src/pages/Machines/MachineDetail/{index.tsx, utils.ts, planilhaVms.ts, components/EquipamentoFormModal.tsx, components/PlanilhaCamerasCampo.tsx, components/RecordingModal.tsx}, agent/src/backup/file_manager/manager.py, agent/tests/test_digifort_gravacoes.py, PROJECT_SPEC.md
**Breaking Change:** Não. Campo novo e opcional no relatório do agente; agentes antigos não o enviam e o painel esconde a coluna.
**Branch:** helena

### [2026-10-29] — Digifort: tempo de gravação real pelos arquivos de índice (`.dix`)

**Alteração:** o mapa de 15 dias, os dias com gravação e o `status_gravacao` das câmeras DIGIFORT deixam de ser deduzidos do ping (câmera respondendo = 15 de 15 dias gravados) e passam a sair dos arquivos que o Digifort grava. Novo `agent/src/vms/digifort_gravacoes.py`. **Formato (observado em 25 arquivos reais, de 3 câmeras):** `<raiz>/<câmera>/Dados/AAAAMMDD_NN.dar` e `Indices/AAAAMMDD_NN.dix`; `NN` é a meia hora do dia de 1 a 48 (1 = 00:00–00:30); o `.dix` tem cabeçalho de 26 bytes (`DGFDB2…`) e um registro de 69 bytes por quadro: marcador `-REG-`, data (double, TDateTime do Delphi), hora (double, fração do dia), hash de 32 caracteres e 16 bytes de posição no `.dar`; os horários são locais. Também é aceita a pasta de uma câmera só (com `Dados` e `Indices` direto; o nome da câmera é o da pasta). **Cálculo:** tempo gravado do dia = soma dos trechos em que um quadro segue o outro em até 30 s; salto maior é interrupção (exemplo real: 389 s sem gravar em `20261028_18`). A leitura amostra 1 registro a cada 600 e só varre tudo onde há salto entre amostras (os horários são crescentes, então o resultado é idêntico ao da leitura completa: conferido nos 16 índices dos exemplos e da pasta ao vivo). Cache por arquivo (nome, tamanho e data de modificação) em `cache_gravacoes_digifort_<hash>.json` na pasta do agente: dias fechados não são relidos; limite de 900 s por execução (o que sobra continua na próxima, e a câmera incompleta sai como `NAO_VERIFICADO`, nunca como "sem gravação"). **Regra do dia (decisão do dono):** qualquer tempo gravado = dia gravado; abaixo de 90% do dia = parcial (hoje é medido contra o tempo já decorrido desde a meia-noite). **Mapa de 15 dias:** `█` gravou, `▒` parcial, `░` não gravou, `·` sem histórico (dia anterior à primeira gravação encontrada: retenção ou câmera nova; evita falsa falha). `total_dias` = dias com gravação; `status_gravacao` = `COM_GRAVACAO` se hoje teve gravação, senão `SEM_GRAVACAO`; câmera sem pasta correspondente ou leitura incompleta = `NAO_VERIFICADO`. **Casamento câmera × pasta:** pelo nome normalizado (sem acento, pontuação e caixa) e, se não houver, ignorando também os espaços quando só uma pasta combina (`One Drive - Trilan` = `OneDrive - Trilan`, caso real de 29/10), contra o nome da câmera da Galeria (planilha importada, Nome ou Descrição conforme a escolha na importação). **Config:** `config_extra.pasta_gravacoes` (nova); o formulário do Digifort passa a ter só "Local de backup do Digifort" (`pasta_origem`) e "Local de gravação das câmeras" (opcional: sem ela o agente mantém o comportamento anterior, só ping); os campos de CSV e de LOG saíram do formulário, mas valores já salvos continuam no `config_extra` e funcionando. Sem CSV, o monitor de ping (`start_webhook`) usa as câmeras da Galeria (`cameras_config`) para o histórico de quedas; câmeras novas na Galeria só entram nesse histórico após reiniciar o agente (o status do backup já considera todas). **Painel/e-mail:** `MiniCalendar` mostra `▒` em amarelo e `·` em cinza, e `RecordingModal` e `email_service` (fallback de agentes antigos) tratam `▒` como "gravou hoje". Nesta primeira etapa não havia campo novo na API nem tela nova; o `pasta_gravacao` e a planilha obrigatória no formulário vieram na entrada seguinte. **Ajuste de robustez:** `ping_camera` lê a saída do `ping` com `errors="replace"` (no Windows pt-BR ela sai em CP850; em Python com modo UTF-8 a decodificação falhava e a câmera aparecia offline). **Validação:** 23 testes novos (`agent/tests/test_digifort_gravacoes.py`, com índices sintéticos no formato real e os arquivos de exemplo) e os 6 do ping passam; câmera 192.168.75.45 (nome "Cliente") respondendo ao ping e gravando ao vivo (08:21:52 até a hora do teste, sem lacunas, 57,7 min no dia, hoje `▒` por estar medido desde a meia-noite). Não testado: Digifort com `Dados`/`Indices` em rede (UNC) ou OneDrive sob demanda, e dias com mais de 15 de retenção. Versão do agente não alterada.
**Arquivos:** agent/src/vms/digifort_gravacoes.py, agent/src/backup/file_manager/manager.py, agent/src/application/webhook_digifort.py, agent/service.py, agent/tests/test_digifort_gravacoes.py, server/dashboard/src/api/types.ts, server/dashboard/src/pages/Machines/MachineDetail/{utils.ts, components/EquipamentoFormModal.tsx, components/MiniCalendar.tsx, components/RecordingModal.tsx}, server/api/services/email_service.py, PROJECT_SPEC.md
**Breaking Change:** Não. `pasta_gravacoes` é opcional; sem ela nada muda. O mapa ganha dois caracteres novos (`▒`, `·`); o painel e o e-mail desta versão os entendem, e um painel antigo mostraria esses dias como "Falhou".
**Branch:** helena

### [2026-10-29] — Administrador da plataforma deixa de ver as contas misturadas

**Problema:** o login só com senha (SUPER_ADMIN) sem `X-Conta-ID` tinha `conta_id = None`, que `filtrar_por_conta` trata como "ver tudo". O setor criado numa conta de Cliente final aparecia na tela do administrador misturado com os Clientes dos integradores, com o rótulo padrão "Cliente". Não era vazamento entre contas de usuário (o teste de isolamento já cobria), e sim a visão global do super admin.
**Alteração (decisão do usuário):** o super admin sem `X-Conta-ID` passa a ficar na **conta da plataforma** (Trilan): `_montar_contexto` em `auth.py` carrega essa conta quando não há header. Para ver outra conta ele a escolhe no seletor (`X-Conta-ID`) e o painel usa os rótulos dela ("Setor" na CLIENTE_FINAL). Não existe mais visão "todas as contas"; se a conta da plataforma não existir, o contexto cai no comportamento antigo (`conta_id` None) como último recurso. Painel: `Sidebar.tsx` sem a opção "Todas as contas"; o seletor mostra a conta atual e escolher a conta da plataforma volta ao padrão. Usuários ADMIN/LEITURA continuam presos à própria conta (REGRA-010 inalterada). Rotas só da plataforma (`verify_admin_token`/`exigir_super_admin`) não mudam.
**Teste:** `test_isolamento_contas.py` (passo 7) agora exige que o super admin sem conta NÃO veja cA nem cB, que `/auth/me` mostre a conta da plataforma, e que com `X-Conta-ID` veja só a conta escolhida (A e B).
**Verificado em Docker local:** isolamento aprovado, 27 testes unitários aprovados (as mesmas 4 falhas antigas de `test_storage`/`test_planilha_vms`), `tsc` do painel sem erro e roteiro de ponta a ponta com 23/23.
**Breaking Change:** Não para o agente nem para usuários de conta; o super admin deixa de ver as contas juntas (muda o que ele vê ao entrar).
**Arquivos:** server/api/auth.py, server/api/tests/test_isolamento_contas.py, server/dashboard/src/components/Sidebar.tsx, PROJECT_SPEC.md
**Branch:** isaque

---

### [2026-10-28] — "Dias gravados" reais por câmera (Hikvision, Motorola, Intelbras) e agente 1.1.29

**Alteração:** a janela "Gravação" mostrava `N/15` (só olhava os últimos 15 dias). Cada câmera passa a informar há quantos dias grava de verdade: dias corridos desde a gravação mais antiga até hoje, contando o primeiro dia e hoje (primeira gravação há 59 dias ⇒ 60). Buracos no meio entram na conta.
- Agente (`factory.py`): novo campo `dias_gravados` em cada item de `cameras` do relatório de NVR (`int >= 1`; `0` = consulta ok e sem gravação; `None` = não foi possível descobrir). Motorola usa a data mais antiga que `queryDatesExistRec` já devolve (sem consulta extra). Hikvision e Intelbras usam `descobrir_dias_gravados`: busca binária (≈10 consultas por câmera, em paralelo com as 15 do mapa) sobre o predicado monótono "há gravação entre o início da janela e o fim do dia X"; funciona com buracos e sem depender da ordem dos resultados do NVR. Janela máxima `DIAS_MAX_RETENCAO = 730` (valor 730 = "730 ou mais").
- Agente (`hikvision/recordings.py`, `intelbras/recordings.py`): `tem_gravacao_entre`, tri-estado (True/False/None); na Intelbras o erro nunca vira "sem gravação".
- Painel (`RecordingModal.tsx`, `types.ts`): célula `Dias gravados: 60` (`730+` no limite; `—` quando o agente não conseguiu). Relatório antigo e Digifort/Defense continuam com `N/15`. Sem legenda (decisão do usuário).
- Servidor: sem mudança (`last_recording_status` é JSON e repassa o campo).
**Fora desta entrega (decisão do usuário):** e-mail de relatório, widgets do Dashboard, Digifort/Defense.
**Ponto de atenção:** a busca de 730 dias nunca foi exercitada em equipamento real nesta entrega; se algum firmware recusar intervalo tão largo, o campo vem `null` e o painel mostra `—` (o mapa de 15 dias não é afetado).
**Breaking Change:** Não. **Requer:** nova build do agente (1.1.29 em `updater.py`, `installer.iss` e `package.json`).
**Arquivos:** agent/src/nvr/factory.py, agent/src/nvr/hikvision/recordings.py, agent/src/nvr/intelbras/recordings.py, server/dashboard/src/api/types.ts, server/dashboard/src/pages/Machines/MachineDetail/components/RecordingModal.tsx, PROJECT_SPEC.md
**Branch:** isaque

---

### [2026-10-28] — Merge auditado do ramo `helena` (e841429) e agente 1.1.28

**Tipo:** merge real (`git merge --no-ff`), sem conflitos; auditado pelo checklist do CLAUDE.md.

**Incorporado:**
- Agente (`webhook_digifort.py`): leitura do SNMP do Digifort reescrita — extração de textos da trap por ASN.1 (OCTET STRING) e varredura ampla, detecção de falha/restauração por OID e por palavras-chave, `SO_REUSEADDR` no soquete da porta 162, mensagem de erro com a causa provável quando a porta está ocupada e o nome da câmera tirado direto da trap quando não está na planilha; `start_webhook` não sobrescreve o CSV de log com valor vazio.
- Agente (`manager.py`): câmeras só configuradas no servidor (fora do export local) entram também no status e no mapa de gravação do Digifort.
- Servidor: `nvrs.ip` e `nvr_cameras.ip` passam a `VARCHAR(255)` (modelo + `ALTER COLUMN` idempotente no `main.py`, mesmo padrão `_run_ddl` da REGRA-007).
- Painel: para DIGIFORT e OLT UNM2000 o `ip` do equipamento grava `127.0.0.1` e a pasta fica só em `config_extra.pasta_origem`; cadastros antigos (pasta no `ip`) continuam abrindo no formulário.

**Verificado e sem problema:** nenhuma rota nova (REGRA-010 não afetada), nenhum `compose`/`nginx`/`requirements`/`.env`/binário alterado, nenhum segredo, nenhum fuso horário (o único `datetime.now` é naive e só alimenta uma linha de log, REGRA-001).

**Ponto de atenção (não bloqueado):** no sniffer SNMP, quando a câmera não é achada na planilha, qualquer texto da trap que não seja palavra reservada vira "nome de câmera" e gera um evento; um pacote UDP estranho na porta 162 pode registrar um nome lixo. Revisar se aparecerem eventos de câmeras inexistentes.

**Breaking Change:** Não. **Requer:** nova build do agente (versão 1.1.28 em `updater.py`, `installer.iss` e `package.json`).
**Branch:** isaque

---

### [2026-10-27] — Multi-contas (etapa 5): telas de Contas, Planos e Minha conta

**Alteração:** super admin ganha a tela "Contas" (`/contas`: lista com busca e filtros por situação e tipo, resumo, criação da conta com o primeiro administrador, modal de Planos e seção de administradores da plataforma) e o detalhe da conta (`/contas/:id`: renovar com prévia da nova validade, ajustar a validade à mão até o fim do dia escolhido em Brasília, suspender/reativar, usuários da conta e histórico de validade, "Entrar na conta"). Todos os usuários têm "Minha conta" (`/minha-conta`: plano, validade, histórico, usuários para o ADMIN e troca da própria senha). No detalhe do Cliente/Setor, o super admin pode movê-lo (com as máquinas) para outra conta. Menu: "Minha conta" para todos e seção "Plataforma" (Contas, Configurações) para o super admin. Revisão: o campo de validade passou a mostrar o dia local (`diaLocalDaValidade`), igual ao cartão; antes usava o dia em UTC e podia aparecer um dia depois. Validado no ambiente local: tsc, `vite build` e 23 verificações de ponta a ponta pela API (criar conta, renovar 30 + 365 = 395 dias, login do cliente com "Setores", usuário LEITURA, último admin protegido, suspender/reativar, ajuste para data passada = VENCIDA, conta da plataforma protegida).
**Arquivos:** server/dashboard/src/{App.tsx,components/Sidebar.tsx,pages/Contas/{ContasPage,ContaDetalhePage,ContaFormModal,PlanosModal,UsuariosSection,HistoricoValidade,contaUi}.tsx,pages/MinhaConta.tsx,pages/Customers/CustomerDetail/index.tsx,pages/Customers/CustomerDetail/components/CustomerHeader.tsx}, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-27] — Multi-contas (etapa 6): documentação, regra de isolamento e skills

**Alteração:** ADR-009 (multi-contas: tipos de conta, validade, bloqueio da conta vencida, conta da plataforma, fora do escopo), REGRA-010 (isolamento por conta nas rotas do painel), REGRA-003 atualizada (login por usuário com bcrypt e papéis; senha única do administrador da plataforma mantida), seção 7 (fluxo de login e `X-Conta-ID`) e seção 8 (rotas novas; rotas só da plataforma marcadas). Skills e subagentes do Claude e do Gemini passam a ensinar `get_contexto` + `services/escopo.py` no lugar de `verify_admin_token` (`criar-endpoint-fastapi` nas duas cópias, `revisao-de-codigo`, `seguranca-e-endurecimento`, `revisor`, `backend-fastapi`); o revisor trata violação da REGRA-010 como crítica. CLAUDE.md: checagem de isolamento no merge de ramos de colaboradores.
**Arquivos:** PROJECT_SPEC.md, CLAUDE.md, .claude/skills/criar-endpoint-fastapi/SKILL.md, .agents/skills/{criar-endpoint-fastapi,revisao-de-codigo,seguranca-e-endurecimento}/SKILL.md, .agents/agents/{revisor,backend-fastapi}/agent.md
**Breaking Change:** Não (só documentação e instruções).
**Branch:** isaque

### [2026-10-27] — Multi-contas (etapa 4b): rótulo Cliente/Setor nas telas e modo somente leitura

**Alteração:** as telas de Clientes, Máquinas, Backups, Visão Geral e Dashboard usam o rótulo da conta (`useRotulos`): "Setor/Setores" na conta de cliente final e "Cliente/Clientes" no integrador e no super admin sem conta escolhida (rotas, nomes de campos e o dashboard público não mudam). Com conta vencida/suspensa ou usuário LEITURA (`useSomenteLeitura`), ficam ocultos: criar/excluir Cliente/Setor e Máquina, editar, backup em fila, parar fila, adicionar/remover máquina da fila e arrastar a ordem, editar máquina, girar chave, gerar backup, reiniciar agente, adicionar/editar/pausar/remover equipamento, editar o dashboard e o compartilhamento. Downloads, galeria, gravações, telemetria e consultas continuam. O servidor já recusa a escrita com 403. No compartilhamento do dashboard, "o cliente" virou "quem recebe o link".
**Arquivos:** server/dashboard/src/pages/{Customers/CustomersPage.tsx,Customers/components/CustomerFormModal.tsx,Customers/CustomerDetail/index.tsx,Customers/CustomerDetail/components/{AddMachineModal,CustomerHeader,CustomerRuns,QueueSection}.tsx,Machines/MachinesPage.tsx,Machines/components/NewMachineModal.tsx,Machines/MachineDetail/index.tsx,Machines/MachineDetail/components/{EditMachineModal,EqCard,MachineHeader,MachineInfoCards}.tsx,Backups.tsx,Overview/{index,MachineHealthCard}.tsx,Dashboards/{DashboardAdminPage,WidgetConfigModal,SharePanel}.tsx}, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-27] — Multi-contas (etapa 4a): painel com login por e-mail, faixa de vencimento e seletor de conta

**Alteração:** login por e-mail e senha (o administrador da plataforma entra pelo botão "Entrar como administrador da plataforma", só com a senha). O painel carrega `GET /auth/me` (recarrega a cada 10 min e ao voltar à aba) e mostra no topo a faixa da validade (amarela a partir de 15 dias, vermelha a partir de 3 dias, vermelha fixa quando vencida/suspensa com aviso de somente leitura) e, para usuário LEITURA, "Seu acesso é somente leitura". O super admin escolhe a conta no menu lateral (enviada em `X-Conta-ID`, guardada em `localStorage`; uma requisição que já traga o header não é sobrescrita); "Configurações" só aparece para ele. O item do menu vira "Setores" em conta de cliente final.
**Arquivos:** server/dashboard/src/{App.tsx,api/types.ts,api/client.ts,api/contas.ts,contexts/AuthContext.tsx,utils/date.ts,pages/Login.tsx,components/AvisoConta.tsx,components/Layout.tsx,components/Sidebar.tsx}, PROJECT_SPEC.md
**Breaking Change:** Não (a tela de login muda: a senha única fica no botão "Entrar como administrador da plataforma").
**Branch:** isaque

### [2026-10-27] — Multi-contas (etapa 3): avisos de vencimento por e-mail e testes de isolamento

**Alteração:** tarefa de fundo de hora em hora (`main.py`, `services/avisos_conta.py`) envia e-mail ao contato e aos administradores da conta a 7, 3 e 1 dia do vencimento e no dia em que vence (marcos gravados em `contas.avisos_enviados`, zerados ao renovar; só o marco mais urgente é enviado; SMTP fora do ar tenta de novo na hora seguinte). Testes: `test_avisos_conta.py` (marcos) e `test_isolamento_contas.py` (integração contra o PostgreSQL local, só com `TRILAN_TESTE_ISOLAMENTO=1` e `httpx` no container de teste). Executado em 27/10/2026 no ambiente local: isolamento 10/10 aprovado (conta A não vê nem vincula dados da B, LEITURA e conta vencida recebem 403, super admin filtra por `X-Conta-ID`, agente da conta vencida recebe config vazia e 403 no relatório, troca de senha derruba o token antigo). Rodar o de integração num processo separado dos testes unitários (estes trocam `DATABASE_URL` para SQLite ao serem importados). Os 4 testes que falham em `test_storage.py`/`test_planilha_vms.py` já falhavam antes do multi-contas (mesmo resultado no commit `688b9ed`; a do `test_planilha_vms.py` é a chave Fernet de teste com 31 bytes).
**Arquivos:** server/api/main.py, server/api/services/avisos_conta.py, server/api/tests/{test_avisos_conta.py,test_isolamento_contas.py}, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-27] — Multi-contas (etapa 2b): isolamento por conta e bloqueio da conta vencida

**Alteração:** as rotas do painel (Clientes, Máquinas, Equipamentos, Backups, Dashboards e `/stats`) recebem o `Contexto` e só enxergam a conta do usuário (helpers em `services/escopo.py`; recurso de outra conta = 404; super admin sem `X-Conta-ID` vê tudo e cria na conta da plataforma). Vincular máquina a Cliente de outra conta → 409. Conta vencida/suspensa: `/agent/config` devolve a lista de equipamentos vazia (o agente encerra o backup sem erro de rede), o ping não dispara backup nem recuperação, `report`/upload respondem 403 e o link público do dashboard responde 404. `conta_id` passa a NOT NULL em `client_groups` e `clients` depois do backfill. Contrato do agente sem mudança.
**Arquivos:** server/api/{main.py,models.py}, server/api/routers/{customers.py,machines.py,equipamentos.py,backups.py,dashboards.py,agent.py}, server/api/services/{escopo.py,contas.py}, server/api/services/dashboards/compartilhamento.py, PROJECT_SPEC.md
**Breaking Change:** Não para o agente nem para o super admin; usuários de conta só veem a própria conta.
**Branch:** isaque

### [2026-10-27] — Multi-contas (etapa 2a): login por usuário e rotas de contas

**Alteração:** login por e-mail e senha (bcrypt, `services/senhas.py`) com papéis SUPER_ADMIN, ADMIN e LEITURA; o login só com senha continua sendo o administrador da plataforma (JWT `sub=admin`). Dependência `get_contexto` (`auth.py`) com a conta do usuário, `X-Conta-ID` para o super admin escolher a conta e bloqueio de escrita (403) para conta vencida/suspensa ou usuário LEITURA. `verify_admin_token` passa a aceitar só o super admin até as rotas serem isoladas por conta (etapa 2b). Rotas novas: `GET /auth/me`, `POST /auth/trocar-senha`, `/admin/planos`, `/admin/contas` (criar, editar, renovar, suspender, reativar), `/admin/clientes/{id}/mover-conta`, `/admin/super-admins`, `/conta` e `/conta/usuarios`. Limite de 10 tentativas de login erradas por IP em 5 min (429). `bcrypt==4.2.1` nas dependências.
**Arquivos:** server/api/{auth.py,schemas.py,main.py,requirements.txt}, server/api/routers/{auth_router.py,contas_admin.py,conta.py}, server/api/services/{senhas.py,contas.py}, PROJECT_SPEC.md
**Breaking Change:** Não (login só com senha mantido).
**Branch:** isaque

### [2026-10-27] — Multi-contas (etapa 1): banco de contas, planos e usuários

**Alteração:** primeira etapa do multi-contas (Integradores com Clientes e Clientes finais com Setores, cada conta com plano e validade). Novas tabelas `planos`, `contas`, `conta_renovacoes` e `usuarios`; colunas `conta_id` (nullable, com índice) em `client_groups` e `clients`. No startup: semente dos planos (Teste 15, Mensal 30, Trimestral 90, Semestral 180, Anual 365, só com a tabela vazia), conta da plataforma "Trilan" (INTEGRADOR, sem validade, id em `settings.conta_plataforma_id`) e backfill de `conta_id` dos Clientes e Máquinas sem conta (a Máquina herda a do Cliente). Regras de validade em `services/contas.py` (`status_da_conta`: OK, AVISO ≤ 15 dias, CRITICO ≤ 3, VENCIDA, SUSPENSA, VITALICIA). Nenhuma rota ou tela muda nesta etapa.
**Arquivos:** server/api/models.py, server/api/main.py, server/api/services/contas.py, server/api/tests/test_contas_status.py, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-27] — Merge do ramo `helena` em `isaque` (auditado)

**Alteração:** incorporados 3 commits de `helena` (`d0e682e`, `236459c`, `004a025`): planilha do Defense carrega só dispositivos que são câmeras, modal de importação de câmeras com escolha Nome/Descrição (Digifort, Teste RTSP e Galeria) e colunas de usuário/senha de câmera nas planilhas dos NVR Motorola, Hikvision e Intelbras (entradas abaixo). Auditoria: sem arquivos sensíveis (compose, nginx, models, main, requirements, build, installer), sem `datetime.now`/`timezone` nas linhas adicionadas, sem segredos (`_SEM_SENHA` é só texto de substituição). Conflitos em `PROJECT_SPEC.md` e `MachineDetail/index.tsx` (agrupamento por tipo de `isaque` com o `useCameraImport` ampliado de `helena`) resolvidos mantendo as duas versões. Nada bloqueado. Atenção: as planilhas dos NVR agora levam o usuário (e, na Motorola, a senha em texto puro) das câmeras; a planilha vai na pasta do pacote final, que o agente compacta em zip AES com a senha da máquina; se a máquina estiver sem senha de zip, o zip sai sem proteção (`archiver.criar_zip`) e essas credenciais ficam legíveis.
**Arquivos:** PROJECT_SPEC.md, server/dashboard/src/pages/Machines/MachineDetail/index.tsx (resolução), agent/src/nvr/{motorola,hikvision,intelbras}/planilha.py, ImportCamerasModal.tsx, PlanilhaVmsModal.tsx, NVRCamerasGalleryModal.tsx, hooks/useCameraImport.ts
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-27] — Painel: equipamentos da Máquina agrupados por tipo

**Alteração:** na tela da Máquina, a seção "Equipamentos" deixa de ser uma fila única e passa a ser dividida por tipo (NVR/DVR, Digifort, Defense IA, OLT, ONU, Mikrotik, PABX, Misto), cada grupo com cabeçalho (ícone, nome e contagem) e os equipamentos em ordem alfabética. Ícone, cor e rótulo dos tipos foram centralizados em `components/eqTipos.tsx` (antes duplicados no `EqCard`). Só visual; sem mudança de API. Os grupos são recolhíveis (cabeçalho clicável com seta) e começam todos recolhidos ao abrir a tela; o estado fica só na memória da página.
**Arquivos:** server/dashboard/src/pages/Machines/MachineDetail/{index.tsx,components/EqCard.tsx,components/eqTipos.tsx}, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-27] — Planilhas dos NVR passam a incluir usuário e senha de cada câmera

**Alteração:** a aba **Câmeras** (e, por consequência, a **Câmeras (completo)**) de cada planilha ganhou as colunas "Usuário da câmera" e "Senha da câmera", a pedido do dono do projeto (a regra anterior descartava as duas). O que cada marca entrega: *Motorola* (`queryDevList`) devolve usuário e senha em texto puro; *Hikvision* (ISAPI `InputProxy`) devolve só o usuário, a senha aparece como `(não exposta pelo NVR)`; *Intelbras* (`RemoteDevice`) devolve o usuário e a senha mascarada (`******`), mostrada como `(mascarada pelo NVR)`. Não há tentativa de obter a senha por outro caminho. Continuam descartados usuário e senha de qualquer outro recurso (e-mail, DDNS, usuários do NVR, listas de senhas de fábrica do `queryBasicCfg`) e a senha de login do próprio NVR. Implementação: Motorola e Hikvision leem os campos direto do XML; na Intelbras o `_Dahua.obter`/`config` ganhou `com_credenciais`, usado só na leitura do `RemoteDevice`. A aba Resumo de cada planilha avisa que o arquivo contém credenciais. **Risco:** a planilha vai no ZIP global da máquina (protegido pela senha do ZIP; sem senha configurada no servidor o ZIP segue sem proteção) e sobe ao servidor, então as credenciais das câmeras passam a existir nesse pacote; tratar o arquivo como sensível. **Validação:** Motorola 192.168.124.2 (16 câmeras, usuário `admin` e senha preenchidos), Hikvision 192.168.20.2 (26, usuário) e Intelbras 192.168.75.6 (2 câmeras com IP, usuário e senha mascarada); a senha de login de cada NVR não aparece em nenhuma planilha. Versão do agente não alterada.
**Arquivos:** agent/src/nvr/motorola/planilha.py, agent/src/nvr/hikvision/planilha.py, agent/src/nvr/intelbras/planilha.py, PROJECT_SPEC.md
**Breaking Change:** Não. Duas colunas novas nas planilhas.
**Branch:** helena

### [2026-10-27] — Digifort: opção de escolha entre Nome ou Descrição na importação de planilhas (Teste RTSP e Galeria)

**Alteração:** Em planilhas exportadas pelo Digifort (que possuem colunas distintas de "Nome" e "Descrição"), o usuário agora pode escolher qual dos dois campos será registrado como o nome/identificador das câmeras no sistema. A opção foi adicionada em dois pontos de inserção:
1. **No Teste RTSP (`CamerasSection` / `useCameraImport`):** ao selecionar o CSV/XLSX, abre um modal de importação (`ImportCamerasModal`) exibindo a detecção da planilha Digifort, opção de seleção por rádio entre "Descrição" e "Nome" (com exemplos reais extraídos do arquivo), prévia das primeiras câmeras com o nome resultante atualizado em tempo real e botão de confirmação.
2. **Na Galeria de Câmeras (`NVRCamerasGalleryModal` / `PlanilhaVmsModal`):** na prévia interativa da planilha antes da importação, foi adicionado um controle para alternar entre "Descrição" e "Nome", re-renderizando instantaneamente a tabela de câmeras lidas e atualizando o pareamento de situação (nova/atualiza) antes de persistir no banco.
Todas as demais informações (IP/Endereço, Modelo/Fabricante e Senha) continuam sendo lidas e atribuídas exatamente como antes, sem qualquer alteração.
**Arquivos:** server/dashboard/src/pages/Machines/MachineDetail/hooks/useCameraImport.ts, server/dashboard/src/pages/Machines/MachineDetail/components/ImportCamerasModal.tsx, server/dashboard/src/pages/Machines/MachineDetail/components/PlanilhaVmsModal.tsx, server/dashboard/src/pages/Machines/MachineDetail/components/NVRCamerasGalleryModal.tsx, server/dashboard/src/pages/Machines/MachineDetail/index.tsx, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-26] — Digifort/Defense: captura RTSP da Galeria estourava o tempo (regressão de 21/10)

**Alteração:** Na Galeria de câmeras de equipamentos Digifort/Defense, capturas RTSP falhavam com "Tempo esgotado (5s) via UDP" (60 de 155 câmeras do Navarro falhavam). Causa: tentativas com timeout de apenas 5–6 s (insuficientes para esperar o próximo quadro-chave em streams H.265+/Smart Codec) e UDP gastando metade do limite de 4 tentativas, testando apenas 2 URLs candidatas e reportando apenas o erro da última tentativa UDP.
Solução:
- Agente (`rtsp_client.py`): removidos `-analyzeduration` e `-probesize` (retorno ao padrão do ffmpeg); timeout TCP de 18 s na URL principal e 8 s nas alternativas; fallback UDP seletivo (8 s na principal, 6 s nas alternativas) executado apenas após falhas de tempo ("Tempo esgotado") ou conexão ("Connection reset", "Connection refused", "timed out", "Invalid data found"); erros 404 e 400 não repetem em UDP; 401 continua parando na 1ª tentativa para evitar lockout; limite de até 4 URLs diferentes dentro de um prazo total de 40 s; motivo de cada tentativa acumulado na mensagem de erro (sem credenciais); no ramo genérico (Hikvision e marca incerta) a ordem das URLs passou a ser `Channels/{n}01`, `Channels/{n}02`, caminho Intelbras/Dahua (`/cam/realmonitor?channel={n}&subtype=0`), ONVIF (`/profile1`) e por último `Channels/{n}` (como só as 4 primeiras são usadas, câmera de outra marca cadastrada como Hikvision agora chega aos caminhos dela); com 404 a mensagem lista cada caminho como "Caminho RTSP não encontrado" e traz uma única dica para conferir o modelo. Versão 1.1.27 do agente (`updater.py`, `installer.iss`, `package.json`).
- Servidor (`equipamentos.py`): espera do painel em modo ao vivo no `test_equipamento_rtsp` elevada de 35 s para 55 s.
As câmeras com `Usuário ou senha RTSP recusados` (credenciais da Galeria erradas) e `Caminho RTSP não encontrado` (modelo cadastrado errado) continuam exigindo correção do cadastro; exige nova versão do agente.
**Arquivos:** agent/src/camera/rtsp_client.py, server/api/routers/equipamentos.py, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-26] — Galeria DIGIFORT/DEFENSE: prévia e guarda da planilha importada

**Alteração:** O usuário não conseguia conferir o conteúdo da planilha antes da importação nem consultá-la depois. Implementada prévia interativa com abas de câmeras lidas (situação nova/atualiza) e visualização da planilha completa antes de importar; o servidor agora armazena a última planilha importada por equipamento DIGIFORT/DEFENSE na tabela `nvr_planilhas`, com os dados integralmente criptografados via Fernet (REGRA-004). Na listagem da planilha salva, as colunas de senha vêm mascaradas por padrão e podem ser reveladas pelo admin via interruptor "Mostrar senhas". Adicionado botão "Planilha importada" na barra de ações da Galeria e rotas PUT/GET/DELETE dedicadas.
**Arquivos:** server/api/models.py, server/api/schemas.py, server/api/services/planilha_vms.py, server/api/routers/equipamentos.py, server/api/tests/test_planilha_vms.py, server/dashboard/src/api/types.ts, server/dashboard/src/pages/Machines/MachineDetail/hooks/useCameraImport.ts, server/dashboard/src/pages/Machines/MachineDetail/components/PlanilhaVmsModal.tsx, server/dashboard/src/pages/Machines/MachineDetail/components/NVRCamerasGalleryModal.tsx, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-23] — Agente 1.1.26: captura da imagem da noite respeita o canal das câmeras de IP compartilhado

**Alteração:** versão 1.1.26 do agente, que leva a correção da Galeria DIGIFORT/DEFENSE (entrada abaixo): `canal_rtsp` na captura e no envio da imagem da noite, câmera de IP compartilhado sem canal marcada com FALHA e motivo, e pareamento por IP só quando é único. Versão em `updater.py`, `installer.iss` e `package.json`. As câmeras de IP compartilhado só voltam a receber imagem da madrugada depois que o `canal_rtsp` de cada uma for preenchido na Galeria.
**Arquivos:** agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-23] — Armazenamento dos backups no servidor segue Cliente > Máquina

**Alteração:** no disco, cada máquina era uma pasta solta na raiz (`<MAQUINA>_<uuid>/`) mesmo com o painel já organizado em Cliente > Máquina. A estrutura passa a ser `BACKUP_STORAGE_PATH/<CLIENTE>_<uuid_cliente>/<MAQUINA>_<uuid_maquina>/backup_*.zip`; máquina sem Cliente em `_sem_cliente/<MAQUINA>_<uuid>/`; `lixeira/` como antes. O UUID no fim do nome é a identidade (a pasta é achada por sufixo `_<uuid>`, então renomear Cliente ou Máquina não perde arquivos). **Leitura** (`get_zip_path`, agora com `customer=`): procura a pasta canônica e depois QUALQUER pasta da máquina (raiz legada, outro Cliente, `_sem_cliente`), mantendo as estruturas legadas. **Escrita** (`save_zip_stream`, `customer=machine.customer`): usa a pasta canônica; se ela não existe mas a máquina já tem pasta (estrutura antiga), continua nela (não divide a máquina); só cria a canônica quando a máquina não tem pasta. **Movimentação:** `reorganizar_maquina` (mover/unir sem sobrescrever; conflitos são reportados) roda, em melhor esforço e sem derrubar a rota, ao adicionar/remover a máquina de um Cliente, ao excluir o Cliente (máquinas vão para `_sem_cliente` e a pasta vazia do Cliente é removida) e `renomear_pasta_do_cliente` ao renomear o Cliente. **Dados antigos:** `POST /api/v1/admin/storage/reorganizar?aplicar=false|true` (admin) simula/executa a mudança de todas as máquinas, devolvendo resumo por ação e caminhos relativos. Sem mudança de banco nem de agente. `delete_old_backups` passou a usar `datetime.utcnow()` (REGRA-001). **Executado em produção em 23/10/2026:** simulação (15 máquinas a mover, nenhum conflito) e depois `aplicar=true`: as 15 pastas legadas foram movidas para `<CLIENTE>_<uuid>/`; nova simulação = 15 `ja_ok` e o download de um backup de cada máquina abre normalmente. Teste novo `tests/test_storage_hierarquia.py` (8 casos), rodado em container; os testes antigos de `tests/test_storage.py` já estavam desatualizados em relação ao nome da pasta e não foram tocados.
**Arquivos:** server/api/services/storage_service.py, routers/storage_admin.py (novo), routers/customers.py, routers/backups.py, routers/agent.py, services/backup_runs.py, main.py, tests/test_storage_hierarquia.py (novo), PROJECT_SPEC.md
**Breaking Change:** Não (leitura aceita todas as estruturas; os dados antigos só mudam de lugar ao rodar a reorganização ou ao vincular/desvincular a máquina).
**Branch:** isaque

### [2026-10-23] — Galeria DIGIFORT/DEFENSE: câmeras de IP compartilhado recebiam a imagem do mesmo canal

**Alteração:** num equipamento DIGIFORT, câmeras diferentes compartilhavam o mesmo IP (gravador/encoder com vários canais; ex.: ELEVADOR A/B/C em um IP e D/E/F em outro) e a captura RTSP (painel e agente) usava só o IP, sempre o canal 1: as imagens da Galeria dessas câmeras eram a mesma. Confirmado com as imagens reais da produção. **Correção:** (1) `nvr_cameras.canal_rtsp` (migração inline; editável em `PUT .../cameras/{canal}` e no formulário da Galeria, "Canal no equipamento"). (2) IP compartilhado = mesmo IP em 2 ou mais câmeras da mesma Galeria (`ips_compartilhados` em `services/galeria_vms.py`). Câmera de IP compartilhado SEM `canal_rtsp` não é capturada (o `test-rtsp` do painel devolve erro explicativo e o agente marca FALHA com o motivo) e não aceita upload de imagem da noite; COM `canal_rtsp` a captura usa o canal (`test-rtsp` envia `canal = canal_rtsp`; o agente repassa `canal_rtsp` ao `test_rtsp_camera`). (3) `POST /agent/nvr-cameras/night-image` aceita `canal_rtsp` e, em IP compartilhado, só grava se o canal enviado for o da câmera da Galeria (agentes antigos não enviam e têm o upload ignorado, em vez de gravar a imagem errada); upload sem par e com IP já existente na Galeria também é ignorado. (4) `parear_cameras` pareia por IP somente quando há exatamente 1 câmera livre com aquele IP (antes pegava a primeira, trocando nome/status/imagem). (5) Agente (`manager.py`, DIGIFORT): o índice por IP guarda a lista de câmeras e só casa por IP quando é única (antes guardava a última). (6) `GET /agent/config` envia `canal_rtsp` e `ip_compartilhado` em `cameras_config`; `GET .../cameras` devolve `canal_rtsp` e `ip_compartilhado`; o painel mostra o selo "IP compartilhado: informe o canal". As imagens já gravadas NÃO são apagadas (o selo avisa que podem estar trocadas). Exige nova versão do agente para a captura da madrugada usar o canal. `tsc` e `pyflakes` conferidos em container.
**Arquivos:** server/api/models.py, main.py, schemas.py, services/galeria_vms.py, routers/equipamentos.py, routers/agent.py, agent/src/backup/file_manager/manager.py, agent/src/camera/rtsp_client.py, server/dashboard/src/api/types.ts, pages/Machines/MachineDetail/components/NVRCamerasGalleryModal.tsx, PROJECT_SPEC.md
**Breaking Change:** Não (campo novo opcional; câmeras de IP único seguem como antes).
**Branch:** isaque

### [2026-10-23] — Painel: página "Backups" (/backups) mais limpa

**Alteração:** a tabela passa de 9 para 7 colunas (Máquina com o Cliente embaixo, Data/Hora com a origem embaixo em português: Agendado, Fila, Avulso, Manual; Status; Equipamentos; Tamanho; E-mail; Baixar). "Equipamentos" deixa de usar blocos de cor sólida e passa a usar o selo `.badge` do painel (`TIPO ok/total`, clicável) com o detalhe num `Modal` padrão (sem o overlay feito à mão e sem o link "Detalhes"); linhas com erro ou parcial ganham uma faixa lateral colorida; e-mail enviado vira ícone de check e o reenvio vira botão de ícone; campos de data no mesmo estilo dos filtros; subtítulo corrigido (o download desta página é o ZIP da máquina) e resumo "N backup(s) · página X de Y". Removido o import sem uso de `Backups.tsx`: `tsc --noEmit` do painel passa sem erros.
**Arquivos:** server/dashboard/src/pages/Backups.tsx, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-23] — Painel: telas do Cliente e da Máquina simplificadas (feedback de uso)

**Alteração:** a tela ficou confusa (pontinhos sem significado, mesmas máquinas em três lugares, histórico e eventos escondidos). **Cliente:** a seção "Situação por máquina" (`CustomerMachines.tsx`, removido) deixa de existir, porque a fila já mostrava por máquina o estado online, a data do último backup e o último status; a seção passa a se chamar "Máquinas e fila de backup" (`QueueSection`) e ganha, em cada linha, a faixa de pontinhos dos últimos resultados (`historicoDaMaquina` em `runUtils.ts`) com contador "N/M OK" e uma legenda (`StatusLegend` em `components/StatusDots.tsx`: OK, parcial/em andamento, erro/não executou, aguardando; do mais antigo ao mais recente); a lista de rodadas ganhou a dica "Clique em uma rodada para ver o resultado de cada máquina". **Máquina:** o histórico mostra sempre as linhas compactas (sem pontinhos, sem cartão de destaque, sem botão para esconder) com o selo "último" na primeira; "Eventos do Agente" começa aberto (continua só com instruções e erros, interruptor "Mostrar pings" desligado por padrão). Sem mudança de API. `tsc` conferido em container: sem erros novos.
**Arquivos:** server/dashboard/src/components/StatusDots.tsx, pages/Customers/CustomerDetail/{index.tsx,runUtils.ts,components/QueueSection.tsx,CustomerRuns.tsx}, pages/Machines/MachineDetail/components/{BackupHistory.tsx,AgentLogs.tsx}, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-23] — Painel: telas do Cliente e da Máquina mais limpas

**Alteração:** **Cliente:** resumo no topo (`CustomerSummary`: última rodada, sucesso em 7 dias, máquinas com falha, e-mail da última rodada); "Rodadas de backup" em linhas compactas e expansíveis (5 últimas, "Ver todas"; rodada aberta sempre expandida; o modal de detalhes deixou de existir); a tabela "Backups por máquina" foi substituída por "Situação por máquina" (`CustomerMachines`: faixa de pontinhos dos últimos 10 resultados, último status, download do ZIP; máquinas com problema primeiro). Tudo é derivado das rodadas (`GET /clients/{id}/runs`), então a tela deixou de chamar `GET /backups?customer_id=`. "Problema" = erro ou parcial (`isStatusProblem`); backup em andamento não conta como falha. **Máquina:** "Histórico de Backups" vira faixa de pontinhos + último backup em destaque (lista dos 10 atrás de um botão); "Eventos do Agente" começa recolhido, com resumo do último ping (online/offline e data) e interruptor "Mostrar pings" (desligado por padrão). **API:** `GET /machines/{id}/logs` ganha `incluir_pings` (padrão `true`; com `false` filtra o tipo `ping` no servidor, senão o limite de 50 eventos ficaria cheio de pings e esconderia as instruções). Componentes compartilhados: `components/StatusDots.tsx` e `utils/statusTone.ts`. Removidos: `CustomerBackups.tsx` e `RunDetailsModal.tsx`. `tsc` conferido em container: sem erros novos (o único erro, `Backups.tsx:3` import sem uso, já existia e não bloqueia o build, que é só `vite build`).
**Arquivos:** server/api/routers/machines.py, server/dashboard/src/api/client.ts, components/StatusDots.tsx, utils/statusTone.ts, pages/Customers/CustomerDetail/{index.tsx,runUtils.ts,components/CustomerSummary.tsx,CustomerRuns.tsx,CustomerMachines.tsx}, pages/Machines/MachineDetail/{index.tsx,components/AgentLogs.tsx,BackupHistory.tsx}, PROJECT_SPEC.md
**Breaking Change:** Não (parâmetro novo opcional).
**Branch:** isaque

### [2026-10-23] — Agente 1.1.25: planilhas da configuração dos NVR, telemetria de rede/SMART Motorola e NVR Intelbras completo

**Alteração:** versão 1.1.25 do agente, que leva o trabalho da Helena incorporado no merge da entrada abaixo (planilha `.xlsx` por NVR no pacote do backup, telemetria de rede e SMART dos discos Motorola, uptime do Intelbras por SNMP, NVR Intelbras completo, mapa de gravação de 15 dias do Digifort/Defense) e o `openpyxl` como dependência nova. Versão em `updater.py`, `installer.iss` e `package.json`. O painel ganha, no mesmo deploy, o widget "Gravadores" personalizável, o termômetro, o ajuste de altura dos widgets e os HDs alinhados em colunas.
**Arquivos:** agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-23] — Merge do ramo `helena` em `isaque` (auditado)

**Alteração:** merge de `isaque_repo/helena` (`f379534`): planilha `.xlsx` da configuração dos NVR (Motorola, Hikvision e Intelbras), telemetria de rede e SMART dos discos Motorola, uptime do NVR Intelbras via SNMP, suporte completo ao NVR Intelbras (câmeras, gravações, backup), correção do mapa de gravação dos VMS Digifort/Defense, `openpyxl` no `agent/requirements.txt` e `customer_name` opcional em `GET /agent/config`. **Verificação do CLAUDE.md:** compose, nginx, `models.py`, migrações e `.env*` sem mudança; nenhum segredo nas linhas adicionadas; sem `queryPlatformCfg`; sem `datetime.now(timezone.utc)` (os `datetime.now()` sem fuso do agente são só data local de consulta de gravação e rótulo "Coletado em" das planilhas, nada vai para o banco). **Bloqueado no merge:** a pasta `teste backup motorola/` (um backup binário de configuração de NVR, `ConfigurationBackupFile`, que pode conter credenciais, e dois scripts de dump) por ser material solto de teste e o repositório de `integracao-equipamentos` ser público; permanecem no ramo `helena`. **Atenção operacional:** a telemetria e a planilha Motorola usam endpoints de leitura além da lista que o spec validou (`queryNetCfg`, `queryDiskDetailInfo`, `queryBasicCfg` e outros); a Helena registra validação em equipamentos reais, mas firmware 1.3.x é frágil (ver `queryPlatformCfg`), então a primeira rodada em Motorola de cliente deve ser acompanhada. Conflito único resolvido: ordem das entradas do changelog.
**Arquivos:** agent/src/**, server/api/routers/agent.py, server/api/schemas.py, agent/requirements.txt, .gitignore, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque (merge de helena)

### [2026-10-23] — Dashboard: HDs do widget "Gravadores" alinhados em colunas

**Alteração:** cada HD era uma linha flexível com o grupo da direita alinhado ao fim, então um texto de idade mais curto ("1 mês") deslocava o termômetro e a temperatura em relação às demais linhas. A lista de HDs de cada gravador passa a ser uma grade CSS compartilhada (colunas `max-content`: nome, selo de saúde, uso, termômetro, capacidade e idade; só entram as colunas que têm dado em algum HD do gravador), dentro de um contêiner com `overflowX: auto`. Células sem dado ficam vazias para manter as colunas; o HD sem nenhum dado mostra "sem dados do disco" ao lado do nome.
**Arquivos:** server/dashboard/src/pages/Dashboards/widgets/TelemetriaEquipamentosWidget.tsx, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-23] — Dashboard: widget ajustado ao conteúdo ao redimensionar (sem espaço vazio)

**Alteração:** a altura do widget (linhas fixas de 50 px) deixava espaço vazio quando o conteúdo era menor, e o "ajustar ao conteúdo" nunca encolhia (media `scrollHeight`, que com `height: 100%` é sempre a altura da caixa). Agora `WidgetFrame` envolve o corpo em `data-widget-conteudo` (`height: 100%`, layout igual ao anterior) e o novo `medirConteudo.ts` (`linhasDoConteudo`) mede a altura natural zerando a altura do invólucro por um instante. `ajustarAoConteudo` usa essa medida (sem aplicar `alturaMin`, o conteúdo real manda); ao soltar a alça de redimensionamento a altura só DIMINUI até o conteúdo (`somenteReduzir`, nunca cresce nem corta); durante o arraste a altura mínima passa a ser `min(alturaMin, conteúdo)`. Duplo clique na alça continua ajustando exatamente (cresce ou encolhe). Widgets com `alturaFluida: true` (por ora só `historico_backups`, cujo gráfico preenche a caixa) ficam fora. Folga restante: até uma linha da grade (~60 px), pois a altura é em linhas.
**Arquivos:** server/dashboard/src/pages/Dashboards/medirConteudo.ts, WidgetFrame.tsx, DashboardCanvas.tsx, DashboardWorkspace.tsx, widgets/registry.tsx, PROJECT_SPEC.md
**Breaking Change:** Não (layouts salvos não mudam; só o comportamento do redimensionamento).
**Branch:** isaque

### [2026-10-23] — Skills e subagentes do Antigravity (Gemini) em `.agents/`

**Alteração:** o executor Antigravity (`agy`) passa a ter skills e subagentes próprios, versionados. `.agents/skills/` (10 skills em português: as 4 do projeto, `fastapi`, `docker-compose-patterns`, `react-vite-boas-praticas`, `seguranca-e-endurecimento`, `revisao-de-codigo`, `depuracao-sistematica`; as 3 últimas adaptadas de `addyosmani/agent-skills`, MIT, commit `aeac41d`), `.agents/agents/` (`backend-fastapi`, `frontend-dashboard`, `agente-windows`, e os somente leitura `revisor` e `depurador`) e `.agents/rules/subagentes.md` (regra `always_on` de quando delegar). Substitui a regra anterior do CLAUDE.md "skills só do Claude, nunca em `.agents/skills/`". As skills do Claude continuam em `.claude/skills/`, em cópias separadas. Teste headless: o `agy` lista os 5 subagentes e as 10 skills e a delegação ao `revisor` funcionou sem alterar arquivos. Também corrigida a skill `gerenciar-containers` (a produção usa a porta 7001, não 7005). Sem mudança de código do produto.
**Arquivos:** .agents/skills/**, .agents/agents/**, .agents/rules/subagentes.md, .claude/skills/gerenciar-containers/SKILL.md, CLAUDE.md, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-23] — Dashboard: widget "Gravadores" personalizável e termômetro de temperatura dos HDs

**Alteração:** a temperatura dos HDs deixa de ser um anel e vira um termômetro vertical com escala 0–70 °C e marcas de atenção (50) e crítico (60) (`Overview/Thermometer.tsx`, usado no modal do NVR e no widget; `percentualTemperaturaHd` removida). O widget `telemetria_equipamentos` ganha dois campos de configuração: `metricas` (lista de `cpu`, `ram`, `uptime`, `disco_uso`, `disco_temperatura`, `disco_saude`, `disco_capacidade`, `disco_idade`; vazio = todas) e `discos` (objeto `{id do gravador: [nomes dos HDs]}`; ausente ou vazio = todos os HDs daquele gravador). O servidor projeta a resposta só com o que foi escolhido (vale também para o link público) e devolve `metricas` com a lista efetiva; o selo "Atenção/Saudável" continua calculado com a telemetria completa. `GET .../dashboard/opcoes` passa a trazer `discos` (nomes dos HDs) em cada equipamento, e as chaves de `discos` entram na validação de isolamento por cliente (`ids_referenciados`). O modal de configuração ganhou o editor `TelemetriaConfigEditor.tsx` (botões de marcar, atalhos e seleção de HDs por gravador). Sem mudança de banco.
**Arquivos:** server/api/services/dashboards/widgets.py, layout.py, esquemas.py, dados.py, server/dashboard/src/pages/Dashboards/TelemetriaConfigEditor.tsx, WidgetConfigModal.tsx, types.ts, widgets/registry.tsx, widgets/TelemetriaEquipamentosWidget.tsx, server/dashboard/src/pages/Overview/Thermometer.tsx, PROJECT_SPEC.md
**Breaking Change:** Não (campos novos opcionais; dashboards antigos exibem tudo como antes).
**Branch:** isaque

### [2026-10-23] — Planilha da configuração dos NVR (Motorola, Hikvision e Intelbras) gerada junto com o backup

**Alteração:** todo backup de NVR/DVR passa a gerar uma planilha `.xlsx` com a configuração lida do equipamento. É um inventário legível (ajuda a reconfigurar o NVR na mão), não um arquivo restaurável: não muda o status do backup (Motorola segue `SEM_ARQUIVOS`; Hikvision e Intelbras seguem com o `.bin`/`.backup` de sempre). Um módulo por marca, escolhido pelo tipo detectado (`PLANILHAS_NVR` em `backup_job.py`: `MOTOROLA`, `INTELBRAS`, `NVR`/`DVR` = Hikvision): `motorola/planilha.py` (NVMS-9000), `hikvision/planilha.py` (ISAPI, só GET) e `intelbras/planilha.py` (CGI Dahua, só `getConfig` e consultas de leitura). A parte comum (estilo, `eh_sensivel`, `SMART_NOMES`, aba **Câmeras (completo)**) fica em `nvr/planilha_comum.py`. **Abas:** Resumo; **Câmeras (completo)** (uma linha por câmera, cada dado em sua coluna, grupos coloridos `Stream |`, `Gravação |`/`Agenda |`, `Movimento |`, `Eventos |`, `Imagem |`; é a aba que abre por padrão); Câmeras; Stream; Gravação/Agendamento; Movimento; Eventos; Imagem; Discos; SMART (Motorola e Hikvision); Rede; configuração do sistema e **Comandos** (resultado de cada consulta, para ver o que o firmware não oferece). Por marca: *Hikvision* (validada no DS-7732NI-K4/16P, firmware V4.74.210, 26 canais): InputProxy (IP, modelo, série, firmware e força da senha de cada câmera, online), Streaming (principal/sub/terceiro: codec, resolução, CBR/VBR, bitrate, FPS, GOP, Smart Codec, áudio), trilhas de gravação e agenda, movimento por canal (sensibilidade, área, agenda), ações por tipo de evento, imagem/OSD, discos com SMART, rede, NTP, portas, UPnP, DDNS, IO; consultas por canal só nas câmeras online (as offline respondem 403). *Intelbras* (validada no iNVD 3016, firmware 4.001, 16 canais): ChannelTitle, RemoteDevice (IP, portas, modelo, série, firmware), Encode (3 formatos principais e 2 sub-streams), Record/RecordMode e agenda (índice 7 = feriado), MotionDetect (área em `MotionDetectWindow[n]` no firmware V3.0), perda de vídeo e máscara, ações dos eventos do sistema, alarmes, discos, rede. O CGI não informa se a câmera está online. *Motorola*: ver entrada anterior (refatorada para usar o módulo comum; ganhou nova tentativa quando a conexão cai). **Segurança:** `userName`/`password` (tag, atributo ou chave) de qualquer recurso nunca vão para a planilha (`eh_sensivel`), exceto as credenciais das câmeras na aba Câmeras (entrada de 27/10/2026); a consulta de usuários do NVR (`userManager`) não é usada; só leitura, pausa entre consultas, timeout, nova tentativa em queda de conexão e limite total de 300 s por NVR; o primeiro recurso (`deviceInfo`/`getSystemInfo`) sem resposta aborta a coleta sem insistir (evita bloquear a conta por login inválido). Uma seção com erro de leitura fica vazia sem derrubar o resto. **Pacote:** `processar_nvr` grava a planilha na pasta de trabalho e devolve o caminho em `_planilha`; `run_backup` remove essa chave antes de reportar ao servidor e move o arquivo para `NVR/PLANILHA/<cliente>_<máquina>_<DD-MM-AAAA>.xlsx` dentro do pacote final (ZIP global da máquina; fica fora do `backup.zip` do equipamento). Com mais de um NVR na máquina, o nome do NVR entra no nome de todas as planilhas; sem `customer_name` (servidor antigo ou máquina sem Cliente) o nome fica `<máquina>_<data>.xlsx`. API: `GET /agent/config` ganhou `customer_name` (opcional). Dependência nova: `openpyxl>=3.1.0` (se não carregar, só as planilhas somem). Tempo acrescentado por NVR: cerca de 15 a 40 s. **Validação:** `processar_equipamento` do agente nos equipamentos reais (Motorola 192.168.124.2, Hikvision 192.168.20.2, Intelbras 192.168.75.6); formato dos XMLs da Motorola conferido também em 192.168.5.2 e 192.168.5.5. Não testados: firmware Motorola 1.4.x, DVR analógico Hikvision/Intelbras e o build do PyInstaller com `openpyxl`. Versão do agente não alterada (entra na próxima).
**Arquivos:** agent/src/nvr/planilha_comum.py, agent/src/nvr/motorola/planilha.py, agent/src/nvr/hikvision/planilha.py, agent/src/nvr/intelbras/planilha.py, agent/src/application/backup_job.py, agent/requirements.txt, server/api/schemas.py, server/api/routers/agent.py, PROJECT_SPEC.md
**Breaking Change:** Não. Campo novo e opcional em `GET /agent/config`; agentes antigos o ignoram e servidores antigos não o enviam.
**Branch:** helena

### [2026-10-23] — Agente 1.1.24: backup manual do UNM2000 gera uma exportação nova na hora

**Alteração:** versão 1.1.24 do agente, que leva a exportação sob demanda do UNM2000 (entrada abaixo). Versão em `updater.py`, `installer.iss` e `package.json`.
**Arquivos:** agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-23] — UNM2000: o backup manual dispara uma exportação nova pela API local

**Alteração:** no equipamento OLT/UNM2000 (agente instalado no próprio servidor do UNM2000), o backup MANUAL do dashboard passa a pedir ao UNM2000 uma exportação completa da configuração antes de copiar o zip (hoje o agente só copiava o `AAAAMMDD_HHMMSS_allback.zip` gerado pelo agendamento das 03:00 do próprio UNM2000, na pasta de origem). Novo `agent/src/olt/unm2000_api.py` (`exportar_configuracao_unm2000`): `POST http://127.0.0.1:52302/unmcmcgi` (JSON), `Logon` (senha em MD5), lista os zips (`GetStoreFileInfo`, `storeflag` 1), espera ficar ocioso (`GetExportEMSCfgStatus`), `ExportEMSCfg` (`type` 0) e aguarda um zip novo aparecer e o status voltar a 100%; limite de 10 minutos; só esses 4 operadores (sem `Logout`, que devolve erro 502 no UNM2000). A exportação leva cerca de 46 s (medido em produção). `trigger` passa por `run_backup` → `processar_equipamento` → `processar_olt` → `realizar_backup_olt`; o backup agendado NÃO muda (usa o zip das 03:00). A exportação é OPT-IN: só roda com `config_extra.exportar_no_manual` verdadeiro, gravado pelo painel quando o formulário do UNM2000 recebe usuário e senha da API (campos novos e opcionais em `EquipamentoFormModal.tsx`/`utils.ts`; em branco o equipamento fica como antes, com o preenchimento `unm2000`/`unm2000`). Host `127.0.0.1` e porta `52302` por padrão (`config_extra.host_api` e `porta_api` opcionais, sem campo no painel). Falha ou tempo esgotado da exportação marca o equipamento como ERRO. Atenção: a retenção local do UNM2000 (10 arquivos, definida pelo cliente) faz cada exportação apagar o zip mais antigo da pasta; o agente copia o novo logo em seguida. Um teste real em 23/10/2026 confirmou a API e a rotação. Fluxo validado com respostas simuladas (sintaxe e 4 cenários) no Docker.
**Arquivos:** agent/src/olt/unm2000_api.py, agent/src/olt/unm2000.py, agent/src/application/backup_job.py, server/dashboard/src/api/types.ts, server/dashboard/src/pages/Machines/MachineDetail/utils.ts, server/dashboard/src/pages/Machines/MachineDetail/components/EquipamentoFormModal.tsx, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-23] — Agente 1.1.23: telemetria de HD dos NVR/DVR Motorola

**Alteração:** versão 1.1.23 do agente, que leva a telemetria de HD da Motorola (detalhes na entrada abaixo). Validada em 23/10/2026 nos equipamentos reais .9 (firmware 1.4.8), .10 (DVR, 1.3.8) e .8 (1.3.4): capacidade, idade e temperatura coincidem com o relatório da exploração, e a descoberta de câmeras (login extraído) continua igual. Versão em `updater.py`, `installer.iss` e `package.json`. Sem mudança de contrato nem de banco.
**Arquivos:** agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-23] — Telemetria de HD dos NVR/DVR Motorola (NVMS-9000)

**Alteração:** a Motorola (TVT, protocolo NVMS-9000) passa a ter telemetria de discos, no mesmo formato da Hikvision: novo `agent/src/nvr/motorola/telemetry.py` (`coletar_telemetria_motorola`) consulta SOMENTE `queryStorageDevInfo` (modelo/capacidade em MB; o id do disco é um GUID), `queryDiskStatus` (`read/write`, `read` ou `bad`; o XML muda entre firmware 1.3.x, texto no `<item>`, e 1.4.x, filho `<diskStatus>`) e `queryDiskSmartInfo` por disco (`powerOnDays`, `temperature`, `diskStatus` good/lowHealth/bad). Resultado: `{"disks": [{device: "HDD<slot>", status, percent: None, total_gb, free_gb: None, power_on_days, temperature_c}]}`; `freeSpace` é sempre 0 (gravação em loop), então não há percentual de uso. Status: `ERRO` (estado `bad` ou SMART `bad`) > `SAUDE_BAIXA` (SMART `lowHealth`) > `SOMENTE_LEITURA` (estado `read`) > `OK`; `StatusBadge` ganhou `SOMENTE_LEITURA` e `SAUDE_BAIXA`. Sem CPU, RAM, uptime nem rede (a Motorola não expõe). Chamadas em sequência, pausa de 1 s e timeout de 30 s (os DVR respondem em até 30 s); qualquer falha devolve `None` e o backup segue. O login NVMS-9000 foi extraído de `buscar_cameras` para `abrir_sessao_motorola` (`cameras.py`), sem mudança de comportamento; a telemetria faz um login próprio por execução. **Regra de segurança:** o código usa lista fixa de endpoints; `queryPlatformCfg` reiniciou três NVR com firmware 1.3.3 em 22/10/2026 e nunca deve ser chamado; o XML bruto (alguns endpoints devolvem senha em texto claro) e o serial dos discos não vão para log. O agente ainda não foi liberado em versão nova; validação nos equipamentos reais pendente.
**Arquivos:** agent/src/nvr/motorola/telemetry.py, agent/src/nvr/motorola/cameras.py, agent/src/nvr/factory.py, server/dashboard/src/components/StatusBadge.tsx, server/dashboard/src/pages/Dashboards/widgets/TelemetriaEquipamentosWidget.tsx, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-22] — Agente 1.1.22: uptime, idade e temperatura dos HDs dos NVR Hikvision

**Alteração:** versão 1.1.22 do agente, que leva a coleta de `uptime_seconds` e, por disco, `power_on_days` e `temperature_c` (detalhes e correção do `freeSpace` 0 na entrada abaixo). Servidor e painel já estavam em produção desde o commit `1c2e970`; os cartões dos HDs só mostram idade e temperatura depois que a máquina atualiza para a 1.1.22 e faz um backup. Versão em `updater.py`, `installer.iss` e `package.json`. Sem mudança de contrato nem de banco.
**Arquivos:** agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-22] — Telemetria do NVR Hikvision: uptime, idade e temperatura dos HDs, capacidade correta e medidores em anel

**Alteração:** a telemetria Hikvision passa a incluir `uptime_seconds` (`ISAPI/System/status`, `deviceUpTime`) e, por disco, `power_on_days` e `temperature_c` (`ISAPI/ContentMgmt/Storage/hdd/<id>/SMARTTest/status`, campos `powerOnDay` e `temprature`; consulta com timeout de 5 s por disco e falha isolada, nunca derruba a coleta). Verificado em dois NVR reais (DS-7732NI-K4/16P e DS-96256NI-I16): `powerOnDay` é o atributo SMART 9 (horas ligado) dividido por 24. **Correção:** os NVR em gravação por sobrescrita devolvem `freeSpace` = 0 em todos os discos, o que virava `percent` 100 e `free_gb` 0 (painel com "0 GB livres" e alerta de disco cheio falso); agora `freeSpace` 0 vira "desconhecido" (`percent` e `free_gb` nulos) e só a capacidade total é exibida. Servidor: `telemetria_equipamento_publica` repassa os campos novos (só numéricos) e `construir_telemetria_equipamentos` envia `uptime_seconds` ao widget. Painel: `RingGauge` ganhou `valueLabel` e `nivel` (opcionais; os usos atuais não mudam) e `label` opcional; `NVRTelemetryModal` mostra CPU e RAM em anel, tempo ligado em texto e um cartão por disco com anel de uso (quando o percentual é real), anel de temperatura (escala 0–70 °C, atenção acima de 50 e crítico acima de 60), capacidade e idade (`fmtIdade`); o widget "Gravadores" segue o mesmo padrão. Idade, uptime e rede ficam em texto (sem limite de 0 a 100%). Intelbras não muda (sem SMART/uptime; os campos novos ficam em "—"). Só o agente precisa de versão nova para coletar os dados; servidor e painel já os aceitam.
**Arquivos:** agent/src/nvr/hikvision/telemetry.py, server/api/services/dashboards/widgets.py, server/dashboard/src/api/types.ts, server/dashboard/src/pages/Dashboards/types.ts, server/dashboard/src/pages/Dashboards/widgets/TelemetriaEquipamentosWidget.tsx, server/dashboard/src/pages/Machines/MachineDetail/telemetry.ts, server/dashboard/src/pages/Machines/MachineDetail/components/NVRTelemetryModal.tsx, server/dashboard/src/pages/Overview/RingGauge.tsx, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-22] — Agente 1.1.21: telemetria de rede dos NVR chega aos clientes

**Alteração:** versão 1.1.21 do agente, que leva a coleta de interfaces e tráfego de rede (`networks`) dos NVR Hikvision (ISAPI) e Intelbras (SNMP), integrada de `helena` no merge `dda48bc`. Servidor e painel já estavam em produção desde esse merge; o bloco de rede só aparece nos modais depois que a máquina atualiza para a 1.1.21. Versão em `updater.py`, `installer.iss` e `package.json`. Sem mudança de contrato nem de banco.
**Arquivos:** agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-22] — Telemetria de NVR: interfaces e tráfego de rede (Hikvision e Intelbras)

**Alteração (branch helena, integrada em isaque):** a telemetria de NVR/DVR passa a incluir `networks` (lista de interfaces com `name`, `ip`, `mac`, `status` UP/DOWN, `speed_mbps`, `recv_mbps` e `sent_mbps`). Hikvision: `ISAPI/System/Network/statistics` (taxa de entrada/saída em kbps, convertida para Mbps) e `ISAPI/System/Network/interfaces` (NIC, IP, MAC e velocidade); a taxa global vai na primeira interface. Intelbras: `IF-MIB` por SNMP (`1.3.6.1.2.1.2.2.1` e `1.3.6.1.2.1.31.1.1.1`), com taxa instantânea por amostragem de octetos. Servidor: `telemetria_equipamento_publica` (`widgets.py`) sanitiza `networks` (até 8 itens, textos em 50 caracteres, números validados) e só descarta a telemetria se CPU, RAM, discos e redes estiverem vazios. Painel: `NVRTelemetryModal.tsx` mostra um cartão por interface com setas de recebimento/envio em Mbps, MAC e selos de status e velocidade; `StatusBadge` ganhou `UP` (Conectado) e `DOWN` (Desconectado). Sem mudança de contrato nem de banco (a telemetria é JSON).
**Integração (merge em isaque):** as correções de RAM total/usada, do `post_report` (`telemetria`) e do `gerar_secretkey` que o changelog da colaboradora listava já estavam em `isaque` (1.1.19 e 1.1.20) e não vinham neste merge. **Bloqueado:** `archive/legacy_scripts/teste_motorola_telemetria.py` (script de teste de NVR Motorola com a senha padrão de equipamento gravada no código); não entra no repositório. Auditoria do merge: sem `datetime.now`/`timezone` nas linhas adicionadas; compose, nginx, `models.py`, migrações, `requirements*.txt` e `build.ps1` intocados. O agente continua em 1.1.20 (nenhuma versão nova foi gerada).
**Arquivos:** agent/src/nvr/hikvision/telemetry.py, agent/src/nvr/intelbras/telemetry.py, server/api/services/dashboards/widgets.py, server/dashboard/src/api/types.ts, server/dashboard/src/components/StatusBadge.tsx, server/dashboard/src/pages/Machines/MachineDetail/components/NVRTelemetryModal.tsx, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** helena, isaque

### [2026-10-22] — Checagem obrigatória de merge de colaboradores

**Alteração:** análise do merge de 06/10 (`538600f`, ADR-006) e do merge de 22/10 (`28212ef`, telemetria de NVR, limpo). O merge de 06/10 levou 25 arquivos, entre eles `models.py` e `routers/agent.py` com `datetime.now(timezone.utc)`, `docker-compose.yml` com `7005`/`pg_data_local`, `nginx.conf` reescrito e arquivos soltos na raiz; a correção real foi o merge auditado de 09/10 (`415f0cc`). O compose voltou em 13/10 (`4c18e45`, merge `7ec3cc4`), e desde então houve 13 merges de `helena` em `isaque` sem entrada de auditoria. Passa a valer a checagem descrita na seção 11 ("Auditoria de merge de ramos de colaboradores") e no `CLAUDE.md`. Nova incompatibilidade IC-016 (`nginx.conf` com `error_log debug`).
**Arquivos:** PROJECT_SPEC.md, CLAUDE.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-22] — Auditoria do PROJECT_SPEC contra o código (só documentação)

**Alteração:** as descrições do documento foram conferidas com o código e corrigidas. Nenhum código, REGRA, ADR (exceto a redação abaixo) ou contrato mudou.
- Seção 2: `python-dotenv`, `pyzipper` (servidor) e `pysnmp` (agente).
- Seção 3: `agent/src/application/estado.py`, `agent/src/nvr/intelbras/`, `services/backup_runs.py`, `api/dashboards.ts`; `routers/nvrs.py` descrito como ativo e oculto do OpenAPI.
- Seção 5: tabelas `client_groups`, `nvr_cameras` e `customer_backup_runs`; colunas `clients.group_id`, `clients.queue_order` e `backups.run_id`; `clients.api_key_hash` é UNIQUE.
- Seção 8: `GET /backups/{id}`, `POST .../cameras/import`, `PUT/DELETE .../cameras/{canal}`, `X-Publish-Token` no registro de versões e as rotas legadas `/clients/{machine_id}/nvrs`.
- Seção 9: nome exibido do serviço (`Trilan — Agente Backup`), `agent.conf` com a seção `[auth]`, e a marca (`config_extra.marca`) decidindo antes da ordem de detecção do factory.
- Seção 12: `PUBLISH_TOKEN`, `MAX_UPLOAD_MB` e `RUN_*`.
- Seção 13: `DVR` e `MOTOROLA` são tipos detectados pelo agente, nunca gravados em `nvrs.tipo` (a marca fica em `config_extra.marca`); NVR Intelbras (SNMP).
- Seção 17: entrada no índice; `OutputBaseFilename` do instalador é fixo.
- Seção 11: tabela de ramos corrigida — `isaque` em `projetoswmfa` (privado) é a produção; `helena` e `integracao-equipamentos` são de colaboradores, sem acesso direto à `isaque`. A porta 7001 do documento estava certa e **não** mudou. `CLAUDE.md`: o repositório `trilan-nvr-backup-automation` é o mesmo `backup-automation` (renomeado) e foi acrescentada a linha com os papéis dos ramos.
- ADR-008: redação ajustada para `.claude/` (exceto `.claude/skills/`, que é versionada). REGRA-003: documentados `X-Publish-Token` e `X-Dashboard-Token` (rotas específicas) e que `rotate-key` também devolve a chave; o contrato não mudou.
- Seção 15: IC-013 (repositório público com histórico exposto — crítica), IC-014 (link do dashboard montado com `PUBLIC_URL`) e IC-015 (`docker-compose.yml` versionado com `7005` e `pg_data_local`, valores de uma colaboradora; a produção usa 7001).
- Não alterado: o texto da REGRA-001 (exceções de `machines.py`, `storage_service.py` e `customers.py:375` aguardam aprovação) e o changelog de 09/10, que continua como registro histórico (a rejeição de `7005`/`pg_data_local` ali descrita foi desfeita no ramo `isaque` em 13/10).
**Arquivos:** PROJECT_SPEC.md, CLAUDE.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-22] — Painel: pausar/retomar equipamento não recarrega mais a página inteira

**Problema:** em `MachineDetail/index.tsx`, depois de pausar/retomar, salvar ou remover um equipamento (e salvar a máquina ou gerar nova API Key), o código chamava `load()` com o spinner (`setLoading(true)`), que troca a tela inteira pelo carregando (`if (loading) return <spinner/>`). A página desmontava e o usuário perdia a posição (tinha de voltar à seção de equipamentos).
**Correção:** essas ações passam a chamar `load(true)` (recarga silenciosa, a mesma do polling de 10 s): a lista atualiza no lugar, sem spinner e sem perder a rolagem. Só frontend; o servidor e o agente não mudam. Os fluxos de importação/exclusão de câmeras em lote continuam com o spinner de propósito (`setBusy`).
**Arquivos:** server/dashboard/src/pages/Machines/MachineDetail/index.tsx, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-22] — Agente 1.1.20: RAM total/usada na telemetria dos NVR (Hikvision e Intelbras)

**Alteração (branch helena, integrada em isaque):** a telemetria passa a incluir `ram_total_gb` e `ram_used_gb`. Hikvision: `_calcular_ram` em `telemetry.py` lê `memoryUsage` e `memoryAvailable` (MB) e calcula o percentual, o total e o usado em GB; sem `memoryAvailable`, mantém o valor bruto como percentual quando está entre 0 e 100. Intelbras: o SNMP lê também o OID de RAM total (`1.3.6.1.4.1.1004849.2.1.9.1.0`, em MB) e deriva o usado a partir do percentual. `crypto.gerar_secretkey` passa a aceitar senha `None` (tratada como vazia). Servidor: `telemetria_equipamento_publica` repassa os dois campos novos (só numéricos; o resto vira `None`). Painel: `types.ts`, `NVRTelemetryModal.tsx` e `ServerHealthCard.tsx` exibem a RAM em GB quando disponível. Sem mudança de contrato nem de banco (a telemetria é JSON). O efeito aparece a cada backup após a máquina atualizar para a 1.1.20.
**Arquivos:** agent/src/backup/crypto.py, agent/src/nvr/hikvision/telemetry.py, agent/src/nvr/intelbras/telemetry.py, server/api/services/dashboards/widgets.py, server/dashboard/src/api/types.ts, server/dashboard/src/pages/Machines/MachineDetail/components/NVRTelemetryModal.tsx, server/dashboard/src/pages/Machines/MachineDetail/components/ServerHealthCard.tsx, agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json
**Breaking Change:** Não.
**Branch:** helena, isaque

### [2026-10-22] — Agente 1.1.19: correção: telemetria dos NVR nunca chegava ao servidor

**Problema:** `post_report` (`agent/src/application/api_client.py`) montava cada item de `nvr_results` com `nome`, `tipo`, `status` e `cameras`, mas **não** com `telemetria`. O agente coletava CPU/RAM/discos (Hikvision por ISAPI, Intelbras por SNMP), o servidor já sabia gravar `nvrs.last_telemetry_status`, porém o campo se perdia no envio — `last_telemetry_status` ficava vazio e os widgets "Gravadores" e os indicadores de disco do "Resumo" apareciam sem dados. Afetava todas as versões do agente até a 1.1.18 (inclusive a branch `helena`).

**Correção:** `post_report` passa a enviar `"telemetria": r.get("telemetria")` (`None` continua sendo ignorado pelo servidor). Sem mudança de contrato nem de servidor. Teste de regressão: `tools/teste_telemetria_nvr_e2e.py`. Liberada na versão 1.1.19 do agente; o efeito aparece a cada backup após a máquina atualizar.

### [2026-10-23] — Telemetria de NVRs Motorola (CPU, RAM, Discos e Rede)

**Alteração:** Suporte a coleta de telemetria em gravadores Motorola (arquitetura NVMS-9000 / TVT):
1. Script de diagnóstico e dump (`teste backup motorola/dump_motorola_telemetria.py`): baseado no padrão do `dump_motorola_cameras.py`, conecta via NVMS-9000 (`reqLogin`/`doLogin` com SHA-512 ou Base64), testa envelopes gerais e com `requireField` para armazenamento (`queryDiskStatus`, `queryDiskDetailInfo`, `queryStorageCapacity`), CPU/RAM (`queryCpuStatus`, `queryMemoryStatus`, `queryDevStatus`) e rede (`queryNetCfg`, `queryNetStatus`), salvando os XMLs brutos em `respostas_telemetria_<ip>/` e exibindo o resumo consolidado e o JSON formatado.
2. Agente (`agent/src/nvr/motorola/telemetry.py`): novo módulo `coletar_telemetria_motorola` extrai CPU (`%`), RAM (`%`, total e usado em GB), tabela de discos (identificador, status normalizado para o `StatusBadge`, percentual de uso, capacidade total e livre em GB) e interfaces de rede (nome, status UP/DOWN, IP, MAC, velocidade e taxas de envio/recebimento).
3. Despacho no `agent/src/nvr/factory.py`: `coletar_telemetria_nvr()` roteia para `coletar_telemetria_motorola` quando `marca == "MOTOROLA"` ou `tipo_nvr == "MOTOROLA"`, integrando diretamente à tela de telemetria (`NVRTelemetryModal`) e aos widgets de gravadores sem exigir mudanças no backend ou frontend.
**Arquivos:** agent/src/nvr/motorola/telemetry.py, agent/src/nvr/factory.py, teste backup motorola/dump_motorola_telemetria.py, teste backup motorola/dump_motorola_cameras.py, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** helena

### [2026-10-21] — Agente 1.1.18: Telemetria de NVR Intelbras via SNMP

**Alteração:** NVR com `config_extra.marca = "Intelbras"` agora coleta telemetria por SNMPv2c (porta 161, community "Public" por padrão, configurável em `config_extra.snmp_community`) em vez de ISAPI: novo `agent/src/nvr/intelbras/telemetry.py` (`coletar_telemetria_intelbras`, usando `pysnmp.hlapi.asyncio`) lê RAM (`%` de uso, OID da MIB proprietária Intelbras) e a tabela de HDs (dispositivo, status, capacidade e livre em GB), traduzindo o status (Normal/Error/Abnormal/...) para os rótulos do `StatusBadge`. Sem OID de CPU na MIB Intelbras — o card mostra "—" nesse campo, igual a qualquer equipamento sem o dado. `factory.coletar_telemetria_nvr()` passa a receber `marca`/`snmp_community` e rotear para SNMP (Intelbras) ou ISAPI (Hikvision e demais); `buscar_cameras()` trata `marca="Intelbras"` como `"HIKVISION"` (câmeras/gravações continuam via ISAPI, que os NVRs Intelbras também falam). O resultado tem o mesmo formato do Hikvision (`cpu_percent`/`ram_percent`/`disks`), então `NVRTelemetryModal` exibe os dois fabricantes sem nenhuma mudança de frontend. Novo seletor "Intelbras" na Marca do NVR (`EquipamentoFormModal.tsx`, antes agrupado em "Hikvision / Intelbras / Outros"). Build: `pysnmp` no `requirements.txt` e `--collect-all pysnmp`/`--collect-all pyasn1` no `build.ps1` (MIBs e módulos carregados dinamicamente, precisam ser coletados à parte pelo PyInstaller).
Integração (merge em isaque): a dependência foi fixada em `pysnmp>=7.1,<8.0.0` — com a faixa original (`>=6.1.2,<7`) o pip instalava a 6.2.6, que não tem `get_cmd`/`walk_cmd` (`ImportError`), o que derrubaria o processamento de NVRs; o módulo foi validado contra um simulador SNMP (RAM, discos e status; community errada devolve `None`) com pysnmp 7.1.30 em Python 3.12 e 3.14. O import em `factory.py` passou a ser protegido (`try/except`): falha do pysnmp desativa só a telemetria Intelbras e nunca o backup. Versão do agente 1.1.18.
**Arquivos:** agent/src/nvr/intelbras/telemetry.py, agent/src/nvr/intelbras/__init__.py, agent/src/nvr/factory.py, agent/src/application/backup_job.py, agent/requirements.txt, agent/build.ps1, server/dashboard/src/pages/Machines/MachineDetail/components/EquipamentoFormModal.tsx, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** helena, isaque

### [2026-10-21] — Dashboards por Cliente: redimensionar com o mouse e conteúdo adaptável (rodada B)

**Alteração:** Em modo de edição cada componente ganha alças (borda direita, borda inferior e canto) para redimensionar com o mouse como uma janela, com encaixe na grade (colunas de 1/12 da largura e linhas de 50px), tamanho mínimo por tipo de widget, etiqueta "N col × M lin" durante o arrasto e atualização ao vivo do layout; "Largura total" e "Ajustar ao conteúdo" (também por duplo clique no canto) substituem os seletores de ¼/½. O conteúdo dos componentes se reorganiza conforme a área (quebra de linha, grades `auto-fit`, gráfico do histórico desenhado no tamanho real) e, no limite, rola dentro do quadro: nenhuma informação é cortada. O componente "Saúde do servidor" passou a mostrar sempre "Atualizado há …" (o servidor envia `segundos_desde_contato` e o tempo continua envelhecendo no navegador) e "Aguardando a primeira comunicação" quando a máquina nunca se comunicou; `iso()` deixou de gerar datas com fuso duplicado.
**Arquivos:** server/dashboard/src/pages/Dashboards/DashboardCanvas.tsx, WidgetAcoesEdicao.tsx, DashboardWorkspace.tsx, WidgetFrame.tsx, types.ts, widgets/*, server/dashboard/src/index.css, server/api/services/dashboards/widgets.py
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-21] — Dashboards por Cliente: tamanho livre dos componentes e pizza de status dos NVRs (rodada A)

**Alteração:** O tamanho dos componentes deixa de ser fixo: `largura` vale 2 a 12 colunas e `altura` 1 a 40 linhas de 50px (antes 1–4 linhas de 150px). Layouts antigos (`schema_version` 1) são convertidos na leitura (altura × 3) para `schema_version` 2, sem tocar no banco até o próximo salvamento. Cada tipo de widget ganha tamanho mínimo no front (`larguraMin`/`alturaMin`) para o conteúdo não quebrar. Novo widget `status_nvr` ("Status dos NVRs (pizza)"): gráfico de pizza SVG da situação das câmeras de cada NVR (gravando, sem gravação, offline, não verificado) com cores fixas por status, uma pizza por NVR ou uma agregada; reaproveita `last_recording_status` e a lista branca de campos/isolamento por cliente (`ids_referenciados` cobre a chave `equipamentos` do novo tipo).
**Arquivos:** server/api/services/dashboards/layout.py, widgets.py, server/dashboard/src/pages/Dashboards/types.ts, useElementSize.ts, PieChart.tsx, widgets/StatusNvrWidget.tsx, widgets/registry.tsx, server/dashboard/src/index.css
**Breaking Change:** Não (layouts antigos são convertidos na leitura).
**Branch:** isaque

### [2026-10-21] — Dashboards por Cliente: componente "Gravadores" e indicadores de disco no Resumo

**Alteração:** A telemetria dos NVR/DVR Hikvision (`nvrs.last_telemetry_status`: CPU, RAM e discos) passa a alimentar o dashboard do Cliente. Novo tipo de widget `telemetria_equipamentos` ("Gravadores (CPU, RAM e discos)": anéis de CPU/RAM, status e ocupação de cada disco, alerta quando o disco tem status diferente de OK/REPOUSO ou ocupação >= 90%, filtro de gravadores e opção "apenas com problema") e três indicadores novos no Resumo (`gravadores_com_telemetria`, `discos_total`, `discos_com_problema`; os tiles de disco só aparecem se houver telemetria). A resposta usa lista branca de campos (sem IP, usuário, senha ou `config_extra`) e o isolamento por cliente cobre a chave `equipamentos` do novo widget (`ids_referenciados`). Nenhuma mudança no agente nem no banco.
**Arquivos:** server/api/services/dashboards/widgets.py, server/api/services/dashboards/layout.py, server/dashboard/src/pages/Dashboards/types.ts, widgets/TelemetriaEquipamentosWidget.tsx, widgets/registry.tsx, widgets/ResumoWidget.tsx, WidgetConfigModal.tsx
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-21] — Telemetria de NVR Hikvision (CPU/RAM/Discos) e status no painel

**Alteração:** (1) Agente: novo `src/nvr/hikvision/telemetry.py` (`coletar_telemetria_hikvision`) lê `ISAPI/System/status` (CPU/RAM) e `ISAPI/ContentMgmt/Storage/hdd` (discos: capacidade, livre, status) de NVR/DVR Hikvision, convertendo MB→GB e calculando o percentual de uso de cada disco; `factory.py` expõe `coletar_telemetria_nvr()`, que só roda para `tipo_nvr` `NVR`/`DVR` (Motorola retorna `None`). `backup_job.processar_nvr` inclui o resultado em `"telemetria"` no retorno do backup. (2) API: `NVRResult.telemetria` (relatório do agente) grava em `NVR.last_telemetry_status` (coluna JSON nova, migração inline em `main.py`); exposta em `NVRResponse.last_telemetry_status`. (3) Painel: botão "Telemetria" no card de equipamento NVR (`EqCard.tsx`) abre `NVRTelemetryModal.tsx`, reaproveitando `MetricTile`/`PctBar` (CPU, RAM) e `StatusBadge` (status de cada disco: OK, Erro, Não Inicializado, Não Formatado, Repouso, Desconhecido — novas entradas no mapa de `StatusBadge.tsx`) e `fmtGb`/`fmtPct` de `telemetry.ts`. Sem dado (equipamento não-Hikvision ou offline na última coleta): modal mostra "Sem dados de telemetria disponíveis.".
**Arquivos:** agent/src/nvr/hikvision/telemetry.py, agent/src/nvr/factory.py, agent/src/application/backup_job.py, server/api/schemas.py, server/api/models.py, server/api/main.py, server/api/routers/agent.py, server/dashboard/src/api/types.ts, server/dashboard/src/components/StatusBadge.tsx, server/dashboard/src/pages/Machines/MachineDetail/components/NVRTelemetryModal.tsx, server/dashboard/src/pages/Machines/MachineDetail/components/EqCard.tsx, server/dashboard/src/pages/Machines/MachineDetail/index.tsx, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** helena, isaque

### [2026-10-21] — Agente 1.1.17: Suporte Completo a Câmeras IP Motorola / ONVIF (MTIDM022603)

**Alteração:** (1) Agente (`rtsp_client.py`): Diferenciação entre NVRs Motorola multiplexados (NVMS-9000, que usam `/chID=N&streamType=main`) e câmeras IP standalone Motorola / ONVIF Profile S (como a Dome 2MP `MTIDM022603`), que passam a tentar as URLs padrão `/profile1` (stream principal), `/profile2` (sub-stream), `/live/ch0`, `/live/ch1`, `/?chID=1&streamType=main`, `/onvif1` e fallback ONVIF genérico. Evita que câmeras avulsas tentem endpoints exclusivos de NVR ou caiam no padrão Hikvision (`/Streaming/Channels/101`). (2) `_eh_motorola` e `_sem_playback`: câmeras diretas (`direct_camera=True`) ou modelos MTI/ONVIF são identificadas como câmeras avulsas sem playback em NVR, prevenindo tentativas de login NVR via SOAP/NVMS. (3) Frontend: Adicionada detecção de prefixo `MTI`/`MTIDM` e marca `MOTOROLA` como protocolo ONVIF no importador CSV (`useCameraImport.ts`) e opção explícita "Motorola (ONVIF)" nos modais de edição (`NVRCamerasGalleryModal.tsx` e `EquipamentoFormModal.tsx`).
(4) Proteção anti-lockout: no máximo 4 tentativas por captura e parada imediata em `401 Unauthorized`. Na integração (merge em isaque) ficou junto da checagem prévia da porta 554 e das mensagens de erro traduzidas sem usuário/senha, e a parada considera só `401 Unauthorized`.
**Arquivos:** agent/src/camera/rtsp_client.py, server/dashboard/src/pages/Machines/MachineDetail/hooks/useCameraImport.ts, server/dashboard/src/pages/Machines/MachineDetail/components/NVRCamerasGalleryModal.tsx, server/dashboard/src/pages/Machines/MachineDetail/components/EquipamentoFormModal.tsx, agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** helena, isaque

### [2026-10-21] — Dashboards por Cliente (etapa 3: documentação e testes)

**Alteração:** Dashboard por Cliente documentado nas seções 3 (estrutura), 5 (tabela `customer_dashboards`), 7 (fluxo do link público: token com hash, fragmento da URL, 404 genérico, limites por IP, isolamento e listas brancas) e 8 (rotas). Nova skill do Claude `criar-widget-dashboard` (como registrar um tipo de widget no backend e no front). Testes de ponta a ponta no repositório: `tools/teste_dashboards_e2e.py` (API: isolamento entre clientes, token inválido/expirado/revogado/regenerado, limite de tentativas, permissão de edição, token sem acesso a rotas admin, resposta pública sem IP/credenciais) e `tools/dashboards_ui/` (Chromium headless em Docker: página pública e de administração, personalizar, salvar, compartilhar e revogar).
**Arquivos:** PROJECT_SPEC.md, CLAUDE.md, .claude/skills/criar-widget-dashboard/SKILL.md, tools/teste_dashboards_e2e.py, tools/dashboards_ui/*, tools/README.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-21] — Dashboards por Cliente (etapa 2B-2: compartilhamento e personalização pelo cliente)

**Alteração:** Painel "Compartilhar" na página do dashboard (admin): gerar o link (validade: sem validade, 7/30/90 dias ou data; permitir ou não a personalização pelo cliente), copiar o link (mostrado uma única vez — o servidor guarda só o hash), ativar/desativar, alterar a validade e a permissão de edição, gerar novo link (invalida o anterior) e revogar. A página pública `/d` passou a usar o mesmo editor (`DashboardWorkspace`): quando o link tem permissão de edição o cliente vê "Personalizar" (sem "Restaurar padrão" nem "Compartilhar") e o layout é salvo no servidor com controle de versão; sem permissão a página é somente leitura.
**Arquivos:** server/dashboard/src/pages/Dashboards/SharePanel.tsx, DashboardAdminPage.tsx, PublicDashboardPage.tsx
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-21] — Dashboards por Cliente (etapa 2B-1: editor e página de administração)

**Alteração:** Editor de dashboard (`DashboardWorkspace`): adicionar/remover componentes, arrastar para reordenar, largura (¼ a total) e altura por componente, configuração por componente (máquinas, equipamentos, tipos, período, visual) gerada a partir dos `campos` de cada tipo de widget (registro modular), filtro geral de período, prévia com dados reais do rascunho (`POST .../dashboard/preview`, admin e público com permissão de edição), salvar com controle de versão (409 em edição concorrente), descartar e restaurar o padrão. Nova página `/clientes/:id/dashboard` e botão "Dashboard" no detalhe do cliente.
**Arquivos:** server/dashboard/src/pages/Dashboards/*, server/dashboard/src/api/dashboards.ts, server/dashboard/src/App.tsx, server/dashboard/src/pages/Customers/CustomerDetail/*, server/api/routers/dashboards.py, server/api/routers/public_dashboard.py, server/api/services/dashboards/esquemas.py
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-21] — Dashboards por Cliente (etapa 2A: visão pública e widgets)

**Alteração:** Registro de widgets no front (resumo, saúde do servidor, status e histórico de backups, câmeras, equipamentos, texto), grade de 12 colunas (`.dash-grid`) e página pública `/d` (sem menu e sem login) que lê o token do fragmento da URL (`/d#<token>`), envia em `X-Dashboard-Token` por um cliente HTTP separado (sem JWT do painel) e atualiza os dados a cada 30 s. Novas rotas de opções para o editor: `GET /api/v1/clients/{id}/dashboard/opcoes` (admin) e `GET /api/v1/public/dashboard/opcoes` (só com permissão de edição). A rota `/d` do nginx do dashboard envia `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex` e `Cache-Control: no-store`.
**Arquivos:** server/dashboard/src/pages/Dashboards/*, server/dashboard/src/api/dashboards.ts, server/dashboard/src/App.tsx, server/dashboard/src/index.css, server/dashboard/nginx-spa.conf, server/api/routers/dashboards.py, server/api/routers/public_dashboard.py, server/api/services/dashboards/{dados,esquemas}.py
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-21] — Dashboards por Cliente (etapa 1: API)

**Alteração:** Nova tabela `customer_dashboards` (um dashboard por Cliente: layout JSON versionado + compartilhamento por link). Registro de tipos de widget plugáveis (`services/dashboards/`: resumo, saúde do servidor, status e histórico de backups, câmeras/gravação, equipamentos, texto) que montam os dados a partir de telemetria, backups e `last_recording_status` já existentes. Rotas de admin (JWT) em `/api/v1/clients/{id}/dashboard` (layout com controle de versão, link de compartilhamento: gerar/regenerar, ativar, validade, permitir edição, revogar) e catálogo em `/api/v1/dashboards/widgets`. Rotas públicas em `/api/v1/public/dashboard` autenticadas só por `X-Dashboard-Token` (token aleatório de 256 bits, guardado como hash SHA-256, mostrado uma única vez; 404 genérico para inválido/expirado/revogado; limite de requisições e de tentativas inválidas por IP em memória, válido para 1 worker). O servidor filtra tudo pelo cliente do token e a resposta pública omite IPs, credenciais e configurações dos equipamentos.
**Arquivos:** server/api/models.py, server/api/main.py, server/api/services/dashboards/*, server/api/routers/dashboards.py, server/api/routers/public_dashboard.py
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-21] — Agente 1.1.16: Fallback RTSP (TCP/UDP e sub-stream) e pareamento por nome/IP na Galeria VMS

**Alteração:** (1) Agente (`rtsp_client.py`): `test_rtsp_camera` agora utiliza fallback automático entre protocolos de transporte (TCP -> UDP) com `-stimeout 5000000` (5s), além de tentar o stream secundário (`102`) e formato simplificado (`/Streaming/Channels/1`) se o principal estiver saturado. Isso resolve o erro de timeout de 15s no FFmpeg em câmeras Hikvision mais antigas (ex: DS-2CD2012-I e DS-2CD2020-I) que funcionavam no VLC (que usa UDP por padrão) mas travavam no TCP forçado enquanto o VMS gravava. (2) Servidor (`equipamentos.py`): `get_nvr_cameras` para VMS pareia câmeras por nome e por IP (não apenas por número sequencial de canal), garantindo que nomes e IPs não se misturem e que câmeras sem registro prévio no banco utilizem o IP reportado pelo agente (eliminando câmeras "sem IP"). (3) `test_equipamento_rtsp`: recupera o IP do relatório de status e persiste automaticamente se o canal ainda não possuía IP cadastrado na galeria, evitando o erro falso "sem IP configurado". (4) `import_cameras`: casa câmeras existentes por nome/IP antes de casar por canal ao importar CSV/XLSX, preservando referências e imagens ao reimportar. (5) Integração (merge de helena em isaque): a captura ao vivo usa `-timeout` (o `-stimeout` não existe no ffmpeg 7.1 do agente e fazia toda captura falhar com "Unrecognized option"), checa a porta 554 antes das tentativas, limita o total a 20 s e devolve motivo traduzido sem usuário/senha. O pareamento de câmeras (nome, IP e nome parecido único, nunca por canal) foi extraído para `services/galeria_vms.py` e é usado pela Galeria, pela captura do painel e pelo envio da imagem da noite.
**Arquivos:** agent/src/camera/rtsp_client.py, agent/src/backup/file_manager/manager.py, server/api/routers/equipamentos.py, server/dashboard/src/pages/Machines/MachineDetail/hooks/useCameraImport.ts, agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json, server/api/services/galeria_vms.py, server/api/routers/agent.py
**Breaking Change:** Não.
**Branch:** helena, isaque

### [2026-10-21] — Agente 1.1.15: Galeria DIGIFORT/DEFENSE com câmeras casadas pelo nome e erro de captura sem senha

**Alteração:** Em equipamentos DIGIFORT/DEFENSE, o servidor passou a casar relatório, imagem da noite e status de captura pelo **nome** da câmera (antes era pelo canal, e a numeração do agente — ordem do export local — difere da da Galeria, o que trocava nome/IP/imagem entre câmeras). O agente envia o canal da Galeria e deduplica por nome. A captura ao vivo do agente verifica a porta 554 antes do ffmpeg, usa timeout de 20 s e devolve o motivo traduzido (porta inacessível, senha recusada, caminho RTSP não encontrado, tempo esgotado); a URL RTSP com usuário/senha nunca vai na mensagem, e o servidor também mascara credenciais recebidas de agentes antigos (rtsp-result, relatório e leitura da Galeria).
**Arquivos:** server/api/routers/agent.py, server/api/routers/equipamentos.py, agent/src/backup/file_manager/manager.py, agent/src/camera/rtsp_client.py
**Breaking Change:** Não (o servidor já corrige a leitura com agentes atuais; a correção do agente chega às máquinas na 1.1.15).
**Branch:** isaque

### [2026-10-20] — Visão Geral: Saúde do Servidor em destaque e layout personalizável

**Alteração:** Cada máquina da Visão Geral é um card com o nome do **cliente** como título e o nome da máquina pequeno, status do último backup, comunicação ("Atualizado agora/há N s", ou última comunicação quando offline) e a Saúde do Servidor como conteúdo principal em medidores em anel (CPU, RAM, GPU e um anel por disco) e as placas de rede físicas em linhas compactas. A página atualiza a cada 10 s. O botão "Personalizar" liga o modo de edição: arrastar e soltar para reordenar, largura por card (¼, ⅓, ½, ⅔, total, grade de 12 colunas) e escolha de quais máquinas aparecem. A escolha fica no `localStorage` do navegador (chave `trilan.overview.layout.v1`), sem mudança no servidor; máquinas novas aparecem sozinhas no fim. O card é compacto (largura padrão ¼) para ver muitas máquinas de uma vez.
**Arquivos:** server/dashboard/src/pages/Overview/ (index.tsx, layout.ts, MachineHealthCard.tsx, RingGauge.tsx), pages/Machines/MachineDetail/components/ServerHealthCard.tsx (exports), src/index.css
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-20] — Skills: três externas instaladas e as do projeto atualizadas

**Alteração:** (1) Instaladas em `.claude/skills/`, baixadas direto do GitHub e revisadas antes: `fastapi` (fastapi/fastapi@6f28852), `vercel-react-best-practices` (vercel-labs/agent-skills@063bee9) e `docker-compose-patterns` (docker/skills@38df58b). (2) Reescritas com a estrutura atual: `criar-novo-agente` (apontava para `agente_unm.py`, que não existe mais), `criar-endpoint-fastapi` (agora com REGRA-001/002/003/004/005/007 e o fluxo dashboard/PROJECT_SPEC) e `gerenciar-containers` (usa o `docker-compose.local.yml`; o de produção é só do Dokploy; testes em container). (3) `CLAUDE.md` registra como aplicar as externas neste projeto e como instalar novas sem `npx skills`.
**Arquivos:** .claude/skills/*, CLAUDE.md, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-20] — Skills só para o Claude Code

**Alteração:** As skills do projeto saem de `.agents/skills/` (lida automaticamente pelo Antigravity/agy, usado como executor) e passam para `.claude/skills/`, que só o Claude Code lê: `criar-endpoint-fastapi`, `criar-novo-agente`, `gerenciar-containers` e `find-skills`. O `professional-frontend` foi removido. O `.gitignore` versiona só `.claude/skills/`; o resto de `.claude/` (permissões locais) continua fora do git. `.agents/` fica só com `rules/git-deploy.md`.
**Arquivos:** .gitignore, .claude/skills/*, .agents/skills/* (removidos), CLAUDE.md, PROJECT_SPEC.md
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-20] — Painel: Saúde do Servidor com resumo e detalhes

**Alteração:** O card "Saúde do Servidor" da página da máquina mostra um status geral (Saudável/Atenção/Crítico, ou Offline), quando os dados foram atualizados, blocos de CPU, RAM e GPU, a lista de todos os discos (usado, livre, total e barra) e todas as placas de rede (físicas em destaque, virtuais atenuadas, com envio e recebimento). O botão "Ver detalhes" abre um modal com cada disco (sistema, usado, livre, total), memória usada/livre, cada placa de rede (física ou virtual) e a GPU com memória. A barra de rede comparada a 1 Gbps fixo saiu. Limites únicos em `telemetry.ts`: atenção acima de 75%, crítico acima de 90%. Sem mudança no agente nem na API: usa a telemetria que já chega no ping.
**Arquivos:** server/dashboard/src/pages/Machines/MachineDetail/telemetry.ts, components/ServerHealthCard.tsx, components/ServerHealthModal.tsx, components/TelemetryBar.tsx, components/MachineInfoCards.tsx, utils.ts, index.tsx
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-20] — Agente 1.1.14: Galeria RTSP para DIGIFORT e DEFENSE

**Alteração:** Equipamentos DIGIFORT e DEFENSE ganham a mesma Galeria de Câmeras do NVR (Referência Ideal + Imagem da Noite via RTSP), já que cada câmera é uma câmera IP própria (ip/usuário/senha/modelo individuais), não um canal do mesmo NVR. (1) `nvr_cameras` ganha `ip`, `username`, `password` (Fernet) e `modelo`, opcionais (NULL em NVR comum). (2) Três formas de popular a galeria: `POST .../cameras/import` (CSV/XLSX exportado do equipamento, ou `sync_from_machine=true` para copiar as câmeras avulsas tipo `CAMERA` da máquina) e `PUT/DELETE .../cameras/{canal}` para editar/remover uma câmera manualmente. (3) `GET .../cameras` resolve o canal "N/A" que DIGIFORT/DEFENSE reportam (casa pelo nome com a galeria ou usa o próximo canal livre) e devolve `ip`/`username`/`modelo`/`has_password`. (4) `POST .../test-rtsp` em equipamento DIGIFORT/DEFENSE exige `canal`, busca a câmera da galeria e monta a tarefa com `direct_camera=True` + `stream_principal=True` (sem canal de NVR); o agente (`executar_tarefa_rtsp`) captura sempre ao vivo nesse caso, para os modos `ao_vivo`/`referencia`/`noite`. (5) `GET /agent/config` envia `cameras_config` (ip/usuário/senha decriptada/modelo) de cada equipamento DIGIFORT/DEFENSE; no backup da madrugada, `capturar_imagens_noite_vms` (novo, em `rtsp_client.py`) captura 1 frame por câmera (stream principal), respeitando um orçamento de 20 min (`LIMITE_IMAGENS_NVR_S`), e envia para `POST /agent/nvr-cameras/night-image` (que agora aceita `ip`/`modelo` opcionais). DIGIFORT cruza isso com `export_cameras.csv` local (`get_detalhes_cameras`, novo); DEFENSE usa só `cameras_config` (o status de queda ainda vem do Webhook CSV). (6) Dashboard: Galeria mostra os botões "Importar CSV/XLSX", "Sincronizar da Máquina" e "+ Câmera" (editar IP/usuário/senha/modelo) quando o equipamento é DIGIFORT/DEFENSE; botões "Galeria" e "Gravações" no card do equipamento passam a aparecer para DEFENSE também (DIGIFORT já tinha).
**Arquivos:** server/api/models.py, server/api/main.py, server/api/schemas.py, server/api/routers/agent.py, server/api/routers/equipamentos.py, agent/src/camera/rtsp_client.py, agent/src/application/webhook_digifort.py, agent/src/backup/file_manager/manager.py, agent/src/olt/unm2000.py, agent/src/application/backup_job.py, agent/src/vms/defense.py, server/dashboard/src/api/types.ts, server/dashboard/src/pages/Machines/MachineDetail/hooks/useCameraImport.ts, server/dashboard/src/pages/Machines/MachineDetail/components/EqCard.tsx, server/dashboard/src/pages/Machines/MachineDetail/components/NVRCamerasGalleryModal.tsx, server/dashboard/src/pages/Machines/MachineDetail/index.tsx, agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json
**Breaking Change:** Não (NVR comum não é afetado; agente antigo em DIGIFORT/DEFENSE simplesmente não recebe `cameras_config` nem captura a imagem da noite, como hoje).
**Branch:** helena

### [2026-10-19] — Publicação de versões: release no repositório público e cadastro sob demanda

**Alteração:** (1) Ao gerar os executáveis, a release (tag = versão, título `v<versão>`, só `TrilanAgentService.exe` e `TrilanAgentTray.exe`) é publicada em `isaqueschaffer/backup-automation` (público; os agentes baixam daqui). (2) O cadastro da versão no painel é sob demanda: só quando o usuário pedir e informar a senha do painel, via `agent/publish_version.ps1`. (3) Servidor: `POST /api/v1/admin/agent-version` passa a aceitar também o header `X-Publish-Token` (variável `PUBLISH_TOKEN`; vazia = desativado), que só serve para registrar versões. Regras fixas registradas em `CLAUDE.md`.
**Arquivos:** CLAUDE.md, agent/publish_version.ps1, server/api/auth.py, server/api/config.py, server/api/routers/agent_update.py, server/.env.example
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-19] — Agente 1.1.13: nome do serviço no Windows

**Alteração:** O nome exibido do serviço em services.msc passa de "Trilan — Agente Backup NVR" para "Trilan — Agente Backup" (`_svc_display_name_` em `service.py`). Máquinas já instaladas recebem o novo nome sozinhas: `_configurar_recuperacao_servico` aplica `sc config TrilanAgentNVR DisplayName=` a cada início. O nome interno do serviço (`TrilanAgentNVR`) não mudou.
**Arquivos:** agent/service.py, agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-16] — Agente 1.1.12: reinício pelo painel e atualização OTA confiáveis

**Problema:** "Reiniciar todos" parava os agentes e eles não voltavam. Causa: o script que religa o serviço era iniciado com `DETACHED_PROCESS`; sem console o PowerShell fecha sem executar nada (1.1.9–1.1.11). Até a 1.1.8, `ping 3s && sc start` tentava uma vez só, cedo demais. No .bat da OTA, `timeout /t` não espera sem console (as pausas fixas nunca aconteceram).
**Alteração:** (1) Scripts auxiliares iniciados com `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP` e stdin/stdout/stderr nulos (nunca `DETACHED_PROCESS`). (2) Reinício por dois caminhos independentes: `SCRIPT_REINICIO` espera o processo do serviço (o bootloader) sair, tenta `Start-Service` até 5x, confere e registra em `logs/reinicio.log`; e o processo termina com `os._exit(1)`, para a recuperação do Windows (`sc failure ... restart/5000/10000/30000`, reaplicada a cada início por `garantir_recuperacao_windows`) religar em 5 s. (3) .bat da OTA: espera o processo antigo sair (até 90 s), copia com novas tentativas, inicia e confere `RUNNING` (até 5x), pausas com `ping`, log em `logs/atualizacao.log`. Uma OTA para a 1.1.12 ainda é aplicada pelo .bat da versão antiga.
**Arquivos:** agent/service.py, agent/src/application/updater.py
**Breaking Change:** Não. Cada reinício pelo painel gera no Visualizador de Eventos um aviso de "serviço terminou inesperadamente" (é o gatilho da recuperação).
**Branch:** isaque

### [2026-10-16] — Agente 1.1.11: backup sem imagem da noite; captura sem imagem cinza; galeria reorganizada

**Alteração:** (1) O backup (manual e agendado) não captura mais a imagem da noite — atrasava muito o backup. A captura é só sob demanda pela Galeria (tarefa RTSP `modo=noite`). (2) Todas as capturas ffmpeg usam `-skip_frame nokey` antes do `-i`: só quadros-chave são decodificados; antes, a conexão que começava entre dois quadros-chave gerava imagem cinza (H.265, intermitente). (3) Servidor: o relatório do agente substitui `last_recording_status`; `_manter_imagem_noite` preserva o `imagem_noite` anterior nos canais sem esse campo; falha da captura da noite pelo painel grava `FALHA`+motivo no canal (`_marcar_imagem_noite`). (4) Galeria: ações em lote no topo por tipo (Referência / Noite) com contador "x/y com imagem", "Capturar faltantes (n)" (padrão) e "Todas", progresso, cancelamento e lista de falhas; lateral com filtros Todas / Sem referência / Sem noite e chips REF/NOITE por câmera; botões de cada imagem abaixo do respectivo painel.
**Arquivos:** agent/src/application/backup_job.py, agent/src/camera/rtsp_client.py, server/api/routers/agent.py, server/api/routers/equipamentos.py, server/dashboard/src/pages/Machines/MachineDetail/components/NVRCamerasGalleryModal.tsx
**Breaking Change:** Não (agentes antigos continuam capturando a noite no backup; o servidor aceita os dois).
**Branch:** isaque

### [2026-10-16] — Agente 1.1.10: instalador, bandeja e reabertura da bandeja após atualização

**Alteração:** (1) Instalador: `--startup=auto` antes da ação (pywin32 usa getopt e ignorava a opção após `install`); `remove` antes do `install`; `PrepareToInstall` para o serviço e fecha a bandeja antes de copiar os arquivos. (2) Bandeja: "Reiniciar serviço" em um único `Restart-Service` elevado; instância única por mutex `Local\TrilanAgentTray` (por sessão). (3) A atualização OTA fecha a bandeja para trocar o arquivo; ao iniciar, o serviço (SYSTEM, sessão 0) a reabre como o usuário de cada sessão ativa/desconectada que não a tem aberta (`WTSQueryUserToken` + `CreateProcessAsUser`), só se o `TrilanAgentTray.exe` foi trocado nos últimos 15 min — não reabre uma bandeja fechada pelo usuário num reinício comum. Na atualização 1.1.9 → 1.1.10 quem aplica é o atualizador antigo; a reabertura funciona porque é feita pelo serviço novo ao iniciar.
**Arquivos:** agent/service.py, agent/tray.py, agent/installer.iss, agent/src/application/updater.py
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-15] — Reinício do agente espera o backup terminar

**Alteração:** No `/agent/ping`, se o agente informa `telemetry.backup_em_andamento` (>= 1.1.8), o servidor não entrega `restart` e mantém `restart_requested` até o ping seguinte sem backup em andamento (evita perder o backup por "Reiniciar"/"Reiniciar todos" no meio). O dashboard mostra "Reinício agendado" no cabeçalho da máquina. Agentes antigos reiniciam como antes. Backup manual não é afetado.
**Arquivos:** server/api/routers/agent.py, server/dashboard/src/pages/Machines/MachineDetail/components/MachineHeader.tsx
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-15] — Imagem da noite: limite de falhas; rodada espera máquina em backup (agente 1.1.8)

**Alteração:** (1) `capture_night_image` (Hikvision) desiste da câmera após 2 falhas de vídeo (`MAX_FALHAS_CAPTURA`) em vez de testar até 40 trechos de 25 s; Motorola testa 1 trecho por modo de horário (local/utc), no máximo 2 falhas. Há também um orçamento de 20 min por NVR para todas as imagens da noite (`LIMITE_IMAGENS_NVR_S`); câmeras restantes ficam com "Tempo limite…". (2) Trecho que atravessa a meia-noite é cortado em 00:00 (a URL usava a data pedida para início e fim, gerando intervalo invertido e 400). (3) O ping do agente informa `telemetry.backup_em_andamento`; passado o prazo (`RUN_DEADLINE_HOURS`), a rodada do Cliente espera a máquina esperada que ainda não reportou e está em backup (ping < 120 s), até `RUN_MAX_HOURS` (6 h) desde o início. Agentes < 1.1.8 mantêm o fechamento no prazo. (4) Log do agente grava só o motivo do ffmpeg, não o banner inteiro.
**Arquivos:** agent/src/camera/rtsp_client.py, agent/src/application/backup_job.py, agent/src/application/api_client.py, agent/src/application/estado.py, agent/service.py, server/api/services/backup_runs.py, server/api/config.py, server/dashboard/src/pages/Customers/CustomerDetail/components/RunDetailsModal.tsx
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-15] — Captura pela gravação: referência de câmera offline e imagem da noite sob demanda (agente 1.1.6)

**Alteração:** `POST .../equipamentos/{id}/test-rtsp` ganhou `modo` (`ao_vivo` padrão | `referencia` | `noite`) e `nome`. A tarefa vai ao agente com `modo`; agentes < 1.1.6 ignoram e capturam ao vivo.
- `referencia`: ao vivo; se falhar (câmera offline), o agente usa o frame do fim do trecho gravado mais recente, buscando do agora para trás até 15 dias (Hikvision: ISAPI em janelas de 6h; Motorola: `queryChlRecLog`).
- `noite`: madrugada (00h–06h) mais recente com gravação, da noite mais nova para a mais antiga, até 15 dias (desiste após 2 falhas de vídeo). O servidor salva em `nvr_cameras.night_image_*` e marca `imagem_noite` OK no `last_recording_status` do canal. Resposta sem `horario` (agente antigo) é recusada.
- `RTSPTestResponse` ganhou `horario` e `origem` ("ao_vivo" | "gravacao"). Espera do servidor: 35s ao vivo, 130s pela gravação (o agente encerra em ~100s); a sessão do banco é liberada durante a espera. Envio do resultado pelo agente: timeout 10s → 60s.
- Galeria: "Capturar referência" (com fallback), "Capturar imagem da noite" e "Enviar imagem"; "Atualizar todas as referências" agora inclui câmeras offline.
**Arquivos:** agent/src/camera/rtsp_client.py, agent/service.py, agent/src/application/api_client.py, agent/src/application/updater.py, agent/installer.iss, server/api/routers/equipamentos.py, server/api/schemas.py, server/dashboard/src/pages/Machines/MachineDetail/components/NVRCamerasGalleryModal.tsx, server/dashboard/package.json
**Breaking Change:** Não (sem `modo` o comportamento é o anterior; agente antigo recebe a tarefa como ao vivo).
**Branch:** isaque

### [2026-10-15] — Upload da imagem de referência; acesso às máquinas pela fila do Cliente

**Alteração:** Na Galeria do NVR, além de "Capturar da câmera" (RTSP pelo agente), o botão "Enviar imagem" sobe um arquivo do computador como referência do canal. O navegador converte para JPEG (qualidade 0,9; lado maior até 3840 px) e usa o mesmo endpoint `POST .../cameras/perfect-image`. `NVRCameraSetPerfect.image_base64` agora é validado: base64 válido, JPEG (`FF D8`), até 10 MB; aceita prefixo `data:`. Na fila do Cliente, a linha da máquina (ou o botão "Abrir") abre `/maquinas/:id`; na máquina, o cabeçalho mostra "Cliente: X › Máquina" e o voltar retorna ao Cliente.
**Arquivos:** server/api/schemas.py, server/dashboard/src/pages/Machines/MachineDetail/components/NVRCamerasGalleryModal.tsx, server/dashboard/src/pages/Machines/MachineDetail/components/MachineHeader.tsx, server/dashboard/src/pages/Machines/MachineDetail/index.tsx, server/dashboard/src/pages/Customers/CustomerDetail/components/QueueSection.tsx
**Breaking Change:** Não (a captura RTSP do agente já envia JPEG).
**Branch:** isaque

### [2026-10-14] — E-mail anexa a imagem de referência das câmeras offline

**Alteração:** O e-mail de relatório (máquina avulsa e rodada do Cliente) anexa a imagem perfeita (`nvr_cameras.perfect_image_base64`) de cada câmera não ONLINE, para o técnico identificar a câmera no local. Sem mudança no agente nem no banco.
**Regras:** só câmeras offline (mesmo critério da seção de câmeras); só a imagem de referência (não a da noite); arquivo `<nome da câmera>.jpg` (caracteres inválidos viram `_`, nomes repetidos ganham ` (2)`); no máximo 10 imagens por e-mail (`MAX_OFFLINE_IMAGES`). O corpo informa quantas foram anexadas, quantas passaram do limite e quantas câmeras offline não têm imagem cadastrada. A câmera é achada pelo NVR (máquina + nome, como no recebimento do relatório) e pelo canal.
**Arquivos:** server/api/services/email_service.py, server/api/services/backup_runs.py, server/api/routers/agent.py, server/api/routers/backups.py, server/api/tests/test_email_offline_images.py
**Breaking Change:** Não (`machine_id` é parâmetro opcional; sem ele o e-mail sai sem imagens).
**Branch:** isaque

### [2026-10-14] — Backup e e-mail por Cliente (rodadas)

**Alteração:** Cliente com várias máquinas recebe 1 e-mail por rodada de backup, com o relatório de todas as máquinas e um ZIP unificado.
**Antes:** 1 e-mail por upload de cada máquina, para os e-mails da máquina (5 máquinas = 5 e-mails); máquina sem ZIP não gerava e-mail.
**Depois:**
- Nova tabela `customer_backup_runs` e `backups.run_id`; `client_groups.email_to` (populado na criação com a união dos e-mails das máquinas). Migração inline idempotente; datetimes naive (REGRA-001).
- Rodada `scheduled` (aberta no 1º relatório agendado), `queue` (aberta no backup em fila do cliente) e `manual_machine` (backup avulso de uma máquina: e-mail só dela). Fecha quando todas as máquinas esperadas reportaram + 90 s para o ZIP chegar (`RUN_UPLOAD_GRACE_SECONDS`), ou no prazo de 2 h (`RUN_DEADLINE_HOURS`); fila que termina pulando máquinas offline fecha logo após o último ZIP. Quem não reportou aparece como "não executou".
- Fechamento por tarefa de fundo a cada 30 s (`services/backup_runs.py`, 1 worker uvicorn) com `UPDATE ... WHERE closed_at IS NULL` para nunca enviar o e-mail duas vezes.
- E-mail do cliente (`send_customer_report`): resumo por máquina, seções de câmeras e backup de cada máquina e link `PUBLIC_URL/api/v1/backups/public-run-download/{run_id}` (sem `PUBLIC_URL`, diz "ZIP disponível no painel"). Máquina sem cliente: e-mail por upload como antes.
- E-mails da máquina com cliente são os do cliente (PUT alterando = 400). Painel: e-mails no cliente, seção "Rodadas de backup" (detalhes, baixar ZIP, reenviar), e-mail travado na máquina.
**Requisito de produção:** definir `PUBLIC_URL` no `.env` para o link do ZIP sair no e-mail automático.
**Verificação:** simulação com SMTP interceptado (rodada completa, máquina faltando, avulso, fila, cancelamento, máquina sem cliente, downloads, reenvio, duplicidade, contrato do agente inalterado) e as 45 chamadas do painel conferidas contra a API.
**Breaking Change:** Não para o agente. A API admin ganhou campos e rotas (o painel foi atualizado junto).
**Branch:** isaque

### [2026-10-14] — Cliente e Máquina reorganizados; fila com arrastar e soltar

**Alteração:** Nomenclatura única (ver ADR-007) em telas, código e API admin; telas planas por entidade.
**Antes:** A lista de máquinas se chamava "Clientes" e criava "Novo Cliente"; clientes apareciam como "Unidade"; a posição na fila era digitada; não havia como remover máquina de um cliente; máquinas de um cliente eram vistas num acordeão.
**Depois:**
- Backend: `Machine`/`Customer` (ORM com colunas antigas), `routers/machines.py` e `routers/customers.py`; novas rotas para vincular/remover máquina e reordenar a fila (409 com fila ativa; fila renumerada ao remover); filtros `customer_id`/`unassigned` em máquinas e `machine_id`/`customer_id` em backups; `BackupResponse` com máquina e cliente; `StatsResponse` com `machines_total`, `machines_active`, `customers_total`; e-mail diz "Máquina:".
- Dashboard: `/clientes`, `/clientes/:id` (fila com arrastar e soltar nativo, adicionar/remover máquina, backups do cliente), `/maquinas`, `/maquinas/:id` (cliente com link; horário travado quando herdado); Backups com colunas e filtros de Cliente e Máquina.
- Contrato JSON admin: `group_id/group_name` → `customer_id/customer_name`; `agents_total/online` e `clients` → `machines_total/online` e `machines`; `client_id/client_name` em backups → `machine_id/machine_name`; NVR e logs usam `machine_id`.
**Verificação:** simulação do app real (SQLite) cobrindo vínculo, fila, horário herdado, filtros e o fluxo do agente; as 42 chamadas do dashboard conferidas contra as 51 rotas do OpenAPI; `tsc` e `vite build` sem erros.
**Breaking Change:** Sim para a API admin (só o dashboard a consome, atualizado junto). Não para o agente.
**Branch:** isaque

### [2026-10-14] — Agente 1.1.5: correções da auditoria

**Alteração:** Versão do agente elevada para 1.1.5 para distribuir, via OTA, as correções da auditoria (todos os clientes estavam na 1.1.4, e o OTA só atualiza para versão maior).
**Inclui:** não loga credenciais de câmera; OTA defensivo (exige https, exceção não derruba o serviço); `buscar_trechos` sem "dummy"; `rtsp_task` não se perde durante backup manual; timeouts em mysqldump/Mikrotik; `ConfigError`; hidden-imports no build.
**Atenção:** Atualizações OTA com URL `http://` passam a ser ignoradas (use https no GitHub Release).
**Arquivos:** agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-13] — Auditoria geral: correções, reestruturação do repositório e do dashboard

**Alteração:** Auditoria por área (API, dashboard, agente, higiene do repositório) seguida das correções seguras.
**Repositório:** `agent/dist`, `__pycache__` e `.claude/settings.json` deixam de ser versionados; removidos `.bat` com API key, `index.xml`, `scratch_test/` (config real de OLT), imagens de teste e arquivos soltos da raiz; scripts avulsos em `tools/`, legado em `archive/legacy_scripts/`; `.gitignore` ampliado. Seção 3 e rotas da seção 8 reescritas conforme o código.
**API:** corrige `UnboundLocalError` do auto-recovery do ping (importava `AgentLog` depois do uso); upload de ZIP sem path traversal, em streaming (`MAX_UPLOAD_MB`) e fora do event loop; ping libera a sessão do banco no long-poll; `test-rtsp` devolve 409 se já houver tarefa; `compare_digest` em senha admin e API key; `backup_hour/minute` validados na entrada (respostas sem limite); `group_id` inexistente = 404; lixeira só após o commit; menos N+1; `update-check` escolhe a maior versão ativa e valida X.Y.Z/SHA-256; migrações inline com um ALTER por transação e logging.
**Agente:** não loga credenciais de `rtsp_task` nem senha da URL RTSP; OTA defensivo (https obrigatório, `tmp_dir` limpo, exceção não derruba o serviço); `buscar_trechos` não devolve mais "dummy" (busca inconclusiva cai nos horários fixos); pings drenados durante backup manual não perdem o `rtsp_task`; timeouts em mysqldump e Mikrotik; `ConfigError` no lugar de `sys.exit`; hidden-imports adicionais no `build.ps1`.
**Dashboard:** `ClientDetail.tsx` (~1580 linhas) dividido em `pages/ClientDetail/` (index, utils, components, hooks); `utils/date.ts`; aliases CSS das variáveis inexistentes; tipos alinhados ao backend; tratamento de erro/corrida nos carregamentos; correção do 422 ao editar máquina sem grupo e da regex `\s` nos nomes de arquivo; `tsc` e `vite build` verificados em cópia fora do projeto.
**Pendente (decisão do dono):** IC-007 a IC-009 e IC-012; rotacionar a API key do agente e a `SECRET_KEY`/senha de dev que estavam versionadas; reescrever o histórico do git para tirar EXEs e segredos.
**Breaking Change:** Não nos contratos de API. Uploads acima de `MAX_UPLOAD_MB` agora recebem 413; atualizações OTA com URL `http://` deixam de ser aplicadas.
**Branch:** isaque

### [2026-10-13] — Ações em massa: reiniciar/backup de todos os clientes e atualizar todas as referências da galeria

**Alteração:** Três botões novos, sem mudança no agente.
**API:** `POST /api/v1/machines/restart-agent-all` e `POST /api/v1/machines/trigger-backup-all` marcam `restart_requested` / `backup_requested` em todos os clientes ativos e online (ping < 180s); offline ficam de fora. Resposta: `{"queued": n, "skipped_offline": m}`. Reaproveitam o fluxo existente de flags consumidas no ping.
**Dashboard:** tela Clientes ganha "Reiniciar todos" e "Backup de todos" (com confirmação). Na galeria do NVR, "Atualizar todas as referências" atualiza uma câmera por vez (todas as não OFFLINE), com progresso, cancelar e resumo de falhas; é sequencial porque `pending_rtsp_tasks` guarda uma única tarefa RTSP por cliente (~15–20s por câmera, limitado pelo ping do agente).
**Arquivos:** server/api/routers/clients.py, server/dashboard/src/api/client.ts, server/dashboard/src/pages/Clients.tsx, server/dashboard/src/pages/ClientDetail.tsx
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-13] — Agente 1.1.4: Galeria/imagem da noite para NVR Motorola (NVMS-9000)

**Alteração:** Captura da imagem da noite e da referência ideal passa a funcionar em NVR Motorola, e a galeria lista as câmeras Motorola.
**Antes:** O backup marcava toda câmera Motorola como `NAO_SUPORTADO`; a referência usava a URL RTSP da Hikvision (404); o canal Motorola era reportado como GUID (`{0000000N-0000-...}`) e o servidor descartava (`int()` falhava), então a galeria ficava vazia.
**Depois:**
- RTSP Motorola: ao vivo `rtsp://.../chID=N&streamType=main`; playback `chID=N&date=AAAA-MM-DD&time=HH:MM:SS&timelen=10&streamType=main`. A rota `test-rtsp` agora envia também `marca` (NVR guarda a marca em `config_extra.marca`, não em `modelo`).
- `factory.py`: o canal Motorola é reportado como inteiro (N do GUID; GUID original em `canal_guid`) e com `dias_com_gravacao`. O servidor também converte GUID de relatórios de agentes antigos (`_canal_int`).
- `motorola/recordings.py`: `buscar_trechos_motorola` usa `queryChlRecLog` (mesmo comando da tela de gravação do NVR; resposta em UTC; erro `noRecord` = sem gravação) para achar o trecho real da madrugada.
- `rtsp_client.capture_night_image_motorola`: 02:00 limitado ao trecho (até 2 trechos por interpretação de horário). Alguns NVRs (ex.: relógio/fuso reconfigurado) exibem/reproduzem no horário UTC cru da busca em vez do fuso local; o agente testa as duas interpretações ("local"/"utc") e lembra a que funcionou por NVR (`_MODO_HORARIO_MOTOROLA`). Sem gravação na madrugada = `SEM_GRAVACAO`; busca falhou = horários fixos como fallback.
- `backup_job.py`: um login Motorola para todas as câmeras; antes das 06h usa o último dia anterior a hoje (a madrugada de hoje ainda não terminou).
**Validação (8 NVRs Motorola, VPN, madrugada de 12/10):** imagem capturada na grande maioria das câmeras com gravação; as restantes são `SEM_GRAVACAO` ou falha com motivo (NVR lista trecho mas não entrega o vídeo em 1–3 canais por NVR).
**Limitação conhecida:** num NVR com fuso divergente e gravação contínua, a interpretação errada do horário poderia devolver um quadro de outro horário; o horário reportado é o solicitado ao NVR.
**Arquivos:** agent/src/camera/rtsp_client.py, agent/src/nvr/factory.py, agent/src/nvr/motorola/recordings.py, agent/src/application/backup_job.py, agent/src/application/updater.py, agent/installer.iss, server/api/routers/equipamentos.py, server/dashboard/package.json
**Breaking Change:** Não. Relatórios Motorola passam a trazer `canal` inteiro; o servidor aceita os dois formatos.
**Branch:** isaque

### [2026-10-09] — Agente 1.1.3: Captura de imagem da noite via histórico ISAPI e Galeria unificada

**Alteração:** Agente busca trechos de gravação na madrugada via ISAPI (`buscar_trechos`) antes de tentar baixar a imagem via RTSP, evitando tentativas cegas (e timeouts) em NVRs que não têm gravação. A galeria do NVR agora une os dados da tabela `nvr_cameras` com `last_recording_status`, listando todas as câmeras gravadas (mesmo as que falharam na imagem).
**Antes:** O ffmpeg tentava baixar 15s de RTSP em horários fixos. Câmeras sem gravação ficavam até 15s bloqueadas. A galeria só mostrava câmeras com imagem capturada com sucesso (`nvr_cameras`).
**Depois:** A galeria lista todas as câmeras. Falhas mostram o motivo (traduzido do log do ffmpeg).
**Arquivos:** `agent/src/nvr/hikvision/recordings.py`, `agent/src/camera/rtsp_client.py`, `agent/src/application/backup_job.py`, `agent/src/application/api_client.py`, `server/api/schemas.py`, `server/api/routers/equipamentos.py`, `server/dashboard/src/pages/ClientDetail.tsx`
**Breaking Change:** Não.
**Branch:** isaque

### [2026-10-09] — Agente 1.1.2: ping em cadência fixa + telemetria sem NaN

**Alteracao:** Ping do agente movido para thread própria com cadência fixa de 15s (início a início); telemetria sanitizada; "Próximo contato (estimado)" sincronizado com o ping real.
**Antes:** O ping só era verificado quando o loop principal acordava (espera de até 60s, e bloqueado durante backups), então saía a cada ~60s enquanto o dashboard contava 15s e ficava em 00:00. GPUtil devolvia NaN para campos `[N/A]` do nvidia-smi e o `requests` recusava serializar o JSON, derrubando todos os pings (cliente aparecia offline e não recebia OTA).
**Depois:** `service.py` roda `_ping_loop` em thread (`PING_INTERVAL_S = 15`); as instruções do ping são enfileiradas e executadas no loop principal via evento `hPingResp`. `hWaitStop` virou manual-reset para as duas threads verem a parada. `api_client._json_safe` troca NaN/inf por null e falha de telemetria não impede o ping. Dashboard mostra "aguardando…" ao passar do horário e consulta o cliente a cada 1s por até 30s.
**Imagem de referência (1.1.2):** `rtsp_client.test_rtsp_camera` passa a capturar o stream principal (`{canal}01` / `subtype=0`) quando a tarefa traz `canal` (galeria do NVR), igual à origem da imagem da noite; antes usava o secundário (`{canal}02` / `subtype=1`), com resolução e proporção diferentes. O teste de câmera direta (sem canal) continua no secundário.
**Galeria do NVR (dashboard):** os painéis "Referência Ideal" e "Último backup (noite)" usam o mesmo componente `CameraImagePanel`, com `object-fit: contain` (quadro inteiro, sem corte) e a resolução da imagem ao lado do título. Antes eram dois blocos duplicados com `cover`, que cortava imagens fora de 16:9.
**Arquivos:** agent/service.py, agent/src/application/api_client.py, agent/src/camera/rtsp_client.py, agent/src/application/updater.py, agent/installer.iss, server/dashboard/src/pages/ClientDetail.tsx, server/dashboard/package.json
**Breaking Change:** Não. Clientes na 1.1.1 com GPU que retorna NaN não pingam e portanto não recebem OTA: atualizar manualmente.
**Branch:** isaque

---

### [2026-10-09] — Versão do agente 1.1.1

**Alteracao:** Versão do agente elevada para 1.1.1 (build com telemetria psutil/GPUtil do merge `helena`).
**Antes:** `CURRENT_VERSION = "1.1.0"`, `AppVersion=1.1.0`.
**Depois:** `CURRENT_VERSION = "1.1.1"`, `AppVersion=1.1.1`, dashboard `package.json` 1.1.1.
**Arquivos:** agent/src/application/updater.py, agent/installer.iss, server/dashboard/package.json
**Breaking Change:** Não. Requer build (`agent/build.ps1`), GitHub Release v1.1.1 e registro no OTA Manager.
**Branch:** isaque

---

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

### [2026-10-23] — Telemetria de NVR Motorola (NVMS-9000 / TVT)

**Alteração:** Suporte completo à telemetria de NVRs Motorola (protocolo NVMS-9000 / arquitetura TVT, modelo MTR16IP / TD-3116B2).
**Implementação:**
- Módulo `agent/src/nvr/motorola/telemetry.py` integrado à `factory.coletar_telemetria_nvr`.
- Autenticação com desafio SHA-512 (`reqLogin`/`doLogin`) e fallback Base64.
- Coleta de Rede: status de interface (`nicStatus` online -> `UP`), IP, MAC, e taxa de transferência real extraída de `<bandwidth>` (`totalBandwidth` - `remainBandwidth` para Rx de câmeras; `sendTotalBandwidth` - `sendRemainBandwidth` para Tx de visualização).
- Coleta de Discos: status de operação (`queryDiskStatus` read/write -> `OK`), dados S.M.A.R.T (`queryDiskSmartInfo`: temperatura em °C, dias de operação `powerOnDays`, integridade física).
- CPU e RAM: tratados como nulos de forma segura (`—`), exibindo traço no modal de telemetria do dashboard (`NVRTelemetryModal.tsx`).
- Script de diagnóstico e dump offline: `teste backup motorola/dump_motorola_telemetria.py`.
**Arquivos:** `agent/src/nvr/motorola/telemetry.py`, `agent/src/nvr/factory.py`, `teste backup motorola/dump_motorola_telemetria.py`
**Breaking Change:** Não
**Branch:** helena

---

### [2026-11-24] — Servidor MCP (Claude, ChatGPT, Gemini)

IA conectada ao sistema pelo Model Context Protocol, em `server/api/mcp_server/` (dentro do Backend, sem serviço novo no Dokploy).
- **Endereço:** `POST https://server.suportetrilan.com.br/mcp` (Streamable HTTP sem estado, respostas JSON; GET/DELETE = 405).
- **Ferramentas:** geradas das rotas do painel (`/api/v1`) que usam `get_contexto` e afins, com o esquema do OpenAPI (~100). Ficam de fora `/api/v1/auth`, `/api/v1/mcp`, `/api/v1/public`, `/api/v1/agent`, o cadastro de versão OTA e uploads multipart. Rota só do super admin só aparece para ele; o super admin escolhe a conta pelo argumento `contexto_conta_id` (vira `X-Conta-ID`). GET = `readOnlyHint`; DELETE, `*-all`, `rotate-key` = `destructiveHint` (o app pede confirmação). Rota nova do painel entra sozinha.
- **Execução:** a ferramenta chama a rota dentro do processo (ASGI) com um JWT de 5 min do usuário com `"via": "mcp"`: valem papel, somente leitura e REGRA-010; a Auditoria grava `<e-mail> (IA via MCP)` (`Contexto.feito_por`). Senhas aparecem como no painel (decisão do usuário).
- **Quem conecta:** só `SUPER_ADMIN` e `ADMIN` com e-mail (o login legado só com senha não).
- **Autenticação:** OAuth 2.1 para Claude, ChatGPT e app do Gemini (metadados RFC 9728/8414 em `/.well-known/...`, registro dinâmico `POST /oauth/register` e client_id por URL (CIMD, só HTTPS em IP público), login em `/oauth/authorize`, PKCE S256 obrigatório, `POST /oauth/token` com access de 1 h e refresh de 90 dias com rotação, `POST /oauth/revoke`). Token pessoal (`trilan_mcp_...`, sem validade) para Antigravity/Gemini CLI, criado em "Minha conta". Trocar a senha ou o papel derruba todos os acessos (`token_versao`).
- **Tabelas novas:** `mcp_tokens` (só o SHA-256), `mcp_oauth_clientes`, `mcp_oauth_codigos` (criadas pelo `create_all`).
- **Rotas do painel:** `GET /api/v1/mcp/info`, `GET|POST /api/v1/mcp/tokens`, `DELETE /api/v1/mcp/tokens/{id}`. Tela: card "Conectar IA (MCP)" em Minha conta.
- **Imagens (`mcp_server/imagens.py`):** fotos em base64 dentro do JSON (`image_base64`, `perfect_image_base64`, `night_image_base64`) saem do texto e vão como conteúdo de imagem do MCP (até 4 por resposta, 8 MB); no JSON fica `[IMAGEM n]`. Antes, a foto ia como texto e era cortada em 80 mil caracteres.
- **Incidente 24/11/2026 13:13 (-03):** a primeira versão da `ver_imagem_camera` lia a galeria inteira (todas as fotos de um NVR grande, dezenas de MB) a cada chamada; o Claude disparou várias em paralelo, o pool do banco esgotou e o uvicorn chegou a 3,9 GB e foi morto por falta de memória (VM de 5 GB, 1 CPU), derrubando junto o Postgres e o Dokploy por alguns minutos. Correção: `GET /api/v1/machines/{id}/equipamentos/{eq}/cameras/{canal}/imagem` (rota `ver_imagem_camera`, carrega só um canal); `get_nvr_cameras` ganhou `incluir_imagens` (o MCP sempre manda `false`: não carrega as fotos e põe um aviso no lugar; o painel continua igual); no máximo 3 chamadas de ferramenta ao mesmo tempo; resposta acima de 15 MB não é aberta.
- **Config opcional:** `MCP_BASE_URL` (vazio = deduz de `X-Forwarded-Proto/Host`).
- **Painel 24 h (mesmo dia):** `POST /api/v1/auth/renovar` (o painel renova o JWT a cada 30 min) e `/version.json` no build do painel (recarrega sozinho após deploy).
