import logging
import subprocess
import os
import re
import shutil
from pathlib import Path
from datetime import datetime

from src.core.config import parse_config_extra


def _montar_status_cameras_defense(equipamento: dict, conf: dict = None) -> list:
    """Monta o status das câmeras (canal 1..N) a partir da config da Galeria do servidor
    (`cameras_config`), cruza com o status do Webhook CSV e captura a imagem da noite via RTSP."""
    cameras_config = equipamento.get("cameras_config") or []
    if not cameras_config:
        return None

    from src.application.webhook_defense import get_status_cameras_defense

    config_extra = parse_config_extra(equipamento)
    caminho_log = config_extra.get("pasta_origem", "")
    status_webhook = get_status_cameras_defense(caminho_log)

    cameras_para_captura = []
    status_cameras = []
    for idx, cam in enumerate(cameras_config, start=1):
        canal = cam.get("canal") or idx
        nome_cam = cam.get("nome") or f"Camera {canal}"
        is_ok = status_webhook.get(nome_cam, "OK") == "OK"
        status_cameras.append({
            "canal": canal,
            "nome": nome_cam,
            "ip": cam.get("ip") or "N/A",
            "online": is_ok,
            "status_comunicacao": "ONLINE" if is_ok else "OFFLINE",
            "status_gravacao": "COM_GRAVACAO" if is_ok else "SEM_GRAVACAO",
            "total_dias": 1,
            "mapa": "OK" if is_ok else "FALHA",
        })
        cameras_para_captura.append({**cam, "canal": canal, "nome": nome_cam})

    if conf is not None:
        from src.camera.rtsp_client import capturar_imagens_noite_vms
        capturar_imagens_noite_vms(equipamento.get("name", "Defense"), cameras_para_captura, conf)
        por_canal = {c["canal"]: c for c in cameras_para_captura}
        for st in status_cameras:
            cap = por_canal.get(st["canal"])
            if cap and "imagem_noite" in cap:
                st["imagem_noite"] = cap["imagem_noite"]

    return status_cameras


def realizar_backup_defense(equipamento: dict, pasta_destino: Path, conf: dict = None) -> dict:
    """
    Realiza o backup do Intelbras Defense IA.
    Modo 1: Coleta o arquivo de backup (.dbk, .zip, etc) gerado automaticamente pelo Defense
            (requer 'pasta_origem' no config_extra).
    Modo 2: Fallback para extrair um dump direto do banco de dados MySQL nativo.
    """
    nome = equipamento.get("name", "Defense")
    logging.info(f"\n{'='*50}\n{nome} [DEFENSE]\n{'='*50}")

    # Extrai configurações que podem vir do painel
    config_extra = parse_config_extra(equipamento)

    pasta_origem_str = config_extra.get("pasta_origem")
    status_cameras = _montar_status_cameras_defense(equipamento, conf)

    # ==========================================
    # MODO 1: Coleta do arquivo nativo do Defense
    # ==========================================
    if pasta_origem_str:
        logging.info(f"  [DEFENSE] Coletando arquivo de backup nativo na pasta: {pasta_origem_str}")
        pasta_origem = Path(pasta_origem_str)
        if not pasta_origem.exists() or not pasta_origem.is_dir():
            logging.error(f"  [DEFENSE] Pasta de origem não encontrada: {pasta_origem}")
            return {"nome": nome, "status": "ERRO", "cameras": status_cameras}

        # Busca apenas os arquivos de backup (.enc, .zip, .dbk) ignorando .cfg e temporários
        extensoes_validas = {".enc", ".zip", ".dbk", ".bak"}
        arquivos = [f for f in pasta_origem.iterdir() if f.is_file() and f.suffix.lower() in extensoes_validas]

        if not arquivos:
            logging.warning(f"  [DEFENSE] Nenhum arquivo encontrado na pasta: {pasta_origem}")
            return {"nome": nome, "status": "SEM_ARQUIVOS", "cameras": status_cameras}

        # Pega o arquivo mais recente baseado na data de modificação
        arquivo_mais_recente = max(arquivos, key=lambda f: f.stat().st_mtime)
        destino_arquivo = pasta_destino / arquivo_mais_recente.name

        try:
            shutil.copy2(arquivo_mais_recente, destino_arquivo)
            logging.info(f"  [DEFENSE] Arquivo de backup copiado com sucesso: {arquivo_mais_recente.name}")
            return {"nome": nome, "status": "OK", "cameras": status_cameras}
        except Exception as e:
            logging.error(f"  [DEFENSE] Erro ao copiar arquivo de backup: {e}")
            return {"nome": nome, "status": "ERRO", "cameras": status_cameras}

    # ==========================================
    # MODO 2: Dump do Banco de Dados MySQL
    # ==========================================
    logging.info(f"  [DEFENSE] Iniciando backup via Dump de Banco de Dados MySQL para {nome}...")
    
    db_host = equipamento.get("ip", "127.0.0.1")
    db_port = config_extra.get("db_port", "3307") # Porta padrao do MySQL no Defense IA
    db_user = equipamento.get("username", "root")
    db_pass = equipamento.get("password", "")
    db_name = config_extra.get("db_name", "defense") # Nome provável do BD
    
    data_atual = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_safe = re.sub(r"[^\w.-]", "_", nome)
    arquivo_dump = pasta_destino / f"DUMP_{nome_safe}_{data_atual}.sql"

    # Define a variável de ambiente para a senha do MySQL
    env = os.environ.copy()
    if db_pass:
        env["MYSQL_PWD"] = db_pass

    # Comando mysqldump
    comando = [
        "mysqldump",
        "-h", db_host,
        "-P", str(db_port),
        "-u", db_user,
        "--single-transaction",
        "--quick",
        "--routines",
        "--events",
        db_name
    ]

    logging.info(f"  Executando comando mysqldump para o banco '{db_name}' em {db_host}:{db_port}...")
    
    try:
        with open(arquivo_dump, 'w', encoding='utf-8') as f_out:
            subprocess.run(comando, env=env, stdout=f_out, stderr=subprocess.PIPE, text=True, check=True, timeout=600)
            
        logging.info(f"  [DEFENSE] Dump gerado com sucesso: {arquivo_dump.name}")
        return {"nome": nome, "status": "OK", "cameras": status_cameras}

    except subprocess.TimeoutExpired:
        logging.error("  Erro: mysqldump excedeu o tempo limite (600s) e foi interrompido.")
        if arquivo_dump.exists():
            arquivo_dump.unlink()
        return {"nome": nome, "status": "ERRO", "cameras": status_cameras}
    except FileNotFoundError:
        logging.error("  Erro: Utilitário 'mysqldump' não encontrado. Verifique se o MySQL Client está instalado e no PATH do sistema.")
        return {"nome": nome, "status": "ERRO", "cameras": status_cameras}
    except subprocess.CalledProcessError as e:
        logging.error(f"  Erro ao executar mysqldump (Código {e.returncode}): {e.stderr.strip()}")
        if arquivo_dump.exists():
            arquivo_dump.unlink() # Remove o arquivo vazio/incompleto
        return {"nome": nome, "status": "ERRO", "cameras": status_cameras}
    except Exception as e:
        logging.error(f"  Erro inesperado durante o dump: {e}")
        return {"nome": nome, "status": "ERRO", "cameras": status_cameras}
