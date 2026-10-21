---
name: criar-widget-dashboard
description: Como adicionar um novo tipo de widget (componente) ao Dashboard por Cliente — modelo de config e montagem dos dados no backend (services/dashboards) e visualização/campos de configuração no front (pages/Dashboards/widgets). Use ao criar ou alterar componentes do dashboard.
---

# Novo tipo de widget do Dashboard por Cliente

O dashboard é modular: cada tipo se registra no backend e no front, sem mexer em rotas, editor ou compartilhamento.
Regra de ouro: o servidor monta os dados e **filtra tudo pelo cliente do dashboard**. A resposta vale também para o link público,
então só devolva o que o cliente pode ver (nada de IP, usuário, senha, `config_extra`, chaves de API).

## Backend (`server/api/services/dashboards/widgets.py`)

1. **Config**: classe Pydantic com `model_config = {"extra": "forbid"}`. Listas de ids (`List[UUID]`, `max_length=200`); vazio significa "todos do cliente".
2. **Montagem**: `def construir_x(ctx: ContextoDados, config: ConfigX) -> Dict[str, Any]`.
   - Use `ctx.maquinas` (só as ativas do cliente, com equipamentos carregados) e `filtrar_maquinas(ctx, config.maquinas)`: ids de outros clientes são ignorados.
   - Consultas extras sempre filtradas por `ctx.maquinas`/`ctx.customer.id`. Datas em UTC naive; serialize com `iso(dt)`.
   - Telemetria só por `telemetria_publica(...)` (lista branca). Resultado serializável em JSON.
3. **Registro**: no fim do arquivo, `registrar(TipoWidget(tipo="x", rotulo=..., descricao=..., config_model=ConfigX, largura_padrao=<3|4|6|8|12>, altura_padrao=<1..4>, construir=construir_x))`.
4. Se a config referencia ids de máquina/equipamento, confira `ids_referenciados` em `layout.py`: ele lê as chaves `maquinas` (qualquer widget) e `equipamentos` (só `cameras`). Chave nova de id exige ajustar essa função (senão o 422 de isolamento não cobre o campo).

## Front (`server/dashboard/src/pages/Dashboards/`)

1. **Tipos** em `types.ts`: `DadosX` com o formato devolvido pela montagem.
2. **Componente** `widgets/XWidget.tsx`: `({ dados, widget })`, preenche a área (`height: 100%`, rolagem interna), estilos inline e variáveis CSS; texto sempre como texto (nunca HTML).
3. **Registro** em `widgets/registry.tsx` (`DEFINICOES`): `rotulo`, `descricao`, `icone` (lucide), `larguraPadrao`, `alturaPadrao`, `configPadrao` (igual aos defaults do Pydantic), `renderizar` (um único cast de `unknown` para `DadosX`) e `campos`.
4. **Campos de configuração** (`CampoWidget`): `maquinas`, `equipamentos`, `tipos`, `periodo`, `opcao` (select com `opcoes`), `booleano` e `texto`. O modal de configuração é gerado a partir deles; tipo de campo novo exige tratar em `WidgetConfigModal.tsx`.
5. O catálogo do servidor (`GET /api/v1/dashboards/widgets`) já lista o tipo novo sozinho.

## Conferir antes de fechar

- Teste de isolamento: com dois clientes, o dashboard de A nunca traz máquina/equipamento de B (use `tools/teste_dashboards_e2e.py` e acrescente verificações do novo tipo).
- A resposta pública não contém IP, credencial ou configuração interna.
- `PROJECT_SPEC.md`: entrada no changelog (e rota/tabela, se mudou o contrato).
