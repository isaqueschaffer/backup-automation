---
name: conciliar-backups-onedrive
description: Concilia os backups dos clientes nas três pontas — API (registros), VM Linux (/opt/trilan/backups) e servidor Windows (pasta do OneDrive) — e diagnostica por que um backup não chegou à nuvem (agente, servidor fora do ar, VM pausada, disco cheio, tarefa de sincronização). Use quando o usuário perguntar sobre a sincronização com o OneDrive, backups faltando, VM/servidor caído ou pedir para "conciliar" os backups.
---

# Conciliar backups: API ↔ VM Linux ↔ OneDrive

Só do Claude (usa acesso SSH às máquinas; **não existe cópia para o Gemini** e nada daqui vai para plano do Gemini).

## Arquitetura (verificada em 13/11/2026)

```
Agente (cliente) --HTTP--> API FastAPI (Dokploy, VM Linux 192.168.75.112)
   grava em /data/backups  ==  /opt/trilan/backups (bind mount)
   compartilhado por Samba: \\192.168.75.112\backups (usuário trilan)
Servidor Windows 192.168.75.27 (host Hyper-V da VM "Ubuntu")
   tarefa Trilan_Sync_Backups_OneDrive (de hora em hora, :30, usuário Administrator, logon interativo)
   C:\TrilanSync\sync_backups_onedrive.ps1 -> robocopy /E /XO (cópia, NÃO espelho)
   destino: C:\Users\Administrator\OneDrive - Trilan\Arquivos de Admin - Backups Clientes
   log: C:\Users\Administrator\AppData\Local\Trilan\sync_backups.log
   cliente OneDrive envia para a nuvem (só com a sessão do Administrator aberta)
```

- A VM é **Hyper-V no próprio servidor Windows**: se o host cai, falta energia ou o disco do host enche, a API cai junto.
- O VHDX da VM é dinâmico (`C:\Users\Public\Documents\Hyper-V\Virtual Hard Disks\Ubuntu.vhdx`, até 127 GB) e o arquivo de memória (`.VMRS`, ~6 GB) fica em `C:\ProgramData\Microsoft\Windows\Hyper-V`. Disco C: cheio no host = VM pausada ("Disk Full") e depois desligada.
- `robocopy /XO` não apaga nada na nuvem: renomeações/exclusões no Linux deixam sobras no OneDrive (esperado).
- O Windows mostra os horários dos arquivos com +1 h em relação à VM (fuso/horário de verão do host); compare por nome e quantidade, não pelo minuto exato.

## Credenciais (nunca imprimir, nunca versionar)

Ficam em arquivos da raiz **fora do git** (listados em `.git/info/exclude`):
- Windows host: `acesso -ao-servidor-windows--vm.md` (usuário `administrator`).
- VM Linux: `acesso-ao-servidor-da-aplicacao-vm-no-servidor-windows.md` (usuário `trilan`; o mesmo valor serve para `sudo -S`).
- API: senha em `CLAUDE.local.md` (login `POST https://server.suportetrilan.com.br/api/v1/auth/login` com `{"password": ...}` → `access_token`).

Ler a senha **dentro do comando** (regex no .md), nunca exibir. Só leitura (GET/consultas) sem pedido do usuário; qualquer ação (disparar backup, mexer na VM, no disco, no script ou na tarefa) só com autorização.

## Como acessar por SSH sem prompt (Windows → OpenSSH)

Não há `sshpass`/`plink`; usar `SSH_ASKPASS` com um `.cmd` temporário no scratchpad (caminho 8.3 `C:\Users\USURIO~2\...`; caminho com acento quebra o askpass) e apagar no fim:

```powershell
$ask = "<scratchpad 8.3>\ask.cmd"
"@echo off`r`necho $pw" | Set-Content $ask -Encoding ascii
$env:SSH_ASKPASS=$ask; $env:SSH_ASKPASS_REQUIRE="force"; $env:DISPLAY="x"
ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -o PreferredAuthentications=password -o PubkeyAuthentication=no usuario@host "<comando>"
[IO.File]::Delete($ask)
```

