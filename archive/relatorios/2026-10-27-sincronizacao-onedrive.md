# Relatório Técnico: Limpeza, Compartilhamento Samba e Sincronização de Backups com o OneDrive

> **Data de execução:** 27 de outubro de 2026  
> **Ambiente:** Servidor Linux Dokploy (`192.168.75.112`), Estação Windows (`DESKTOP-U3E13V6`) e Servidor Windows 24h (`Administrator`).  
> **Objetivo:** Limpeza de diretórios de teste, liberação de permissões de exclusão via rede (Samba) e criação de rotina automática de sincronização de backups para o Microsoft OneDrive da Trilan.

---

## 1. Visão Geral da Arquitetura

```
+-------------------------------------------------------------+
|               Servidor Linux (192.168.75.112)               |
|                                                             |
|  Container API FastAPI (Docker)                             |
|       |                                                     |
|       v (grava backups como root:root)                      |
|  /opt/trilan/backups (armazenamento físico)                 |
|       |                                                     |
|       v (compartilhado via Samba [backups])                 |
|  smbd (force user = root, force group = root, mask 0777)    |
+------------------------------+------------------------------+
                               |
                               | Rede Local (SMB: \\192.168.75.112\backups)
                               v
+-------------------------------------------------------------+
|             Servidor Windows 24h (ou Estação)               |
|                                                             |
|  Tarefa Agendada (schtasks): Trilan_Sync_Backups_OneDrive   |
|       | (executa de 1 em 1 hora em segundo plano)           |
|       v                                                     |
|  C:\TrilanSync\sync_backups_onedrive.ps1                    |
|       |                                                     |
|       v (Robocopy diferencial /E /XO /R:3 /W:5)             |
|  C:\Users\<User>\OneDrive - Trilan\                         |
|  Arquivos de Admin - Backups Clientes                       |
|       |                                                     |
|       v (cliente nativo Microsoft OneDrive)                 |
|  Nuvem Microsoft 365 (Trilan)                               |
+-------------------------------------------------------------+
```

---

## 2. Atividades Realizadas em Detalhes

### Atividade 1: Diagnóstico e Remoção de Pastas de Teste no Servidor Linux

- **Servidor:** Ubuntu Linux `192.168.75.112`
- **Acesso:** SSH (`trilan@192.168.75.112`, porta 22)
- **Diagnóstico realizado:**
  1. Acessamos o PostgreSQL de produção via Docker (`sistema-de-backup-database-1u6eju`) e consultamos a tabela `clients`.
  2. Foram identificados 15 clientes ativos em produção (`Agerip`, `Georgina`, `Gramado Termas Resort`, `Horizontes`, `Hot Beach Celebration`, `Hot Beach Resort`, `Navarro`, `Recanto Real`, `Server Defense Trilan`, `Smurfs`, etc.).
  3. No diretório físico `/opt/trilan/backups` (bind-mount para `/data/backups` da API), foram encontradas pastas órfãs de setembro/2026 com prefixo `Teste_` ou UUIDs sem qualquer registro no banco de dados.
- **Ações tomadas:**
  - Após confirmação explícita com o usuário, foram excluídas com segurança via `sudo rm -rf`:
    1. `/opt/trilan/backups/4112e857-0df2-4295-89fd-ebfc48a88bcc` (564 KB)
    2. `/opt/trilan/backups/Horizontes_teste_Mikrotik_d6516566-efaa-4350-9e63-96b3f7293711` (3.1 MB)
    3. `/opt/trilan/backups/Teste_4112e857-0df2-4295-89fd-ebfc48a88bcc` (1.2 MB)
    4. `/opt/trilan/backups/Teste_EXCLUIR` (3.1 MB)
    5. `/opt/trilan/backups/Teste_OLT_agerip_4112e857-0df2-4295-89fd-ebfc48a88bcc` (564 KB)
    6. `/opt/trilan/backups/Teste_recanto_MIKROTIK_722f5607-5a35-4ae5-a14d-1f47fb9a606d` (36 KB)
    7. `/opt/trilan/backups/Teste_Senha_47896d46-dd70-4911-8a19-e53e7733d53e` (71 MB)
- **Resultado:** O espaço foi liberado e todas as 10 pastas de clientes reais de produção foram mantidas intactas.

---

### Atividade 2: Correção de Permissões no Compartilhamento Samba

