import hashlib
import logging
import re
import shutil
import sys
import time
import requests
from datetime import datetime
from pathlib import Path
from requests.auth import HTTPDigestAuth
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from src.core.config import load_conf, parse_config_extra, DIR_AGENT
from src.application.api_client import fetch_server_config, post_report, upload_zip
from src.application import log_remoto
from src.nvr.factory import verificar_gravacao_nvr, coletar_telemetria_nvr
from src.nvr.intelbras.backup import baixar_configuracao_intelbras
from src.nvr.motorola.backup import baixar_configuracao_motorola
try:
    from src.nvr.hikvision.planilha import gerar_planilha_hikvision
    from src.nvr.intelbras.planilha import gerar_planilha_intelbras
    from src.nvr.motorola.planilha import gerar_planilha_motorola
    # tipo de NVR detectado -> funcao que grava a planilha da configuracao
    PLANILHAS_NVR = {
        "MOTOROLA": gerar_planilha_motorola, "INTELBRAS": gerar_planilha_intelbras,
        "NVR": gerar_planilha_hikvision, "DVR": gerar_planilha_hikvision,
    }
except Exception:
    # openpyxl ausente ou incompativel: so a planilha dos NVR fica indisponivel (o backup segue normal)
    logging.warning("Planilha dos NVR indisponivel: falha ao carregar o openpyxl.", exc_info=True)
    PLANILHAS_NVR = {}
from src.olt.unm2000 import realizar_backup_olt
from src.olt.vsol import realizar_backup_vsol
from src.pabx.issabel import realizar_backup_issabel
from src.mikrotik.routeros import realizar_backup_mikrotik
from src.vms.defense import realizar_backup_defense
from src.backup.crypto import gerar_secretkey
from src.backup.downloader import sem_query
from src.nvr.hikvision import backup as backup_hikvision
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

def nome_seguro(nome: str) -> str:
    """Nome de equipamento seguro para caminhos/comandos (espacos viram '_')."""
    return re.sub(r"[^\w.-]", "_", nome or "")


