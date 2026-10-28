"""
Módulo de Auto-Atualização OTA (Over The Air) do Agente Trilan.

Fluxo:
1. O agente verifica periodicamente (a cada ping) se há nova versão disponível no servidor.
2. Se houver, baixa o novo TrilanAgentService.exe de uma URL pública (ex: GitHub Release).
3. Verifica a integridade via SHA256.
4. Substitui o próprio executável em disco.
5. Reinicia o serviço Windows via sc.exe.
"""
import hashlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time

import requests

logger = logging.getLogger("trilan.updater")

CURRENT_VERSION = "1.1.29"   # <-- Atualizar manualmente a cada build
_UPDATE_CHECK_INTERVAL = 3600  # segundos entre verificações de update (1h)
_last_update_check: float = 0.0


def get_current_version() -> str:
    return CURRENT_VERSION


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _download_file(url: str, dest_path: str) -> bool:
    """Faz download de uma URL para dest_path com tratamento de erros."""
    try:
        logger.info(f"[OTA] Iniciando download: {url}")
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
        logger.info(f"[OTA] Download concluído: {downloaded} bytes")
        return True
    except Exception as e:
        logger.error(f"[OTA] Falha no download: {e}")
        return False


def check_and_apply_update(conf: dict) -> bool:
    """
    Verifica se há atualização disponível no servidor.
    Se houver, baixa, verifica hash, substitui e reinicia o serviço.
    
    Retorna True se uma atualização foi iniciada (o serviço vai reiniciar).
    """
    global _last_update_check

    # Não verificar com muita frequência
    if time.time() - _last_update_check < _UPDATE_CHECK_INTERVAL:
        return False
    _last_update_check = time.time()

    server_url = conf.get("server_url", "").rstrip("/")
    headers = {
        "X-Client-ID": conf.get("client_id", ""),
        "X-API-Key": conf.get("api_key", ""),
    }

    try:
        resp = requests.get(
            f"{server_url}/api/v1/agent/update-check",
            headers=headers,
            params={"current_version": CURRENT_VERSION},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"[OTA] Falha ao verificar atualização: {e}")
        return False

    if not data.get("has_update"):
        logger.info(f"[OTA] Versão atual ({CURRENT_VERSION}) está atualizada.")
        return False

    new_version = data.get("version", "?")
    url_service = data.get("url_service")
    expected_hash = (data.get("sha256_service") or "").lower()

    url_tray = data.get("url_tray")
    expected_tray_hash = (data.get("sha256_tray") or "").lower()

    if not url_service or not expected_hash:
        logger.error("[OTA] Dados de atualização incompletos recebidos do servidor.")
        return False

    if not str(url_service).lower().startswith("https://"):
        logger.error("[OTA] url_service nao usa https://. Atualização ignorada.")
        return False
    if url_tray and not str(url_tray).lower().startswith("https://"):
        logger.warning("[OTA] url_tray nao usa https://. O Tray não será atualizado.")
        url_tray = None

    logger.info(f"[OTA] Atualização encontrada! Versão atual: {CURRENT_VERSION} -> Nova versão disponível: {new_version}. Iniciando atualização...")

    # Baixa em pasta temporária
    tmp_dir = tempfile.mkdtemp(prefix="trilan_update_")
    tmp_exe = os.path.join(tmp_dir, "TrilanAgentService_new.exe")
    tmp_tray_exe = os.path.join(tmp_dir, "TrilanAgentTray_new.exe")
    aplicado = False
    try:
        if not _download_file(url_service, tmp_exe):
            logger.error("[OTA] Download falhou. Atualização cancelada.")
            return False

        # Verifica integridade SHA256 do Service
        actual_hash = _sha256_file(tmp_exe)
        if actual_hash != expected_hash:
            logger.error(
                f"[OTA] FALHA DE INTEGRIDADE NO SERVICE! "
                f"Esperado: {expected_hash} | Recebido: {actual_hash}. "
                "Atualização cancelada por segurança."
            )
            return False
        
        # Download e verificação do Tray (opcional)
        has_tray_update = False
        if url_tray and expected_tray_hash:
            logger.info("[OTA] Atualização de Tray encontrada. Iniciando download do Tray...")
            if _download_file(url_tray, tmp_tray_exe):
                actual_tray_hash = _sha256_file(tmp_tray_exe)
                if actual_tray_hash == expected_tray_hash:
                    has_tray_update = True
                    logger.info(f"[OTA] Hash do Tray verificado com sucesso.")
                else:
                    logger.warning(f"[OTA] Falha de integridade no Tray (Esperado: {expected_tray_hash} | Recebido: {actual_tray_hash}). O Tray não será atualizado.")
            else:
                logger.warning("[OTA] Download do Tray falhou. Apenas o serviço será atualizado.")

        logger.info(f"[OTA] Verificações concluídas com sucesso. Construindo script de deploy...")

        # Caminho do executável atual (Service)
        current_exe = sys.executable
        base_dir = os.path.dirname(current_exe)
        tray_exe = os.path.join(base_dir, "TrilanAgentTray.exe")

        # Script batch para substituir o exe e reiniciar o serviço. Roda FORA do processo do serviço
        # (detached) para poder substituir arquivos em uso. Em vez de tempos fixos, espera o processo
        # antigo sair, copia com novas tentativas (arquivo ainda travado) e confere se o serviço subiu.
        # Pausas com "ping": o "timeout" do Windows não espera sem console (o .bat roda destacado).
        log_ota = os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"),
                               "Trilan NVR Backup Agent", "logs", "atualizacao.log")

        def passo(rotulo, comando, tentativas, espera_s):
            # Repete `comando` até dar certo (errorlevel 0). Sem blocos ( ): %N% não expande dentro deles.
            return (
                f"set N=0\n:{rotulo}\n{comando}\n"
                f"if not errorlevel 1 goto {rotulo}_ok\n"
                f"set /a N+=1\nif %N% GEQ {tentativas} goto {rotulo}_falha\n"
                f"ping -n {espera_s + 1} 127.0.0.1 >nul\ngoto {rotulo}\n"
                f':{rotulo}_falha\necho [%date% %time%] FALHA: {rotulo} >> "{log_ota}"\n'
                f":{rotulo}_ok\n"
            )

        bat_content = "@echo off\n"
        bat_content += f'echo [%date% %time%] Atualizando para {new_version}... >> "{log_ota}"\n'
        bat_content += "sc stop TrilanAgentNVR >nul 2>&1\n"
        if has_tray_update:
            # Mata o Tray para destravar o arquivo e permitir a substituição
            bat_content += "taskkill /F /IM TrilanAgentTray.exe >nul 2>&1\n"
        # Espera (até 90 s) não haver mais TrilanAgentService.exe rodando ("find" sem achar = errorlevel 1)
        bat_content += (
            "set N=0\n:espera\n"
            'tasklist /FI "IMAGENAME eq TrilanAgentService.exe" | find /I "TrilanAgentService.exe" >nul\n'
            "if errorlevel 1 goto espera_ok\n"
            "set /a N+=1\nif %N% GEQ 90 goto espera_falha\n"
            "ping -n 2 127.0.0.1 >nul\ngoto espera\n"
            f':espera_falha\necho [%date% %time%] FALHA: processo antigo nao encerrou >> "{log_ota}"\n'
            ":espera_ok\n"
        )
        bat_content += passo("copia", f'copy /y "{tmp_exe}" "{current_exe}" >nul 2>&1', 15, 2)
        if has_tray_update:
            bat_content += passo("copia_tray", f'copy /y "{tmp_tray_exe}" "{tray_exe}" >nul 2>&1', 15, 2)
        bat_content += "sc config TrilanAgentNVR start= delayed-auto >nul 2>&1\n"
        bat_content += "sc failure TrilanAgentNVR reset= 86400 actions= restart/5000/restart/10000/restart/30000 >nul 2>&1\n"
        bat_content += "sc failureflag TrilanAgentNVR 1 >nul 2>&1\n"
        bat_content += passo("inicia", 'sc start TrilanAgentNVR >nul 2>&1\nping -n 4 127.0.0.1 >nul\n'
                                       'sc query TrilanAgentNVR | find "RUNNING" >nul', 5, 2)
        bat_content += f'echo [%date% %time%] Atualizacao concluida. >> "{log_ota}"\n'
        bat_content += 'del "%~f0"\n'
        bat_path = os.path.join(tmp_dir, "apply_update.bat")
        with open(bat_path, "w") as f:
            f.write(bat_content)

        logger.info("[OTA] Aplicando atualização via script batch. Serviço reiniciará em instantes...")
        # Console oculto + entradas/saídas nulas (sem DETACHED_PROCESS: sem console, comandos como
        # "timeout" e o PowerShell não funcionam). O processo continua após o serviço encerrar.
        subprocess.Popen(
            ["cmd", "/c", bat_path],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        aplicado = True  # o .bat (destacado) ainda usa tmp_dir
        return True  # Sinaliza ao chamador que o serviço vai reiniciar
    finally:
        if not aplicado:
            shutil.rmtree(tmp_dir, ignore_errors=True)