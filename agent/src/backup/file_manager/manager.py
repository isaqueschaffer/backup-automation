import os
import logging
from pathlib import Path
from typing import Dict, Any

from src.backup.file_manager.models import BackupStatus, BackupGroup
from src.backup.file_manager.utils import get_agent_date, sanitize_name
from src.backup.file_manager.parsers import BaseParser, UNM2000Parser, HuaweiParser
from src.backup.file_manager.validators import Validator
from src.backup.file_manager.copier import SafeCopier

class FileManager:
    def __init__(self, check_hash: bool = True):
        self.copier = SafeCopier(check_hash=check_hash)

    def process_equipment(self, equipamento: dict, pasta_destino: Path, tipo_parser: str) -> Dict[str, Any]:
        """
        Orquestra o backup de um equipamento lendo da pasta de origem.
        """
        nome_original = equipamento.get("name", "Equipamento_Desconhecido")
        nome_safe = sanitize_name(nome_original)
        
        config_extra = equipamento.get("config_extra", {})
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

        status_cameras = None
        if equipamento.get("tipo", "").upper() == "DIGIFORT":
            logging.info("  [DIGIFORT] Buscando status de gravacoes e CSV do Agente Webhook...")
            try:
                import requests
                # Puxa status
                resp_status = requests.get("http://localhost:8080/status", timeout=5)
                if resp_status.status_code == 200:
                    status_dict = resp_status.json()
                    status_cameras = []
                    for nome_cam, st in status_dict.items():
                        is_ok = (st == "OK")
                        status_cameras.append({
                            "canal": "N/A",
                            "nome": nome_cam,
                            "ip": "N/A",
                            "online": is_ok,
                            "status_comunicacao": "ONLINE" if is_ok else "OFFLINE",
                            "status_gravacao": "COM_GRAVACAO" if is_ok else "SEM_GRAVACAO",
                            "total_dias": 1,
                            "mapa": "█" if is_ok else "░"
                        })
                    logging.info("  [DIGIFORT] Status das cameras obtido com sucesso.")
                
                # Puxa CSV
                resp_csv = requests.get("http://localhost:8080/csv", timeout=5)
                if resp_csv.status_code == 200:
                    caminho_csv = pasta_eq / "quedas_cameras.csv"
                    with open(caminho_csv, 'wb') as f:
                        f.write(resp_csv.content)
                    arquivos_copiados.append("quedas_cameras.csv")
                    logging.info("  [DIGIFORT] CSV adicionado ao backup.")
            except Exception as e:
                logging.warning(f"  [DIGIFORT] Falha ao comunicar com o agente webhook: {e}")

        logging.info(f"  Backup processado com sucesso. Arquivos: {', '.join(arquivos_copiados)}")

        return {
            "nome": nome_original,
            "status": BackupStatus.OK.value,
            "arquivos": arquivos_copiados,
            "destino": str(pasta_eq),
            "tamanho_mb": grupo_recente.total_size_mb,
            "cameras": status_cameras
        }

    def _get_parser(self, tipo_parser: str) -> BaseParser:
        if tipo_parser.upper() == "UNM2000":
            return UNM2000Parser()
        elif tipo_parser.upper() == "HUAWEI":
            return HuaweiParser()
        return None
