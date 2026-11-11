# Agente Windows da Trilan: como funciona

Documento sobre os executáveis do agente que roda na máquina do cliente (versão 1.1.43). Descreve o que cada
executável faz, o que acontece desde a instalação, as rotinas em segundo plano, o ciclo do backup, a comunicação
com o servidor e a atualização automática (OTA).

## 1. Visão geral

O agente fica em um PC ou servidor Windows na mesma rede dos equipamentos do cliente (NVRs, OLTs, PABX, Mikrotik,
VMS). Ele **não decide nada sozinho**: a lista de equipamentos, as credenciais, o horário do backup e a senha do ZIP
vêm do servidor a cada ciclo. O único dado local é o `agent.conf` (URL do servidor, Client ID e API Key).

```
 Rede do cliente                                   Nuvem
┌──────────────────────────────┐             ┌──────────────────────┐
│ NVR / OLT / PABX / Mikrotik  │             │  API (FastAPI)       │
│ Digifort / Defense           │◄───────────►│  + Painel (React)    │
│            ▲                 │  HTTPS/HTTP │                      │
│            │ HTTP, SNMP,     │  X-Client-ID│  /api/v1/agent/...   │
│            │ Telnet, SSH, FTP│  X-API-Key  │                      │
│  ┌─────────┴───────────┐     │             └──────────────────────┘
│  │ TrilanAgentService  │─────┼─► ping, config, relatório, ZIP, logs
│  │ (Serviço Windows)   │     │
│  └─────────▲───────────┘     │
│            │ evento Windows  │
│  ┌─────────┴───────────┐     │
│  │ TrilanAgentTray     │     │  ícone na bandeja (controle manual)
│  └─────────────────────┘     │
└──────────────────────────────┘
```

## 2. Os executáveis

| Arquivo | Origem | Função |
|---|---|---|
| `TrilanAgentService.exe` | `service.py` (PyInstaller `--onefile`, console) | O agente de verdade: Serviço Windows `TrilanAgentNVR`, nome exibido "Trilan — Agente Backup". Roda como SYSTEM. |
| `TrilanAgentTray.exe` | `tray.py` (PyInstaller `--onefile --windowed`) | Ícone na bandeja para o usuário controlar o serviço. Não faz backup. |
| `TrilanAgentSetup.exe` | `installer.iss` (Inno Setup) | Instalador para máquinas novas. Empacota os dois acima. |

Só o Service e o Tray são cadastrados no painel para a atualização automática; o Setup serve para máquinas novas.

Os módulos do pacote `src/` são empacotados dentro do Service. `build.ps1` lista os `--hidden-import` necessários
(`updater`, `backup_job`, webhooks, `huawei_active`, `psutil`, `GPUtil`, ffmpeg, `pysnmp`...). Módulo novo que só é
importado dentro de função precisa entrar nessa lista, ou o executável falha em tempo de execução.

## 3. Instalação (`TrilanAgentSetup.exe`)

1. Pede ao instalador: **URL do servidor**, **Client ID** e **API Key** (valores gerados no painel). Os três são
   obrigatórios.
2. Antes de copiar, para o serviço e encerra a bandeja e o processo antigo (executável em uso não pode ser
   substituído).
3. Copia os executáveis para `C:\Program Files (x86)\Trilan NVR Backup Agent` e grava o `agent.conf`:
   ```ini
   [server]
   url = <URL do servidor>

   [auth]
   client_id = <Client ID>
   api_key = <API Key>
   ```
4. Registra o serviço (`remove` e depois `--startup=delayed install`), configura início **automático atrasado** e
   **recuperação de falhas** (reinicia em 5 s, 10 s e 30 s, zera a contagem após 24 h), e inicia.
5. Cria regras de firewall de entrada na porta TCP 21 para os dois executáveis (usada pelo FTP da OLT Huawei, ver §7)
   e um atalho na inicialização do Windows para a bandeja.
6. Na desinstalação: para e remove o serviço, encerra a bandeja e remove as regras de firewall.

O início atrasado evita o erro 1053: o executável de arquivo único leva alguns segundos para se descompactar no boot,
e o Windows daria timeout de 30 s num serviço de início normal.

