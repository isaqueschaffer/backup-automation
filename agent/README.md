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
