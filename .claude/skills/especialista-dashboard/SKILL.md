---
name: especialista-dashboard
description: Especialista no Dashboard por Cliente. Quando um equipamento ganha suporte novo (tipo em TIPOS_EQUIPAMENTO, coluna de status nova, módulo novo no agente) ou o usuário pede "o dash do equipamento X", descobre quais dados esse equipamento já manda, propõe o que vale mostrar, pergunta ao usuário quais informações interessam (AskUserQuestion) e só então monta o widget. Use também depois da skill criar-novo-agente, ao revisar um merge que trouxe equipamento novo, ou quando o usuário perguntar o que dá para mostrar no dashboard de algum equipamento.
---

# Especialista em Dashboard por Cliente

O Dashboard por Cliente (`server/api/services/dashboards/` + `server/dashboard/src/pages/Dashboards/`) é o que **o cliente final vê**, inclusive pelo link público.
Esta skill decide **o que** mostrar de cada equipamento; a skill `criar-widget-dashboard` diz **como** implementar. Use as duas juntas.
Pergunte antes de construir: a escolha do que entra no dash é do usuário, não sua (o portão é o mesmo da `tirar-duvidas`).

## 1. Detectar o que está sem dashboard

Rode e compare (só leitura):

```bash
grep -n "TIPOS_EQUIPAMENTO =" server/api/schemas.py
grep -n "Column(JSON" server/api/models.py                      # colunas de status do NVR/equipamento
grep -n "tipo=\"" server/api/services/dashboards/widgets.py      # widgets registrados
grep -nE "olt_status|antena_status|last_alarm_status|last_telemetry_status|last_recording_status|conexao_status" server/api/services/dashboards/*.py
git log --oneline -15 -- server/api/schemas.py server/api/models.py agent/src   # o que entrou de novo
```

Mapa de cobertura em 13/11/2026 (atualize esta tabela quando criar um widget):

| Tipo | De onde vêm os dados | No dashboard hoje |
|---|---|---|
| NVR (Hikvision, Motorola) | `cameras` (gravação/online), `last_recording_status`, `last_telemetry_status` (CPU/RAM/discos) | `cameras`, `status_nvr`, `telemetria_equipamentos`, `equipamentos`, `resumo` |
| DIGIFORT, MIXED, CAMERA | câmeras e status do backup | `cameras`, `status_nvr`, `equipamentos` |
| OLT (UNM2000, VSOL, Huawei) | `olt_status` (OLTs/ONUs, a cada 5 min; leitor em `routers/equipamentos.py` `get_olt_status`) | `status_olt` (totais, PONs com problema, licença; sem ONU individual) |
| DEFENSE (centrais Intelbras) | `last_alarm_status` (`alarmes`, `incendio`, a cada 5 min) | `alarmes_defense` (disparo, desconexão, partições; armada/desarmada fora do link público) |
| ANTENA (Wi-Fi via MikroTik) | `antena_status` (`antenas` com ONLINE/OFFLINE/SEM_REGISTRO/ERRO, quando caiu, visto online; `services/antenas.py`, a cada 3 min) | `antenas` + cartão no `resumo` |
| MIKROTIK, PABX, ONU | apenas resultado do backup (`Backup.nvr_results`) | `equipamentos` |
| Máquina (servidor do agente) | `Machine` telemetria (CPU/RAM/disco/rede) | `saude_servidor`, `resumo` |

Equipamento com dados ricos e só "status do backup" no dash = candidato a widget próprio. Diga isso ao usuário logo no começo.

Modelo a copiar (13/11/2026): os widgets `antenas`, `status_olt` e `alarmes_defense` em `widgets.py` usam `equipamentos_do_tipo`, `_atualidade` (marca "sem atualização" pelo intervalo do agente), `nivel` por item calculado no servidor e lista branca `*_publico`. No front, usam as peças de `widgets/statusComum.tsx` (`CartaoEquipamento`, `Linha`, `COR_NIVEL`). Para esconder algo só no link público, use `ctx.publico`.

## 2. Inventariar os dados do equipamento

Antes de propor qualquer coisa, leia de onde o dado nasce e o formato real:
- **Agente**: o módulo do fabricante (`agent/src/<tipo>/...`) e o envio em `agent/src/application/api_client.py` / `status_<tipo>.py`.
- **API**: o receptor em `server/api/routers/agent.py` (o que é gravado e com que chaves), o serviço em `server/api/services/<tipo>.py` e o schema.
- **Painel interno**: o modal/card que já mostra esse dado ao técnico (`pages/Machines/MachineDetail/components/`, ex.: `AntenasModal.tsx`). Ele mostra o que o dado tem; o dash do cliente costuma precisar de bem menos.
- **Testes** (`server/api/tests/test_<tipo>.py`, `agent/tests/`) trazem exemplos de payload.

Classifique cada campo:

