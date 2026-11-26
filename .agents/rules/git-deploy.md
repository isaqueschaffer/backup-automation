---
trigger: always_on
description: Instruções obrigatórias sobre como realizar push de código, características do Dokploy e sincronização de repositórios.
---

# Características do Ambiente

1. **Sem acesso ao Dokploy (Produção)**: Você (Gemini) NÃO tem acesso ao painel do Dokploy. A única forma de levar código à produção é pelo Git.
2. **Deploy NÃO é automático (desde 25/11/2026)**: o Dokploy põe no ar o ramo `producao` do repositório público `isaqueschaffer/backup-automation`, que só o dono pode atualizar. Você envia o código para a `isaque` (push duplo abaixo) e **não** empurra para `producao` nem dispara deploy: quem leva à produção é o dono (ou o Claude, pelo `server/deploy_producao.ps1`). No relatório, diga se a mudança precisa ir ao ar (servidor/painel) para o dono fazer o deploy.
3. **A produção não usa `server/docker-compose.yml`**: no Dokploy ela são Applications separados (Backend = `/server/api`, Frontend = `/server/dashboard`, build Railpack) mais um Postgres do próprio Dokploy. Mexer no compose não muda a produção; variáveis de ambiente, serviço novo e volumes são configurados pelo dono no Dokploy. Se a tarefa exigir isso, escreva no relatório exatamente o que precisa ser configurado lá.
4. **Colega de Equipe**: Existe um repositório secundário (`isaqueschaffer/backup-automation`) onde um colega trabalha exclusivamente na branch `integracao-equipamentos`.

# Regra Obrigatória para Commits e Pushes

Sempre que a IA finalizar uma implementação e for fazer o push das alterações, é **OBRIGATÓRIO** enviar o código para os dois repositórios simultaneamente (Push Duplo).

Execute os seguintes comandos no terminal:

1. **Repositório Principal (ramo de trabalho; não põe nada no ar sozinho)**:
   ```bash
   git push origin isaque
   ```

2. **Repositório Secundário (Sincronização com o Colega)**:
   ```bash
   git push https://github.com/isaqueschaffer/backup-automation.git isaque:integracao-equipamentos
   ```

**ATENÇÃO**: Nunca envie o código apenas para o `origin`. Você deve obrigatoriamente rodar o segundo push para garantir que o colega receba o código atualizado. **Nunca** faça push para o ramo `producao` nem rode `server/deploy_producao.ps1`.

# Criação de Versão do Agente (OTA)
Quando uma nova versão do Agente Windows for compilada e colocada no GitHub Releases:
- Não tente alterar o banco de dados via SQL ou código. 
- Oriente o desenvolvedor a rodar o script `agent/publish_version.ps1` passando o link direto do GitHub.
- Antes de rodar o `build.ps1`, SEMPRE verifique se a versão dentro de `agent/src/application/updater.py` (variável `CURRENT_VERSION`) foi atualizada para bater com a nova versão.