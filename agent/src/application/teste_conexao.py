"""Teste de conexão ("Testar conexão") pedido pelo painel (agente >= 1.1.44).

O servidor manda no ping (`conexao_task`) o equipamento como em /agent/config (com a senha aberta) e um `task_id`.
O teste segue as mesmas rotinas de login do backup e, a cada etapa, envia o estado inteiro ao servidor
(`/agent/conexao-progresso`), que o painel mostra numa barra de progresso. Na OLT a leitura já é a coleta das ONUs,
enviada na hora (`/agent/olt/status`), sem esperar o ciclo de 5 minutos.

Nada aqui grava a senha em log: as mensagens de erro passam por `_sem_senha`.
"""
import logging
import socket
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from src.core.config import parse_config_extra

TIMEOUT_TCP_S = 6


class _Teste:
    """Etapas do teste e envio do estado ao servidor a cada mudança."""

    def __init__(self, task: dict, enviar: Callable[[dict], None]):
        self.task_id = task.get("task_id")
        self.enviar = enviar
        self.etapas = []
        self.senha = task.get("password") or ""

    def _sem_senha(self, texto) -> Optional[str]:
        if texto is None:
            return None
        texto = str(texto)
        if self.senha and len(self.senha) >= 3:
            texto = texto.replace(self.senha, "***")
        return texto[:700]

    def _publicar(self, concluido=False, ok=None, mensagem=None):
        try:
            self.enviar({
                "task_id": self.task_id, "etapas": self.etapas, "concluido": concluido, "ok": ok,
                "mensagem": self._sem_senha(mensagem),
            })
        except Exception as e:  # falha de envio não derruba o teste: o servidor encerra pelo prazo
            logging.warning(f"[CONEXAO] Falha ao enviar o progresso: {e}")

    def planejar(self, *etapas):
        """Define as etapas (id, rótulo) antes de começar, para a barra saber o total."""
        self.etapas = [{"id": i, "rotulo": r, "estado": "pendente", "detalhe": None} for i, r in etapas]
        self._publicar()

    def _etapa(self, etapa_id):
        for e in self.etapas:
            if e["id"] == etapa_id:
                return e
        e = {"id": etapa_id, "rotulo": etapa_id, "estado": "pendente", "detalhe": None}
        self.etapas.append(e)
        return e

    def iniciar(self, etapa_id, detalhe=None):
        e = self._etapa(etapa_id)
        e.update(estado="andamento", detalhe=self._sem_senha(detalhe))
        self._publicar()

    def ok(self, etapa_id, detalhe=None):
        e = self._etapa(etapa_id)
        e.update(estado="ok", detalhe=self._sem_senha(detalhe))
        self._publicar()

    def erro(self, etapa_id, detalhe):
        e = self._etapa(etapa_id)
        e.update(estado="erro", detalhe=self._sem_senha(detalhe))

    def concluir(self, ok: bool, mensagem: str):
        if not ok:
            for e in self.etapas:
                if e["estado"] == "pendente":
                    e["estado"] = "pulado"
        self._publicar(concluido=True, ok=ok, mensagem=mensagem)


class _Falha(Exception):
    """Etapa que falhou: a mensagem vai para o painel."""


# ── auxiliares ─────────────────────────────────────────────────────────────

def host_porta(endereco: str, porta_padrao: int):
    """('host', porta) de um IP que pode vir com protocolo, porta ou caminho (http://1.2.3.4:8080/x)."""
    texto = (endereco or "").strip()
    if "://" in texto:
        url = urlparse(texto)
        padrao = 443 if url.scheme == "https" else porta_padrao
        return url.hostname or "", url.port or padrao
    texto = texto.split("/")[0]
    if texto.count(":") == 1:
        host, porta = texto.split(":")
        try:
            return host, int(porta)
        except ValueError:
            return host, porta_padrao
    return texto, porta_padrao