- **Windows remoto:** mandar o script como `powershell -NoProfile -EncodedCommand <base64 UTF-16LE>` (caminhos com espaço quebram com aspas).
- **Linux remoto:** `echo <base64 UTF-8 sem \r> | base64 -d | bash` (o PowerShell come aspas e `\n`).
- Sem `accept-new`, a primeira conexão a um host novo trava esperando "yes".
- Varredura recursiva do C: inteiro no Windows passa de 8 min: mire nas pastas conhecidas.

## Roteiro da conciliação

1. **API (o que deveria existir):**
   - `GET /api/v1/machines`: `is_online`, `agent_version`, `last_seen`, `last_backup_at` (UTC), `backup_hour:minute` (hora local da máquina), `customer_name`.
   - `GET /api/v1/backups?date_from=AAAA-MM-DD&size=100&page=N`: agrupar por cliente, dia (UTC−3) e status.
   - Dias sem registro → ver logs da máquina: `GET /api/v1/machines/{id}/logs?limit=500&incluir_pings=false&q=BACKUP` (máx. 500, mais recentes primeiro; filtrar por `q` e `nivel=ERROR,WARNING`).
   - Sinal de servidor fora do ar: `INICIANDO BACKUP — SCHEDULED` seguido de `BACKUP FINALIZADO.` em ~20–30 s, sem "Backup concluido", e `Falha ao buscar config: ... ConnectTimeout/Read timed out`. O agente aborta sem ZIP e sem registro.
2. **VM Linux (o que chegou):** por pasta de cliente em `/opt/trilan/backups`: nº de arquivos, `du -sm`, arquivo mais novo (`find -printf '%TY-%Tm-%Td_%TH:%TM'`). Mais `uptime -s`, `journalctl --list-boots`, fim do boot anterior (`sudo journalctl -b -1 -n 40`), `free -m`, `df -h`.
3. **Windows / OneDrive (o que subiu):** a mesma contagem por pasta no destino; `Get-ScheduledTaskInfo Trilan_Sync_Backups_OneDrive`; últimas linhas e linhas `ERRO` do log; `Get-Process OneDrive`; `quser` (sessão do Administrator aberta?).
4. **Host Hyper-V (quando a API ficou fora):**
   - Log `Microsoft-Windows-Hyper-V-Worker-Admin`: 12635/12636 = Disk Full; 18524 = VM pausada; 18528 = VM desligada; 3326/12030 = falha ao ligar por falta de espaço; 18500 = ligou.
   - Log System: 41/6008 = desligamento inesperado (energia/travamento); 6005 = boot.
   - `Get-PSDrive C,D`, `Get-VHD` do VHDX, `Get-VM Ubuntu | Select ProcessorCount, MemoryStartup`.
5. **Comparar e concluir:** API × VM × OneDrive por cliente (quantidade e último arquivo). Classificar cada diferença:
   - **falta na API e na VM** → o backup não rodou ou abortou (agente/servidor);
   - **está na VM e falta no OneDrive** → sincronização (tarefa, SMB, sessão, OneDrive pausado);
   - **sobra no OneDrive** → renomeação/exclusão no Linux (esperado com `/XO`).

## Recuperação de backup perdido (servidor)

`routers/agent.py` (ping): se passou mais de 30 min do **último** horário agendado (o de hoje, se já passou, senão o de ontem: `_ultimo_horario_agendado`) e não há backup depois dele nem `ping_recovery` desde então, o servidor manda o agente fazer o backup no próximo ping. Até 13/11/2026 comparava só com o horário de "hoje", e o agendamento das 23:00 nunca se recuperava quando o servidor voltava depois da meia-noite.

## Achados de 13/11/2026 (referência)

- Backups das 23:00 de 11/11 e 12/11 não existem: em 11/11 o host Windows desligou sem shutdown limpo às 21:09; em 12/11 a VM ficou lenta a partir de ~22:40, foi pausada às 02:43 por **disco C: do host cheio**, desligada às 03:13 e só voltou às 08:41.
- VM e OneDrive estavam idênticos (sincronização ok); a falha estava antes (servidor fora do ar e recuperação que não disparava).
- VM com 1 vCPU e ~5,9 GB de RAM (host com 24 núcleos lógicos e 16 GB) e swap em uso; disco D: do host com ~864 GB livres, enquanto VHDX e `.VMRS` estão no C:.
