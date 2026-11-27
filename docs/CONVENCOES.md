# Convenções do projeto

Glossário do domínio e regras de nomes e de organização de pastas. Vale para **código novo e arquivos tocados**:
o que já existe com outro nome **não é renomeado** só por estilo (renomear tabela, rota ou função pública quebra a
produção, o agente em campo ou as ferramentas do MCP, que usam o nome da função da rota como nome da ferramenta).

## Glossário: conceito × código × banco

Vários nomes no código e no banco vêm de antes do sistema de contas e não batem com o conceito. Leia esta tabela
antes de mexer em modelos, rotas ou consultas.

| Conceito (como o usuário fala) | Modelo (`server/api/models.py`) | Tabela | Rota da API | Rota do painel |
|---|---|---|---|---|
| **Conta** (integrador ou cliente final; o inquilino) | `Conta` | `contas` | `/api/v1/conta`, `/api/v1/admin/contas` | `/contas` |
| **Cliente / Setor** (empresa atendida, agrupa máquinas) | `Customer` | **`client_groups`** | **`/api/v1/clients`** | `/clientes` |
| **Máquina** (computador ou Mikrotik com o agente) | `Machine` | **`clients`** | `/api/v1/machines` | `/maquinas` |
| **Equipamento** (NVR, câmera, OLT, PABX, Mikrotik, antena, Digifort, Defense...) | **`NVR`** (qualquer tipo; o campo `tipo` diz qual) | **`nvrs`** | `/api/v1/machines/{id}/equipamentos` | dentro da máquina |
| Câmera de um equipamento | `NVRCamera` | `nvr_cameras` | `.../equipamentos/{id}/cameras` | Galeria |
| Backup (um envio de uma máquina) | `Backup` | `backups` | `/api/v1/backups` | `/backups` |
| Rodada de backup do Cliente (junta as máquinas da fila) | `CustomerBackupRun` | `customer_backup_runs` | dentro de `/clients` | detalhe do Cliente |
| Usuário do painel | `Usuario` | `usuarios` | `/api/v1/conta/usuarios` | `/minha-conta`, Configurações |

Pegadinhas que já causaram erro:
- O cabeçalho `X-Client-ID` que o agente manda é o **id da Máquina** (vem da época em que a máquina se chamava "client").
- `/api/v1/clients` é **Cliente** (tabela `client_groups`), mas a tabela `clients` é **Máquina**. E no router legado
  `routers/nvrs.py` (oculto do OpenAPI, sem chamador; candidato a remoção) o `/api/v1/clients/{machine_id}/nvrs`
  usa "clients" no sentido de **Máquina**.
- "NVR" no código quase sempre quer dizer "equipamento de qualquer tipo". Para o NVR de verdade, filtre por `tipo`.
- Colunas `timestamptz` herdadas voltam com fuso: compare datas sempre por `services/datas.para_utc_naive` (REGRA-001).

## Nomes

**Idioma.** Código novo em **português**, sem acento nos identificadores (`obter_cliente`, `listar_auditoria`,
`status_alarmes_defense.py`), seguindo o que o projeto já faz desde outubro de 2026. Termos técnicos consagrados
ficam em inglês (`token`, `webhook`, `upload`, `backup`, `ping`, `payload`). Não traduzir nem renomear o que já
existe em inglês (`machines.py`, `Customer`, `fetchSettings`); ao criar algo ao lado, use o padrão novo.

**Python** (API e agente): módulos e funções em `snake_case`, classes em `PascalCase`, constantes em `MAIUSCULAS`.
Função de uso interno com `_` na frente e **não importada por outro módulo** (se outro precisa dela, ela vira
pública ou vai para um módulo comum: `services/` na API, `src/core/` no agente).

**API**: rota nova com caminho em português e kebab-case (`/testar-conexao`, `/imagem-noite`); `detail` de erro
em português, com acento, dizendo o que fazer; toda rota de painel recebe `ctx` (`get_contexto`) e busca por
`obter_*`/`filtrar_por_conta` (REGRA-010). Docstring de uma linha em toda rota: ela vira a descrição da ferramenta
no MCP.

**Painel (TypeScript/React)**: componente e página em `PascalCase.tsx`; página de rota termina em `Page`
(`ContasPage.tsx`); hook começa com `use` e fica em `hooks/` da pasta que o usa; funções de API em `api/`
(nunca `api.get/post` direto no componente); cores pelos tokens do CSS (`var(--ok)`), não por hexadecimal.

**Arquivos e pastas**: sem espaço nem acento no nome (`fiberhome-zabbix/`, não `Template OLT FH/`). Documentos em
`MAIUSCULAS.md` só para os de entrada (`README.md`, `CHANGELOG.md`, `CONVENCOES.md`); o resto em minúsculas com
hífen. Datas no nome em `AAAA-MM-DD` (`2026-10-27-sincronizacao-onedrive.md`).

## Onde cada coisa fica

| Tipo de arquivo | Lugar |
|---|---|
| Rota da API | `server/api/routers/<assunto>.py` (lógica de negócio em `services/`, não no router) |
| Regra de negócio, acesso a disco/SMTP, cálculos | `server/api/services/` |
| Teste da API | `server/api/tests/test_<assunto>.py` (preparo comum em `tests/conftest.py`) |
| Coletor de um equipamento no agente | `agent/src/<tipo>/<marca>/` (ex.: `nvr/hikvision/`) |
| Código comum do agente | `agent/src/core/` |
| Ferramenta avulsa do agente (não vai no produto) | `agent/ferramentas/` |
| Ferramenta de diagnóstico ou teste e2e do sistema | `tools/` |
| Página do painel | `server/dashboard/src/pages/<Area>/` |
| Componente reutilizado por mais de uma página | `server/dashboard/src/components/` (não dentro de `pages/`) |
| Histórico de mudanças | `docs/CHANGELOG.md` (entrada nova no topo, nunca reescrever as antigas) |
| Estado atual, regras, decisões, rotas, variáveis | `PROJECT_SPEC.md` |
| Material antigo, só consulta | `archive/` (com uma linha no `archive/README.md`) |
| Credenciais locais das IAs | `.credenciais/` (fora do git) |
| Binários (exe, imagem do container) | release do GitHub, nunca no git (ADR-008) |
