---
name: criar-novo-agente
description: Guia de como desenvolver a integração para um novo agente de backup de NVR.
---

# Implementando um Novo Agente NVR

Para criar um script/agente de backup para uma nova marca ou modelo de NVR, siga as etapas:

1. **Arquivo do Agente (`agent/`)**:
   - O código principal do novo agente deve residir na pasta `agent/`.
   - Crie um arquivo Python dedicado, inspirando-se em arquivos existentes como `agente_unm.py` ou `teste_backup_unm.py`.

2. **Configuração (`agent/agent.conf`)**:
   - Se o novo agente exigir configurações específicas (IPs, portas, credenciais padrão), adicione um bloco documentado em `agent/agent.conf`.

3. **Serviço (`agent/service.py`)**:
   - Verifique como o agente se conecta ao loop principal ou agendador em `service.py`. Integre a lógica do novo agente para que ele possa ser acionado pelo sistema.

4. **Comunicação com a API**:
   - Lembre-se de que o agente precisa enviar os status dos backups e logs para os endpoints da API localizada em `server/api/routers/agent.py`.
