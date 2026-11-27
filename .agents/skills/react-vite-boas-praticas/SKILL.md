---
name: react-vite-boas-praticas
description: Boas práticas de desempenho para o painel React (SPA Vite, sem Next.js) em server/dashboard. Use ao criar, alterar ou revisar componentes, hooks, listas, gráficos e busca de dados do painel.
license: MIT
metadata:
  author: vercel (adaptado para este projeto)
  version: "1.0.0"
---

# Boas práticas de React no painel (Vite)

Adaptação das regras de desempenho da Vercel para o painel em `server/dashboard` (React + Vite + TypeScript, SPA).
As regras do projeto sempre prevalecem. Neste projeto:

- Não é Next.js: ignore tudo sobre servidor, RSC, `server-*`, hidratação e `next/dynamic`. Para carregar um componente pesado só quando preciso, use `React.lazy` + `import()`.
- Não adicionar dependências (SWR, bibliotecas de estado, etc.) sem pedido explícito. A busca de dados segue o padrão que já existe em `src/api/`.
- Estilos inline e variáveis CSS existentes; ícones só de `lucide-react`; sem `any`; o `tsc` tem `noUnusedLocals/Parameters`.
- Antes de aplicar uma regra, leia o componente vizinho e siga o padrão dele. Não refatore código que não faz parte da tarefa.

Cada regra tem um arquivo em `rules/` com exemplo incorreto e correto. Abra só o que a tarefa pedir.

## Quando aplicar
Ao escrever ou revisar componentes React, hooks, listas grandes, gráficos, polling/busca de dados e ao notar re-renderizações ou carregamento lento.

## Regras por prioridade

### 1. Cascatas de requisições (crítico)
- `async-cheap-condition-before-await` - checar condição barata antes de aguardar algo remoto
- `async-defer-await` - mover o await para o ramo em que o valor é usado
- `async-parallel` - `Promise.all()` para chamadas independentes
- `async-dependencies` - paralelizar o que não depende uma da outra
- `async-suspense-boundaries` - só se o componente já usar Suspense

### 2. Tamanho do bundle (crítico)
- `bundle-barrel-imports` - importar direto do arquivo, evitar arquivos "barrel"
- `bundle-analyzable-paths` - caminhos de import estáticos
- `bundle-conditional` - carregar módulo só quando o recurso for ativado
- `bundle-preload` - pré-carregar ao passar o mouse/foco
- (`bundle-dynamic-imports` e `bundle-defer-third-party` citam `next/dynamic`: leia só a ideia e use `React.lazy`)

### 3. Busca de dados no cliente (médio-alto)
- `client-event-listeners` - não duplicar listeners globais
- `client-passive-event-listeners` - listeners passivos para scroll
- `client-localstorage-schema` - versionar e minimizar dados no localStorage

### 4. Re-renderização (médio)
- `rerender-defer-reads` - não assinar estado usado só em callbacks
- `rerender-memo` / `rerender-memo-with-default-value` - extrair trabalho caro; elevar props padrão não primitivas
- `rerender-dependencies` - dependências primitivas em efeitos
- `rerender-derived-state` / `rerender-derived-state-no-effect` - derivar durante a renderização, não em efeito
- `rerender-functional-setstate` - `setState(prev => ...)` para callbacks estáveis
- `rerender-lazy-state-init` - função em `useState` para valores caros
- `rerender-simple-expression-in-memo` - não usar memo para expressões simples
- `rerender-split-combined-hooks` - separar hooks com dependências independentes
- `rerender-move-effect-to-event` - lógica de interação em handlers
- `rerender-transitions` / `rerender-use-deferred-value` - `startTransition` e valor adiado para atualizações não urgentes
- `rerender-use-ref-transient-values` - refs para valores transitórios e frequentes
- `rerender-no-inline-components` - nunca definir componente dentro de componente

### 5. Renderização (médio)
- `rendering-animate-svg-wrapper` - animar o `div` que envolve o SVG
- `rendering-content-visibility` - `content-visibility` em listas longas
- `rendering-hoist-jsx` - JSX estático fora do componente
- `rendering-svg-precision` - reduzir precisão das coordenadas SVG
- `rendering-activity` - mostrar/esconder sem desmontar
- `rendering-conditional-render` - ternário em vez de `&&` quando o valor pode ser `0`
- `rendering-usetransition-loading` - `useTransition` para estado de carregamento
- `rendering-resource-hints` / `rendering-script-defer-async` - só se mexer em `index.html`

### 6. JavaScript (baixo-médio)
`js-batch-dom-css`, `js-index-maps`, `js-cache-property-access`, `js-cache-function-results`, `js-cache-storage`, `js-combine-iterations`, `js-length-check-first`, `js-early-exit`, `js-hoist-regexp`, `js-min-max-loop`, `js-set-map-lookups`, `js-tosorted-immutable`, `js-flatmap-filter`, `js-request-idle-callback`.

### 7. Avançado (baixo)
`advanced-effect-event-deps`, `advanced-event-handler-refs`, `advanced-init-once`, `advanced-use-latest`.
