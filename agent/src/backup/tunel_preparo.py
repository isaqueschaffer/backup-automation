"""
Preparação do backup de cada tipo de equipamento para o TÚNEL do Mikrotik: nada é gravado no roteador. O resultado
de cada função é o mesmo dict que o agente Windows devolve (nome, status, cameras, telemetria...) mais:
  - status "PRONTO" + `arquivos_origem` = [(BackupFile, nome_no_zip)] (BackupFile com origem sftp/memória/http),
    ou um status final (ERRO, SEM_ARQUIVOS, PARCIAL...) quando não há o que enviar;
  - `status_final`: status a gravar quando o envio der certo (ex.: "PARCIAL"; padrão "OK");
  - `_planilha`: bytes do .xlsx do NVR (vai ao ZIP global em NVR/PLANILHA/, fora do backup.zip);
  - `_limpeza`: funções a rodar no fim do envio (ex.: apagar os arquivos temporários do roteador-alvo).
Arquivos pequenos (configs) ficam inteiros em memória até LIMITE_MEMORIA; acima disso é ERRO com mensagem clara.
"""
import io
import logging
import re
from pathlib import Path
from typing import Optional

from src.backup.downloader import LIMITE_MEMORIA, LimiteMemoriaExcedido
from src.core.config import parse_config_extra

EXTS_BACKUP_DEFENSE = {".enc", ".zip", ".dbk", ".bak"}


def _data_arquivo() -> str:
    from src.backup.archiver import data_hoje
    return data_hoje()


def _memoria(nome_arquivo: str, dados: bytes, tipo: str):
    from src.backup.file_manager.models import BackupFile
    return BackupFile(path=Path(nome_arquivo), file_type=tipo, dados=dados), nome_arquivo


# ─── NVR ─────────────────────────────────────────────────────────────────────

def preparar_nvr(eq: dict, senha_zip: Optional[str]) -> dict:
    """Mesmo fluxo do agente Windows (`processar_nvr`), em memória: status das câmeras, telemetria, config
    (Intelbras CGI / Hikvision ISAPI .bin + .xls; Motorola = SEM_ARQUIVOS) e planilha .xlsx."""
    import requests
    from requests.auth import HTTPDigestAuth
    from src.application.backup_job import PLANILHAS_NVR
    from src.backup.crypto import gerar_secretkey
    from src.backup.downloader import baixar_bytes
    from src.nvr.factory import coletar_telemetria_nvr, verificar_gravacao_nvr
    from src.nvr.intelbras.backup import baixar_configuracao_intelbras_memoria

    nome = eq.get("name", "NVR")
    ip, user, pwd = eq.get("ip", ""), eq.get("username", "admin"), eq.get("password", "")
    config_extra = parse_config_extra(eq)
    marca = config_extra.get("marca")
    if not ip:
        logging.error(f"  [NVR] {nome}: IP não informado.")
        return {"nome": nome, "status": "ERRO", "cameras": None}
    logging.info(f"\n{'='*50}\n{nome} [NVR / túnel] (IP: {ip})\n{'='*50}")

    retorno = verificar_gravacao_nvr(ip, user, pwd, marca)
    if isinstance(retorno, tuple) and len(retorno) == 2:
        cameras_status, tipo_nvr = retorno
    else:
        cameras_status, tipo_nvr = retorno, "DESCONHECIDO"
    if not cameras_status and tipo_nvr == "DESCONHECIDO":
        logging.error("  NVR INACESSIVEL ou falha no login.")
        return {"nome": nome, "status": "ERRO"}
    if not cameras_status:
        logging.warning("  Nenhuma câmera encontrada no NVR. Prosseguindo com backup de configurações.")
    logging.info(f"  NVR acessivel (Detectado: {tipo_nvr}).")
    telemetria = coletar_telemetria_nvr(ip, user, pwd, tipo_nvr, marca, config_extra.get("snmp_community"))

    arquivos = []
    status = "OK"
    try:
        if tipo_nvr == "MOTOROLA":
            logging.info("  NVR Motorola detectado. Backup restauravel da configuracao nao suportado nativamente. "
                         "Gravacoes verificadas.")
            status = "SEM_ARQUIVOS"
        elif tipo_nvr == "INTELBRAS" or (marca and marca.upper() == "INTELBRAS"):
            logging.info("  NVR Intelbras detectado. Baixando configuracao completa via CGI (em memória)...")
            dados = baixar_configuracao_intelbras_memoria(ip, user, pwd, limite=LIMITE_MEMORIA)
            if dados is not None:
                arquivos.append(_memoria(f"CONFIG_INTELBRAS_{_data_arquivo()}.backup", dados, "NVR_CONFIG"))
            else:
                status = "PARCIAL"
        else:
            try:
                sessao = requests.Session()
                sessao.auth = HTTPDigestAuth(user, pwd)
                sessao.verify = False
                sessao.get(f"http://{ip}/ISAPI/System/status", timeout=5).raise_for_status()
                sk, iv = gerar_secretkey(senha_zip)
                url_bin = f"http://{ip}/ISAPI/System/configurationData?secretkey={sk}&security=1&iv={iv}"
                dados = baixar_bytes(sessao, url_bin, min_bytes=100_000, valida_xml=True)
                if dados is not None:
                    logging.info("  Backup NVR OK.")
                    arquivos.append(_memoria(f"CONFIG_NVR_{_data_arquivo()}.bin", dados, "NVR_CONFIG"))
                url_xls = f"http://{ip}/ISAPI/ContentMgmt/InputProxy/ipcConfig"
                dados = baixar_bytes(sessao, url_xls)
                if dados is not None:
                    logging.info("  Backup IPCAM OK.")
                    arquivos.append(_memoria(f"CONFIG_IPCAM_{_data_arquivo()}.xls", dados, "NVR_CONFIG"))
                status = "OK" if len(arquivos) == 2 else "PARCIAL"
            except LimiteMemoriaExcedido:
                raise
            except Exception:
                logging.warning("  API ISAPI falhou. Backup de arquivos pulado.", exc_info=True)
                status = "PARCIAL"
    except LimiteMemoriaExcedido as e:
        logging.error(f"  [NVR] {nome}: {e}")
        return {"nome": nome, "status": "ERRO", "cameras": cameras_status, "telemetria": telemetria}

    res = {"nome": nome, "cameras": cameras_status, "telemetria": telemetria}
    if arquivos:
        res["status"] = "PRONTO"
        res["status_final"] = status
        res["arquivos_origem"] = arquivos
    else:
        res["status"] = status

    # Planilha com a configuracao lida do equipamento; falha nunca muda o status do backup
    gerar = PLANILHAS_NVR.get(tipo_nvr)
    if gerar is not None:
        buf = io.BytesIO()
        try:
            if gerar(ip, user, pwd, buf):
                res["_planilha"] = buf.getvalue()
        except Exception:
            logging.warning(f"  Nao foi possivel gerar a planilha do NVR {nome}.", exc_info=True)
    return res