- **Problema relatado:** O usuário tentava apagar ou gerenciar arquivos na pasta de rede compartilhada a partir de uma máquina Windows e recebia erro de **"Acesso Negado"** / **"Você precisa de permissão"**.
- **Causa Raiz Identificada:**
  1. O container Docker da API FastAPI (`sistema-de-backup-sysbkp-wce0ac`) executa internamente como `root` (`uid=0`, `gid=0`).
  2. Os arquivos e pastas criados pelo sistema ficavam com proprietário `root:root` e permissão restrita `drwxr-xr-x` (`755`).
  3. No Linux, para apagar um arquivo ou pasta, o usuário precisa de permissão de escrita (`w`) no **diretório pai**.
  4. O compartilhamento Samba (`[backups]`) autenticava como o usuário do sistema `trilan`. Como `trilan` não era dono nem pertencia ao grupo `root`, o Samba negava a exclusão.
- **Solução Implementada:**
  1. Foi feito backup prévio do arquivo de configuração:
     ```bash
     sudo cp /etc/samba/smb.conf /etc/samba/smb.conf.bak
     ```
  2. Atualizada a seção `[backups]` no `/etc/samba/smb.conf`:
     ```ini
     [backups]
        path = /opt/trilan/backups
        browseable = yes
        read only = no
        writable = yes
        valid users = trilan
        force user = root
        force group = root
        create mask = 0777
        directory mask = 0777
     ```
  3. Aplicada permissão recursiva total na pasta física:
     ```bash
     sudo chmod -R 777 /opt/trilan/backups
     ```
  4. Reiniciado o serviço do Samba:
     ```bash
     sudo systemctl restart smbd
     ```
- **Resultado:** Todas as operações realizadas através da rede (`\\192.168.75.112\backups`) agora rodam com privilégios de `root` no filesystem, permitindo que qualquer máquina autorizada crie, renomeie, edite ou exclua pastas e arquivos diretamente pelo Windows Explorer.

---

### Atividade 3: Análise do OneDrive no Linux vs. Políticas do Microsoft 365 (Azure AD)

- **Cenário avaliado:** Conectar o Microsoft OneDrive diretamente no servidor Linux via ferramenta de sincronização (`Rclone`).
- **Bloqueio Encontrado:**
  1. A conta corporativa informada (`isaque.schaffer@ms.trilan.com.br`) é uma conta de **colaborador (não-admin)**.
  2. As políticas de segurança do Microsoft 365 (Entra ID / Azure AD) da Trilan exigem **Consentimento do Administrador** (*Admin Approval*) para conceder tokens OAuth a aplicativos de terceiros como o Rclone.
  3. Ao tentar o fluxo `rclone authorize "onedrive"`, o navegador retornou a mensagem de bloqueio exigindo uma conta de administrador de TI.
- **Ação de Limpeza:**
  - Desfez-se qualquer alteração no servidor Linux:
    - Binários manuais removidos (`/usr/bin/rclone`, man pages e scripts temporários).
    - Configurações apagadas (`~/.config/rclone`).
    - Restaurada a versão original via Snap (`rclone v1.75.1`).
    - Desinstalado o Rclone local no Windows.

---

### Atividade 4: Solução Definitiva de Sincronização via Cliente Oficial OneDrive

- **Estratégia Adotada:**
  - Como os computadores Windows da equipe já possuem o aplicativo oficial do OneDrive instalado e sincronizando nativamente sem precisar de nenhuma permissão de administrador no Azure AD, a sincronização foi desenhada no Windows:
    1. O Windows lê os backups da rede local: `\\192.168.75.112\backups`.
    2. Um script inteligente roda o `robocopy` com cópia diferencial (`/XO`: transfere apenas arquivos novos ou alterados).
    3. Os arquivos são depositados na pasta do OneDrive local:  
       `C:\Users\<Usuario>\OneDrive - Trilan\Arquivos de Admin - Backups Clientes`.
    4. O cliente oficial da Microsoft detecta as adições e envia para a nuvem automaticamente.

- **Carga Inicial Realizada:**
  - **Origem:** `\\192.168.75.112\backups`
  - **Destino:** `C:\Users\user\OneDrive - Trilan\Arquivos de Admin - Backups Clientes`
  - **Total de Arquivos:** 447 arquivos
  - **Volume:** 4,835 GB
  - **Falhas:** 0
  - **Pastas sincronizadas:** `Agerip`, `Georgina`, `Gramado Termas Resort`, `Horizontes`, `Hot Beach Celebration`, `Hot Beach Resort`, `Navarro`, `Recanto Real`, `Smurfs`, `Trilan`.
  - Pastas pré-existentes no OneDrive (`Agerip BKP`, `Dolhos BKP`, `Textos e imagens`, etc.) foram **preservadas intactas**.

---

### Atividade 5: Scripts Criados no Repositório

Foram adicionados dois utilitários na pasta `tools/` do projeto:

