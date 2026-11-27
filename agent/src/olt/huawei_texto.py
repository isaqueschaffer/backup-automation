"""
OLT Huawei no túnel do Mikrotik: backup TEXTUAL por SSH (`display current-configuration`), capturado em memória.

O agente Windows sobe um FTP efêmero (porta 21) para a OLT empurrar o arquivo (`backup configuration ftp ...`). No
Mikrotik isso exigiria porta 21 aberta e NAT no roteador, então aqui o agente só lê a configuração em texto. Ela serve
para restaurar colando no terminal, mas NÃO é o binário (`backup configuration`/`backup data`) do Windows.
"""
import logging
import re
import time
from datetime import datetime
from typing import Optional, Tuple

TAMANHO_MINIMO = 500                 # config real de OLT tem bem mais; abaixo disso é erro/ajuda do comando
TIMEOUT_TOTAL_S = 600
SILENCIO_FIM_S = 8                   # sem nada novo por este tempo e já com prompt: terminou
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[=>()][0-9A-B]?")
_MORE = re.compile(r"-{2,}\s*More\s*(?:\([^)]*\))?\s*-{2,}\s*(?:\x1b\[[0-9;]*[A-Za-z]|[\x08 ])*", re.IGNORECASE)
_PROMPT_FIM = re.compile(r"(?:^|\n)[^\n]{0,60}[>#]\s*$")


def limpar_saida(bruto: str, comando: str = "") -> str:
    """Tira códigos ANSI, marcadores de paginação (`---- More ----`), backspaces, CR e o eco do comando/prompt final."""
    t = _ANSI.sub("", bruto)
    t = _MORE.sub("", t)
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[^\n]*\x08+[^\n]*", lambda m: re.sub(r".\x08", "", m.group(0)).replace("\x08", ""), t)
    linhas = t.split("\n")
    if comando:
        for i, l in enumerate(linhas[:5]):
            if comando in l:
                linhas = linhas[i + 1:]
                break
    while linhas and not linhas[-1].strip():
        linhas.pop()
    if linhas and re.fullmatch(r"\S{0,60}[>#]\s*", linhas[-1]):
        linhas.pop()        # prompt depois do `return`
    return "\n".join(l.rstrip() for l in linhas).strip("\n") + "\n"


def config_valida(texto: str) -> Tuple[bool, str]:
    """(ok, motivo). Config de VRP termina em `return`; recusa saída de erro ou curta demais."""
    t = (texto or "").strip()
    if len(t.encode("utf-8")) < TAMANHO_MINIMO:
        return False, f"saída muito curta ({len(t)} caracteres)"
    ultimas = [l.strip() for l in t.splitlines() if l.strip()][-3:]
    if "return" not in ultimas:
        return False, "a configuração não terminou com 'return' (saída cortada)"
    if re.search(r"Unknown command|Error: ", t[:400]):
        return False, "a OLT recusou o comando"
    return True, ""


def ler_config_por_shell(shell, limite_bytes: int, timeout_total: float = TIMEOUT_TOTAL_S,
                         silencio: float = SILENCIO_FIM_S) -> str:
    """Roda `display current-configuration` num shell interativo já em modo privilegiado e devolve o texto bruto,
    respondendo à paginação com espaço. `shell` só precisa de send/recv/recv_ready."""
    comando = "display current-configuration"
    shell.send(comando + "\n")
    bruto = ""
    fim = time.time() + timeout_total
    ultimo = time.time()
    while time.time() < fim:
        if shell.recv_ready():
            parte = shell.recv(65536).decode("utf-8", errors="ignore")
            bruto += parte
            ultimo = time.time()
            if len(bruto) > limite_bytes:
                raise ValueError(f"a configuração passou de {limite_bytes // (1024 * 1024)} MB")
            if re.search(r"-{2,}\s*More", parte[-200:], re.IGNORECASE):
                shell.send(" ")         # próxima página
            continue
        if time.time() - ultimo >= silencio and _PROMPT_FIM.search(_ANSI.sub("", bruto[-200:])) \
                and "return" in bruto[-400:]:
            break
        time.sleep(0.3)
    else:
        raise TimeoutError("a OLT não terminou de enviar a configuração a tempo")
    return bruto


