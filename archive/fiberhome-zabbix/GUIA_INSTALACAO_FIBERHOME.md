# Guia de Instalação: Monitoramento FiberHome (Zabbix)

Este guia descreve como configurar a integração entre o Zabbix e o servidor UNM2000 para monitoramento de sinais ópticos e resolução de nomes de ONUs.

---

## 1. Configuração do Banco de Dados (Servidor Windows)

Para que o Zabbix consiga ler os nomes das ONUs, precisamos criar um usuário de leitura no MySQL do UNM2000.

### Passo 1: Criar o arquivo de inicialização
No PowerShell do Windows, execute o comando abaixo para criar o arquivo de reset com as permissões corretas:
```powershell
Set-Content -Path "D:\reset.txt" -Value "CREATE USER IF NOT EXISTS 'zabbix_reader'@'%' IDENTIFIED BY 'Zabbix@2024';", "GRANT SELECT ON integratecfgdb.* TO 'zabbix_reader'@'%';", "FLUSH PRIVILEGES;"
```

### Passo 2: Aplicar as permissões no MySQL
1. Abra o `services.msc` e **Pare** o serviço `MySQL_Unm`.
2. No PowerShell (como Administrador), execute os comandos abaixo para forçar o encerramento e aplicar o arquivo:
```powershell
taskkill /F /IM mysqld.exe
& "D:\MySQL_Unm\bin\mysqld.exe" --defaults-file="D:\MySQL_Unm\my.ini" --init-file="D:\reset.txt" --console
```
3. Aguarde até aparecer a mensagem `ready for connections`.
4. Encerre o processo (Ctrl+C) e **Inicie** o serviço `MySQL_Unm` novamente no `services.msc`.

---

## 2. Instalação dos Scripts (Servidor Zabbix Linux)

### Localização dos Scripts
Os scripts devem ser colocados no diretório oficial de scripts externos do Zabbix:
`📂 /usr/lib/zabbix/externalscripts/`

### Comandos de Instalação e Permissões
No terminal Linux, após copiar os arquivos para a pasta, execute:
```bash
# Dar permissão de execução
chmod +x /usr/lib/zabbix/externalscripts/fiberhome_optical.py
chmod +x /usr/lib/zabbix/externalscripts/fiberhome_onu_discovery_name.py
chmod +x /usr/lib/zabbix/externalscripts/unm_license_check.py

# Ajustar o dono dos arquivos para o usuário do zabbix
chown zabbix:zabbix /usr/lib/zabbix/externalscripts/fiberhome_*
chown zabbix:zabbix /usr/lib/zabbix/externalscripts/unm_license_check.py

# Instalar biblioteca necessária para conexão com banco
apt update && apt install python3-pymysql -y
```

---

## 3. Configuração no Zabbix (Frontend)

### Macros Necessárias
Adicione estas macros no Host da OLT ou no Template:

| Macro | Descrição | Sugestão de Valor |
| :--- | :--- | :--- |
| `{$SNMP_COMMUNITY}` | Comunidade SNMP da OLT | `adsl` |
| `{$GEPON_USER}` | Usuário Telnet (Sinal) | `GEPON` |
| `{$GEPON_PASS}` | Senha Telnet (Sinal) | `GEPON` |
| `{$GEPON_ENABLE}` | Senha Enable (Sinal) | `GEPON` |
| `{$DB_HOST}` | (Opcional) IP do UNM2000 | `192.168.31.5` |
| `{$UNM_LICENSE_DATE}` | Data de Licenciamento | `2024-05-14` |

---

## 4. Testes de Validação

Rode estes comandos no Linux para confirmar se tudo está OK:

**Testar nomes das ONUs:**
```bash
python3 /usr/lib/zabbix/externalscripts/fiberhome_onu_discovery_name.py <IP_OLT> <COMUNIDADE>
```

**Testar sinal óptico (CLI):**
```bash
# Exemplo para Slot 1, PON 1, ONU 1
python3 /usr/lib/zabbix/externalscripts/fiberhome_optical.py <IP_OLT> GEPON GEPON GEPON 1 1 1
```

**Testar dias de licença:**
```bash
python3 /usr/lib/zabbix/externalscripts/unm_license_check.py 2024-05-14
```

---
*Guia gerado em 04/05/2026 para suporte técnico FiberHome.*