def processar_nvr(equipamento: dict, zip_password: str, pasta_data: Path, conf: dict = None) -> dict:
    """Processa backup de NVR (Hikvision/Intelbras/Motorola).

    Hikvision (desde 1.1.69): a configuração (.bin e .xls) é baixada ANTES da verificação de gravação, que é a parte
    pesada e trava o serviço web dos NVR mais fracos; depois se completa o que faltou, com novas tentativas. O
    resultado leva `motivo` quando não fica OK (vai para o painel e para o log)."""
    nome, ip, user, pwd = (
        equipamento["name"], equipamento["ip"],
        equipamento["username"], equipamento["password"]
    )
    logging.info(f"\n{'='*50}\n{nome} [NVR] (IP: {ip})\n{'='*50}")

    pasta_nvr = pasta_data
    pasta_nvr.mkdir(parents=True, exist_ok=True)

    config_extra = parse_config_extra(equipamento)
    marca = config_extra.get("marca")
    marca_up = (marca or "").upper()

    # Hikvision ou marca não informada: tenta a configuração antes (Intelbras e Motorola têm caminho próprio)
    config_hik = None
    if marca_up not in ("MOTOROLA", "INTELBRAS"):
        config_hik = backup_hikvision.baixar_antes_da_gravacao(ip, user, pwd, zip_password)

    retorno = verificar_gravacao_nvr(ip, user, pwd, marca)
    if isinstance(retorno, tuple) and len(retorno) == 2:
        cameras_status, tipo_nvr = retorno
    else:
        cameras_status, tipo_nvr = retorno, "DESCONHECIDO"

    if not cameras_status and tipo_nvr == "DESCONHECIDO":
        if config_hik and (config_hik.get("bin") or config_hik.get("xls")):
            # O NVR respondeu à configuração e parou na verificação: o backup de fato está salvo
            _gravar_config_hikvision(config_hik, pasta_nvr)
            motivo = "câmeras e gravação não lidas (o NVR parou de responder depois da configuração)"
            falhas = backup_hikvision.descrever_falhas(config_hik, telemetria_esperada=False)
            motivo = f"{motivo}; {falhas}" if falhas else motivo
            logging.warning(f"  {nome} PARCIAL: {motivo}", extra={"enviar_servidor": True})
            return {"nome": nome, "status": "PARCIAL", "motivo": motivo}
        logging.error("  NVR INACESSIVEL ou falha no login.")
        return {"nome": nome, "status": "ERRO", "motivo": "NVR inacessível ou falha no login"}

    if not cameras_status:
        logging.warning("  Nenhuma câmera encontrada no NVR. Prosseguindo com backup de configurações.")

    logging.info(f"  NVR acessivel (Detectado: {tipo_nvr}).")

    telemetria = coletar_telemetria_nvr(ip, user, pwd, tipo_nvr, marca, config_extra.get("snmp_community"))

    status = "OK"
    motivo = ""

    if tipo_nvr == "MOTOROLA":
        logging.info("  NVR Motorola detectado. Exportando configuracao restauravel (sem plugin)...")
        arq_cfg = pasta_nvr / f"CONFIG_MOTOROLA_{data_hoje()}.bin"
        if not baixar_configuracao_motorola(ip, user, pwd, arq_cfg):
            status, motivo = "PARCIAL", "configuração do NVR Motorola não exportada (ver o log)"
    elif tipo_nvr == "INTELBRAS" or marca_up == "INTELBRAS":
        logging.info("  NVR Intelbras detectado. Baixando configuracao completa via CGI...")
        arq_cfg = pasta_nvr / f"CONFIG_INTELBRAS_{data_hoje()}.backup"
        if not baixar_configuracao_intelbras(ip, user, pwd, arq_cfg):
            status, motivo = "PARCIAL", "configuração do NVR Intelbras não baixada (ver o log)"
    else:
        try:
            config_hik = backup_hikvision.completar(ip, user, pwd, zip_password, config_hik)
        except Exception as e:
            logging.warning("  API ISAPI falhou. Backup de arquivos pulado.", exc_info=True)
            config_hik = {"bin": None, "xls": None, "motivos": {"bin": f"{type(e).__name__}: {sem_query(e)}",
                                                                 "xls": f"{type(e).__name__}: {sem_query(e)}"}}
        _gravar_config_hikvision(config_hik, pasta_nvr)
        status = "OK" if config_hik.get("bin") and config_hik.get("xls") else "PARCIAL"
        motivo = backup_hikvision.descrever_falhas(config_hik, cameras_status, telemetria)

    if status != "OK" or motivo:
        nivel = logging.WARNING if status != "OK" else logging.INFO
        logging.log(nivel, f"  {nome} {status}: {motivo or 'sem detalhe'}", extra={"enviar_servidor": True})

    # A imagem da noite não é mais capturada no backup (atrasava backups manuais e agendados):
    # ela é capturada sob demanda pela Galeria do NVR no painel (tarefa RTSP modo "noite").

    # Planilha com a configuracao lida do equipamento (qualquer marca); falha nunca muda o status do backup
    planilha = None
    gerar_planilha = PLANILHAS_NVR.get(tipo_nvr)
    if gerar_planilha is not None:
        arq_planilha = pasta_nvr / f"PLANILHA_{nome_seguro(nome)}.xlsx"
        if gerar_planilha(ip, user, pwd, arq_planilha):
            planilha = arq_planilha  # o run_backup move para NVR/PLANILHA/ do pacote final

    resultado = {"nome": nome, "status": status, "cameras": cameras_status, "telemetria": telemetria}
    if motivo:
        resultado["motivo"] = motivo
    if planilha is not None:
        resultado["_planilha"] = planilha  # caminho local; o run_backup remove antes de reportar ao servidor
    return resultado


