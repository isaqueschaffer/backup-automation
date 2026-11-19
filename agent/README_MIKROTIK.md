# Trilan Agent for RouterOS ARMv7 — EXPERIMENTAL PILOT

The Windows version in branch `isaque` is unchanged. This branch adds a separate Linux runner and Dockerfile. **Not production ready**.

## Imagem completa (1.1.58) — o que o agente Linux faz

**O Mikrotik é uma PONTE/TÚNEL até o servidor:** pouco processamento e nada gravado no roteador, nem arquivo temporário. Tudo o que ele faz é em memória e o resultado vai direto ao servidor. **Faz backup só em túnel** (ver abaixo): lê o backup do UNM2000/Digifort do cliente por SMB e o envia em fluxo ao servidor. NVR, PABX, VSOL, Huawei e demais tipos que gravam em disco ficam com os agentes Windows. Não roda os webhooks Defense/Digifort (gravam CSV). A imagem leva tudo o que as rotinas dele usam, para as versões seguintes chegarem pela OTA sem trocar a imagem:

| Rotina (1.1.58) | Usa |
| :---- | :---- |
| Ping, reinício pelo painel, OTA, log no painel | — |
| Captura da Galeria sob demanda (ao vivo, referência, noite; uma por vez) | `ffmpeg` mínimo (JPEG por pipe, sem arquivo) |
| Presença das câmeras, status das OLTs (SNMP), antenas (SSH no MikroTik \+ ping), alarmes do Defense e armar/desarmar central | `ping`, `pysnmp`, `paramiko` |
| Teste de conexão pedido pelo painel | — |
| Backup em túnel (UNM2000 e Digifort por pasta de rede, no horário e sob demanda) | `smbprotocol`, `pyzipper` |

- Ciclo automático da imagem da noite (19h30–4h, um frame de cada câmera a cada 10 min): desligado no Mikrotik; `TRILAN_NOITE_AUTOMATICA=true` liga. O backup em túnel vem ligado; `TRILAN_ENABLE_BACKUPS=false` desliga.

### Backup em túnel (`src/backup/tunel.py`)

```
pasta do UNM2000/Digifort --SMB--> montador do ZIP (memória) --fila ~2 MB--> PUT em pedaços --> servidor
```

- **Nada vai ao disco do roteador:** o ZIP com a senha da máquina e o `backup.zip` de cada equipamento são montados enquanto os bytes passam (mesma estrutura do agente Windows: `<TIPO>/backup_<tipo>_<nome>/backup.zip`). A fila é pequena e bloqueia a leitura quando o envio está lento: a memória fica em poucos MB, seja qual for o tamanho.

- **Servidor:** `PUT /api/v1/agent/backup/upload-stream/{backup_id}` (corpo em pedaços; mesmas regras do envio comum: limite de tamanho, ZIP só substitui o anterior ao terminar, e-mail do relatório). Se a conexão cair no meio, o `.part` é descartado. `POST /api/v1/agent/backup/{backup_id}/resultado` corrige o status de um equipamento.

- **Ordem:** o relatório sai antes do envio, com os equipamentos prontos como OK (provisório). Se a leitura de um deles falhar ou o tamanho lido divergir do informado pelo cliente (`CORROMPIDO`), o servidor descarta o parcial, o status é corrigido e o ZIP é refeito sem ele. Falha de rede: uma nova tentativa; depois, `ERRO` nos pendentes.

- **Conferência:** só pelo tamanho (não há cópia local para comparar o hash). Compressão desligada (os backups já vêm comprimidos e a CPU do roteador é pouca); `TRILAN_TUNEL_COMPRESSAO=deflate` liga.

- **Não entra no túnel** (grava arquivo em disco): NVR, PABX, VSOL, Huawei, Mikrotik, Defense (status `TIPO_NAO_SUPORTADO` no relatório). O status das câmeras do Digifort que o agente Windows lê dos arquivos copiados (tempo de gravação) também não sai pelo túnel: precisa dos arquivos em disco.

