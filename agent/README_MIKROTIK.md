# Trilan Agent for RouterOS ARMv7 — EXPERIMENTAL PILOT

The Windows version in branch `isaque` is unchanged. This branch adds a separate Linux runner and Dockerfile. **Not production ready**.

## Implemented
- Reuses existing client configuration, `/api/v1/agent/config`, and `/api/v1/agent/ping`.
- Heartbeats roughly every 15 seconds (API latency permitting).
- Remote restart command stops the agent (requires external RouterOS container restart policy).
- Manual and scheduled backup dispatch exists, but is **disabled by default**.

## Disabled / unvalidated
- NVR, OLT, PABX, VMS backup routines have NOT been certified on ARMv7.
- RTSP/FFmpeg, camera/OLT monitoring, Huawei inbound FTP, Defense webhooks, UNM2000 local-file access and OTA upgrades are not enabled in this pilot.
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

### Imagem publicada

`ghcr.io/isaqueschaffer/trilan-agent:armv7-piloto1` (GitHub Container Registry, ligada a
`isaqueschaffer/backup-automation`). Pelo RouterOS, com registry `https://ghcr.io`, basta adicionar o container por
`remote-image`. Sem acesso ao registry, use o `.tar` do `docker save` (`/container add file=...`).

### Como gerar e publicar de novo

```powershell
cd agent
docker buildx build --platform linux/arm/v7 -f Dockerfile.mikrotik -t trilan-agent:armv7 --load .
docker image inspect trilan-agent:armv7 --format '{{.Os}}/{{.Architecture}}/{{.Variant}}'   # linux/arm/v7
docker save --platform linux/arm/v7 -o dist/trilan-agent-armv7.tar trilan-agent:armv7        # arquivo para o RouterOS
docker tag trilan-agent:armv7 ghcr.io/isaqueschaffer/trilan-agent:armv7-piloto<N>
docker push ghcr.io/isaqueschaffer/trilan-agent:armv7-piloto<N>
```

O push exige o login no GHCR com permissão `write:packages` (`gh auth refresh -h github.com -s write:packages` e
depois `gh auth token | docker login ghcr.io -u isaqueschaffer --password-stdin`).

### Configuração para o teste

- Montar um `agent.conf` em `/app/agent.conf`, de preferência de uma **máquina de teste** criada no painel (nunca de
  cliente real). URL: `https://server.suportetrilan.com.br` (o piloto recusa `http://` sem
  `TRILAN_ALLOW_INSECURE_HTTP=true`).
- O piloto só faz o ping a cada 15 s (a máquina aparece online no painel) e trata o reinício (encerra o processo; o
  RouterOS precisa religar o container). Backups, câmeras, OLTs, RTSP, webhooks e OTA estão desligados.

## Acceptance gates before production
1. ARMv7 image builds and boots; heartbeat visible in test tenant.
2. TLS verification and safe storage of `agent.conf`.
3. Resource limits, watchdog, bounded ZIP writes and out-of-space tests.
4. Per-vendor integration tests and failure recovery.
5. OTA controller and safe rollback external to RouterOS container.
