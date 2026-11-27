# WhatsApp por QR code (solução arquivada)

**Situação:** retirada do código em 10/11/2026, por decisão do dono. A solução funcionou, mas por enquanto não vai ser usada.
**Onde está o código:** commit `9804e4c` ("WhatsApp por QR code: relatorios e avisos tambem por WhatsApp", 09/11/2026), ramo `isaque` de `projetoswmfa/trilan-backup-automation`. A remoção é o commit que adicionou este arquivo.

## O que ela fazia

Os mesmos relatórios e avisos que saem por e-mail passavam a sair também por WhatsApp, num texto resumido, com as imagens das câmeras offline:

- relatório de backup da máquina sem Cliente (upload do ZIP e reenvio);
- relatório da rodada do Cliente (fechamento e reenvio);
- notificações de licença e personalizadas, e avisos de vencimento da conta (para o WhatsApp de contato da conta).

O e-mail não mudava: uma falha no WhatsApp nunca afetava o e-mail, e um aviso contava como enviado se tivesse saído por pelo menos um canal.

## Como funcionava

```
API (FastAPI) ──HTTP interno, header apikey──> container "whatsapp" (Node + Baileys) ──> WhatsApp Web
     ^                                                 │
     └── painel: Configurações > WhatsApp (QR code) <──┘ (GET /status, /qr)
```

- **Ponte `server/whatsapp/`** (Node 22, `@whiskeysockets/baileys` ^6.7.16, express): mantém uma sessão do WhatsApp Web lida por QR code. Ela não publica porta: só a API fala com ela, pela rede interna. A ponte expõe `POST /message/sendText/:instance` e `POST /message/sendMedia/:instance` (o mesmo formato da Evolution API v2, só por conveniência), mais `GET /status`, `GET /qr`, `POST /logout` e `GET /health`. A chave `API_KEY` (no mínimo 16 caracteres) é obrigatória e comparada em tempo constante. A ponte resolve o número com `onWhatsApp` (cobre o 9º dígito dos celulares do Brasil), usa `fetchLatestBaileysVersion` e reconecta sozinha. A sessão fica em `/data/auth`: sem volume, ela pede um QR novo a cada recriação do container.
- **API:**
  - `services/whatsapp_service.py`: envio com até 3 tentativas, só em falha de rede ou erro 5xx, e pausa entre as mensagens. Nunca levanta exceção.
  - `services/whatsapp_relatorios.py`: monta o texto a partir dos mesmos helpers do e-mail e manda no máximo 10 imagens de câmeras offline. Roda numa thread com sessão própria do banco e grava `AgentLog` `whatsapp_sent`/`whatsapp_error`.
  - `whatsapp_numero.py`: normaliza e valida os números. Guarda só os dígitos, com o DDI (`5511999998888`). Um número de 10 ou 11 dígitos sem `+` é tratado como do Brasil e ganha o 55.
  - `routers/whatsapp_router.py`, só para o admin global: `GET /api/v1/whatsapp/conexao`, `POST /api/v1/whatsapp/desconectar` e `POST /api/v1/whatsapp/teste`.
  - Variáveis: `WHATSAPP_BRIDGE_KEY` (sem ela, o WhatsApp fica desligado), `WHATSAPP_BRIDGE_URL` (padrão `http://whatsapp:3000`) e `WHATSAPP_INSTANCE` (padrão `trilan`).
- **Painel:**
  - cartão WhatsApp em Configurações: QR code atualizado a cada 3 s, número conectado, botão Desconectar e mensagem de teste;
  - campo "WhatsApp do relatório" no Cliente e na Máquina (a máquina com Cliente herda os números do Cliente, como os e-mails);
  - campo "WhatsApp de contato" na Conta;
  - "WhatsApp enviado" e "Erro de WhatsApp" no log da máquina.
- **Testes:** `server/api/tests/test_whatsapp.py`, com 26 testes. Cobrem a normalização, a configuração, o envio com retentativas, a montagem das mensagens e o limite de imagens.

## Decisões e o que aprendemos

- Primeiro tentamos a Evolution API externa. Trocamos pela ponte própria para não depender de um servidor de terceiros: o QR code é lido no nosso painel.
- O Baileys **não é oficial**. O número remetente pode ser bloqueado pelo WhatsApp, e a biblioteca precisa ser atualizada quando o protocolo muda. Para um uso sério, avaliar a API oficial do WhatsApp Business (Cloud API), que é paga por conversa e exige modelos de mensagem aprovados.
- Na produção, o `docker-compose.yml` não vale: o serviço precisou virar um Application próprio no Dokploy. Ver a seção "Produção no Dokploy" do `CLAUDE.md`.

## Banco de dados (as colunas foram apagadas)

A migração criou três colunas, que **foram apagadas** da produção em 10/11/2026 (`DROP COLUMN IF EXISTS`, num deploy único). Os números de WhatsApp que estavam cadastrados se perderam.

| Tabela | Coluna | Tipo |
|---|---|---|
| `client_groups` (Cliente) | `whatsapp_to` | `TEXT[] NOT NULL DEFAULT '{}'` |
| `clients` (Máquina) | `whatsapp_to` | `TEXT[] NOT NULL DEFAULT '{}'` |
| `contas` | `whatsapp_contato` | `VARCHAR(30)`, aceita nulo |

**Por que apagar:** sem o campo no model, a coluna `whatsapp_to` (NOT NULL) fazia todo INSERT de Cliente ou Máquina falhar quando a tabela vinha do `create_all`, onde o `default=[]` fica só no Python. Isso foi reproduzido no banco local. Deixar as colunas exigiria um `SET DEFAULT '{}'` no código para sempre; apagá-las limpa o código.

Para trazer o WhatsApp de volta, a migração inline do commit `9804e4c` (`_MIGRACOES_COLUNAS`) recria as colunas vazias.

## Como trazer de volta

1. `git revert <commit da remoção>` (ou `git checkout 9804e4c -- <arquivos>`). Resolver os conflitos no `PROJECT_SPEC.md` e nos compose, que mudaram depois.
2. A migração inline é idempotente e recria as colunas apagadas (vazias).
3. O Application "WhatsApp" do Dokploy foi excluído na remoção, e a sessão (QR já lido) se perdeu com ele. Para voltar, criar de novo um Application "WhatsApp" com estas configurações: build pelo Dockerfile `server/whatsapp/Dockerfile`, branch `isaque`, volume em `/data`, `API_KEY` igual à `WHATSAPP_BRIDGE_KEY` do Backend, `INSTANCE_NAME=trilan` e sem domínio.
4. No Backend, definir `WHATSAPP_BRIDGE_KEY` (só uma linha) e `WHATSAPP_BRIDGE_URL=http://<appName do WhatsApp>:3000`.
5. Ler o QR code em Configurações > WhatsApp com o celular do número remetente e fazer o envio de teste.
6. Conferir se a versão do Baileys ainda conecta, porque ela pode ter ficado velha.