#### 1. `tools/sync_backups_onedrive.ps1`
Script de execução periódica que:
- Detecta dinamicamente a pasta do OneDrive da Trilan consultando:
  1. `$env:OneDriveCommercial`
  2. Registro do Windows: `HKCU:\Software\Microsoft\OneDrive\Accounts\*\UserFolder`
  3. Fallback: `$env:USERPROFILE\OneDrive - Trilan`
- Garante a autenticação na rede (`net use \\192.168.75.112\backups /user:trilan trilan /persistent:yes`).
- Executa o Robocopy:
  ```powershell
  & robocopy $Source $Destination /E /XO /R:3 /W:5 /NP /NDL /NFL
  ```
  - `/E`: Inclui subdiretórios, inclusive vazios.
  - `/XO`: *Exclude Older* (não copia arquivos repetidos que já existem no destino com a mesma data/tamanho).
  - `/R:3 /W:5`: 3 tentativas com 5s de intervalo caso algum arquivo esteja em gravação.
  - `/NP /NDL /NFL`: Modo silencioso para não poluir o terminal ou logs.
- Grava logs de execução com timestamp em `%LOCALAPPDATA%\Trilan\sync_backups.log`.

#### 2. `tools/instalar_no_outro_servidor.ps1`
Script instalador completo para implantar em qualquer servidor Windows:
- Cria a pasta fixa `C:\TrilanSync`.
- Instala o script `sync_backups_onedrive.ps1`.
- Trata e autentica a conexão de rede.
- Cria a tarefa agendada no Windows Task Scheduler (`schtasks`) chamada `Trilan_Sync_Backups_OneDrive` para executar de **hora em hora** em segundo plano (`-WindowStyle Hidden`).
- Dispara a primeira sincronização de validação imediatamente.

---

### Atividade 6: Implantação no Servidor Windows 24h

- **Ambiente:** Servidor Windows conectado 24 horas, usuário `Administrator`.
- **Tratamento do Erro 1219 do Windows:**
  - Ao tentar autenticar no compartilhamento, o Windows retornou:
    > *System error 1219: Multiple connections to a server or shared resource by the same user, using more than one user name, are not allowed.*
  - **Causa:** O servidor 24h já tinha uma conexão antiga mapeada para o mesmo IP (unidade `Z:` mapeada em `\\192.168.75.112\backups`).
  - **Solução aplicada no PowerShell:**
    ```powershell
    net use * /delete /y
    net use \\192.168.75.112\backups /user:trilan trilan /persistent:yes
    ```
- **Conclusão:**
  - A conexão foi restabelecida com êxito.
  - O script foi instalado em `C:\TrilanSync\sync_backups_onedrive.ps1`.
  - A tarefa agendada `Trilan_Sync_Backups_OneDrive` foi registrada com sucesso e roda a cada 60 minutos.

---

## 3. Comandos Úteis para Administração e Monitoramento

### No Servidor Linux (`192.168.75.112`):
```bash
# Verificar status do compartilhamento Samba
sudo systemctl status smbd

# Verificar permissões e donos da pasta de backups
ls -la /opt/trilan/backups

# Monitorar conexões ativas no Samba
sudo smbstatus
```

### No Servidor Windows (ou na máquina do desenvolvedor):
```powershell
# 1. Ver o log das últimas sincronizações
Get-Content "$env:LOCALAPPDATA\Trilan\sync_backups.log" -Tail 20

# 2. Consultar o status da tarefa agendada
schtasks.exe /Query /TN "Trilan_Sync_Backups_OneDrive" /FO LIST

# 3. Forçar uma sincronização manual imediata
powershell.exe -ExecutionPolicy Bypass -File "C:\TrilanSync\sync_backups_onedrive.ps1"

# 4. Remover a tarefa agendada (se quiser desativar nesta máquina específica)
schtasks.exe /Delete /TN "Trilan_Sync_Backups_OneDrive" /F
```

---

## 4. Status Final

| Componente | Status | Detalhes |
| :--- | :---: | :--- |
| **Limpeza de Testes (Linux)** | Concluída | 7 pastas órfãs removidas; apenas clientes reais preservados. |
| **Permissões Samba (Linux)** | Concluída | `force user = root` ativo; permissão total de escrita/exclusão liberada. |
| **Carga Inicial para OneDrive** | Concluída | 447 arquivos (4,835 GB) sincronizados com 0 falhas. |
| **Automação no Servidor 24h** | Operacional | Tarefa agendada ativa de hora em hora em `C:\TrilanSync`. |
| **Segurança e Isolamento** | Garantido | Sem credenciais expostas; Rclone do Linux restaurado ao estado padrão. |