def preparar_backup_huawei_texto(equipamento: dict, limite_memoria: int) -> dict:
    """Devolve {"nome", "status": "PRONTO"|"ERRO", "arquivos_origem": [(BackupFile, nome_no_zip)]}."""
    from src.backup.file_manager.models import BackupFile
    from src.backup.sftp_origem import ErroSftp, abrir_ssh
    from src.core.config import parse_config_extra
    from pathlib import Path

    nome = (equipamento.get("name") or "Huawei").replace(" ", "_")
    erro = {"nome": nome, "status": "ERRO", "cameras": None}
    ip = equipamento.get("ip")
    usuario = equipamento.get("username")
    senha = equipamento.get("password")
    cfg = parse_config_extra(equipamento)
    if not ip or not usuario or not senha:
        logging.error(f"[HUAWEI] {nome} — Faltam credenciais (ip/usuario/senha). Abortando.")
        return erro
    try:
        porta = int(equipamento.get("porta") or equipamento.get("port") or 22)
    except (TypeError, ValueError):
        porta = 22

    from contextlib import ExitStack
    from src.olt.huawei_sessao import conectar_com_novas_tentativas, sair_da_olt, sessao_exclusiva
    from src.olt.huawei_status import explicar_erro_ssh

    ssh = None
    shell = None
    pilha = ExitStack()
    try:
        pilha.enter_context(sessao_exclusiva(ip))  # uma sessao por vez do agente na OLT (status, teste, backup)
        logging.info(f"[HUAWEI] Conectando via SSH em {ip}:{porta} (usuario: {usuario})...")
        ssh = conectar_com_novas_tentativas(
            lambda: abrir_ssh(ip, porta, usuario, senha, None, cfg.get("ssh_fingerprint") or None,
                              disabled_algorithms={"keys": [], "pubkeys": []}),
            f"Backup de {nome}")
        shell = ssh.invoke_shell(width=200, height=500)
        shell.settimeout(15)

        def esperar(marcas, timeout=15):
            fim, saida = time.time() + timeout, ""
            while time.time() < fim:
                if shell.recv_ready():
                    saida += shell.recv(4096).decode("utf-8", errors="ignore")
                    if any(m in saida for m in marcas):
                        return saida
                time.sleep(0.3)
            raise TimeoutError(f"prompt não encontrado em {timeout}s: {saida[-200:]!r}")

        esperar([">"])
        shell.send("enable\n")
        esperar(["#"])
        for cmd in ("screen-length 0 temporary", "undo smart"):     # sem paginação (o que a OLT aceitar)
            shell.send(cmd + "\n")
            time.sleep(1)
            while shell.recv_ready():
                shell.recv(4096)
        logging.info("[HUAWEI] Lendo 'display current-configuration'...")
        bruto = ler_config_por_shell(shell, limite_memoria)
        texto = limpar_saida(bruto, "display current-configuration")
        ok, motivo = config_valida(texto)
        if not ok:
            logging.error(f"[HUAWEI] {nome}: configuração lida não parece válida: {motivo}.")
            return erro
        dados = texto.encode("utf-8")
        arq = f"current-configuration_{nome.lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        logging.info(f"[HUAWEI] {nome}: config em TEXTO capturada ({len(dados):,} bytes). Restaura-se colando no "
                     f"terminal da OLT; não é o binário do 'backup configuration' do agente Windows.",
                     extra={"enviar_servidor": True})
        bf = BackupFile(path=Path(arq), file_type="HUAWEI_TEXTO", dados=dados)
        return {"nome": nome, "status": "PRONTO", "arquivos_origem": [(bf, arq)], "cameras": None}
    except ErroSftp as e:
        logging.error(f"[HUAWEI] {nome}: {e}")
    except TimeoutError as e:
        logging.error(f"[HUAWEI] TIMEOUT — {explicar_erro_ssh(e, ip, porta)}")
    except Exception as e:
        logging.error(f"[HUAWEI] FALHA em {ip}:{porta}: {explicar_erro_ssh(e, ip, porta)}")
    finally:
        try:
            if shell is not None:
                sair_da_olt(shell)  # logout limpo: libera a sessao na OLT (1.1.70)
            if ssh is not None:
                ssh.close()
        except Exception:
            pass
        pilha.close()
    return erro
