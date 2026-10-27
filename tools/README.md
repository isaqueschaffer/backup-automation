# tools/

Utilitários avulsos de apoio e diagnóstico. **Não fazem parte do build do agente nem do deploy do servidor.**
Nenhum deles é importado pelo código de produção.

| Arquivo | Para que serve |
|---|---|
| `agente_digifort.py` | Agente Digifort standalone (ver abaixo) |
| `agente_webhook_digifort.py` | Versão standalone do webhook do Digifort |
| `simulador_digifort.py` | Simula eventos do Digifort para testar o webhook |
| `snmp_sniffer.py` | Escuta traps SNMP para diagnóstico |
| `test_webhook.py` | Dispara um webhook de teste |
| `teste_print_hikvision.py` | Teste manual de login/consulta em NVR Hikvision (pede credenciais por argumento) |
| `teste_telemetria_nvr_e2e.py` | Telemetria de NVR ponta a ponta (post_report real do agente → API → widget Gravadores); roda em container contra a stack local |

Credenciais e chaves de API **nunca** devem ser gravadas nestes scripts: passe por argumento ou variável de ambiente.

---

# tools/

Scripts utilitários e ferramentas de análise standalone, **não integrados ao agente de backup**.

## agente_digifort.py

Script de análise de logs do software **Digifort** (NVR). Lê os logs do Digifort e gera um relatório de status das câmeras (quedas, erros de gravação, etc.).

### Como usar

1. Edite as constantes no início do arquivo:
   - `PASTA_LOGS_DIGIFORT` — caminho real da pasta de logs do Digifort no servidor do cliente
   - `PASTA_RELATORIOS` — pasta onde o relatório será salvo (ex: OneDrive compartilhado)

2. Execute diretamente:
   ```
   python agente_digifort.py
   ```

### Observações

- Este script é **independente** do serviço Windows de backup (`TrilanAgentNVR`).
- Requer Python 3.x instalado na máquina onde for executado.
- Os caminhos padrão no script são exemplos e devem ser ajustados para cada cliente.

## Testes do Dashboard por Cliente (rodar só no ambiente local)

| Arquivo | O que testa |
|---|---|
| `teste_dashboards_e2e.py` | API: isolamento entre clientes, token do link (inválido, expirado, revogado, regenerado), limite de tentativas, edição permitida/negada, token não abre rotas admin, resposta pública sem IP/credenciais. Uso: `python tools/teste_dashboards_e2e.py <senha-admin-local>` |
| `dashboards_ui/` | Navegador de verdade (Chromium headless em Docker): `seed.py <senha> seed.json` cria um cliente de demonstração e `ui_test.js` abre a página pública e a de administração, personaliza, salva, compartilha e revoga, gerando capturas de tela. Execução: `docker run --rm --add-host=host.docker.internal:host-gateway -v <pasta com seed.json e ui_test.js>:/work -e NODE_PATH=/usr/src/app/node_modules --entrypoint node zenika/alpine-chrome:with-puppeteer /work/ui_test.js` |