- `verificar_imagem.py` monta um ZIP com senha em fluxo no build e reprova a imagem se falhar (pega problema de zipfile/cripto no ARMv7 antes de chegar ao roteador).

- **Python 3.14**, o mesmo do build do Windows (a 1.1.57 trazia código que o 3.11 da imagem antiga não compilava).

- **Fuso** `TZ=America/Sao_Paulo` na imagem (sem ele o container ficava em UTC: horário do backup e janela da noite 3 h adiantados).

- **ffmpeg mínimo** compilado no build (só RTSP/RTP, H.264/H.265/MJPEG/MPEG-4 e saída JPEG): o do Debian ocupava \~420 MB e não cabia no RB4011.

- **`verificar_imagem.py`** roda no fim do build e reprova a imagem se faltar programa, fuso, biblioteca ou se algum módulo não compilar/importar. Num container em uso: `python /app/verificar_imagem.py`.

- **OTA com biblioteca nova:** em vez de recusar toda mudança no `requirements-linux.txt`, a OTA confere se cada biblioteca está instalada na versão pedida e instala as que faltam com `pip --user --only-binary=:all:` em `/app/data/pyuser` (Python puro passa; nada é compilado no roteador). Imagem nova só para biblioteca compilada sem wheel ARMv7 ou programa novo do sistema.

## Disabled / unvalidated

- The router never stores a backup (bridge design): the tunnel streams it through memory (see "Backup em túnel").  
- Existing API client has `verify=False`. Correct certificate validation before production.  
- Existing timeout implementation can leave Python threads alive; introduce process-based cancellation before production.  
- Some Python dependencies or base image variants may not support ARMv7; build and runtime testing are still required.

## Build on a Docker builder

```sh
docker buildx build --platform linux/arm/v7 -f agent/Dockerfile.mikrotik -t trilan-agent:armv7 ./agent --load
```

Confirm the resulting image's architecture and test it on ARMv7 Linux before loading into RouterOS. RouterOS does not run Docker Engine or Compose.

## Configuration

- Mount `agent.conf` in `/app/agent.conf`, using the existing \[server\] URL and \[auth\] Client ID / API Key fields.  
- Do not commit credentials or embed them into container images.  
- Default `TRILAN_ENABLE_BACKUPS=false`. Do not enable on a production RB4011 until storage limits, backups and monitoring are proven.  
- `TRILAN_ALLOW_INSECURE_HTTP=true` is only for isolated laboratory testing.

### Regras de rede e firewall (SSH e Antenas)

Quando o equipamento `ANTENA` (ou `MIKROTIK`) estiver no mesmo roteador onde o container roda, o agente precisa alcançar o SSH do RouterOS e pingar as antenas a partir da bridge do container (`br-trilan`, `172.30.250.2/30`):

- Execute o script `agent/mikrotik/setup.rsc` no terminal do RouterOS (`/import setup.rsc`) após criar `br-trilan` e `veth-trilan`. Ele libera de forma idempotente:  
  - `chain=input` na porta `22` TCP vindo de `br-trilan` (antes do `drop` padrão);  
  - `172.30.250.0/30` no `AVAILABLE-FROM` do `/ip service ssh` (caso haja restrição de IP configurada, sem apagar os endereços existentes);  
  - `chain=forward` vindo de `br-trilan` e `srcnat masquerade` para `172.30.250.0/30` (para o ping ICMP às antenas funcionar).  
- **No painel:** prefira cadastrar o IP estático do gateway da bridge do container (`172.30.250.1`) no equipamento `ANTENA`, evitando dependência de IPs dinâmicos (DHCP) de outras interfaces. Nunca use `127.0.0.1` (aponta para dentro do próprio container).

## RB4011 constraints

