"""Servidor MCP (Model Context Protocol): Claude, ChatGPT e Gemini usam o sistema em nome de um administrador.

- servidor.py: endpoint POST /mcp (JSON-RPC, Streamable HTTP sem estado) e as rotas dos tokens em "Minha conta".
- ferramentas.py: transforma as rotas do painel (/api/v1) em ferramentas, respeitando papel e conta (REGRA-010).
- executor.py: chama a rota dentro do próprio processo com um JWT curto do usuário (marca "via": "mcp").
- oauth.py: servidor OAuth 2.1 (PKCE, registro dinâmico e metadados por URL) para os conectores dos apps.
- tokens.py: tokens pessoais e OAuth (só o hash no banco).
"""
