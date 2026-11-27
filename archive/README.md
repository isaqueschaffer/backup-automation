# archive/

Material antigo, mantido só para consulta. Nada daqui é usado em produção nem entra em nenhum build.
(Até 26/11/2026 parte disto ficava numa pasta `legacy/` na raiz; as duas foram juntadas aqui.)

| Pasta | O que é |
|---|---|
| `legacy_scripts/` | Scripts anteriores ao agente atual (UNM2000, backup de NVR, checagem de gravação, V-SOL). O comportamento equivalente hoje está em `agent/src/`. `digifort_snmp.py` é o monitoramento antigo do Digifort por traps SNMP (porta 162 UDP), trocado pelo ping ICMP do agente. |
| `fiberhome-zabbix/` | Monitoramento de OLT FiberHome/UNM2000 pelo **Zabbix**, de antes do sistema: templates (`template-cloud-fiberhome-2.0.yaml`, `zbx_export_templates.yaml`), scripts de descoberta de ONUs e sinal óptico, checagem de licença do UNM, consulta SQL das ONUs por OLT, o guia de instalação e protótipos de painel (`dash-kpi/`, `lista-onus/`). A senha do banco do UNM é lida de `UNM_DB_USER`/`UNM_DB_PASS`. |
| `relatorios/` | Relatórios técnicos de intervenções passadas (ex.: a criação da sincronização dos backups com o OneDrive, 27/10/2026). O procedimento em vigor está na skill `.claude/skills/conciliar-backups-onedrive/`. |
| `whatsapp/` | Documentação da solução de WhatsApp por QR code (ponte Baileys), retirada do código em 10/11/2026; o código está no commit `9804e4c`. |
