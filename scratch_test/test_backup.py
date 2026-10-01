import sys
import os
from pathlib import Path
from datetime import datetime

# Ajusta o sys.path para importar os módulos da raiz
agent_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'agent'))
sys.path.insert(0, agent_path)

from src.backup.file_manager.manager import FileManager
from src.backup.file_manager.utils import sanitize_name

# MOCK get_agent_date() no módulo utils
import src.backup.file_manager.validators as val
import src.backup.file_manager.manager as man

def test_unm2000():
    print("--- TESTE UNM2000 ---")
    origem = Path("scratch_test/unm_orig")
    destino = Path("scratch_test/unm_dest")
    origem.mkdir(parents=True, exist_ok=True)
    destino.mkdir(parents=True, exist_ok=True)
    
    # Criar arquivo
    zip_path = origem / "20260918_030154_allback.zip"
    with open(zip_path, "w") as f:
        f.write("dados zip")
        
    equipamento = {"name": "OLT Teste", "config_extra": {"pasta_origem": str(origem), "validar_hash": True}}
    
    fm = FileManager()
    res = fm.process_equipment(equipamento, destino, "UNM2000")
    print("Resultado:", res)

def test_huawei():
    print("\n--- TESTE HUAWEI ---")
    origem = Path("scratch_test/huawei_orig")
    destino = Path("scratch_test/huawei_dest")
    origem.mkdir(parents=True, exist_ok=True)
    destino.mkdir(parents=True, exist_ok=True)
    
    # Criar arquivo CONFIGURATION e DB
    with open(origem / "CONFIGURATION_10.11.104.2-2026-09-18-033011-123.txt", "w") as f:
        f.write("config")
    with open(origem / "DB_10.11.104.2-2026-09-18-033011-456.dat", "w") as f:
        f.write("db")
        
    equipamento = {"name": "OLT Huawei", "fabricante": "huawei", "config_extra": {"pasta_origem": str(origem)}}
    
    fm = FileManager()
    res = fm.process_equipment(equipamento, destino, "HUAWEI")
    print("Resultado:", res)

if __name__ == "__main__":
    test_unm2000()
    test_huawei()