def _tcp(t: _Teste, etapa_id: str, host: str, porta: int):
    t.iniciar(etapa_id, f"{host}:{porta}")
    if not host:
        t.erro(etapa_id, "IP não informado no cadastro")
        raise _Falha("O cadastro está sem IP.")
    inicio = time.monotonic()
    try:
        with socket.create_connection((host, porta), timeout=TIMEOUT_TCP_S):
            pass
    except socket.timeout:
        t.erro(etapa_id, f"{host}:{porta} não respondeu em {TIMEOUT_TCP_S} s")
        raise _Falha(f"O equipamento {host} não respondeu na porta {porta}: confira o IP, a porta e se esta máquina "
                     "alcança essa rede (VPN, rota, firewall).")
    except OSError as e:
        t.erro(etapa_id, f"{host}:{porta}: {e.strerror or e}")
        raise _Falha(f"Não foi possível abrir conexão com {host}:{porta} ({e.strerror or e}).")
    t.ok(etapa_id, f"{host}:{porta} respondeu em {int((time.monotonic() - inicio) * 1000)} ms")


def _pasta(t: _Teste, etapa_id: str, caminho: str):
    t.iniciar(etapa_id, caminho)
    if not caminho:
        t.erro(etapa_id, "Pasta de origem não informada")
        raise _Falha("O cadastro está sem a pasta de origem dos backups.")
    pasta = Path(caminho)
    if not pasta.is_dir():
        t.erro(etapa_id, f"{caminho} não existe ou não está acessível para o serviço")
        raise _Falha(f"A pasta {caminho} não existe ou o serviço do agente não tem acesso a ela.")
    try:
        qtd = sum(1 for _ in pasta.iterdir())
    except OSError as e:
        t.erro(etapa_id, f"Sem permissão de leitura: {e}")
        raise _Falha(f"O serviço do agente não consegue ler a pasta {caminho}.")
    t.ok(etapa_id, f"{qtd} item(ns) em {caminho}")


# ── por tipo ───────────────────────────────────────────────────────────────

def _testar_nvr(t: _Teste, eq: dict, cfg: dict) -> str:
    import requests
    from src.nvr.factory import buscar_cameras
    from src.nvr.motorola.cameras import abrir_sessao_motorola
    from src.utils.http import fazer_get

    ip, usuario, senha = (eq.get("ip") or "").strip(), eq.get("username") or "", eq.get("password") or ""
    marca = (cfg.get("marca") or "").upper()
    t.planejar(("rede", "Alcançando o IP do equipamento"), ("login", "Autenticando"), ("leitura", "Lendo as câmeras"))
    host, porta = host_porta(ip, 80)
    _tcp(t, "rede", host, porta)

    t.iniciar("login", f"Marca: {marca.title() or 'detectar automaticamente'}")
    modelo = None
    recusado = False
    candidatos = [marca] if marca else ["HIKVISION", "INTELBRAS", "MOTOROLA"]
    for m in candidatos:
        try:
            if m == "MOTOROLA":
                if abrir_sessao_motorola(ip, usuario, senha) is not None:
                    modelo = "Motorola"
                    break
                recusado = True
                continue
            url = (f"http://{ip}/ISAPI/System/deviceInfo" if m == "HIKVISION"
                   else f"http://{ip}/cgi-bin/magicBox.cgi?action=getDeviceType")
            r = fazer_get(url, usuario, senha, timeout=8)
            if r.status_code == 200:
                modelo = m.title()
                if m == "HIKVISION" and "<model>" in r.text:
                    modelo += " " + r.text.split("<model>", 1)[1].split("</model>", 1)[0].strip()
                elif m == "INTELBRAS" and "type=" in r.text:
                    modelo += " " + r.text.split("type=", 1)[1].splitlines()[0].strip()
                break
            if r.status_code in (401, 403):
                recusado = True
        except requests.RequestException:
            continue
    if not modelo:
        if recusado:
            t.erro("login", "Usuário ou senha recusados")
            raise _Falha("O equipamento respondeu, mas recusou o usuário ou a senha. Atenção: várias tentativas "
                         "erradas podem bloquear o usuário no NVR por alguns minutos.")
        t.erro("login", "Nenhuma API conhecida respondeu (Hikvision ISAPI, Intelbras CGI, Motorola NVMS)")
        raise _Falha("O IP responde, mas não parece um NVR/DVR compatível. Confira o IP, a porta HTTP e a marca.")
    t.ok("login", modelo)

    t.iniciar("leitura")
    cameras, tipo, _ = buscar_cameras(ip, usuario, senha, marca or None)
    if not cameras:
        t.erro("leitura", "O equipamento não listou nenhuma câmera")
        raise _Falha(f"Login ok ({modelo}), mas nenhuma câmera foi listada: confira se o usuário tem permissão de "
                     "leitura dos canais.")
    online = sum(1 for c in cameras.values() if isinstance(c, dict) and c.get("online") is True)
    t.ok("leitura", f"{len(cameras)} câmera(s), {online} online")
    return f"Conectado ao {modelo}: {len(cameras)} câmera(s) encontradas, {online} online."