# ─── DEFENSE ─────────────────────────────────────────────────────────────────

def preparar_defense(eq: dict) -> dict:
    """Backup do Defense no túnel + status das câmeras (online e gravações pela API do Defense, como no Windows).
    Sem as câmeras no relatório a Galeria e a Gravação do equipamento ficavam vazias no painel, embora o teste
    de conexão listasse as câmeras. O status vai em qualquer desfecho do arquivo de backup."""
    res = _preparar_arquivo_defense(eq)
    try:
        from src.vms.defense import _montar_status_cameras_defense
        res["cameras"] = _montar_status_cameras_defense(eq)
        if res["cameras"]:
            logging.info(f"  [DEFENSE] {eq.get('name', 'Defense')}: {len(res['cameras'])} câmera(s) no relatório.")
    except Exception:
        logging.warning(f"  [DEFENSE] {eq.get('name', 'Defense')}: falha ao obter o status das câmeras.", exc_info=True)
    return res


def _preparar_arquivo_defense(eq: dict) -> dict:
    """Arquivo de backup mais recente (.enc/.zip/.dbk/.bak) da `pasta_origem`, por SFTP (`acesso_remoto=sftp`) ou
    por SMB provisionado por SSH (cadastros antigos). Sem `pasta_origem`: ERRO (não há dump do banco no Mikrotik)."""
    from src.backup.file_manager.models import BackupFile
    from src.backup.sftp_origem import ErroSftp, PastaSftp, conexao_do_cadastro, usa_sftp

    nome = eq.get("name", "Defense")
    config_extra = parse_config_extra(eq)
    pasta_origem = config_extra.get("pasta_origem", "")
    erro = {"nome": nome, "status": "ERRO", "cameras": None}
    if not pasta_origem:
        logging.error(f"  [DEFENSE] {nome}: configure a pasta de backup do Defense (pasta_origem). "
                      f"O backup por dump do banco não existe no agente do Mikrotik.")
        return erro

    if usa_sftp(config_extra):
        con, msg = conexao_do_cadastro(eq, config_extra)
        if con is None:
            logging.error(f"  [DEFENSE] {nome}: {msg}")
            return erro
        try:
            pasta = PastaSftp(con, pasta_origem)
            arquivos = [e for e in pasta.listar() if not e.is_dir and Path(e.name).suffix.lower() in EXTS_BACKUP_DEFENSE]
        except ErroSftp as e:
            logging.error(f"  [DEFENSE] {nome}: {e}")
            return erro
        if not arquivos:
            logging.warning(f"  [DEFENSE] {nome}: nenhum arquivo de backup em {pasta.raiz}")
            return {"nome": nome, "status": "SEM_ARQUIVOS", "cameras": None}
        mais_recente = max(arquivos, key=lambda e: e.mtime)
        bf = BackupFile(path=Path(mais_recente.name), file_type="DEFENSE_BACKUP", remote_path=mais_recente.path,
                        is_sftp=True, sftp=pasta, _size=mais_recente.size)
        logging.info(f"  [DEFENSE] {nome}: arquivo encontrado por SFTP — {mais_recente.name}")
        return {"nome": nome, "status": "PRONTO", "arquivos_origem": [(bf, mais_recente.name)], "cameras": None}

    # SMB provisionado por SSH (comportamento da 1.1.60, mantido para cadastros que já funcionam)
    from src.backup.smb_ssh_provisioner import alvo_por_ssh, usa_provisionamento_ssh
    from src.backup.tunel import _smbclient
    host = config_extra.get("smb_host") or eq.get("ip", "")
    if not usa_provisionamento_ssh(config_extra):
        logging.error(f"  [DEFENSE] {nome}: acesso remoto não configurado (SFTP ou SMB por SSH) para o túnel do Mikrotik.")
        return erro
    alvo, msg = alvo_por_ssh(pasta_origem, host, config_extra)
    if not alvo:
        logging.warning(f"  [DEFENSE] {nome}: falha ao obter acesso SMB: {msg}")
        return erro
    try:
        smb = _smbclient()
        smb.register_session(server=alvo.host, username=alvo.username, password=alvo.password, port=alvo.port)
        arquivos = [e for e in smb.scandir(alvo.unc_path)
                    if not e.is_dir() and Path(e.name).suffix.lower() in EXTS_BACKUP_DEFENSE]
        if not arquivos:
            logging.warning(f"  [DEFENSE] {nome}: nenhum arquivo de backup em {alvo.unc_path}")
            return {"nome": nome, "status": "SEM_ARQUIVOS", "cameras": None}
        mais_recente = max(arquivos, key=lambda e: e.stat().st_mtime)
        unc = alvo.unc_path.rstrip("\\") + "\\" + mais_recente.name
        bf = BackupFile(path=Path(unc), file_type="DEFENSE_BACKUP", remote_path=unc, is_smb=True)
        logging.info(f"  [DEFENSE] {nome}: arquivo encontrado — {mais_recente.name}")
        return {"nome": nome, "status": "PRONTO", "arquivos_origem": [(bf, mais_recente.name)], "cameras": None}
    except Exception as e:
        logging.error(f"  [DEFENSE] {nome}: falha ao acessar backup via SMB: {e}", exc_info=True)
        return erro


