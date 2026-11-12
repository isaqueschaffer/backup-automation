# Trilan Agent for RouterOS ARMv7 — EXPERIMENTAL PILOT

The Windows version in branch `isaque` is unchanged. This branch adds a separate Linux runner and Dockerfile. **Not production ready**.

## Implemented
- Reuses existing client configuration, `/api/v1/agent/config`, and `/api/v1/agent/ping`.
- Heartbeats roughly every 15 seconds (API latency permitting).
- Remote restart command stops the agent; `launcher_linux.py` starts it again (>= 1.1.52).
- OTA of the agent code (>= 1.1.52): see "Atualização automática" below.
- Manual and scheduled backup dispatch exists, but is **disabled by default**.

## Disabled / unvalidated
- NVR, OLT, PABX, VMS backup routines have NOT been certified on ARMv7.
- RTSP/FFmpeg, camera/OLT monitoring, Huawei inbound FTP, Defense webhooks, UNM2000 local-file access are not enabled in this pilot.
- Existing API client has `verify=False`. Correct certificate validation before production.
- Existing timeout implementation can leave Python threads alive; introduce process-based cancellation before production.
- Some Python dependencies or base image variants may not support ARMv7; build and runtime testing are still required.

## Build on a Docker builder
```sh
docker buildx build --platform linux/arm/v7 -f agent/Dockerfile.mikrotik -t trilan-agent:armv7 ./agent --load
```
Confirm the resulting image's architecture and test it on ARMv7 Linux before loading into RouterOS. RouterOS does not run Docker Engine or Compose.

## Configuration
- Mount `agent.conf` in `/app/agent.conf`, using the existing [server] URL and [auth] Client ID / API Key fields.
- Do not commit credentials or embed them into container images.
- Default `TRILAN_ENABLE_BACKUPS=false`. Do not enable on a production RB4011 until storage limits, backups and monitoring are proven.
- `TRILAN_ALLOW_INSECURE_HTTP=true` is only for isolated laboratory testing.

## RB4011 constraints
RouterOS 7.25.1 / ARMv7; 1 GiB RAM; 512 MiB internal NAND. Backups create temporary files and ZIPs that can exhaust NAND and overload router CPU. Keep VLAN/bridge/firewall untouched during initial heartbeat-only validation. Configure VETH, routes, policy and storage per site, not from a generic script.

## Build validado em 11/11/2026 (em português)

Primeiro build ARMv7 que chegou ao fim, feito numa máquina Windows x86 com Docker Desktop 29.9.3 (buildx + QEMU).

**Problemas encontrados e correções no `Dockerfile.mikrotik`:**
1. `error: No such file or directory: 'gcc'`: o PyPI não tem wheel ARMv7 (32 bits) de `pynacl`, `pycryptodome`,
   `pycryptodomex`, `psutil`, `Pillow` e `cffi`, então o pip compila o código-fonte, e a imagem `python:3.11-slim`
   não tem compilador.
2. `The 'make' utility is missing from PATH`: o `pynacl` compila a libsodium e precisa do `make`.

Solução: build em **dois estágios**. O estágio `builder` instala `gcc make libc6-dev libffi-dev libssl-dev
libjpeg-dev zlib1g-dev` e roda o `pip install --prefix=/install`. A imagem final copia só o `/install` e as bibliotecas
de execução (`libffi8 libjpeg62-turbo zlib1g`); o compilador não vai para o roteador. Também entrou um
`.dockerignore` (sem ele o contexto levava `venv/`, `dist/`, logs e o `agent.conf` real ao builder; o Dockerfile não
copia esses arquivos para a imagem, mas o envio ficava lento).

**Resultado:**
- `docker image inspect trilan-agent:armv7 --format '{{.Os}}/{{.Architecture}}/{{.Variant}}'` → `linux/arm/v7`.
- Imagem de ~60 MB (o `.tar` do `docker save` tem 60,2 MB).
- Teste emulado: `platform.machine()` = `armv7l`; todas as bibliotecas do `requirements-linux.txt` e os módulos
  `backup_job`, `api_client`, `status_olt`, `log_remoto` e `nvr.factory` importam sem erro.
- Aviso do `paramiko` 3.4.0: o TripleDES vai mudar de lugar numa versão futura do `cryptography`. Funciona hoje, mas o
  SSH com as OLTs Huawei antigas (motivo do `paramiko` fixo) precisa ser testado no piloto.

**Tempo de build:** cerca de 1h40 sem cache, quase tudo no `pip install` (o QEMU traduz cada instrução ARM para x86, de
10 a 20 vezes mais lento que nativo; `pynacl` ~31 min, `pycryptodomex` ~34 min, `Pillow` ~7 min). Com o cache do
Docker, um build que só muda o código do agente refaz apenas as últimas camadas. Para acelerar de vez: guardar as wheels
compiladas, usar um builder ARM nativo ou o índice piwheels (de terceiros; não adotado sem decisão).

