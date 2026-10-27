# -*- coding: utf-8 -*-
"""
Módulo OLT — Backup de Arquivos (UNM2000 e Huawei)
Refatorado para utilizar a nova arquitetura baseada em FileManager.
"""

from pathlib import Path
from src.backup.file_manager.manager import FileManager
from src.olt.unm2000_api import exportar_configuracao_unm2000

# ============================================================
# FUNÇÃO PRINCIPAL — chamada pelo backup_job.py
# ============================================================

def realizar_backup_olt(equipamento: dict, pasta_destino: Path, conf: dict = None, trigger: str = "scheduled") -> dict:
    """
    Realiza o backup de uma OLT baseada em arquivos locais (UNM2000 ou Huawei).
    No gatilho manual pede uma exportação nova ao UNM2000 antes de copiar.
    O equipamento deve ter em config_extra:
        pasta_origem: str — caminho de onde exportam os backups

    Retorna dict com status, nome, arquivos processados, etc.
    """
    
    # Determina qual parser usar baseado no fabricante configurado
    config_extra = equipamento.get("config_extra") or {}
    fabricante = (
        equipamento.get("fabricante")
        or config_extra.get("fabricante_olt")
        or config_extra.get("fabricante")
        or ""
    ).lower().strip()
    
    # Fallback
    if not fabricante or fabricante == "olt":
        nome_lower = (equipamento.get("name") or "").lower()
        if "huawei" in nome_lower:
            fabricante = "huawei"
        else:
            fabricante = "unm2000"
            
    tipo_parser = "HUAWEI" if "huawei" in fabricante else "UNM2000"
    
    if (
        trigger == "manual"
        and tipo_parser == "UNM2000"
        and (equipamento.get("tipo") or "").upper() == "OLT"
    ):
        if exportar_configuracao_unm2000(equipamento) is False:
            return {"nome": equipamento.get("name", "UNM2000"), "status": "ERRO", "cameras": None}

    # A verificação de Hash pode ser opcional através de config
    check_hash = config_extra.get("validar_hash", True)
    if isinstance(check_hash, str):
        check_hash = check_hash.lower() == "true"
        
    fm = FileManager(check_hash=check_hash)
    return fm.process_equipment(equipamento, pasta_destino, tipo_parser, conf)