def _gravar_config_hikvision(config_hik: dict, pasta_nvr: Path) -> None:
    """Grava no disco o que veio da configuração Hikvision (`.bin` e `.xls`), com o mesmo nome de antes."""
    for chave, nome_arq in (("bin", f"CONFIG_NVR_{data_hoje()}.bin"), ("xls", f"CONFIG_IPCAM_{data_hoje()}.xls")):
        dados = config_hik.get(chave)
        if dados:
            destino = pasta_nvr / nome_arq
            destino.write_bytes(dados)
            logging.info(f"  Salvo: {destino.name} ({len(dados)/1024:.1f} KB) SHA-256: {hashlib.sha256(dados).hexdigest()[:16]}...")


def processar_olt(
    equipamento: dict,
    pasta_data: Path,
    conf: dict = None,
    trigger: str = "scheduled",
    somente_preparar: bool = False,
) -> dict:
    """`somente_preparar` (agente do Mikrotik, nada em disco): UNM2000/Digifort por pasta de rede ou SFTP, VSOL em
    memória e Huawei por SSH (config em texto); devolve status "PRONTO" com `arquivos_origem` para o túnel ler."""

    tipo = (equipamento.get("tipo") or "").lower()

    config_extra = parse_config_extra(equipamento)

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

    if somente_preparar:
        # Túnel do Mikrotik: nada em disco. VSOL (HTTP) em memória; Huawei por SSH, config em texto; UNM2000/Digifort
        # seguem abaixo (pasta de rede/SFTP, só lida em fluxo).
        if fabricante == "vsol":
            from src.backup.tunel_preparo import preparar_vsol
            return preparar_vsol(equipamento)
        if fabricante == "huawei":
            from src.backup.tunel_preparo import preparar_huawei
            return preparar_huawei(equipamento)
        if fabricante not in ("unm", "unm2000"):
            logging.warning(f"  [OLT] Fabricante '{fabricante}' não tem backup no túnel do Mikrotik.")
            return {"nome": equipamento.get("name", "OLT"), "status": "TIPO_NAO_SUPORTADO", "cameras": None}

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
            pasta_data,
            conf,
            trigger,
            somente_preparar=somente_preparar,
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


def processar_hikcentral(equipamento: dict, pasta_data: Path, conf: dict = None, trigger: str = "scheduled",
                         somente_preparar: bool = False) -> dict:
    """HikCentral (VSM): copia a pasta de backup mais recente (VSM_V<versão>_BACKUP_<data>_<n>) de `pasta_origem`,
    local, SMB ou SFTP, como o UNM2000 e o Digifort. `somente_preparar`: túnel do Mikrotik (nada em disco)."""
    from src.backup.file_manager.manager import FileManager
    check_hash = parse_config_extra(equipamento).get("validar_hash", True)
    if isinstance(check_hash, str):
        check_hash = check_hash.lower() == "true"
    return FileManager(check_hash=check_hash).process_equipment(
        equipamento, pasta_data, "HIKCENTRAL", conf, somente_preparar=somente_preparar)


def processar_pabx(equipamento: dict, pasta_data: Path) -> dict:
    pasta_data.mkdir(parents=True, exist_ok=True)
    return realizar_backup_issabel(equipamento, pasta_data)


def processar_mikrotik(equipamento: dict, pasta_data: Path) -> dict:
    pasta_data.mkdir(parents=True, exist_ok=True)
    return realizar_backup_mikrotik(equipamento, pasta_data)


def processar_defense(equipamento: dict, pasta_data: Path, conf: dict = None) -> dict:
    pasta_data.mkdir(parents=True, exist_ok=True)
    return realizar_backup_defense(equipamento, pasta_data, conf)


# Um equipamento que não responde (socket, FTP, ffmpeg...) sem limite de tempo prendia o backup da máquina inteira
# por dias, e com ele o reinício pelo painel e a atualização. Passado o limite, ele vira ERRO e o backup segue.
LIMITE_EQUIPAMENTO_S = 2 * 3600


