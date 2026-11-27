---
name: revisao-de-codigo
description: Revisão de alterações de código em cinco eixos (correção, legibilidade, arquitetura, segurança, desempenho) com checagem das regras do projeto. Use antes de dar uma tarefa por concluída, ao revisar o trabalho de outro agente ou ao auditar um diff.
license: MIT
metadata:
  origem: adaptado de addyosmani/agent-skills (code-review-and-quality), commit aeac41d
---

# Revisão de código

Aprove a mudança quando ela melhora a saúde do código e segue as convenções do projeto, mesmo sem ser perfeita. Não aprove "no escuro": cite evidência (arquivo e linha) de que você leu o que mudou.

## Como revisar
1. **Contexto**: leia o plano/tarefa. O que a mudança deve fazer e o que NÃO deve tocar?
2. **Escopo**: liste os arquivos alterados. Arquivo fora do plano é achado (informe, não corrija sem ordem).
3. **Cinco eixos** em cada arquivo:
   - Correção: faz o que o plano diz? casos de borda (vazio, nulo, limites)? caminhos de erro?
   - Legibilidade: nomes claros, fluxo direto, sem esperteza; menos linhas quando possível; sem código morto nem variável/import sem uso (o `tsc` falha com `noUnusedLocals/Parameters`).
   - Arquitetura: segue o padrão dos arquivos vizinhos? não vaza lógica específica para módulo compartilhado? não duplica helper que já existe?
   - Segurança: veja a skill `seguranca-e-endurecimento`.
   - Desempenho: consulta N+1, laço sem limite, lista sem paginação, re-render desnecessário.
4. **Regras do projeto** (PROJECT_SPEC.md, seção 6; CLAUDE.md): confira as que o diff toca.
   - REGRA-001: datas do banco sem fuso (`datetime.utcnow()`); nunca `datetime.now(timezone.utc)`.
   - REGRA-003: autenticação do painel (`get_contexto`, `exigir_super_admin`, `exigir_admin_conta`) x agente (`X-API-Key`); rotas novas precisam de uma das duas (`verify_admin_token` só por compatibilidade, aceita só o super admin).
   - REGRA-010: isolamento por conta — Cliente/Máquina por `obter_cliente`/`obter_maquina`, listas por `filtrar_por_conta` (`services/escopo.py`); outra conta = 404; registro novo com `conta_id`. Violação é `Crítico:`.
   - REGRA-004: senhas de equipamento/ZIP com Fernet (`encrypt`/`decrypt`); respostas do admin nunca trazem senha.
   - REGRA-007: migrações inline em `main.py` (sem Alembic), idempotentes.
   - Dashboard por Cliente: tudo filtrado pelo cliente; resposta pública só com lista branca (sem IP, usuário, senha, `config_extra`).
   - Compose, nginx, `requirements*.txt`, `agent/build.ps1`, `agent/installer.iss`, `.env*`: só mudam se o plano mandar.
5. **Classifique cada achado**: `Crítico:` (segurança, perda de dados, quebra de funcionalidade), sem prefixo (correção obrigatória), `Opcional:` e `Nit:`. Comece pelo que importa; poucos achados de alta convicção valem mais que uma lista longa.

## Remédios estruturais
Ao apontar complexidade, proponha a saída: trocar cadeia de `if` por tabela/despachante, juntar ramos duplicados, separar orquestração de regra de negócio, reusar o helper existente, apagar wrapper que só repassa.

## Honestidade
Não suavize problema real, não escreva "LGTM" sem evidência, quantifique quando puder. Código de IA pede mais atenção, não menos.

## Saída
Veredito (`Aprovado` / `Pedir ajustes`), lista de achados por severidade com arquivo:linha e a correção sugerida, e os arquivos fora do plano.
