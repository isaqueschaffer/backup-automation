---
name: tirar-duvidas
description: Antes de mexer em código, arquivo ou ambiente, tira todas as dúvidas com o usuário (perguntas objetivas, uma rodada) para fazer exatamente o que ele imagina e evitar retrabalho. Use em todo pedido de mudança que não seja trivial ou totalmente especificado — telas, endpoints, regras de negócio, agente, deploy, refatorações — e sempre que o usuário disser "me pergunte antes", "tire suas dúvidas" ou invocar /tirar-duvidas.
---

# Tirar dúvidas antes de executar

Objetivo: o resultado bater com o que o usuário tem na cabeça, na primeira entrega. Perguntar custa um minuto; refazer custa a confiança e o tempo dele.
Esta skill é um portão: **nenhuma edição, comando que altere estado, plano para o Gemini ou commit acontece antes de as dúvidas serem resolvidas.**

## 1. Entender sem incomodar (antes de perguntar)

Leia o necessário para perguntar bem. Dúvida que o código, o `PROJECT_SPEC.md`, o `CLAUDE.md` ou a memória respondem **não vai para o usuário**: descubra sozinho.
- Veja como a coisa funciona hoje (arquivos, telas, endpoints relacionados). Só leitura.
- Procure padrões já existentes no projeto que sirvam de resposta ("como as outras telas fazem").
- Anote o que continua ambíguo depois disso. Só isso vira pergunta.

## 2. Decidir se precisa perguntar

Pule as perguntas (e diga em uma linha o que vai fazer) quando o pedido já define resultado, escopo e comportamento, ou quando é correção pontual com causa e efeito claros. Pergunte quando houver ao menos uma destas:
- **Mais de um resultado visual ou de comportamento razoável** (layout, ordem, textos, o que mostrar quando vazio).
- **Escopo aberto**: quais telas, quais tipos de equipamento, quais clientes, só visual ou também API.
- **Efeito difícil de desfazer ou visível a clientes**: banco, produção, link público, envio de e-mail, versão do agente, deploy.
- **Conflito possível com regra do projeto** (REGRA-001 de datas, porta 7001, compose, `PROJECT_SPEC`).
- **Termos do usuário com mais de um sentido** ("organizar", "limpar", "melhorar", "mais rápido").

## 3. Como perguntar

Use a ferramenta `AskUserQuestion`, em **uma única rodada** (até 4 perguntas por chamada; se faltarem mais, priorize as que mudam o resultado e deixe o resto para uma segunda rodada curta, só se for essencial).
- Cada pergunta é fechada, em português simples, com 2 a 4 opções concretas. O usuário sempre pode escrever "Outro".
- Ponha a opção que você recomenda **primeiro**, com "(Recomendada)" no rótulo e o porquê na descrição.
- Use `preview` quando a diferença for visual (esboço em texto do layout de cada opção).
- Use `multiSelect` quando as opções não forem excludentes (ex.: "quais tipos agrupar").
- Nada de pergunta cuja resposta é óbvia, de confirmar o que o usuário acabou de dizer, ou de pedir permissão para ler arquivos.
- Não despeje perguntas em texto corrido quando a ferramenta resolve; se ela não estiver disponível, liste as perguntas numeradas, com a sua sugestão em cada uma, e espere.

Boas perguntas mudam o que será construído. Exemplos do projeto:
- "Os grupos de equipamentos devem começar abertos ou recolhidos?" (opções com a recomendada).
- "A mudança vale só para a tela da Máquina ou também para a do Cliente?"
- "Tipo sem equipamento: esconder o grupo ou mostrar vazio?"

## 4. Confirmar o entendimento

Depois das respostas, escreva um **resumo curto do que será feito** (3 a 6 linhas: o que muda, onde, o que fica de fora, decisões tomadas). Se alguma resposta abriu nova dúvida que muda o resultado, faça uma segunda rodada curta; senão, siga adiante sem pedir novo "ok": o resumo serve para o usuário interromper se algo estiver errado.
Não repita o que já foi respondido e não reabra decisões do usuário.

## 5. Executar

Só agora aplique as regras de trabalho do projeto (plano em `.cerebro/` para o Gemini, revisão do diff, `PROJECT_SPEC`, commit e push duplo conforme a memória). Cada resposta do usuário vira requisito no plano, escrita literalmente, para o executor não "reinterpretar".
Ao entregar, aponte em uma linha cada decisão que veio das perguntas, para o usuário conferir se saiu como pediu.

## Limites

- Perguntar não é desculpa para adiar: se o pedido é claro, execute.
- Nunca pergunte o que dá para descobrir lendo o projeto.
- Nunca peça senha, token ou segredo nas perguntas.
- Se o usuário disser "decide você" ou "faz do jeito que achar melhor", não pergunte: siga a opção recomendada e registre a escolha no resumo.