## 4. O serviço (`TrilanAgentService.exe`)

### 4.1 Inicialização

- `SvcDoRun` avisa o Windows de que está "em execução" imediatamente, antes de qualquer trabalho pesado.
- Em threads de apoio, reaplica o início atrasado e as políticas de recuperação (auto-cura, mesmo em máquinas
  atualizadas por OTA) e reabre a bandeja se ela acabou de ser atualizada (§8).
- O ciclo principal roda dentro de um laço de resiliência: se estourar erro inesperado, registra, espera 10 s e tenta
  de novo. O processo nunca sai com código 0 por engano, para o Windows poder reiniciá-lo.

### 4.2 Leitura da configuração

`_load_schedule_and_run`:

1. Lê o `agent.conf` (pasta do executável). Se faltar ou estiver malformado, registra o erro e tenta de novo depois.
2. Busca `GET /api/v1/agent/config`. Da resposta tira a hora e o minuto do backup (`backup_hour`, `backup_minute`).
3. Se o servidor estiver fora do ar, usa 02:00 e sincroniza sozinho quando a conexão voltar.
4. Inicia os monitores locais de Digifort e Defense, conforme os equipamentos retornados (§6).

### 4.3 Threads em segundo plano

Todas são daemon e terminam no evento de parada do serviço.

| Thread | Intervalo | O que faz |
|---|---|---|
| Ping | 15 s | `POST /agent/ping` com a telemetria da máquina. A resposta traz as instruções (backup, reinício, teste RTSP). |
| Presença das câmeras | 5 min (1ª após 90 s) | Lê online/offline das câmeras dos equipamentos e envia a `/agent/cameras/status`. Pula se há backup em andamento. |
| Imagem da noite | 10 min (1ª após 120 s) | Só entre 19h30 e 4h: captura um quadro ao vivo por RTSP das câmeras Digifort/Defense, uma vez por noite e por câmera; repete as que falharam a cada 30 min. |
| Status das OLTs | 5 min (1ª após 150 s) | Coleta ONUs, PONs, placas e sinal óptico e envia a `/agent/olt/status`. |
| Vigia de backup | 1 min | Se um backup passa de **6 h**, reinicia o serviço à força (§5.4). |
| Logs remotos | 20 s | Envia os logs acumulados ao servidor (§9). |

O **loop principal** só cuida do agendamento. Calcula o próximo horário, dorme em fatias de até 5 s esperando um destes
eventos: parada do serviço, **backup manual** (evento `Global\TrilanAgentNVR_RunNow`, acionado pela bandeja) ou
**resposta de ping** com instrução. Chegando a hora, executa o backup.

### 4.4 Instruções recebidas no ping

Processadas pelo loop principal, nesta ordem:

1. Se ainda não tinha carregado a configuração (subiu sem rede), busca agora e recalcula o horário.
2. **Teste RTSP** (`rtsp_task`): executado em thread própria, o resultado volta em `/agent/rtsp-result`. A galeria de
   câmeras do painel usa isso.
3. **`restart`**: reinicia o serviço (§5.4).
4. **`backup`**: backup manual disparado pelo painel. Pings repetidos com o mesmo comando acumulados durante a
   execução são descartados.
5. Verificação de **atualização OTA** (§8), no máximo uma vez por hora.

### 4.5 Proteções do backup

- **Duplicata**: ignora um backup que comece menos de 60 s após o fim do anterior.
- **Limite por equipamento**: cada equipamento roda numa thread com limite de **2 h**. Passou disso, vira `ERRO` e o
  backup segue com o próximo.
- **Vigia de 6 h**: cobre o que o limite por equipamento não pega.
- Estado compartilhado (`estado.py`): `backup_em_andamento` e `backup_inicio`. O ping informa isso ao servidor, que
  não fecha a rodada do cliente enquanto a máquina ainda faz backup.

## 5. O backup (`backup_job.run_backup`)

### 5.1 Sequência

