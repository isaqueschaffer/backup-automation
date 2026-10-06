import sys

with open("agent/service.py", "r", encoding="utf-8") as f:
    content = f.read()

# Block 1
block1_old = """<<<<<<< HEAD
        log(f"Servidor configurado: {server_url}")
        log(f"Client ID: {client_id}")

        headers = {"X-Client-ID": client_id, "X-API-Key": api_key}
        log(f"Testando comunicacao com o servidor: {server_url}/api/v1/agent/config ...")
        config_loaded = True
=======
        log(f"Testando comunicacao com o servidor: {conf['server_url']}/api/v1/agent/config ...")
>>>>>>> origin/integracao-equipamentos"""
block1_new = """        config_loaded = True
        log(f"Testando comunicacao com o servidor: {conf['server_url']}/api/v1/agent/config ...")"""

content = content.replace(block1_old, block1_new)

# Block 2
block2_old = """<<<<<<< HEAD
        self._run_loop(hora, minuto, server_url, headers, config_loaded)

    def _restart_service(self):
        import subprocess
        subprocess.Popen(
            ["cmd", "/c", "ping 127.0.0.1 -n 4 >nul && sc start TrilanAgentNVR"],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
        )
        self.stop_requested = True
        win32event.SetEvent(self.hWaitStop)

    def _run_loop(self, hora: int, minuto: int, server_url: str, headers: dict, config_loaded: bool = True):
=======
        headers = {"X-Client-ID": conf["client_id"], "X-API-Key": conf["api_key"]}
        self._run_loop(hora, minuto, conf["server_url"], headers, conf)

    def _run_loop(self, hora: int, minuto: int, server_url: str, headers: dict, conf: dict):
>>>>>>> origin/integracao-equipamentos"""
block2_new = """        headers = {"X-Client-ID": conf["client_id"], "X-API-Key": conf["api_key"]}
        self._run_loop(hora, minuto, conf["server_url"], headers, conf, config_loaded)

    def _restart_service(self):
        import subprocess
        subprocess.Popen(
            ["cmd", "/c", "ping 127.0.0.1 -n 4 >nul && sc start TrilanAgentNVR"],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
        )
        self.stop_requested = True
        win32event.SetEvent(self.hWaitStop)

    def _run_loop(self, hora: int, minuto: int, server_url: str, headers: dict, conf: dict, config_loaded: bool = True):"""

content = content.replace(block2_old, block2_new)

# Block 3
block3_old = """<<<<<<< HEAD
                # Envia ping a cada 5 minutos (300s) se online, ou a cada 10 minutos (600s) se offline
                intervalo_ping = 300 if (time.time() - last_successful_ping < 300) else 600
                
                if time.time() - last_ping_time >= intervalo_ping:
                    try:
                        ping_resp = requests.post(
                            f"{server_url}/api/v1/agent/ping",
                            headers=headers, timeout=10, verify=False,
                        )
                        ping_resp.raise_for_status()
                        
                        if time.time() - last_successful_ping > 300 and config_loaded:
                            log("Servidor voltou a responder apos periodo de desconexao!")

                        last_ping_time = time.time()
                        last_successful_ping = time.time()
                        
                        # Se ligou sem internet/servidor, reinicia agora para baixar a config correta
                        if not config_loaded:
                            log("Servidor voltou a responder! Reiniciando servico para buscar configuracoes e horario corretos...")
                            self._restart_service()
                            return
                        
=======
                # Envia ping a cada 5 minutos (300 segundos) para manter status "Online"
                if time.time() - last_ping_time >= 300:
                    last_ping_time = time.time()
                    try:
                        ping_resp = ping_server(conf)
                        
                        if ping_resp:
                            log(f"Ping recebido pelo servidor. Instrucoes: {ping_resp}")
                        else:
                            log("Ping enviado, mas resposta vazia.")
                            
>>>>>>> origin/integracao-equipamentos
                        # Verifica se o servidor solicitou reinicio
                        if ping_resp and ping_resp.get("restart"):
                            log("Reinicio solicitado pelo dashboard. Agendando reinicio do servico...")
                            self._restart_service()
                            return
<<<<<<< HEAD
                    except Exception as e:
                        log(f"Falha na conexao com o servidor (tentando novamente em 10 minutos): {e}", is_error=True)
                        last_ping_time = time.time()
=======
                        if ping_resp and ping_resp.get("backup"):
                            log("Geracao de backup manual solicitada pelo dashboard!")
                            self._executar_backup(agent_mod, "manual")
                            
                        # Se o agente enviou nova versão no ping, aplicamos
                        if ping_resp and ping_resp.get("version"):
                            version = ping_resp.get("version")
                            log(f"Verificando atualizacao para a versao {version}...")
                            updated = check_and_apply_update(conf, version)
                            if updated:
                                log("Agente atualizado. Reiniciando o servico...")
                                self._restart_service()
                                return
                                
                    except Exception as e:
                        log(f"Falha ao pingar servidor: {e}", is_error=True)
                        
                        if time.time() - last_successful_ping >= 600:
                            log("Sem conexao com o servidor ha 10 minutos. Reiniciando o servico...")
                            self._restart_service()
                            return
>>>>>>> origin/integracao-equipamentos"""
block3_new = """                # Envia ping a cada 5 minutos (300s) se online, ou a cada 10 minutos (600s) se offline
                intervalo_ping = 300 if (time.time() - last_successful_ping < 300) else 600
                
                if time.time() - last_ping_time >= intervalo_ping:
                    try:
                        ping_resp = ping_server(conf)
                        
                        if ping_resp:
                            log(f"Ping recebido pelo servidor. Instrucoes: {ping_resp}")
                        
                        if time.time() - last_successful_ping > 300 and config_loaded:
                            log("Servidor voltou a responder apos periodo de desconexao!")

                        last_ping_time = time.time()
                        last_successful_ping = time.time()
                        
                        # Se ligou sem internet/servidor, reinicia agora para baixar a config correta
                        if not config_loaded:
                            log("Servidor voltou a responder! Reiniciando servico para buscar configuracoes e horario corretos...")
                            self._restart_service()
                            return
                            
                        # Verifica se o servidor solicitou reinicio
                        if ping_resp and ping_resp.get("restart"):
                            log("Reinicio solicitado pelo dashboard. Agendando reinicio do servico...")
                            self._restart_service()
                            return
                            
                        if ping_resp and ping_resp.get("backup"):
                            log("Geracao de backup manual solicitada pelo dashboard!")
                            self._executar_backup(agent_mod, "manual")
                            
                        # Se o agente enviou nova versão no ping, aplicamos
                        if ping_resp and ping_resp.get("version"):
                            version = ping_resp.get("version")
                            log(f"Verificando atualizacao para a versao {version}...")
                            updated = check_and_apply_update(conf, version)
                            if updated:
                                log("Agente atualizado. Reiniciando o servico...")
                                self._restart_service()
                                return
                                
                    except Exception as e:
                        log(f"Falha na conexao com o servidor (tentando novamente em 10 minutos): {e}", is_error=True)
                        last_ping_time = time.time()"""

content = content.replace(block3_old, block3_new)

with open("agent/service.py", "w", encoding="utf-8") as f:
    f.write(content)