RouterOS 7.25.1 / ARMv7; 1 GiB RAM; 512 MiB internal NAND. Backups create temporary files and ZIPs that can exhaust NAND and overload router CPU. Keep VLAN/bridge/firewall untouched during initial heartbeat-only validation. Configure VETH, routes, policy and storage per site, not from a generic script.

## Build validado em 11/11/2026 (em português)

Primeiro build ARMv7 que chegou ao fim, feito numa máquina Windows x86 com Docker Desktop 29.9.3 (buildx \+ QEMU).

**Problemas encontrados e correções no `Dockerfile.mikrotik`:**

1. `error: No such file or directory: 'gcc'`: o PyPI não tem wheel ARMv7 (32 bits) de `pynacl`, `pycryptodome`, `pycryptodomex`, `psutil`, `Pillow` e `cffi`, então o pip compila o código-fonte, e a imagem `python:3.11-slim` não tem compilador.  
2. `The 'make' utility is missing from PATH`: o `pynacl` compila a libsodium e precisa do `make`.

Solução: build em **dois estágios**. O estágio `builder` instala `gcc make libc6-dev libffi-dev libssl-dev libjpeg-dev zlib1g-dev` e roda o `pip install --prefix=/install`. A imagem final copia só o `/install` e as bibliotecas de execução (`libffi8 libjpeg62-turbo zlib1g`); o compilador não vai para o roteador. Também entrou um `.dockerignore` (sem ele o contexto levava `venv/`, `dist/`, logs e o `agent.conf` real ao builder; o Dockerfile não copia esses arquivos para a imagem, mas o envio ficava lento).

**Resultado:**

- `docker image inspect trilan-agent:armv7 --format '{{.Os}}/{{.Architecture}}/{{.Variant}}'` → `linux/arm/v7`.  
- Imagem de \~60 MB (o `.tar` do `docker save` tem 60,2 MB).  
- Teste emulado: `platform.machine()` \= `armv7l`; todas as bibliotecas do `requirements-linux.txt` e os módulos `backup_job`, `api_client`, `status_olt`, `log_remoto` e `nvr.factory` importam sem erro.  
- Aviso do `paramiko` 3.4.0: o TripleDES vai mudar de lugar numa versão futura do `cryptography`. Funciona hoje, mas o SSH com as OLTs Huawei antigas (motivo do `paramiko` fixo) precisa ser testado no piloto.

**Tempo de build:** cerca de 1h40 sem cache, quase tudo no `pip install` (o QEMU traduz cada instrução ARM para x86, de 10 a 20 vezes mais lento que nativo; `pynacl` \~31 min, `pycryptodomex` \~34 min, `Pillow` \~7 min). Com o cache do Docker, um build que só muda o código do agente refaz apenas as últimas camadas. Para acelerar de vez: guardar as wheels compiladas, usar um builder ARM nativo ou o índice piwheels (de terceiros; não adotado sem decisão).

**Não validado ainda:** execução do `service_linux.py` contra o servidor, importação no RouterOS e o desempenho no RB4011. O fuso do container: o agendamento usa `datetime.now()`; sem `TZ` definido o container fica em UTC (irrelevante enquanto `TRILAN_ENABLE_BACKUPS=false`, mas definir `TZ=America/Sao_Paulo` antes de ligar os backups).

### Imagem no repositório

`agent/mikrotik/trilan-agent-armv7.tar` (57,4 MB, `docker save` de `trilan-agent:armv7`, `linux/arm/v7`, agente 1.1.52 com launcher e OTA, gerada em 12/11/2026). Desde a 1.1.52 **não fica no git** (o push de 57 MB ao `origin` caía): vai como anexo `trilan-agent-armv7.tar` da release em `isaqueschaffer/backup-automation` (a da 1.1.52 leva a imagem atual) e o arquivo local está no `.gitignore`. SHA-256: `567590623c0c865e9c637f649807bf2132b6f327174dcc7c03ae874fb900674d`. No RouterOS: enviar o `.tar` ao roteador e `/container add file=trilan-agent-armv7.tar ...`.