1. Carrega o `agent.conf` e busca a configuração do servidor: `equipamentos` (ou o campo legado `nvrs`),
   `zip_password`, `client_name` (a máquina) e `customer_name` (o cliente).
2. Descarta equipamentos do tipo `CAMERA`.
3. Recria as pastas temporárias `tmp_backup_work` e `tmp_backup_final` ao lado do executável.
4. Para cada equipamento, em sequência: roda o processador do tipo dentro do limite de 2 h, grava o resultado na
   pasta de trabalho e gera um `backup.zip` interno (sem senha) em `<TIPO>/backup_<tipo>_<nome>/`.
5. Envia o **relatório** a `POST /agent/backup/report` com o status de cada equipamento e a telemetria. O servidor
   devolve um `backup_id`.
6. Com o `backup_id`, monta **um único ZIP da máquina** (`backup_<Maquina>_<dd-mm-aaaa>.zip`), criptografado com
   **AES** e a `zip_password`, e o envia a `POST /agent/backup/upload/<backup_id>`.
7. Apaga as pastas temporárias.

Um equipamento que falha não derruba o backup: ele recebe `ERRO` e a rodada continua.

Status final da rodada: `OK` se todos OK, `ERROR` se todos falharam, `PARTIAL` nos demais casos. Os status por
equipamento incluem `OK`, `PARCIAL`, `ERRO`, `SEM_ARQUIVOS`, `JA_PROCESSADO`, `TIPO_NAO_SUPORTADO` e os de backup de
arquivo (`BACKUP_ANTIGO`, `BACKUP_INCOMPLETO`, `BACKUP_INCONSISTENTE`, `BACKUP_NAO_ENCONTRADO`,
`BACKUP_EM_PROCESSAMENTO`, `BACKUP_CORROMPIDO`).

### 5.2 Gatilhos

`scheduled` (horário), `manual` (bandeja), `manual_dashboard` (painel). O gatilho viaja no relatório.

### 5.3 Processador por tipo de equipamento

| Tipo | Módulo | O que o agente faz |
|---|---|---|
| `NVR` | `src/nvr` | Detecta a marca, lista as câmeras, confere gravação, coleta telemetria e baixa a configuração. Detalhes em §5.5. |
| `OLT` / `DIGIFORT` | `src/olt` | Backup por fabricante: `vsol` (HTTP, baixa `usrcfg.conf`), `huawei` (ativo, via FTP), `unm`/`unm2000` (copia arquivos exportados pelo UNM2000 de uma pasta local, `pasta_origem`). No gatilho manual pede uma exportação nova antes de copiar. |
| `PABX` | `src/pabx/issabel.py` | Faz login no Issabel, dispara o backup completo e baixa o `.tar`. |
| `MIKROTIK` | `src/mikrotik/routeros.py` | SSH (paramiko) e baixa o backup do RouterOS. |
| `DEFENSE` | `src/vms/defense.py` | API do Defense (autenticação por assinatura) para exportar o backup do VMS. |
| outros | | Retornam `TIPO_NAO_SUPORTADO`. |

O fabricante da OLT é lido de `fabricante`, depois de `config_extra`; na falta, é deduzido do nome do equipamento.

### 5.4 Reinício

Pedido pelo painel (instrução `restart`) ou pelo vigia de backup travado. Dois caminhos independentes:

1. Um script PowerShell fora do processo espera o serviço encerrar e o inicia de novo (até 5 tentativas), gravando em
   `reinicio.log`.
2. O processo termina com código de erro e a recuperação do Windows o religa em 5 s.

Se há backup em andamento, o loop principal está preso nele e não leria o comando. Por isso a thread de ping trata o
reinício direto e encerra o processo na hora.

### 5.5 Backup de NVR em detalhe

1. `buscar_cameras` identifica a marca. Com `marca` no `config_extra` (HIKVISION, INTELBRAS, MOTOROLA) usa a marca
   informada; sem ela, tenta Hikvision (ISAPI), depois Intelbras (CGI Dahua), depois Motorola.
