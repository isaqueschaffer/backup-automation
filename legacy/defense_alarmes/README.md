# Alarmes do Defense (Intelbras) — removido em 11/11/2026

Funcionalidade que lia as centrais de alarme Intelbras cadastradas num equipamento DEFENSE
(`/api/alarm-centrals`, porta configurável, padrão 3001) e mostrava o status (central conectada,
partições armadas/desarmadas) num modal do dashboard. Retirada "por enquanto" da interface e do
agente, a pedido do usuário; os arquivos ficam aqui como referência para reativar depois.

**Arquivos movidos para aqui (sem alteração de conteúdo):**
- `status_alarmes_defense.py` — era `agent/src/application/status_alarmes_defense.py` (loop de coleta)
- `defense_alarmes.py` — era `agent/src/vms/defense_alarmes.py` (cliente HTTP da API de alarmes)
- `test_defense_alarmes.py` — era `agent/tests/test_defense_alarmes.py`
- `AlarmesModal.tsx` — era `server/dashboard/src/pages/Machines/MachineDetail/components/AlarmesModal.tsx`

**O que foi desligado (não movido, só removido) nos arquivos que continuam ativos:**
- `agent/service.py`: thread `_alarmes_loop` e seu start em `_run_loop`.
- `agent/src/application/api_client.py`: função `send_status_alarmes`.
- `server/api/routers/agent.py`: rota `POST /defense/alarmes/status` e o import de `StatusAlarmeReport`.
- `server/api/routers/equipamentos.py`: rota `GET /{id}/alarmes`.
- `server/api/schemas.py`: `EquipamentoStatusAlarme` e `StatusAlarmeReport`.
- Dashboard: botão "Alarmes" no `EqCard.tsx`, o `AlarmesModal` e o campo "Porta dos Alarmes" no
  `EquipamentoFormModal.tsx` (e os tipos `AlarmPartition`/`AlarmCentral`/`AlarmeStatusResponse` e
  `porta_alarme` em `types.ts`/`utils.ts`).

**O que ficou:** a coluna `last_alarm_status` em `NVR` (banco) continua existindo, só não é mais escrita
nem lida — o projeto só faz migração aditiva, nunca remove coluna.

**Para reativar:** mover os quatro arquivos de volta aos caminhos originais, religar os pontos listados
acima e revisar se a API de alarmes do Defense IA mudou nesse meio tempo.