def _testar_olt(t: _Teste, eq: dict, cfg: dict, conf: dict) -> str:
    from src.application.api_client import send_status_olts
    from src.application.status_olt import _fabricante_olt, coletar_status_olts

    fabricante = _fabricante_olt(eq, cfg)
    etapas = []
    hosts = []
    if "vsol" in fabricante:
        from src.olt.vsol import _montar_base_url
        base = _montar_base_url(str(eq.get("ip") or ""), cfg)
        hosts = [("rede", host_porta(base, 80))]
    elif "huawei" in fabricante:
        try:
            porta = int(cfg.get("porta_ssh") or 22)
        except (TypeError, ValueError):
            porta = 22
        hosts = [("rede", host_porta(eq.get("ip") or "", porta))]
    elif "unm" in fabricante:
        from src.olt.unm_telnet import PORTA_PADRAO, parse_hosts
        try:
            porta = int(cfg.get("telnet_porta") or PORTA_PADRAO)
        except (TypeError, ValueError):
            porta = PORTA_PADRAO
        if cfg.get("pasta_origem"):
            etapas.append(("pasta", "Pasta de origem dos backups (UNM2000)"))
        for i, h in enumerate(parse_hosts(cfg.get("olts"))):
            hosts.append((f"rede{i}", (h["ip"], porta), h.get("nome")))
    else:
        t.planejar(("rede", "Identificando o fabricante"))
        t.erro("rede", f"Fabricante não reconhecido: {fabricante or 'não informado'}")
        raise _Falha("Escolha o fabricante da OLT no cadastro (UNM2000, VSOL ou Huawei).")

    for item in hosts:
        nome = item[2] if len(item) > 2 and item[2] else item[1][0]
        etapas.append((item[0], f"Alcançando {nome}" if len(hosts) > 1 else "Alcançando o IP da OLT"))
    if hosts:
        etapas.append(("leitura", "Login e leitura das ONUs"))
        etapas.append(("envio", "Enviando o status ao painel"))
    if not etapas:
        t.planejar(("leitura", "Configuração da OLT"))
        t.erro("leitura", "Sem pasta de origem e sem IPs de OLT para monitorar")
        raise _Falha("Nada para testar: informe a pasta de origem dos backups e/ou os IPs das OLTs (Telnet).")
    t.planejar(*etapas)

    if "unm" in fabricante and cfg.get("pasta_origem"):
        _pasta(t, "pasta", cfg.get("pasta_origem"))
    for item in hosts:
        _tcp(t, item[0], *item[1])
    if not hosts:
        return "Pasta de origem dos backups acessível."

    if "unm" in fabricante and not (cfg.get("telnet_usuario") or "").strip():
        t.erro("leitura", "Usuário do Telnet não informado")
        raise _Falha("Informe o usuário e a senha do Telnet das OLTs no cadastro.")
    t.iniciar("leitura", "Pode levar alguns minutos em OLTs com muitas ONUs")
    lista = coletar_status_olts([{**eq, "active": True}])
    olts = (lista[0].get("olts") if lista else None) or []
    if not olts:
        t.erro("leitura", "A coleta não devolveu nenhuma OLT")
        raise _Falha("A coleta das ONUs não devolveu dados.")
    erros = [o for o in olts if o.get("erro")]
    total_onus = sum(len(o.get("onus") or []) for o in olts if not o.get("erro"))
    if erros and len(erros) == len(olts):
        t.erro("leitura", "; ".join(f"{o.get('nome') or o.get('ip')}: {o.get('erro')}" for o in erros))
        raise _Falha(f"Falha no login/leitura da OLT: {erros[0].get('erro')}")
    detalhe = f"{len(olts) - len(erros)} de {len(olts)} OLT(s), {total_onus} ONU(s)"
    t.ok("leitura", detalhe)

    t.iniciar("envio")
    if send_status_olts(conf, lista):
        t.ok("envio", "Status atualizado no painel")
    else:
        t.erro("envio", "O servidor não aceitou o status")
        raise _Falha("A OLT respondeu, mas o envio do status ao painel falhou; o ciclo normal tenta de novo em 5 min.")
    if erros:
        nomes = ", ".join(str(o.get("nome") or o.get("ip")) for o in erros)
        raise _Falha(f"{detalhe}. Sem resposta de: {nomes}.")
    return f"Conectado: {detalhe}. O status das ONUs já está no painel."


