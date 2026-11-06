---
trigger: always_on
description: Como e quando delegar o trabalho aos subagentes especializados deste projeto.
---

# Regras de Uso dos Subagentes Especializados

O agente principal deve coordenar o desenvolvimento delegando o trabalho aos subagentes especializados configurados em `.agents/agents/`:

1. **Subagentes Disponíveis e Quando Usar**:
   - `backend-fastapi`: alterações na API FastAPI em `server/api` (rotas, models, schemas, migrações inline, widgets).
   - `frontend-dashboard`: alterações no painel React/Vite em `server/dashboard/src` (componentes, telas, widgets, tipos).
   - `agente-windows`: alterações no agente Windows em `agent/src` (backups, drivers de equipamentos, serviço, telemetria).
   - `revisor`: auditoria de diffs e arquivos alterados contra as REGRAs do projeto e segurança; chamar ao final de qualquer tarefa de código antes de declarar concluído.
   - `depurador`: investigação de causa raiz ao receber erros de execução, falhas de build/tsc ou bugs inesperados; chamar antes de tentar consertos no escuro.

2. **Diretrizes de Delegação**:
   - **Contexto Inicial**: cada subagente inicia sem o histórico da conversa. Passe sempre o caminho do plano da tarefa e a lista exata de arquivos que ele deve ler ou editar.
   - **Contratos e Paralelismo**: o contrato entre camadas (nomes de campos, tipos e schemas JSON) deve ser definido pelo plano antes de delegar. Quando backend e frontend forem independentes após o contrato fixado, delegue a execução em paralelo.
   - **Ciclo de Revisão**: ao finalizar alterações de código, acione o `revisor`. Quaisquer achados classificados como `Crítico:` ou sem prefixo (obrigatórios) devem ser corrigidos antes do encerramento.
   - **Erros e Falhas**: se algo falhar ou quebrar de forma inesperada, chame o `depurador` para obter a causa raiz e a correção antes de modificar arquivos.
   - **Sem Git para Subagentes**: subagentes nunca executam commits ou pushes (a regra de `git-deploy.md` é privativa do agente principal e não se aplica a eles; ordens de "sem comandos git" valem estritamente para todos).
   - **Comunicação Final**: o resumo final apresentado ao usuário deve discriminar com clareza os arquivos criados ou alterados por cada subagente.