2. `verificar_gravacao_nvr` confere, por câmera, se há gravação nos últimos 15 dias (mapa `█░`) e calcula quantos
   dias o NVR guarda (busca binária, limite de 730 dias). Marca `online`, `status_comunicacao` e `status_gravacao`
   (`COM_GRAVACAO`, `SEM_GRAVACAO`, `NAO_VERIFICADO`). Hikvision usa 10 threads, Intelbras 5.
3. Telemetria do NVR: Hikvision por ISAPI, Intelbras por SNMP (porta 161; comunidade em `snmp_community`), Motorola
   por HTTP/XML.
4. Configuração:
   - **Hikvision**: baixa `CONFIG_NVR_<data>.bin` (cifrado com a senha do ZIP) e `CONFIG_IPCAM_<data>.xls`.
   - **Intelbras**: baixa `CONFIG_INTELBRAS_<data>.backup` pelo CGI.
   - **Motorola**: não há backup restaurável; só verifica a gravação e o status fica `SEM_ARQUIVOS`.
5. Gera uma **planilha** `.xlsx` com a configuração lida do equipamento, colocada em `NVR/PLANILHA/` do pacote final.
   Falha da planilha nunca altera o status do backup.

Se o NVR não responde e a marca não foi identificada, o resultado é `ERRO` (acesso ou login).

## 6. Monitores locais (Digifort e Defense)

Iniciados ao carregar a configuração, só quando há um equipamento do tipo correspondente.

- **Digifort**: monitoramento por **ping ICMP** a cada 60 s das câmeras listadas no cadastro (`cameras_config`) e
  numa exportação em CSV. Registra as quedas em `quedas_cameras.csv`. A presença das câmeras lê o último estado.
- **Defense**: servidor HTTP local na **porta 8181**, que recebe os webhooks de falha e de normalização das câmeras
  e grava em `status_cameras.csv`.

A porta 8181 precisa estar liberada no firewall da máquina para o Defense enviar os avisos.

## 7. Integração com OLTs

- **UNM2000 (FiberHome)**: o agente roda no próprio servidor da UNM2000. Lê ONUs, PONs e placas por **Telnet** (porta
  23) e os nomes das ONUs no MySQL local. O `README.md` descreve a credencial de leitura e as variáveis
  `TRILAN_UNM_*`.
- **VSOL**: HTTP/HTTPS. Faz login em `/action/login.html`, mantém a sessão e baixa a configuração.
- **Huawei**: o backup ativo pede à OLT que envie o arquivo por FTP ao agente (descobre o IP local com rota para a
  OLT), por isso a regra de firewall da porta 21. O status é coletado por SSH.

## 8. Atualização automática (OTA)

Roda no processo do serviço, no máximo uma vez por hora (`_UPDATE_CHECK_INTERVAL`), junto do tratamento do ping.

1. `GET /agent/update-check?current_version=<versão>`.
2. Se `has_update`, valida o retorno: precisa de URL e SHA-256 do Service, e as URLs precisam ser **https**. O Tray é
   opcional.
3. Baixa os executáveis para uma pasta temporária e confere o **SHA-256**. Qualquer divergência cancela a atualização.
   Se só o Tray falhar, o Service é atualizado mesmo assim.
4. Gera um `apply_update.bat` (a versão vinda do servidor é filtrada para caracteres seguros) e o executa
   **fora do processo do serviço**. O script:
   - para o serviço (e mata o Tray, se ele também será atualizado);
   - espera até ~45 s o processo antigo sair, e se não sair o encerra à força;
   - copia os arquivos novos, com até 15 tentativas;
   - reaplica o início atrasado e a recuperação de falhas;
   - inicia o serviço (até 5 tentativas) e confere se está `RUNNING`;
   - registra tudo em `atualizacao.log` e apaga a si mesmo.
5. O serviço informa "parado" ao Windows e sai na hora (`os._exit(0)`), senão a recuperação religaria a versão antiga.
6. Ao subir já na versão nova, o serviço reabre a bandeja em cada sessão de usuário (console ou RDP), **somente se**
   o `TrilanAgentTray.exe` foi trocado nos últimos 15 min. Assim não reabre uma bandeja que o usuário fechou.
   Como o serviço roda na sessão 0, ele usa o token do usuário de cada sessão para abrir a janela.