def _testar_pabx(t: _Teste, eq: dict, cfg: dict) -> str:
    import requests
    from src.pabx.issabel import login

    ip = (eq.get("ip") or "").strip()
    url_base = ip if ip.startswith("http") else f"https://{ip}"
    t.planejar(("rede", "Alcançando o PABX"), ("login", "Autenticando no Issabel"))
    _tcp(t, "rede", *host_porta(url_base, 443))
    t.iniciar("login")
    s = requests.Session()
    s.cookies.set("lang", "pt_BR")
    try:
        login(s, url_base, eq.get("username") or "", eq.get("password") or "")
        r = s.get(f"{url_base}/index.php?menu=backup_restore", verify=False, timeout=15)
    except requests.RequestException as e:
        t.erro("login", str(e))
        raise _Falha(f"O PABX não respondeu ao login: {e}")
    finally:
        s.close()
    if "input_pass" in r.text:
        t.erro("login", "Usuário ou senha recusados")
        raise _Falha("O Issabel recusou o usuário ou a senha.")
    t.ok("login", "Acesso ao menu de backup liberado")
    return "Conectado ao Issabel: login e acesso ao backup ok."


def _testar_mikrotik(t: _Teste, eq: dict, cfg: dict) -> str:
    import paramiko

    ip = (eq.get("ip") or "").strip()
    t.planejar(("rede", "Alcançando o Mikrotik (SSH)"), ("login", "Autenticando no SSH"), ("leitura", "Lendo a identidade"))
    _tcp(t, "rede", ip, 22)
    t.iniciar("login")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(ip, port=22, username=eq.get("username") or "", password=eq.get("password") or "",
                    timeout=15, look_for_keys=False, allow_agent=False)
        t.ok("login")
        t.iniciar("leitura")
        _, stdout, _ = ssh.exec_command("/system identity print", timeout=20)
        saida = stdout.read().decode(errors="ignore")
        nome = saida.split("name:", 1)[1].strip().splitlines()[0] if "name:" in saida else ""
        t.ok("leitura", nome or "Sem nome")
        return f"Conectado ao Mikrotik {nome}".strip() + "."
    except paramiko.AuthenticationException:
        t.erro("login", "Usuário ou senha recusados")
        raise _Falha("O Mikrotik recusou o usuário ou a senha do SSH.")
    except Exception as e:
        etapa = "leitura" if any(x["id"] == "login" and x["estado"] == "ok" for x in t.etapas) else "login"
        t.erro(etapa, str(e))
        raise _Falha(f"Falha no SSH do Mikrotik: {e}")
    finally:
        ssh.close()


def _testar_antena(t: _Teste, eq: dict, cfg: dict, conf: dict) -> str:
    from src.application.api_client import send_status_antenas
    from src.application.status_antena import coletar_antena, porta_ssh

    ip, porta = (eq.get("ip") or "").strip(), porta_ssh(cfg)
    t.planejar(("rede", "Alcançando o MikroTik (SSH)"), ("leitura", "Entrando e lendo vizinhos, ARP e DHCP"),
               ("antenas", "Conferindo as antenas cadastradas"), ("envio", "Enviando o status ao painel"))
    _tcp(t, "rede", ip, porta)
    t.iniciar("leitura")
    if not eq.get("username") or not eq.get("password"):
        t.erro("leitura", "Usuário ou senha do MikroTik não informados")
        raise _Falha("Informe o usuário e a senha do SSH do MikroTik.")
    res = coletar_antena({**eq, "active": True})
    if res.get("erro"):
        t.erro("leitura", res["erro"])
        raise _Falha(res["erro"])
    mk = res.get("mikrotik") or {}
    t.ok("leitura", f"{mk.get('identidade') or 'MikroTik'}: {mk.get('dispositivos', 0)} dispositivo(s) na rede")

    t.iniciar("antenas")
    antenas, descobertas = res.get("antenas") or [], res.get("descobertas") or []
    online = sum(1 for a in antenas if a.get("status") == "ONLINE")
    t.ok("antenas", f"{online} de {len(antenas)} antena(s) online; {len(descobertas)} encontrada(s) na busca automática")

    t.iniciar("envio")
    if send_status_antenas(conf, [res]):
        t.ok("envio", "Status atualizado no painel")
    else:
        t.erro("envio", "O servidor não aceitou o status")
        raise _Falha("O MikroTik respondeu, mas o envio do status ao painel falhou; o ciclo normal tenta de novo em 3 min.")
    return (f"Conectado ao MikroTik {mk.get('identidade') or ''}: {online} de {len(antenas)} antena(s) online, "
            f"{len(descobertas)} nova(s) na busca automática.").replace("  ", " ")