**Não validado ainda:** execução do `service_linux.py` contra o servidor, importação no RouterOS e o desempenho no
RB4011. O fuso do container: o agendamento usa `datetime.now()`; sem `TZ` definido o container fica em UTC (irrelevante
enquanto `TRILAN_ENABLE_BACKUPS=false`, mas definir `TZ=America/Sao_Paulo` antes de ligar os backups).

### Imagem no repositório

`agent/mikrotik/trilan-agent-armv7.tar` (57,4 MB, `docker save` de `trilan-agent:armv7`, `linux/arm/v7`, agente
1.1.52 com launcher e OTA, gerada em 12/11/2026), versionada como arquivo comum no ramo `isaque`. SHA-256:
`567590623c0c865e9c637f649807bf2132b6f327174dcc7c03ae874fb900674d`. No RouterOS: enviar o `.tar` ao roteador e
`/container add file=trilan-agent-armv7.tar ...`.

### Como gerar de novo

```powershell
cd agent
docker buildx build --platform linux/arm/v7 -f Dockerfile.mikrotik -t trilan-agent:armv7 --load .
docker image inspect trilan-agent:armv7 --format '{{.Os}}/{{.Architecture}}/{{.Variant}}'   # linux/arm/v7
docker save --platform linux/arm/v7 -o mikrotik/trilan-agent-armv7.tar trilan-agent:armv7
```

Depois, commit e push do `.tar` como qualquer arquivo. O GitHub recusa arquivo acima de 100 MB; se a imagem crescer
até lá, passar a usar Git LFS ou um registry.

### Configuração para o teste

- Montar um `agent.conf` em `/app/agent.conf`, de preferência de uma **máquina de teste** criada no painel (nunca de
  cliente real). URL: `https://server.suportetrilan.com.br` (o piloto recusa `http://` sem
  `TRILAN_ALLOW_INSECURE_HTTP=true`).
- O piloto só faz o ping a cada 15 s (a máquina aparece online no painel) e trata o reinício (encerra o processo; o
  RouterOS precisa religar o container). Backups, câmeras, OLTs, RTSP, webhooks e OTA estão desligados.

## Atualização automática (OTA, desde a 1.1.52)

A imagem passa a rodar `launcher_linux.py` em vez do `service_linux.py` direto:

- O agente consulta `GET /api/v1/agent/update-check?plataforma=linux` 2 min depois de subir e a cada hora. A versão
  só é oferecida se tiver o pacote Linux cadastrado (`url_linux` + `sha256_linux`, via `publish_version.ps1 -UrlLinux`).
- O pacote `TrilanAgentLinux.tar.gz` (anexo da release) leva só o código Python. As bibliotecas compiladas para ARM
  continuam as da imagem. Por isso uma versão que muda o `requirements-linux.txt` é recusada (log "precisa de imagem
  nova") e exige gerar e importar a imagem de novo.
- Fica em `/app/data/code/`: `atual/` (em uso), `anterior/`, `pendente` (versão ainda não confirmada) e `falhou`.
  O 1º ping bem-sucedido confirma a versão. Se ela cair 3 vezes ou não pingar em 10 min, o launcher volta para a
  anterior (ou para a da imagem) e não a baixa de novo por 24 h.
- O "Reiniciar agente" do painel agora funciona: o agente encerra e o launcher o sobe de novo em ~2 s.
- Container recriado com imagem mais nova que `/app/data/code/atual`: a pasta da OTA é descartada e vale a imagem.

**Uma única troca manual:** a imagem anterior à 1.1.52 não tem launcher nem OTA. Importar esta imagem no RouterOS uma
vez; daí em diante as versões chegam sozinhas, como nos agentes Windows. Recomendado: montar `/app/data` num `mount`
do RouterOS para a OTA sobreviver a um container recriado (sem o mount, ela fica no disco do container e se perde só se
o container for removido; a imagem continua funcionando).

```routeros
/container/stop [find where tag~"trilan"]
/container/remove [find where tag~"trilan"]
/container/add file=trilan-agent-armv7.tar interface=veth-trilan root-dir=<disco>/trilan-root \
    mounts=<mount do agent.conf>,<mount de /app/data> start-on-boot=yes logging=yes
/container/start [find where tag~"trilan"]
```
(Ajustar `interface`, `root-dir` e os `mounts` aos que já estão configurados no roteador.)

## Acceptance gates before production
1. ARMv7 image builds and boots; heartbeat visible in test tenant.
2. TLS verification and safe storage of `agent.conf`.
3. Resource limits, watchdog, bounded ZIP writes and out-of-space tests.
4. Per-vendor integration tests and failure recovery.
5. OTA controller and safe rollback external to RouterOS container.