A versão fica em três lugares: `updater.py` (`CURRENT_VERSION`), `installer.iss` e `server/dashboard/package.json`.
O cadastro da versão no painel libera a atualização para todos os agentes.

## 9. Logs

| Arquivo | Conteúdo |
|---|---|
| `C:\ProgramData\Trilan NVR Backup Agent\logs\servico.log` | Log do serviço (pasta gravável sem administrador). |
| `...\logs\atualizacao.log` | Resultado do script de OTA. |
| `...\logs\reinicio.log` | Resultado do script de reinício. |
| `<pasta do agente>\logs\agent.log` | Log detalhado do backup. |
| Visualizador de Eventos do Windows | Mensagens do serviço. |

**Logs remotos** (`log_remoto.py`): as mensagens selecionadas (as marcadas com `enviar_servidor` e as de erro ou aviso) são
filtradas, **deduplicadas** (janela de 10 min), limitados em tamanho (4 000 caracteres) e enfileirados (máximo 500).
A thread de logs envia lotes de até 100 a cada 20 s para `/agent/logs`, com o nome do equipamento em execução. Antes
do envio, senhas, tokens e chaves são mascarados (`password=***`, `rtsp://user:***@host`). Falha no envio de logs nunca
gera novo log, para evitar laço infinito.

## 10. Telemetria no ping

A cada 15 s o ping leva: CPU (medida em 1 s), RAM, todos os discos (percentual, total, livre), tráfego por placa de
rede em Mbps, GPU (se houver NVIDIA) e o estado do backup (`backup_em_andamento`, `backup_ha_min`). O servidor usa o
último ping para mostrar "online/offline" e estimar o próximo contato (`last_seen` + 15 s).

## 11. A bandeja (`TrilanAgentTray.exe`)

- Ícone na bandeja: verde com o serviço rodando, vermelho se parado. Consulta `sc query` a cada 10 s.
- Menu: **Executar backup agora** (aciona o evento `Global\TrilanAgentNVR_RunNow`), **Iniciar**, **Parar**,
  **Reiniciar serviço** (pedem UAC), **Ver Logs (Tempo Real)** (PowerShell lendo `servico.log` com `-Wait`) e **Sair**.
- Mutex `Local\TrilanAgentTray` impede ícones duplicados.
- O evento do backup manual é criado pelo serviço com acesso liberado, para o usuário comum disparar sem elevação.

## 12. Rede e segurança

- **Autenticação**: cabeçalhos `X-Client-ID` e `X-API-Key` em todas as chamadas.
- **Sentido**: o agente sempre conecta ao servidor (saída). A única porta de entrada é a do Defense (8181), a do FTP da
  Huawei (21) e o que o equipamento exigir.
- **Certificado**: as chamadas ao servidor usam `verify=False` (aceita certificado autoassinado). Os equipamentos
  também são acessados sem validar certificado.
- **ZIP**: criptografia AES-256 com senha por máquina (`zip_password`). Se o servidor não configurar a senha, o ZIP sai
  sem senha, com aviso no log.
- **Tamanho dos arquivos**: o upload tem timeout de 120 s.
- **Credenciais dos equipamentos** vêm do servidor a cada ciclo e não são gravadas em disco; os logs as mascaram.

## 13. Endpoints usados pelo agente

Todos sob `/api/v1/agent/`:

| Método | Caminho | Uso |
|---|---|---|
| GET | `config` | Equipamentos, horário, senha do ZIP. |
| POST | `ping` | Telemetria e recebimento de instruções. |
| GET | `update-check` | Verifica versão nova. |
| POST | `backup/report` | Relatório do backup. |
| POST | `backup/upload/{backup_id}` | Envio do ZIP final. |
| POST | `rtsp-result` | Resultado de teste RTSP. |
| POST | `cameras/status` | Presença das câmeras. |
| POST | `nvr-cameras/night-image` | Imagem da noite. |
| POST | `olt/status` | Status das OLTs. |
| POST | `logs` | Logs remotos. |

## 14. Problemas comuns