| Classe | Exemplo | No dash do cliente |
|---|---|---|
| Situação (está funcionando?) | ONLINE/OFFLINE, central armada, câmera gravando | quase sempre: é o principal |
| Problema / alerta | antena caída há 2 h, disparo de incêndio, disco com falha, ONU com sinal ruim | sim, em destaque e primeiro |
| Capacidade / saúde | CPU, RAM, disco, sinal óptico (dBm), uptime | às vezes; com limiar claro |
| Atualidade | `atualizado_em`, visto online em | sempre (dado velho não pode parecer atual) |
| Identificação | nome, modelo, quantidade | sim, curto |
| Detalhe técnico | MAC, OID, porta, firmware, logs | quase nunca |
| **Sensível** | IP, usuário, senha, `config_extra`, MAC completo, chaves | **nunca** (vale o link público) |

Se a informação que faria sentido mostrar **não existe** (ex.: histórico, quando só guardamos o último status), diga isso: mostrar exige gravar no agente/API antes, e isso entra nas perguntas.

## 3. Propor e perguntar

Monte 3 a 6 informações candidatas, ordenadas pelo valor para o cliente (situação e problemas primeiro). Formatos que funcionam neste dash:
- **Contador/KPI** ("18 de 20 antenas online"), bom para o `resumo` ou um widget pequeno.
- **Pizza ou barra de situação** (padrão do `status_nvr`), quando há várias unidades com estados.
- **Lista com semáforo** (nome + situação + "há quanto tempo"), problemas no topo.
- **Barras de uso** (padrão do `telemetria_equipamentos`) para percentuais com limiar.
- **Linha do tempo / histórico**: só se o dado for guardado ao longo do tempo.

Depois pergunte com `AskUserQuestion`, numa rodada (até 4 perguntas). Recomendada sempre primeiro, com o porquê. Perguntas típicas:
1. **Quais informações entram** (`multiSelect`): as candidatas do passo anterior, cada uma com uma linha dizendo o que o cliente ganha vendo aquilo.
2. **Onde entra**: widget novo dedicado ao tipo (recomendado quando há dado próprio) × estender o `equipamentos`/`resumo` × as duas coisas (widget + contador no resumo).
3. **Visual** (com `preview` em texto mostrando cada esboço): pizza agregada, lista com semáforo, cartões por equipamento.
4. **Regras de cor / alerta**: quando fica amarelo e vermelho (ex.: offline há mais de X min, sinal abaixo de -27 dBm), e o que mostrar quando o dado está velho ou o equipamento nunca mandou status.

Segunda rodada curta só se a resposta abriu algo que muda o resultado (ex.: "quero histórico" → precisa de tabela nova; perguntar retenção). Não pergunte o que o código responde (formato do dado, onde fica). Se o usuário disser "decide você", siga as recomendadas e registre no resumo.

Feche com um resumo de 3 a 6 linhas: o widget (nome e tipo), o que mostra, as cores/limiares, o que ficou de fora e por quê.

## 4. Construir

Siga a `criar-widget-dashboard` (config Pydantic, `construir_x`, `registrar`, componente, `registry.tsx`, campos). Além dela:
- **Lista branca do dado**: crie `<tipo>_publico(raw)` em `widgets.py`, no molde de `telemetria_equipamento_publica`: copia só as chaves escolhidas, valida tipo numérico, corta strings, limita listas. Nunca repasse a coluna JSON inteira.
- **Filtro por tipo**: só equipamentos `e.tipo == "<TIPO>"` de `equipamentos_ativos(m)` das máquinas do contexto; config com `equipamentos: List[UUID]` (vazio = todos) e confira `ids_referenciados` em `layout.py` para incluir o widget novo na lista que lê `equipamentos`.
- **Atualidade**: devolva `atualizado_em` (via `iso`) e `segundos_desde`; no front, marque como "sem atualização" quando passar do intervalo do agente (status a cada 5 min → velho após ~15 min). Datas em UTC naive (REGRA-001).
- **Estados vazios**: "nenhum equipamento deste tipo" e "ainda não recebeu status" com texto próprio, sem quebrar o quadro.
- **Problemas primeiro**: ordene a lista com o pior estado no topo; reaproveite as cores já usadas nos widgets (variáveis CSS do tema).
- **Gráfico**: antes de escrever código de gráfico, carregue a skill `dataviz`; reaproveite `PieChart.tsx` e `useElementSize` em vez de biblioteca nova.
- **Resumo**: se o usuário quis contador no `resumo`, acrescente a chave em `construir_resumo` e no `ResumoWidget.tsx` sem mudar as que existem.
- **Testes**: em `server/api/tests/`, cobrir a lista branca (campo sensível não aparece), o filtro por tipo e o isolamento entre clientes; ampliar `tools/teste_dashboards_e2e.py` com o tipo novo.

## 5. Fechar

- Atualize a tabela de cobertura do passo 1 desta skill.
- `PROJECT_SPEC.md`: changelog com o widget novo e o que ele mostra.
- Mudou só servidor/painel: não há versão do agente; commit e push conforme a memória/CLAUDE.md (o push na `isaque` faz deploy).
- Ao entregar, liste em uma linha cada decisão que veio das perguntas, para o usuário conferir.