### Como gerar de novo

```powershell
cd agent
docker buildx build --platform linux/arm/v7 -f Dockerfile.mikrotik -t trilan-agent:armv7 --load .
docker image inspect trilan-agent:armv7 --format '{{.Os}}/{{.Architecture}}/{{.Variant}}'   # linux/arm/v7
docker save --platform linux/arm/v7 -o mikrotik/trilan-agent-armv7.tar trilan-agent:armv7
```

&nbsp;

Depois, anexar o `.tar` à release da versão (`gh release upload <versão> agent/mikrotik/trilan-agent-armv7.tar -R isaqueschaffer/backup-automation`), sem commit. Anexo de release aceita até 2 GB.

### Configuração para o teste

- Montar um `agent.conf` em `/app/agent.conf`, de preferência de uma **máquina de teste** criada no painel (nunca de cliente real). URL: `https://server.suportetrilan.com.br` (o piloto recusa `http://` sem `TRILAN_ALLOW_INSECURE_HTTP=true`).  
- (Até a 1.1.51 o piloto só fazia o ping. Desde a 1.1.58 roda todas as rotinas da tabela "Imagem completa"; só o backup continua desligado por padrão.)

## Atualização automática (OTA, desde a 1.1.52)

A imagem passa a rodar `launcher_linux.py` em vez do `service_linux.py` direto:

- O agente consulta `GET /api/v1/agent/update-check?plataforma=linux` 2 min depois de subir e a cada hora. A versão só é oferecida se tiver o pacote Linux cadastrado (`url_linux` \+ `sha256_linux`, via `publish_version.ps1 -UrlLinux`).  
- O pacote `TrilanAgentLinux.tar.gz` (anexo da release) leva só o código Python. As bibliotecas compiladas para ARM continuam as da imagem. Até a 1.1.57, uma versão que mudava o `requirements-linux.txt` era recusada (log "precisa de imagem nova"); desde a 1.1.58 a OTA instala a biblioteca que falta quando há wheel pronta (ver acima) e só recusa se o pip não conseguir.  
- Fica em `/app/data/code/`: `atual/` (em uso), `anterior/`, `pendente` (versão ainda não confirmada) e `falhou`. O 1º ping bem-sucedido confirma a versão. Se ela cair 3 vezes ou não pingar em 10 min, o launcher volta para a anterior (ou para a da imagem) e não a baixa de novo por 24 h.  
- O "Reiniciar agente" do painel agora funciona: o agente encerra e o launcher o sobe de novo em \~2 s.  
- Container recriado com imagem mais nova que `/app/data/code/atual`: a pasta da OTA é descartada e vale a imagem.

**Uma única troca manual:** a imagem anterior à 1.1.52 não tem launcher nem OTA. Importar esta imagem no RouterOS uma vez; daí em diante as versões chegam sozinhas, como nos agentes Windows. Recomendado: montar `/app/data` num `mount` do RouterOS para a OTA sobreviver a um container recriado (sem o mount, ela fica no disco do container e se perde só se o container for removido; a imagem continua funcionando).

```routeros
/container/stop [find where tag~"trilan"]
/container/remove [find where tag~"trilan"]
/container/add file=trilan-agent-armv7.tar interface=veth-trilan root-dir=<disco>/trilan-root \
    mounts=<mount do agent.conf>,<mount de /app/data> start-on-boot=yes logging=yes
/container/start [find where tag~"trilan"]
```

&nbsp;

(Ajustar `interface`, `root-dir` e os `mounts` aos que já estão configurados no roteador.)

## Acceptance gates before production

1. ARMv7 image builds and boots; heartbeat visible in test tenant.  
2. TLS verification and safe storage of `agent.conf`.  
3. Resource limits, watchdog, bounded ZIP writes and out-of-space tests.  
4. Per-vendor integration tests and failure recovery.  
5. OTA controller and safe rollback external to RouterOS container.