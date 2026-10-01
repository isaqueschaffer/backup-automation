import os
import sys
from pathlib import Path
import logging
from src.olt.huawei_active import realizar_backup_huawei_ativo

logging.basicConfig(level=logging.INFO, format="%(message)s")

def main():
    if len(sys.argv) < 4:
        print("Uso: python scratch_test_huawei.py <IP> <USUARIO> <SENHA>")
        sys.exit(1)
        
    ip = sys.argv[1]
    username = sys.argv[2]
    password = sys.argv[3]
    
    equipamento = {
        "name": "TESTE_HUAWEI",
        "ip": ip,
        "username": username,
        "password": password
    }
    
    pasta_destino = Path("tmp_test_huawei")
    pasta_destino.mkdir(exist_ok=True)
    
    print(f"\n--- INICIANDO TESTE HUAWEI PARA {ip} ---")
    resultado = realizar_backup_huawei_ativo(equipamento, pasta_destino)
    print(f"\n--- RESULTADO FINAL: {resultado} ---")
    
    print("\nArquivos na pasta destino:")
    for f in pasta_destino.iterdir():
        print(f" - {f.name} ({f.stat().st_size} bytes)")

if __name__ == "__main__":
    main()