def _executar_com_limite(func, limite_s: float, *args, **kwargs):
    """Roda func em thread e espera até `limite_s`. Levanta TimeoutError se passou (a thread fica órfã, em
    segundo plano: não há como matar uma thread, mas o backup não depende mais dela)."""
    import threading

    saida = {}
    # O nome do equipamento do log remoto é por thread: repassa o de quem chamou para a thread nova
    equipamento = log_remoto._obter_equipamento_contexto()

    def _alvo():
        try:
            with log_remoto.equipamento_atual(equipamento):
                saida["valor"] = func(*args, **kwargs)
        except BaseException as e:  # repassa qualquer erro para quem chamou
            saida["erro"] = e

    thread = threading.Thread(target=_alvo, daemon=True)
    thread.start()
    thread.join(limite_s)
    if thread.is_alive():
        raise TimeoutError(f"sem resposta em {int(limite_s // 60)} min")
    if "erro" in saida:
        raise saida["erro"]
    return saida.get("valor")


def processar_equipamento(equipamento: dict, zip_password: str, pasta_data: Path, conf: dict = None, trigger: str = "scheduled") -> dict:
    """
    Despachante principal — roteia o processamento pelo tipo do equipamento.
    Tipos suportados: NVR, OLT, PABX
    Tipos futuros:    ONU, PABX (retornam status TIPO_NAO_SUPORTADO)
    """
    tipo = (equipamento.get("tipo") or "NVR").upper()

    if tipo == "NVR":
        return processar_nvr(equipamento, zip_password, pasta_data, conf)

    if tipo == "OLT" or tipo == "DIGIFORT":
        return processar_olt(equipamento, pasta_data, conf, trigger)

    if tipo == "HIKCENTRAL":
        return processar_hikcentral(equipamento, pasta_data, conf, trigger)

    if tipo == "PABX":
        return processar_pabx(equipamento, pasta_data)

    if tipo == "MIKROTIK":
        return processar_mikrotik(equipamento, pasta_data)

    if tipo == "DEFENSE":
        return processar_defense(equipamento, pasta_data, conf)

    # Tipos cadastrados mas ainda não implementados
    logging.warning(f"  Tipo '{tipo}' ainda não suportado pelo agente. Equipamento: {equipamento.get('name')}")
    return {"nome": equipamento.get("name", "?"), "status": "TIPO_NAO_SUPORTADO", "cameras": None}


