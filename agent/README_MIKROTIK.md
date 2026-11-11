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

## Acceptance gates before production
1. ARMv7 image builds and boots; heartbeat visible in test tenant.
2. TLS verification and safe storage of `agent.conf`.
3. Resource limits, watchdog, bounded ZIP writes and out-of-space tests.
4. Per-vendor integration tests and failure recovery.
5. OTA controller and safe rollback external to RouterOS container.