def _testar_defense(t: _Teste, eq: dict, cfg: dict) -> str:
    from src.vms.defense import consultar_status_cameras_defense_api

    ip = (eq.get("ip") or "").strip()
    try:
        porta = int(cfg.get("porta_api") or 4433)
    except (TypeError, ValueError):
        porta = 4433
    t.planejar(("rede", "Alcançando a API do Defense IA"), ("login", "Login e leitura das câmeras"))
    _tcp(t, "rede", ip, porta)
    t.iniciar("login")
    if not eq.get("password"):
        t.erro("login", "Senha não informada")
        raise _Falha("Informe a senha do usuário da API do Defense IA.")
    ret = consultar_status_cameras_defense_api(ip=ip, username=eq.get("username") or "system",
                                               password=eq.get("password"), porta_api=porta,
                                               incluir_gravacoes=False)
    cameras = ret[1] if len(ret) >= 2 else []
    if not cameras:
        t.erro("login", "A API não devolveu câmeras")
        raise _Falha("A API do Defense não devolveu câmeras: usuário ou senha incorretos, ou nenhuma câmera "
                     "cadastrada no servidor.")
    t.ok("login", f"{len(cameras)} câmera(s)")
    return f"Conectado ao Defense IA: {len(cameras)} câmera(s)."


def _testar_digifort(t: _Teste, eq: dict, cfg: dict) -> str:
    t.planejar(("pasta", "Pasta de origem dos backups do Digifort"))
    _pasta(t, "pasta", cfg.get("pasta_origem") or "")
    return "Pasta de origem dos backups do Digifort acessível."


def _testar_generico(t: _Teste, eq: dict, cfg: dict) -> str:
    try:
        porta = int(cfg.get("porta") or 80)
    except (TypeError, ValueError):
        porta = 80
    t.planejar(("rede", "Alcançando o IP do equipamento"))
    host, porta = host_porta(eq.get("ip") or "", porta)
    _tcp(t, "rede", host, porta)
    return f"O equipamento responde em {host}:{porta}."


def executar_teste_conexao(task: dict, conf: dict, enviar: Callable[[dict], None]) -> dict:
    """Executa o teste e devolve o estado final (também enviado ao servidor). Nunca levanta erro."""
    t = _Teste(task, enviar)
    tipo = (task.get("tipo") or "NVR").upper()
    cfg = parse_config_extra(task)
    try:
        if tipo == "NVR":
            mensagem = _testar_nvr(t, task, cfg)
        elif tipo == "OLT":
            mensagem = _testar_olt(t, task, cfg, conf)
        elif tipo == "PABX":
            mensagem = _testar_pabx(t, task, cfg)
        elif tipo == "MIKROTIK":
            mensagem = _testar_mikrotik(t, task, cfg)
        elif tipo == "ANTENA":
            mensagem = _testar_antena(t, task, cfg, conf)
        elif tipo == "DEFENSE":
            mensagem = _testar_defense(t, task, cfg)
        elif tipo == "DIGIFORT":
            mensagem = _testar_digifort(t, task, cfg)
        else:
            mensagem = _testar_generico(t, task, cfg)
        t.concluir(True, mensagem)
        return {"ok": True, "mensagem": mensagem}
    except _Falha as f:
        t.concluir(False, str(f))
        return {"ok": False, "mensagem": t._sem_senha(str(f))}
    except Exception as e:
        for e_ in t.etapas:
            if e_["estado"] == "andamento":
                e_["estado"] = "erro"
        msg = f"Erro inesperado no agente: {e.__class__.__name__}: {e}"
        # sem traceback: o texto pode trazer a senha, e os avisos sobem ao painel (log remoto)
        logging.warning(f"[CONEXAO] {t._sem_senha(msg)} ({task.get('name')})")
        t.concluir(False, msg)
        return {"ok": False, "mensagem": t._sem_senha(msg)}