def _guardar_planilha(origem: Path, pasta_final: Path, cliente: str, maquina: str, nvr_nome: str, planilhas: dict) -> Path:
    """Move a planilha do NVR para NVR/PLANILHA/<cliente>_<maquina>_<data>.xlsx do pacote final.
    Com mais de um NVR Motorola na maquina, o nome do NVR entra no nome de todas as planilhas."""
    pasta = pasta_final / "NVR" / "PLANILHA"
    pasta.mkdir(parents=True, exist_ok=True)

    def nome_arquivo(nvr: str = "") -> str:
        partes = [nome_seguro(p) for p in (cliente, maquina, nvr) if p]
        return "_".join(partes + [data_hoje()]) + ".xlsx"

    if not planilhas:
        destino = pasta / nome_arquivo()
    else:
        for anterior, caminho in list(planilhas.items()):
            novo = pasta / nome_arquivo(anterior)
            if caminho != novo:
                caminho.replace(novo)
                planilhas[anterior] = novo
        destino = pasta / nome_arquivo(nvr_nome)
    shutil.move(str(origem), str(destino))
    planilhas[nvr_nome] = destino
    return destino


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
    customer_name = server_cfg.get("customer_name")  # None em servidor antigo: o nome do arquivo fica sem o cliente

    if not equipamentos:
        logging.error("Nenhum equipamento configurado no servidor para este cliente.")
        return

    # Ignora as câmeras (elas não fazem parte do backup principal automático) e as antenas (só monitoramento pelo MikroTik)
    equipamentos = [eq for eq in equipamentos if str(eq.get("tipo")).upper() not in ("CAMERA", "ANTENA")]

    # Resumo por tipo
    por_tipo: dict = {}
    for eq in equipamentos:
        t = (eq.get("tipo") or "NVR").upper()
        por_tipo[t] = por_tipo.get(t, 0) + 1

    logging.info(f"Cliente      : {client_name}")
    logging.info(f"Equipamentos : {len(equipamentos)} total — " + ", ".join(f"{v} {k}" for k, v in por_tipo.items()))

    TEMP_DIR_WORK = DIR_AGENT / "tmp_backup_work"
    TEMP_DIR_FINAL = DIR_AGENT / "tmp_backup_final"

    for d in (TEMP_DIR_WORK, TEMP_DIR_FINAL):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            if d.exists():
                for item in d.iterdir():
                    try:
                        if item.is_dir():
                            shutil.rmtree(item, ignore_errors=True)
                        else:
                            item.unlink(missing_ok=True)
                    except Exception:
                        pass
        d.mkdir(parents=True, exist_ok=True)

    started_at = datetime.utcnow()
    resultados = []
    planilhas = {}  # nome do NVR -> planilha ja colocada em NVR/PLANILHA/

    for eq in equipamentos:
        tipo = (eq.get("tipo") or "NVR").upper()
        nome = eq.get("name", "equipamento")
        nome_safe = nome_seguro(nome)

        try:
            # Diretório temporário de trabalho
            pasta_trabalho = TEMP_DIR_WORK / f"{tipo}_{nome_safe}"
            pasta_trabalho.mkdir(parents=True, exist_ok=True)

            with log_remoto.equipamento_atual(nome):
                res = _executar_com_limite(processar_equipamento, LIMITE_EQUIPAMENTO_S,
                                           eq, zip_password, pasta_trabalho, conf, trigger)
            res["tipo"] = tipo
            planilha = res.pop("_planilha", None)

            if planilha is not None:
                try:
                    destino = _guardar_planilha(planilha, TEMP_DIR_FINAL, customer_name, client_name, nome, planilhas)
                    logging.info(f"  Planilha do NVR salva em NVR/PLANILHA/{destino.name}")
                except Exception:
                    logging.warning(f"  Nao foi possivel guardar a planilha do NVR {nome}.", exc_info=True)

            # Monta a estrutura final
            pasta_final_eq = TEMP_DIR_FINAL / tipo / f"backup_{tipo.lower()}_{nome_safe}"
            pasta_final_eq.mkdir(parents=True, exist_ok=True)

            # Cria o ZIP interno sem senha
            zip_interno_path = pasta_final_eq / "backup.zip"
            if any(pasta_trabalho.iterdir()):
                criar_zip(pasta_trabalho, zip_interno_path, senha=None)
        except Exception:
            logging.error(f"  Falha inesperada no backup do equipamento {nome}. Seguindo para o proximo.",
                          exc_info=True, extra={"equipamento": nome})
            res = {"nome": nome, "status": "ERRO", "cameras": None, "tipo": tipo}
        resultados.append(res)

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
        msg_resumo = f"  {icone} [{r.get('tipo', 'NVR')}] {r['nome']}"
        if r["status"] in ("OK", "JA_PROCESSADO"):
            logging.info(msg_resumo, extra={"enviar_servidor": True, "equipamento": r["nome"]})
        else:
            logging.warning(msg_resumo, extra={"equipamento": r["nome"]})

    backup_id = post_report(conf, started_at, finished_at, resultados, trigger)
    if backup_id:
        todos_arquivos = [f for f in TEMP_DIR_FINAL.rglob("*") if f.is_file()]
        if todos_arquivos:
            # Nome do ZIP da máquina: backup_<Nome_Da_Maquina>_<Data>.zip (protegido pela senha da máquina)
            nome_zip_global = f"backup_{nome_seguro(client_name)}_{data_hoje()}.zip"

            zip_global_path = criar_zip(TEMP_DIR_FINAL, nome_zip_global, zip_password)
            if zip_global_path:
                logging.info(f"  Enviando pacote de backup global: {zip_global_path.name}")
                upload_zip(conf, backup_id, zip_global_path, device_type="MIXED")

    shutil.rmtree(TEMP_DIR_WORK, ignore_errors=True)
    shutil.rmtree(TEMP_DIR_FINAL, ignore_errors=True)
    logging.info(f"\nBackup concluido em {(finished_at - started_at).total_seconds():.1f}s", extra={"enviar_servidor": True})
