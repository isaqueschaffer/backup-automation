---
trigger: always_on
description: Instruções obrigatórias sobre como realizar push de código, características do Dokploy e sincronização de repositórios.
---

# Características do Ambiente

1. **Sem acesso ao Dokploy (Produção)**: Você (Gemini) NÃO tem acesso ao painel do Dokploy. A única forma de levar código à produção é pelo Git.
2. **Deploy Automático**: Qualquer código que precise ir para a API/Dashboard em produção deve ser enviado para a branch `isaque` do repositório principal (`projetoswmfa`). O Dokploy rastreia essa branch e refaz o build/deploy automaticamente quando há novos commits.
3. **A produção não usa `server/docker-compose.yml`**: no Dokploy ela são Applications separados (Backend = `/server/api`, Frontend = `/server/dashboard`, build Railpack) mais um Postgres do próprio Dokploy. Mexer no compose não muda a produção; variáveis de ambiente, serviço novo e volumes são configurados pelo dono no Dokploy. Se a tarefa exigir isso, escreva no relatório exatamente o que precisa ser configurado lá.
4. **Colega de Equipe**: Existe um repositório secundário (`isaqueschaffer/backup-automation`) onde um colega trabalha exclusivamente na branch `integracao-equipamentos`.

# Regra Obrigatória para Commits e Pushes

Sempre que a IA finalizar uma implementação e for fazer o push das alterações, é **OBRIGATÓRIO** enviar o código para os dois repositórios simultaneamente (Push Duplo).

Execute os seguintes comandos no terminal:

1. **Repositório Principal (Atualiza o Dokploy em Produção)**:
   ```bash
   git push origin isaque
   ```

2. **Repositório Secundário (Sincronização com o Colega)**:
   ```bash
   git push https://github.com/isaqueschaffer/backup-automation.git isaque:integracao-equipamentos
   ```

**ATENÇÃO**: Nunca envie o código apenas para o `origin`. Você deve obrigatoriamente rodar o segundo push para garantir que o colega receba o código atualizado.

# Criação de Versão do Agente (OTA)
Quando uma nova versão do Agente Windows for compilada e colocada no GitHub Releases:
- Não tente alterar o banco de dados via SQL ou código. 
- Oriente o desenvolvedor a rodar o script `agent/publish_version.ps1` passando o link direto do GitHub.
- Antes de rodar o `build.ps1`, SEMPRE verifique se a versão dentro de `agent/src/application/updater.py` (variável `CURRENT_VERSION`) foi atualizada para bater com a nova versão.