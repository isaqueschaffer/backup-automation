---
name: criar-endpoint-fastapi
description: Padrão para criação de novos endpoints na API FastAPI do projeto.
---

# Fluxo para criação de novos Endpoints

Quando o usuário pedir para criar uma nova rota/endpoint na API, siga este processo estritamente:

1. **Schemas (`server/api/schemas.py`)**: 
   - Comece sempre criando os modelos do Pydantic para validação de entrada (Request) e saída (Response).
   - Certifique-se de documentar o schema se houver campos complexos.

2. **Models/DB (`server/api/models.py`)**:
   - Caso o endpoint precise de manipulação no banco de dados, certifique-se de que o modelo SQLAlchemy exista ou crie-o.

3. **Routers (`server/api/routers/<modulo>.py`)**:
   - Adicione o endpoint no arquivo correspondente à feature.
   - Utilize as dependências apropriadas (como sessão de banco de dados).
   - Trate exceções HTTP corretamente.

4. **Main (`server/api/main.py`)**:
   - Se for um novo arquivo de router, lembre-se de registrá-lo usando `app.include_router()`.