| Sintoma | Causa provável | Como verificar |
|---|---|---|
| Serviço não aparece como online no painel | Sem rede, URL ou API Key errada | `servico.log`: "FALHA na comunicacao com o servidor". Conferir o `agent.conf`. |
| Erro 1053 ao iniciar | Início normal em vez de atrasado | O serviço se auto-corrige; senão `sc config TrilanAgentNVR start= delayed-auto`. |
| Backup parado há horas | Equipamento sem resposta | O vigia reinicia o serviço em 6 h; o limite por equipamento é 2 h. |
| Atualização não aplica | Executável travado | `atualizacao.log` (o script encerra à força depois de ~45 s). |
| Defense não registra quedas | Porta 8181 bloqueada | Liberar no firewall. |
| Bandeja sumiu após atualizar | Fechada pelo usuário ou sessão sem serviço | Abrir `TrilanAgentTray.exe`; o serviço só a reabre nos 15 min após a troca. |
| NVR "INACESSIVEL" | IP, usuário ou senha errados, ou marca não detectada | Preencher `marca` no `config_extra` do equipamento. |

## 15. Versão MikroTik (piloto ARMv7)

Desde 11/11/2026 existe um piloto para rodar o agente como container no MikroTik RB4011 (RouterOS 7, ARMv7, 1 GiB de
RAM, ~479 MB livres), no lugar de um PC Windows no cliente. A versão Windows não mudou.

| Arquivo | Função |
|---|---|
| `service_linux.py` | Processo Linux simples no lugar do `service.py`: ping a cada 15 s, reinício (encerra o processo) e agendamento do backup. |
| `requirements-linux.txt` | Dependências sem as de Windows (`pypiwin32`, `pystray`, `GPUtil`) e ainda sem o ffmpeg. |
| `Dockerfile.mikrotik` | Imagem `linux/arm/v7` em dois estágios (compila as bibliotecas e leva só o resultado). |
| `.dockerignore` | Tira `venv/`, `dist/`, logs e o `agent.conf` do contexto do build. |
| `README_MIKROTIK.md` | Limites do piloto, build validado, publicação no GHCR e configuração do teste. |

Imagem publicada: `ghcr.io/isaqueschaffer/trilan-agent:armv7-piloto1` (~60 MB). A configuração entra por um
`agent.conf` montado em `/app/agent.conf`; nada de credencial dentro da imagem.

O piloto **só valida a presença** (ping e online no painel). Backups (`TRILAN_ENABLE_BACKUPS=false` por padrão),
câmeras, OLTs, RTSP/ffmpeg, webhooks do Digifort/Defense, FTP da Huawei e OTA ficam desligados até serem testados no
RB4011.

O que depende de Windows e precisa de outro caminho no Linux: serviço e bandeja (`win32*`), OTA (`.bat`, `sc`,
`taskkill`), ping do Digifort (flags do `ping` do Windows), caminhos `C:\` e `ProgramData`. O backup da UNM2000 lê
arquivos e o MySQL do próprio servidor da UNM2000 e não roda no roteador.

## 16. Referência de arquivos

```
agent/
├── service.py              Serviço Windows, threads e loop principal
├── tray.py                 Ícone da bandeja
├── agent.py                Ponto de entrada manual do backup (python agent.py)
├── build.ps1               Gera os .exe (PyInstaller)
├── installer.iss           Instalador (Inno Setup)
├── publish_version.ps1     Cadastra a versão no painel
└── src/
    ├── core/config.py          Leitura do agent.conf
    ├── application/            Backup, API, OTA, logs, presença, noite, OLT, webhooks, estado
    ├── nvr/                    Hikvision, Intelbras, Motorola (câmeras, gravações, telemetria, planilha)
    ├── olt/                    UNM2000, VSOL, Huawei
    ├── pabx/issabel.py         Issabel
    ├── mikrotik/routeros.py    RouterOS
    ├── vms/                    Defense e Digifort
    ├── camera/rtsp_client.py   Captura de quadros e teste RTSP (ffmpeg)
    └── backup/                 Criptografia, ZIP, download, gerenciador de arquivos
```
