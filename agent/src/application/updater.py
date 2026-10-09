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
import subprocess
import sys
import tempfile
import time

import requests

logger = logging.getLogger("trilan.updater")

CURRENT_VERSION = "1.1.1"   # <-- Atualizar manualmente a cada build
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
    expected_hash = data.get("sha256_service", "").lower()
    
    url_tray = data.get("url_tray")
    expected_tray_hash = data.get("sha256_tray", "").lower() if data.get("sha256_tray") else ""

    if not url_service or not expected_hash:
        logger.error("[OTA] Dados de atualização incompletos recebidos do servidor.")
        return False

    logger.info(f"[OTA] Atualização encontrada! Versão atual: {CURRENT_VERSION} -> Nova versão disponível: {new_version}. Iniciando atualização...")

    # Baixa em pasta temporária
    tmp_dir = tempfile.mkdtemp(prefix="trilan_update_")
    tmp_exe = os.path.join(tmp_dir, "TrilanAgentService_new.exe")
    tmp_tray_exe = os.path.join(tmp_dir, "TrilanAgentTray_new.exe")

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
        os.remove(tmp_exe)
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

    # Script batch para substituir o exe e reiniciar o serviço
    # Roda FORA do processo do serviço (detached) para poder substituir arquivos em uso
    bat_content = f"@echo off\n"
    bat_content += "timeout /t 4 /nobreak >nul\n"
    bat_content += "sc stop TrilanAgentNVR >nul 2>&1\n"
    
    if has_tray_update:
        # Mata o Tray para destravar o arquivo e permitir a substituição
        bat_content += "taskkill /F /IM TrilanAgentTray.exe >nul 2>&1\n"
        
    bat_content += "timeout /t 3 /nobreak >nul\n"
    bat_content += f'copy /y "{tmp_exe}" "{current_exe}" >nul 2>&1\n'
    
    if has_tray_update:
        bat_content += f'copy /y "{tmp_tray_exe}" "{tray_exe}" >nul 2>&1\n'
        
    bat_content += "timeout /t 2 /nobreak >nul\n"
    bat_content += "sc start TrilanAgentNVR >nul 2>&1\n"
    bat_content += 'del "%~f0"\n'
    bat_path = os.path.join(tmp_dir, "apply_update.bat")
    with open(bat_path, "w") as f:
        f.write(bat_content)

    logger.info("[OTA] Aplicando atualização via script batch. Serviço reiniciará em instantes...")
    subprocess.Popen(
        ["cmd", "/c", bat_path],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
    )

    return True  # Sinaliza ao chamador que o serviço vai reiniciar
