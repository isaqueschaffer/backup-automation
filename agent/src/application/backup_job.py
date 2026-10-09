import json
import logging
import shutil
import sys
import requests
from datetime import datetime
from pathlib import Path
from requests.auth import HTTPDigestAuth
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from src.core.config import load_conf, DIR_AGENT
from src.application.api_client import fetch_server_config, post_report, upload_zip
from src.nvr.factory import verificar_gravacao_nvr
from src.olt.unm2000 import realizar_backup_olt
from src.olt.vsol import realizar_backup_vsol
from src.pabx.issabel import realizar_backup_issabel
from src.mikrotik.routeros import realizar_backup_mikrotik
from src.vms.defense import realizar_backup_defense
from src.backup.crypto import gerar_secretkey
from src.backup.downloader import baixar_arquivo
from src.backup.archiver import criar_zip, data_hoje

TEMP_DIR = DIR_AGENT / "tmp_backup"

def setup_logging():
    log_dir = DIR_AGENT / "logs"
    log_dir.mkdir(exist_ok=True)
    logger = logging.getLogger()
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter("[%(asctime)s] %(message)s", "%Y-%m-%d %H:%M:%S")
        fh = logging.FileHandler(log_dir / "agent.log", encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        if sys.stdout is not None:
            ch = logging.StreamHandler(sys.stdout)
            ch.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(ch)


# ─────────────────────────────────────────────────────────────
# PROCESSADORES POR TIPO DE EQUIPAMENTO
# ─────────────────────────────────────────────────────────────

def processar_nvr(equipamento: dict, zip_password: str, pasta_data: Path) -> dict:
    """Processa backup de NVR (Hikvision/Motorola/Digifort)."""
    nome, ip, user, pwd = (
        equipamento["name"], equipamento["ip"],
        equipamento["username"], equipamento["password"]
    )
    logging.info(f"\n{'='*50}\n{nome} [NVR] (IP: {ip})\n{'='*50}")

    pasta_nvr = pasta_data
    pasta_nvr.mkdir(parents=True, exist_ok=True)

    config_extra = equipamento.get("config_extra") or {}
    if isinstance(config_extra, str):
        try:
            config_extra = json.loads(config_extra)
        except Exception:
            config_extra = {}
    marca = config_extra.get("marca")

    retorno = verificar_gravacao_nvr(ip, user, pwd, marca)
    if isinstance(retorno, tuple) and len(retorno) == 2:
        cameras_status, tipo_nvr = retorno
    else:
        cameras_status, tipo_nvr = retorno, "DESCONHECIDO"

    if not cameras_status:
        logging.error("  NVR INACESSIVEL ou falha no login.")
        return {"nome": nome, "status": "ERRO"}

    logging.info(f"  NVR acessivel (Detectado: {tipo_nvr}).")

    sessao = requests.Session()
    sessao.auth = HTTPDigestAuth(user, pwd)
    sessao.verify = False

    sucessos = 0
    status = "OK"

    if tipo_nvr == "MOTOROLA":
        logging.info("  NVR Motorola detectado. Backup de arquivos de configuracao nao suportado nativamente. Gravacoes verificadas.")
        status = "SEM_ARQUIVOS"
    else:
        try:
            sessao.get(f"http://{ip}/ISAPI/System/status", timeout=5).raise_for_status()

            # Config NVR (.bin)
            sk, iv = gerar_secretkey(zip_password)
            url_bin = f"http://{ip}/ISAPI/System/configurationData?secretkey={sk}&security=1&iv={iv}"
            arq_bin = pasta_nvr / f"CONFIG_NVR_{data_hoje()}.bin"
            if baixar_arquivo(sessao, url_bin, arq_bin, min_bytes=100_000, valida_xml=True):
                logging.info("  Backup NVR OK.")
                sucessos += 1

            # Config IPCAM (.xls)
            url_xls = f"http://{ip}/ISAPI/ContentMgmt/InputProxy/ipcConfig"
            arq_xls = pasta_nvr / f"CONFIG_IPCAM_{data_hoje()}.xls"
            if baixar_arquivo(sessao, url_xls, arq_xls):
                logging.info("  Backup IPCAM OK.")
                sucessos += 1

            status = "OK" if sucessos == 2 else "PARCIAL"
        except Exception:
            logging.warning("  API ISAPI falhou. Backup de arquivos pulado.", exc_info=True)
            status = "PARCIAL"

    # Captura a foto da madrugada para câmeras compatíveis
    from src.application.api_client import upload_night_image
    from src.core.config import load_conf
    conf = load_conf()

    if tipo_nvr != "MOTOROLA" and cameras_status:
        from src.camera.rtsp_client import capture_night_image
        logging.info("  Iniciando extração de imagens noturnas (Playback RTSP) para os canais gravados...")
        for cam_st in cameras_status:
            dias_gravacao = cam_st.get("dias_com_gravacao", [])
            if dias_gravacao:
                # Pega a data mais recente com gravação (o último item na lista, ou ordenamos só para garantir)
                dias_ordenados = sorted(dias_gravacao)
                data_alvo = dias_ordenados[-1]
                
                try:
                    b64_img = capture_night_image(ip, user, pwd, cam_st["canal"], data_alvo)
                    if b64_img:
                        dt_iso = f"{data_alvo}T02:00:00"
                        payload = {
                            "nvr_name": nome,
                            "canal": cam_st["canal"],
                            "nome": cam_st["nome"],
                            "image_base64": b64_img,
                            "night_image_date": dt_iso
                        }
                        sucesso_up = upload_night_image(conf, payload)
                        if sucesso_up:
                            logging.info(f"    [OK] Imagem noturna do canal {cam_st['canal']} ({data_alvo}) enviada.")
                        else:
                            logging.warning(f"    [ERRO] Falha ao enviar imagem noturna do canal {cam_st['canal']} para o servidor.")
                    else:
                        logging.warning(f"    [FALHA] Não foi possível extrair o frame do canal {cam_st['canal']} (RTSP vazio).")
                except Exception as e:
                    logging.warning(f"    [ERRO] Exceção ao capturar imagem do canal {cam_st['canal']}: {e}")

    return {"nome": nome, "status": status, "cameras": cameras_status}


def processar_olt(
    equipamento: dict,
    pasta_data: Path
) -> dict:

    tipo = (equipamento.get("tipo") or "").lower()

    config_extra = equipamento.get("config_extra") or {}
    if isinstance(config_extra, str):
        try:
            config_extra = json.loads(config_extra)
        except Exception:
            config_extra = {}

    fabricante = (
        equipamento.get("fabricante")
        or config_extra.get("fabricante_olt")
        or config_extra.get("fabricante")
        or ""
    ).lower().strip()

    # Fallback caso fabricante não venha explícito mas esteja no nome ou config
    if not fabricante or fabricante == "olt":
        nome_lower = (equipamento.get("name") or "").lower()
        if "vsol" in nome_lower:
            fabricante = "vsol"
        elif "unm" in nome_lower or "huawei" in nome_lower:
            fabricante = "unm2000"
        elif "pasta_origem" in config_extra and config_extra.get("pasta_origem"):
            fabricante = "unm2000"

    if tipo == "digifort":
        fabricante = "unm2000"

    logging.info(
        f"[OLT] Tipo={tipo} | Fabricante={fabricante}"
    )

    if fabricante == "vsol":
        return realizar_backup_vsol(
            equipamento,
            pasta_data
        )

    if fabricante == "huawei":
        from src.olt.huawei_active import realizar_backup_huawei_ativo
        return realizar_backup_huawei_ativo(
            equipamento,
            pasta_data
        )

    if fabricante in ("unm", "unm2000"):
        return realizar_backup_olt(
            equipamento,
            pasta_data
        )

    logging.error(
        f"[OLT] Fabricante não suportado: {fabricante}"
    )

    return {
        "nome": equipamento.get(
            "name",
            "OLT_desconhecida"
        ),
        "status": "ERRO",
        "cameras": None,
    }


def processar_pabx(equipamento: dict, pasta_data: Path) -> dict:
    pasta_data.mkdir(parents=True, exist_ok=True)
    return realizar_backup_issabel(equipamento, pasta_data)


def processar_mikrotik(equipamento: dict, pasta_data: Path) -> dict:
    pasta_data.mkdir(parents=True, exist_ok=True)
    return realizar_backup_mikrotik(equipamento, pasta_data)


def processar_defense(equipamento: dict, pasta_data: Path) -> dict:
    pasta_data.mkdir(parents=True, exist_ok=True)
    return realizar_backup_defense(equipamento, pasta_data)


def processar_equipamento(equipamento: dict, zip_password: str, pasta_data: Path) -> dict:
    """
    Despachante principal — roteia o processamento pelo tipo do equipamento.
    Tipos suportados: NVR, OLT, PABX
    Tipos futuros:    ONU, PABX (retornam status TIPO_NAO_SUPORTADO)
    """
    tipo = (equipamento.get("tipo") or "NVR").upper()

    if tipo == "NVR":
        return processar_nvr(equipamento, zip_password, pasta_data)

    if tipo == "OLT" or tipo == "DIGIFORT":
        return processar_olt(equipamento, pasta_data)

    if tipo == "PABX":
        return processar_pabx(equipamento, pasta_data)

    if tipo == "MIKROTIK":
        return processar_mikrotik(equipamento, pasta_data)

    if tipo == "DEFENSE":
        return processar_defense(equipamento, pasta_data)

    # Tipos cadastrados mas ainda não implementados
    logging.warning(f"  Tipo '{tipo}' ainda não suportado pelo agente. Equipamento: {equipamento.get('name')}")
    return {"nome": equipamento.get("name", "?"), "status": "TIPO_NAO_SUPORTADO", "cameras": None}


# ─────────────────────────────────────────────────────────────
# EXECUÇÃO PRINCIPAL
# ─────────────────────────────────────────────────────────────

def run_backup(trigger: str = "scheduled"):
    setup_logging()
    logging.info(f"\n{'='*60}\nINICIANDO BACKUP — {trigger.upper()}\n{'='*60}")

    conf = load_conf()

    logging.info("Buscando configuracao do servidor...")
    try:
        server_cfg = fetch_server_config(conf)
    except Exception as e:
        logging.error(f"Falha ao buscar config: {e}")
        return

    # Aceita tanto o campo novo (equipamentos) quanto o legado (nvrs)
    equipamentos = server_cfg.get("equipamentos") or server_cfg.get("nvrs") or []
    zip_password = server_cfg.get("zip_password")
    if not zip_password:
        logging.warning("AVISO DE SEGURANCA: zip_password nao configurado no servidor para este cliente. O ZIP sera criado sem senha.")
    client_name = server_cfg["client_name"]

    if not equipamentos:
        logging.error("Nenhum equipamento configurado no servidor para este cliente.")
        return

    # Ignora as câmeras (elas não fazem parte do backup principal automático)
    equipamentos = [eq for eq in equipamentos if str(eq.get("tipo")).upper() != "CAMERA"]

    # Resumo por tipo
    por_tipo: dict = {}
    for eq in equipamentos:
        t = (eq.get("tipo") or "NVR").upper()
        por_tipo[t] = por_tipo.get(t, 0) + 1

    logging.info(f"Cliente      : {client_name}")
    logging.info(f"Equipamentos : {len(equipamentos)} total — " + ", ".join(f"{v} {k}" for k, v in por_tipo.items()))

    TEMP_DIR_WORK = DIR_AGENT / "tmp_backup_work"
    TEMP_DIR_FINAL = DIR_AGENT / "tmp_backup_final"

    shutil.rmtree(TEMP_DIR_WORK, ignore_errors=True)
    shutil.rmtree(TEMP_DIR_FINAL, ignore_errors=True)
    TEMP_DIR_WORK.mkdir(parents=True)
    TEMP_DIR_FINAL.mkdir(parents=True)

    started_at = datetime.utcnow()
    resultados = []

    for eq in equipamentos:
        tipo = (eq.get("tipo") or "NVR").upper()
        nome = eq.get("name", "equipamento")
        nome_safe = nome.replace(" ", "_")

        # Diretório temporário de trabalho
        pasta_trabalho = TEMP_DIR_WORK / f"{tipo}_{nome_safe}"
        pasta_trabalho.mkdir(parents=True, exist_ok=True)

        res = processar_equipamento(eq, zip_password, pasta_trabalho)
        res["tipo"] = tipo
        resultados.append(res)

        # Monta a estrutura final
        pasta_final_eq = TEMP_DIR_FINAL / tipo / f"backup_{tipo.lower()}_{nome_safe}"
        pasta_final_eq.mkdir(parents=True, exist_ok=True)

        # Cria o ZIP interno sem senha
        zip_interno_path = pasta_final_eq / "backup.zip"
        if any(pasta_trabalho.iterdir()):
            criar_zip(pasta_trabalho, zip_interno_path, senha=None)

    finished_at = datetime.utcnow()

    for r in resultados:
        icone = {
            "OK": "OK", "PARCIAL": "PARCIAL", "ERRO": "ERRO",
            "SEM_ARQUIVOS": "SEM_ARQUIVOS", "JA_PROCESSADO": "JA_PROCESSADO",
            "TIPO_NAO_SUPORTADO": "SKIP",
            "BACKUP_ANTIGO": "ANTIGO", "BACKUP_INCOMPLETO": "INCOMPLETO",
            "BACKUP_INCONSISTENTE": "INCONSISTENTE", "BACKUP_NAO_ENCONTRADO": "NAO_ENCONTRADO",
            "BACKUP_EM_PROCESSAMENTO": "ESPERA", "BACKUP_CORROMPIDO": "CORROMPIDO"
        }.get(r["status"], r["status"])
        logging.info(f"  {icone} [{r.get('tipo', 'NVR')}] {r['nome']}")

    backup_id = post_report(conf, started_at, finished_at, resultados, trigger)
    if backup_id:
        todos_arquivos = [f for f in TEMP_DIR_FINAL.rglob("*") if f.is_file()]
        if todos_arquivos:
            # Define o nome do ZIP global
            data_str = datetime.now().strftime("%d_%m_%Y")
            nome_zip_global = f"backup_{data_str}.zip"

            zip_global_path = criar_zip(TEMP_DIR_FINAL, nome_zip_global, zip_password)
            if zip_global_path:
                logging.info(f"  Enviando pacote de backup global: {zip_global_path.name}")
                upload_zip(conf, backup_id, zip_global_path, device_type="MIXED")

    shutil.rmtree(TEMP_DIR_WORK, ignore_errors=True)
    shutil.rmtree(TEMP_DIR_FINAL, ignore_errors=True)
    logging.info(f"\nBackup concluido em {(finished_at - started_at).total_seconds():.1f}s")
