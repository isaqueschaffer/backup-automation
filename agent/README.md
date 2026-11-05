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

O agente le o estado das ONUs, o sinal optico e os nomes cadastrados de cada ONU direto da UNM2000. Para ativar:

1. **No painel**, cadastre um equipamento tipo OLT (fabricante UNM2000) e informe:
   - O **IP da OLT** (acesso Telnet, porta 23) e o usuario/senha do Telnet (padrao FiberHome: `GEPON`/`GEPON`).
   - O **IP do servidor da UNM2000** no campo "Nomes das ONUs" (nao e o IP da OLT). Deixe usuario e senha do banco
     em branco para usar a credencial padrao (usuario so-leitura `zabbix_reader`); so preencha se aquele servidor
     usar outra.

2. **Em cada servidor da UNM2000**, crie uma vez o usuario so-leitura que o agente usa para ler os nomes das ONUs.
   Rode no console do proprio servidor (PowerShell como Administrador); nao e preciso SSH nem acesso remoto ao MySQL,
   o root e usado so localmente aqui:

   ```powershell
   $mysql = @("D:\MySQL\bin\mysql.exe","D:\MySQL_Unm\bin\mysql.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
   if (-not $mysql) { $mysql = (Get-ChildItem C:\,D:\ -Recurse -Filter mysql.exe -ErrorAction SilentlyContinue | Select-Object -First 1).FullName }
   & $mysql -h 127.0.0.1 -uroot -pvislecaina -e "GRANT SELECT ON integratecfgdb.* TO 'zabbix_reader'@'%' IDENTIFIED BY 'Zabbix@2024'; FLUSH PRIVILEGES;"
   ```

   - Usa a forma `GRANT ... IDENTIFIED BY` (cria o usuario se nao existir) por compatibilidade com o MySQL antigo da UNM2000.
   - O `'%'` permite que o agente, que roda em outra maquina, conecte pela rede (porta 3306).
   - `-uroot -pvislecaina` e a senha padrao de instalacao do MySQL da UNM2000; troque se a sua for diferente.

3. **Conferir** que o usuario le pela rede (de qualquer maquina, trocando o IP pelo do servidor da UNM2000):

   ```powershell
   & $mysql -h <IP_DO_SERVIDOR_UNM> -uzabbix_reader -pZabbix@2024 -e "SELECT COUNT(*) FROM integratecfgdb.t_ontdevice;"
   ```

O servico envia o status das OLTs ao painel a cada 5 minutos. ONUs sem nome dado pelo operador na UNM2000 aparecem
so pelo serial. A credencial padrao do banco pode ser trocada na maquina do agente pelas variaveis de ambiente
`TRILAN_UNM_DB_USER` e `TRILAN_UNM_DB_PASS`.

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