# ─── PABX / OLT VSOL / OLT Huawei / MIKROTIK ────────────────────────────────

def preparar_pabx(eq: dict) -> dict:
    from src.pabx.issabel import preparar_backup_issabel_tunel
    return preparar_backup_issabel_tunel(eq, LIMITE_MEMORIA)


def preparar_vsol(eq: dict) -> dict:
    from src.olt.vsol import realizar_backup_vsol
    res = realizar_backup_vsol(eq, Path("."), em_memoria=True)
    dados = res.pop("_dados", None)
    if res.get("status") == "OK" and dados:
        nome_arq, conteudo = dados[0]
        if len(conteudo) > LIMITE_MEMORIA:
            logging.error(f"  [VSOL] configuração com {len(conteudo) // (1024 * 1024)} MB passa do limite de memória.")
            return {"nome": res["nome"], "status": "ERRO", "cameras": None}
        res["status"] = "PRONTO"
        res["arquivos_origem"] = [_memoria(nome_arq, conteudo, "OLT_VSOL")]
    return res


def preparar_huawei(eq: dict) -> dict:
    from src.olt.huawei_texto import preparar_backup_huawei_texto
    return preparar_backup_huawei_texto(eq, LIMITE_MEMORIA)


def preparar_mikrotik(eq: dict) -> dict:
    from src.mikrotik.routeros import preparar_backup_mikrotik_tunel
    return preparar_backup_mikrotik_tunel(eq)


# ─── planilhas do NVR (ZIP global, fora do backup.zip) ───────────────────────

def nomear_planilhas(planilhas: dict, cliente: Optional[str], maquina: str) -> list:
    """Mesmos nomes do agente Windows (`_guardar_planilha`): NVR/PLANILHA/<cliente>_<maquina>_<data>.xlsx; com mais de
    uma planilha, o nome do NVR entra no nome de todas. Devolve [(caminho_no_zip, bytes)]."""
    def seguro(p):
        return re.sub(r"[^\w.-]", "_", p or "")

    def nome(nvr=""):
        partes = [seguro(p) for p in (cliente, maquina, nvr) if p]
        return "_".join(partes + [_data_arquivo()]) + ".xlsx"

    return [(f"NVR/PLANILHA/{nome(nvr if len(planilhas) > 1 else '')}", dados) for nvr, dados in planilhas.items()]
