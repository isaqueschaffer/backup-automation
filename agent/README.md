# Trilan NVR Backup — Agente Cliente (Windows)

Agente leve que roda como Servico Windows no computador do cliente,
conectado a rede local dos NVRs.

## Pre-requisitos

- Python 3.8+
- Windows 10/11 ou Windows Server
- Acesso de rede aos IPs dos NVRs

## Instalacao

1. Copie toda a pasta agent/ para o PC do cliente.
2. Instale as dependencias:

   ```
   pip install -r requirements.txt
   ```

3. Copie agent.conf.example para agent.conf e preencha:

   ```ini
   [server]
   url = http://hd208ec5kxz.sn.mynetname.net:7001

   [auth]
   client_id = COLE_O_ID_DO_PAINEL
   api_key   = sk_trilan_COLE_A_KEY_DO_PAINEL
   ```

4. Instale e inicie o servico (como Administrador):

   ```
   python service.py install
   python service.py start
   ```

5. (Opcional) Execute o app da bandeja para controle visual:

   ```
   pythonw tray.py
   ```

## Configuracoes

Toda a configuracao de NVRs, horario e e-mail fica no servidor.
O unico arquivo que precisa ser editado no cliente e o agent.conf.

## Monitoramento de OLTs FiberHome (UNM2000)

O agente le o estado das ONUs, o sinal optico e os nomes cadastrados de cada ONU direto da UNM2000. Como o agente roda
no proprio servidor da UNM2000, o monitoramento e praticamente automatico:

1. **No painel**, cadastre um equipamento tipo OLT (fabricante UNM2000) e informe:
   - O **IP da OLT** (acesso Telnet, porta 23) e o usuario/senha do Telnet (padrao FiberHome: `GEPON`/`GEPON`).
   - O bloco **"Nomes das ONUs"** pode ficar **em branco**: o agente le o MySQL local (127.0.0.1) e, se a credencial de
     leitura padrao for recusada, cria sozinho o usuario so-leitura usando o root local (sem SSH nem acesso remoto).
     Preencha o IP so se o banco das ONUs estiver em **outro** servidor; e o usuario/senha so se aquele servidor usar
     outra credencial.

2. Pronto. O servico envia o status das OLTs ao painel a cada 5 minutos.

### Como a leitura dos nomes funciona

- Credencial de leitura padrao: usuario so-leitura `zabbix_reader` (`GRANT SELECT` em `integratecfgdb`), nunca o root.
- Criacao automatica: se esse usuario nao existir, o agente loga no MySQL local como root e roda o `GRANT` por ele.
  Senha do root (padrao de instalacao da UNM2000): `vislecaina`, trocavel por `TRILAN_UNM_ROOT_PASS`. A criacao pode
  ser desligada com `TRILAN_UNM_AUTOCRIAR=0`. O root e usado SO localmente, nunca sai da maquina.
- Variaveis de ambiente (opcionais) na maquina do agente: `TRILAN_UNM_DB_USER`/`TRILAN_UNM_DB_PASS` (credencial de
  leitura), `TRILAN_UNM_ROOT_USER`/`TRILAN_UNM_ROOT_PASS` (root para a criacao), `TRILAN_UNM_AUTOCRIAR`.
- ONUs sem nome dado pelo operador na UNM2000 aparecem so pelo serial.

### Criar o usuario de leitura manualmente (opcional)

So e necessario se a criacao automatica estiver desligada ou se o root tiver outra senha. No console do servidor da
UNM2000 (PowerShell como Administrador):

```powershell
$mysql = @("D:\MySQL\bin\mysql.exe","D:\MySQL_Unm\bin\mysql.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $mysql) { $mysql = (Get-ChildItem C:\,D:\ -Recurse -Filter mysql.exe -ErrorAction SilentlyContinue | Select-Object -First 1).FullName }
& $mysql -h 127.0.0.1 -uroot -pvislecaina -e "GRANT SELECT ON integratecfgdb.* TO 'zabbix_reader'@'%' IDENTIFIED BY 'Zabbix@2024'; FLUSH PRIVILEGES;"
```

## Comandos do servico

```
python service.py install   # Instala o servico
python service.py start     # Inicia o servico
python service.py stop      # Para o servico
python service.py restart   # Reinicia o servico
python service.py remove    # Remove o servico
```

## Logs

Os logs ficam em agent/logs/servico.log e tambem no Visualizador de Eventos do Windows.
