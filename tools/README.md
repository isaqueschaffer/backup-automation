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
