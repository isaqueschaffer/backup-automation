# archive/

Código legado, mantido só para consulta. Não é usado em produção nem entra em nenhum build.

- `whatsapp/` — documentação da solução de WhatsApp por QR code (ponte Baileys), retirada do código em 10/11/2026; o código está no commit `9804e4c`.
- `legacy_scripts/` — scripts antigos (UNM2000, backup de NVR, checagem de gravação, V-SOL) anteriores ao agente atual (`agent/`).
  O comportamento equivalente hoje está em `agent/src/`.
- `legacy_scripts/digifort_snmp.py` — método legado de monitoramento do Digifort via receptor de traps SNMP (porta 162 UDP). Substituído em produção pela checagem ativa via Ping ICMP direto do Agente Windows.
