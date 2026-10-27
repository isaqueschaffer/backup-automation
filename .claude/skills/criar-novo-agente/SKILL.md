---
name: criar-novo-agente
description: Como adicionar ao agente Windows o backup de um novo tipo de equipamento ou de uma nova marca (NVR, OLT, PABX, Mikrotik, VMS...), incluindo API, dashboard, build e release. Use ao integrar um equipamento ou fabricante novo.
---

# Integração de um novo equipamento no agente (`agent/`)

O agente roda como serviço Windows (`service.py`, pywin32), empacotado com PyInstaller (`agent/build.ps1`) e Inno Setup (`installer.iss`).
O backup (`run_backup` em `src/application/backup_job.py`) busca os equipamentos no servidor (`GET /api/v1/agent/config`), processa um por um, zipa e envia o relatório e o ZIP.

## Onde fica cada coisa

| Caminho | Conteúdo |
|---|---|
| `src/nvr/hikvision/`, `src/nvr/motorola/` | NVR/DVR por marca (câmeras e gravações); `src/nvr/factory.py` escolhe a marca |
| `src/nvr/<marca>/planilha.py`, `src/nvr/planilha_comum.py` | Planilha `.xlsx` da configuração do NVR, gerada no backup (`PLANILHAS_NVR` em `backup_job.py`); nunca grava usuário/senha |
| `src/olt/` | `unm2000.py`, `vsol.py`, `huawei_active.py` |
| `src/pabx/issabel.py`, `src/mikrotik/routeros.py`, `src/vms/defense.py` | um módulo por fabricante |
| `src/camera/rtsp_client.py` | captura RTSP com ffmpeg |
| `src/backup/` | download, ZIP com senha, cópia de arquivos |
| `src/core/config.py` | `load_conf()` (`agent.conf`) e `parse_config_extra()` |
| `src/application/api_client.py` | chamadas ao servidor (config, relatório, upload, ping) |

## Nova marca de um tipo existente (ex.: outra OLT)

1. `src/<tipo>/<fabricante>.py` com `realizar_backup_<fabricante>(equipamento: dict, pasta_destino: Path) -> dict`.
2. Rotear no `processar_<tipo>()` do `backup_job.py` pela escolha gravada em `config_extra` (ex.: `fabricante_olt`, `marca`).
3. Dashboard: a opção no `EquipamentoFormModal.tsx` e em `buildEqPayload` (`pages/Machines/MachineDetail/utils.ts`), salvando em `config_extra`.

## Tipo novo

1. **Agente**: módulo + `processar_<tipo>()` + um `if tipo == "<TIPO>"` em `processar_equipamento()` (`backup_job.py`). Tipo sem processador volta como `TIPO_NAO_SUPORTADO`.
2. **API**: incluir em `TIPOS_EQUIPAMENTO` (`server/api/schemas.py`); a validação de `routers/equipamentos.py` e do relatório em `routers/agent.py` usa essa lista.
3. **Dashboard**:
   - `TipoEquipamento` em `src/api/types.ts`;
   - `TIPOS` e `TIPO_ICONE_EMOJI` em `pages/Machines/MachineDetail/utils.ts`;
   - campos e validação no `EquipamentoFormModal.tsx` e em `buildEqPayload`;
   - ícone e cor em `components/EqCard.tsx`.

## Contrato do processador

- Entrada: o equipamento como o servidor manda: `id`, `tipo`, `name`, `ip`, `username`, `password` (já descriptografada), `config_extra` (ler com `parse_config_extra`).
- Saída: `{"nome": name, "status": "OK" | "ERRO", "cameras": None}` (`cameras` só no NVR). Arquivos vão para `pasta_destino` (`mkdir(parents=True, exist_ok=True)`); o job zipa a pasta.
- Exceção nunca escapa: registrar com `logging` (vai para `logs/agent.log`) e devolver `"status": "ERRO"`. Um equipamento com falha não pode parar o backup dos outros.
- Timeout em toda chamada de rede. `nome_seguro()` para nomes usados em caminhos e comandos. Senha nunca no log.

## Build e entrega

- Dependência nova: `agent/requirements.txt`; se ela tiver arquivos de dados, `--collect-all <pacote>` no `build.ps1`.
- Módulo importado só dentro de função (como `src.olt.huawei_active`): `--hidden-import src.<tipo>.<modulo>` no comando do `TrilanAgentService` em `build.ps1`, senão o PyInstaller não o inclui.
- Versão nova do agente: checklist do `CLAUDE.md` (versão em 3 lugares, build, release no repositório público, cadastro no painel só com "publique").
- Changelog no `PROJECT_SPEC.md`.
