import sys
import logging
from pathlib import Path
import json

# Configura o logging para exibir no console
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# Adiciona a pasta pai ao PYTHONPATH para conseguir importar os módulos do agente
sys.path.append(str(Path(__file__).resolve().parent))

from src.vms.defense import realizar_backup_defense

def testar():
    print("="*60)
    print("TESTE DE INTEGRAÇÃO - DEFENSE IA")
    print("="*60)

    # Simula os dados que viriam da API
    equipamento_mock = {
        "name": "Defense Cliente Exemplo",
        "tipo": "DEFENSE",
        "config_extra": {
            # Caminho real passado por você
            "pasta_origem": r"C:\Intelbras Defense IA\Intelbras Defense IA Server\bak\db_backup"
        }
    }

    # Cria uma pasta de destino temporária para o teste
    pasta_destino = Path("tmp_teste_defense")
    pasta_destino.mkdir(exist_ok=True)
    
    print(f"-> Simulando equipamento: {equipamento_mock['name']}")
    print(f"-> Pasta Origem configurada: {equipamento_mock['config_extra']['pasta_origem']}")
    print(f"-> Pasta Destino (para o ZIP): {pasta_destino.absolute()}\n")

    # Chama a função que criamos!
    resultado = realizar_backup_defense(equipamento_mock, pasta_destino)

    print("\n" + "="*60)
    print("RESULTADO DO TESTE:")
    print(json.dumps(resultado, indent=4, ensure_ascii=False))
    print("="*60)
    
    # Verifica o que foi copiado para a pasta destino
    arquivos_copiados = list(pasta_destino.iterdir())
    if arquivos_copiados:
        print("\nArquivos salvos na pasta de destino:")
        for arq in arquivos_copiados:
            tamanho_mb = arq.stat().st_size / (1024 * 1024)
            print(f" - {arq.name} ({tamanho_mb:.2f} MB)")
    else:
        print("\nNenhum arquivo foi copiado.")

if __name__ == "__main__":
    testar()
