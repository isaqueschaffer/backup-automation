# tools/

Utilitários de apoio, diagnóstico e testes ponta a ponta. **Nenhum faz parte do build do agente nem do deploy do
servidor**, e nenhum é importado pelo código de produção (exceto `verificar_regras.py`, que o CI roda).

Credenciais e chaves de API **nunca** são gravadas nestes scripts: passe por argumento ou variável de ambiente.

## Processo

| Arquivo | Para que serve | Uso |
|---|---|---|
| `verificar_regras.py` | Verificações da auditoria de merge (CLAUDE.md) nas linhas adicionadas: segredo, arquivo de credencial ou binário grande reprovam; REGRA-001, REGRA-010, `verify=False` novo e a senha padrão em lugar novo viram aviso. Roda no CI (`.github/workflows/ci.yml`) | `python tools/verificar_regras.py <commit_base> [<commit_final>]` |

## Testes ponta a ponta (só no ambiente local, nunca contra a produção)

| Arquivo | O que testa | Uso |
|---|---|---|
| `teste_dashboards_e2e.py` | Dashboard por Cliente pela API: isolamento entre clientes, token do link (inválido, expirado, revogado, regenerado), limite de tentativas, edição permitida/negada, token não abre rotas admin, resposta pública sem IP/credenciais | `python tools/teste_dashboards_e2e.py <senha-admin-local>` |
| `dashboards_ui/` | O mesmo dashboard num navegador de verdade (Chromium headless em Docker): `seed.py` cria um cliente de demonstração e `ui_test.js` abre as páginas, personaliza, salva, compartilha e revoga, gerando capturas de tela | `python tools/dashboards_ui/seed.py <senha> seed.json` e depois `docker run --rm --add-host=host.docker.internal:host-gateway -v <pasta com seed.json e ui_test.js>:/work -e NODE_PATH=/usr/src/app/node_modules --entrypoint node zenika/alpine-chrome:with-puppeteer /work/ui_test.js` |
| `teste_telemetria_nvr_e2e.py` | Telemetria de NVR de ponta a ponta (post_report real do agente → API → widget Gravadores) | Em container, contra a stack local |

## Diagnóstico e simulação

| Arquivo | Para que serve |
|---|---|
| `teste_print_hikvision.py` | Teste manual de login/consulta em NVR Hikvision (credenciais por argumento) |
| `simulador_digifort.py` | Simula eventos do Digifort para testar o webhook |
| `test_webhook.py` | Dispara um webhook de teste |
| `snmp_sniffer.py` | Escuta traps SNMP para diagnóstico |

## Digifort standalone (anteriores ao agente atual)

O agente (`agent/src/vms/`) já cobre o Digifort; estes dois ficam para uso avulso num cliente sem o agente.

| Arquivo | Para que serve |
|---|---|
| `agente_digifort.py` | Lê os logs do Digifort e gera um relatório de status das câmeras (quedas, erros de gravação). Antes de rodar, ajuste no início do arquivo `PASTA_LOGS_DIGIFORT` (logs no servidor do cliente) e `PASTA_RELATORIOS` (onde salvar o relatório); depois `python agente_digifort.py` |
| `agente_webhook_digifort.py` | Versão standalone do webhook do Digifort |
