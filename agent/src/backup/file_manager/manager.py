import os
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Any

from src.backup.file_manager.models import BackupStatus, BackupGroup
from src.backup.file_manager.utils import get_agent_date, sanitize_name
from src.backup.file_manager.parsers import BaseParser, UNM2000Parser, HuaweiParser
from src.backup.file_manager.validators import Validator
from src.backup.file_manager.copier import SafeCopier
from src.core.config import parse_config_extra

def _gerar_mapa_vms(is_ok: bool) -> tuple:
    """Retorna (total_dias, mapa_15, dias_com_gravacao) para equipamentos VMS (Digifort/Defense)."""
    hoje = datetime.now().date()
    dias_15 = [(hoje - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(15)]
    if is_ok:
        return 15, "█" * 15, dias_15
    return 0, "░" * 15, []

def _resumos_gravacao_digifort(pasta_gravacoes: str):
    """Resumo de gravacao de cada camera lido dos arquivos de indice do Digifort: {nome da pasta: resumo ou None}.
    None (no lugar do dict) = pasta de gravacoes nao configurada: o chamador usa o ping, como antes.
    Configurada mas ilegivel/inexistente devolve {} (as cameras ficam NAO_VERIFICADO, nunca 'gravando' por engano)."""
    if not (pasta_gravacoes or "").strip():
        return None
    try:
        from src.core.config import DIR_AGENT
        from src.vms.digifort_gravacoes import calcular_gravacoes, caminho_cache, resumir_camera
        pasta = pasta_gravacoes.strip()
        hoje, agora = date.today(), datetime.now()
        brutos = calcular_gravacoes(pasta, hoje, cache=caminho_cache(pasta, DIR_AGENT))
        if not brutos:
            logging.warning(f"  [DIGIFORT] Nenhuma pasta de camera (com Dados e Indices) em: {pasta}")
        return {nome: (resumir_camera(por_dia, hoje, agora) if por_dia is not None else None)
                for nome, por_dia in brutos.items()}
    except Exception:
        logging.warning("  [DIGIFORT] Falha ao calcular o tempo de gravacao pelos arquivos.", exc_info=True)
        return {}


def _gravacao_digifort(nome_cam: str, is_ok: bool, resumos, usadas: set) -> tuple:
    """(total_dias, mapa, dias_com_gravacao, status_gravacao, pasta) de uma camera do Digifort.
    `pasta` e o nome da pasta de gravacao usada (None = nenhuma pasta com o nome da camera, ou pasta de gravacoes
    nao configurada: o chamador so informa a pasta no relatorio quando ela esta configurada)."""
    if resumos is None:  # pasta de gravacoes nao configurada: so o ping diz se esta gravando
        total_dias, mapa, dias = _gerar_mapa_vms(is_ok)
        return total_dias, mapa, dias, "COM_GRAVACAO" if is_ok else "SEM_GRAVACAO", None
    from src.vms.digifort_gravacoes import casar_pasta
    pasta = casar_pasta(nome_cam, resumos)
    if pasta:
        usadas.add(pasta)
    resumo = resumos.get(pasta) if pasta else None
    if resumo is None:  # sem pasta para a camera (ou leitura incompleta): nao da para afirmar nada
        return 0, "", [], "NAO_VERIFICADO", pasta
    return resumo["total_dias"], resumo["mapa"], resumo["dias_com_gravacao"], resumo["status_gravacao"], pasta


class FileManager:
    def __init__(self, check_hash: bool = True):
        self.copier = SafeCopier(check_hash=check_hash)

    def process_equipment(self, equipamento: dict, pasta_destino: Path, tipo_parser: str, conf: dict = None) -> Dict[str, Any]:
        """Backup do equipamento a partir da pasta de origem (ver _processar_backup). No Digifort, o status das
        cameras (ping e tempo de gravacao) vai no relatorio em qualquer desfecho do backup, e nao so quando um
        backup novo foi copiado: BACKUP_ANTIGO, JA_PROCESSADO ou NAO_ENCONTRADO nao escondem mais as gravacoes."""
        resultado = self._processar_backup(equipamento, pasta_destino, tipo_parser, conf)
        if (equipamento.get("tipo") or "").upper() == "DIGIFORT" and resultado.get("cameras") is None:
            try:
                pasta_destino.mkdir(parents=True, exist_ok=True)
                # A imagem da noite continua so no backup novo (RTSP em todas as cameras e pesado)
                resultado["cameras"] = self._status_cameras_digifort(
                    equipamento, pasta_destino, conf, [], capturar_imagens=False)
            except Exception:
                logging.warning("  [DIGIFORT] Falha ao obter o status das cameras.", exc_info=True)
        return resultado

    def _processar_backup(self, equipamento: dict, pasta_destino: Path, tipo_parser: str, conf: dict = None) -> Dict[str, Any]:
        """
        Orquestra o backup de um equipamento lendo da pasta de origem.
        """
        nome_original = equipamento.get("name", "Equipamento_Desconhecido")
        nome_safe = sanitize_name(nome_original)

        config_extra = parse_config_extra(equipamento)
        pasta_origem_str = config_extra.get("pasta_origem", "")
        
        logging.info(f"\n{'='*50}\n{nome_original} [{tipo_parser}]\n{'='*50}")

        if not pasta_origem_str:
            logging.error(f"  [{tipo_parser}] config_extra.pasta_origem não informado.")
            return {"nome": nome_original, "status": BackupStatus.ERRO.value, "cameras": None}

        pasta_origem = Path(pasta_origem_str)
        
        # Garante pasta de destino para este equipamento
        pasta_eq = pasta_destino
        pasta_eq.mkdir(parents=True, exist_ok=True)

        parser = self._get_parser(tipo_parser)
        if not parser:
            logging.error(f"  [{tipo_parser}] Parser não suportado.")
            return {"nome": nome_original, "status": BackupStatus.ERRO.value, "cameras": None}

        # 1. Busca Backups (já ordenados do mais recente para o mais antigo)
        grupos = parser.find_backups(pasta_origem)
        
        if not grupos:
            logging.error(f"  [{tipo_parser}] Nenhum backup encontrado em: {pasta_origem}")
            return {"nome": nome_original, "status": BackupStatus.NAO_ENCONTRADO.value, "cameras": None}

        # 2. Avalia o grupo mais recente
        grupo_recente = grupos[0]
        data_agente = get_agent_date()
        is_huawei = isinstance(parser, HuaweiParser)
        
        logging.info(f"  Data esperada: {data_agente.strftime('%d/%m/%Y')}")
        logging.info(f"  Data do backup mais recente: {grupo_recente.date.strftime('%d/%m/%Y')}")

        sucesso_validacao, status_validacao = Validator.validate_group_for_copy(grupo_recente, data_agente, is_huawei)
        
        if not sucesso_validacao:
            logging.warning(f"  Ação: Cópia ignorada. Motivo: {status_validacao.value}")
            return {"nome": nome_original, "status": status_validacao.value, "cameras": None}

        # 3. Verifica duplicidade (já foi copiado?)
        # O nome do arquivo destino deve conter a identificação do equipamento
        prefixo = "OLT_" + ("HUAWEI_" if is_huawei else "UNM2000_")
        arquivos_para_copiar = []
        ja_processado = True
        
        for f in grupo_recente.files:
            if is_huawei:
                # OLT_HUAWEI_<NOME>_<DATA>_CONFIGURATION.txt
                nome_destino = f"{prefixo}{nome_safe}_{grupo_recente.date.strftime('%Y%m%d_%H%M%S')}_{f.file_type}{f.path.suffix}"
            elif f.file_type == "DIGIFORT_DIR":
                nome_destino = f.path.name
            else:
                ext = f.path.suffix if f.path.is_file() else ""
                nome_destino = f"{prefixo}{nome_safe}_{grupo_recente.date.strftime('%Y%m%d_%H%M%S')}{ext}"
                
            caminho_destino = pasta_eq / nome_destino
            arquivos_para_copiar.append((f.path, caminho_destino))
            
            if not caminho_destino.exists():
                ja_processado = False

        if ja_processado:
            logging.info(f"  Backup de {grupo_recente.date.strftime('%d/%m/%Y')} já existe e foi validado.")
            return {"nome": nome_original, "status": BackupStatus.JA_PROCESSADO.value, "cameras": None}

        # 4. Verifica Estabilidade (está sendo escrito?)
        if not Validator.is_stable(grupo_recente):
            logging.warning(f"  Ação: Cópia ignorada. Motivo: {BackupStatus.EM_PROCESSAMENTO.value}")
            return {"nome": nome_original, "status": BackupStatus.EM_PROCESSAMENTO.value, "cameras": None}

        # 5. Cópia Segura
        logging.info(f"  Iniciando cópia segura ({grupo_recente.total_size_mb:.2f} MB total)")
        
        arquivos_copiados = []
        for origem, destino in arquivos_para_copiar:
            sucesso_copia, status_copia = self.copier.copy_file(origem, destino)
            if not sucesso_copia:
                logging.error(f"  Falha ao copiar: {origem.name}")
                return {"nome": nome_original, "status": status_copia.value, "cameras": None}
            arquivos_copiados.append(destino.name)

        # O DEFENSE não passa por aqui (src/vms/defense.py): só o Digifort monta o status das câmeras
        status_cameras = None
        if (equipamento.get("tipo") or "").upper() == "DIGIFORT":
            status_cameras = self._status_cameras_digifort(equipamento, pasta_eq, conf, arquivos_copiados)

        logging.info(f"  Backup processado com sucesso. Arquivos: {', '.join(arquivos_copiados)}")

        return {
            "nome": nome_original,
            "status": BackupStatus.OK.value,
            "arquivos": arquivos_copiados,
            "destino": str(pasta_eq),
            "tamanho_mb": grupo_recente.total_size_mb,
            "cameras": status_cameras
        }

    def _status_cameras_digifort(self, equipamento: dict, pasta_eq: Path, conf: dict, arquivos_copiados: list,
                                 capturar_imagens: bool = True):
        """Status das cameras do Digifort: ping, tempo de gravacao (arquivos de indice) e, se `capturar_imagens`,
        imagem da noite via RTSP. Independe do backup da configuracao ter sido copiado agora: o chamador roda isto
        tambem quando o backup e antigo, ja foi processado ou nao foi encontrado. Retorna a lista ou None se falhou."""
        nome_original = equipamento.get("name", "Equipamento_Desconhecido")
        status_cameras = None
        logging.info("  [DIGIFORT] Buscando status de gravacoes e CSV localmente...")
        try:
            from src.application.webhook_digifort import get_detalhes_cameras, get_status_cameras, get_caminho_csv, ping_camera

            cfg_ext = parse_config_extra(equipamento)
            caminho_export = cfg_ext.get("caminho_csv", "")
            caminho_log = cfg_ext.get("caminho_log_csv", "")

            # Câmeras detectadas localmente (export_cameras.csv): canal 1..N, nome, ip, status.
            # Câmeras configuradas na Galeria do servidor: ip/usuário/senha/modelo por nome.
            status_dict = get_status_cameras(caminho_export, caminho_log)
            detalhes_locais = get_detalhes_cameras(caminho_export, caminho_log, status_dict=status_dict)
            cameras_servidor = equipamento.get("cameras_config") or []
            por_nome_servidor = {(c.get("nome") or "").strip().lower(): c for c in cameras_servidor}
            por_ip_servidor = {}
            for c in cameras_servidor:
                ip_srv = (c.get("ip") or "").strip()
                if ip_srv:
                    por_ip_servidor.setdefault(ip_srv, []).append(c)

            resumos_gravacao = _resumos_gravacao_digifort(cfg_ext.get("pasta_gravacoes", ""))
            pastas_usadas = set()

            status_cameras = []
            cameras_para_captura = []
            for det in detalhes_locais:
                canal = det["canal"]
                nome_cam = det["nome"]
                ip_local = (det.get("ip") or "").strip()
                cam_srv = por_nome_servidor.get((nome_cam or "").strip().lower())
                if not cam_srv and ip_local:
                    cams_ip = por_ip_servidor.get(ip_local) or []
                    if len(cams_ip) == 1:
                        cam_srv = cams_ip[0]
                ip_cam = ip_local or (cam_srv.get("ip") if cam_srv else "") or "N/A"
                is_ok = det["status"] == "OK"
                total_dias, mapa_str, dias_gravados, status_grav, pasta_grav = _gravacao_digifort(
                    nome_cam, is_ok, resumos_gravacao, pastas_usadas)
                status_cameras.append({
                    "canal": canal,
                    "nome": nome_cam,
                    "ip": ip_cam,
                    "online": is_ok,
                    "status_comunicacao": "ONLINE" if is_ok else "OFFLINE",
                    "status_gravacao": status_grav,
                    **({"pasta_gravacao": pasta_grav} if resumos_gravacao is not None else {}),
                    "total_dias": total_dias,
                    "mapa": mapa_str,
                    "dias_com_gravacao": dias_gravados,
                })
                if ip_cam and ip_cam != "N/A":
                    # O canal enviado ao servidor é o da Galeria
                    cameras_para_captura.append({
                        "canal": cam_srv["canal"] if cam_srv and cam_srv.get("canal") is not None else canal,
                        "nome": nome_cam,
                        "ip": ip_cam,
                        "username": (cam_srv or {}).get("username") or "admin",
                        "password": (cam_srv or {}).get("password") or "navarro@123",
                        "modelo": (cam_srv or {}).get("modelo") or "Hikvision",
                        "canal_rtsp": (cam_srv or {}).get("canal_rtsp"),
                        "ip_compartilhado": bool((cam_srv or {}).get("ip_compartilhado")),
                    })

            # Câmeras só configuradas no servidor (não detectadas no export local) também entram na captura e no status
            nomes_vistos = {(c.get("nome") or "").strip().lower() for c in cameras_para_captura}
            for cam_srv in cameras_servidor:
                nome_srv = cam_srv.get("nome") or ""
                nome_srv_lower = nome_srv.strip().lower()
                if nome_srv_lower not in nomes_vistos:
                    ip_srv = (cam_srv.get("ip") or "").strip()
                    if ip_srv:
                        cameras_para_captura.append(cam_srv)
                        
                    if nome_srv in status_dict:
                        st_val = status_dict[nome_srv]
                    elif nome_srv_lower in status_dict:
                        st_val = status_dict[nome_srv_lower]
                    elif ip_srv and ip_srv != "N/A":
                        is_ping_ok = ping_camera(ip_srv)
                        st_val = "OK" if is_ping_ok else "FALHA"
                    else:
                        st_val = "FALHA"

                    is_ok = (st_val == "OK")
                    total_dias, mapa_str, dias_gravados, status_grav, pasta_grav = _gravacao_digifort(
                        nome_srv, is_ok, resumos_gravacao, pastas_usadas)
                    status_cameras.append({
                        "canal": cam_srv.get("canal") or (len(status_cameras) + 1),
                        "nome": nome_srv,
                        "ip": ip_srv or "N/A",
                        "online": is_ok,
                        "status_comunicacao": "ONLINE" if is_ok else "OFFLINE",
                        "status_gravacao": status_grav,
                        **({"pasta_gravacao": pasta_grav} if resumos_gravacao is not None else {}),
                        "total_dias": total_dias,
                        "mapa": mapa_str,
                        "dias_com_gravacao": dias_gravados,
                    })

            if resumos_gravacao:
                sem_camera = sorted(set(resumos_gravacao) - pastas_usadas)
                if sem_camera:
                    logging.info(f"  [DIGIFORT] Pastas de gravacao sem camera com o mesmo nome na planilha: {', '.join(sem_camera)}")
                sem_pasta = [c["nome"] for c in status_cameras if c["status_gravacao"] == "NAO_VERIFICADO"]
                if sem_pasta:
                    amostra = ", ".join(str(n) for n in sem_pasta[:10]) + ("..." if len(sem_pasta) > 10 else "")
                    logging.warning(f"  [DIGIFORT] {len(sem_pasta)} camera(s) sem pasta de gravacao correspondente "
                                    f"(NAO_VERIFICADO): {amostra}")
            logging.info("  [DIGIFORT] Status das cameras obtido com sucesso.")

            if capturar_imagens and cameras_para_captura and conf is not None:
                from src.camera.rtsp_client import capturar_imagens_noite_vms
                logging.info(f"  [DIGIFORT] Capturando imagem da noite de {len(cameras_para_captura)} camera(s) via RTSP...")
                capturar_imagens_noite_vms(nome_original, cameras_para_captura, conf)
                por_nome_captura = {(c.get("nome") or "").strip().lower(): c for c in cameras_para_captura}
                for st in status_cameras:
                    cap = por_nome_captura.get((st["nome"] or "").strip().lower())
                    if cap and "imagem_noite" in cap:
                        st["imagem_noite"] = cap["imagem_noite"]

            arquivo_log = get_caminho_csv(caminho_log)
            import os, shutil
            if os.path.isfile(arquivo_log):
                caminho_csv = pasta_eq / "quedas_cameras.csv"
                shutil.copy2(arquivo_log, caminho_csv)
                arquivos_copiados.append("quedas_cameras.csv")
                logging.info("  [DIGIFORT] CSV adicionado ao backup.")
        except Exception as e:
            logging.warning(f"  [DIGIFORT] Falha ao processar status: {e}")
        return status_cameras

    def _get_parser(self, tipo_parser: str) -> BaseParser:
        if tipo_parser.upper() == "UNM2000":
            return UNM2000Parser()
        elif tipo_parser.upper() == "HUAWEI":
            return HuaweiParser()
        return None
