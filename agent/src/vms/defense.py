import logging
import subprocess
import os
import shutil
from pathlib import Path
from datetime import datetime

def realizar_backup_defense(equipamento: dict, pasta_destino: Path) -> dict:
    """
    Realiza o backup do Intelbras Defense IA.
    Modo 1: Coleta o arquivo de backup (.dbk, .zip, etc) gerado automaticamente pelo Defense 
            (requer 'pasta_origem' no config_extra).
    Modo 2: Fallback para extrair um dump direto do banco de dados MySQL nativo.
    """
    nome = equipamento.get("name", "Defense")
    logging.info(f"\n{'='*50}\n{nome} [DEFENSE]\n{'='*50}")

    # Extrai configurações que podem vir do painel
    config_extra = equipamento.get("config_extra") or {}
    if isinstance(config_extra, str):
        import json
        try:
            config_extra = json.loads(config_extra)
        except:
            config_extra = {}

    pasta_origem_str = config_extra.get("pasta_origem")

    # ==========================================
    # MODO 1: Coleta do arquivo nativo do Defense
    # ==========================================
    if pasta_origem_str:
        logging.info(f"  [DEFENSE] Coletando arquivo de backup nativo na pasta: {pasta_origem_str}")
        pasta_origem = Path(pasta_origem_str)
        if not pasta_origem.exists() or not pasta_origem.is_dir():
            logging.error(f"  [DEFENSE] Pasta de origem não encontrada: {pasta_origem}")
            return {"nome": nome, "status": "ERRO", "cameras": None}

        # Busca apenas os arquivos de backup (.enc, .zip, .dbk) ignorando .cfg e temporários
        extensoes_validas = {".enc", ".zip", ".dbk", ".bak"}
        arquivos = [f for f in pasta_origem.iterdir() if f.is_file() and f.suffix.lower() in extensoes_validas]
        
        if not arquivos:
            logging.warning(f"  [DEFENSE] Nenhum arquivo encontrado na pasta: {pasta_origem}")
            return {"nome": nome, "status": "SEM_ARQUIVOS", "cameras": None}

        # Pega o arquivo mais recente baseado na data de modificação
        arquivo_mais_recente = max(arquivos, key=lambda f: f.stat().st_mtime)
        destino_arquivo = pasta_destino / arquivo_mais_recente.name

        try:
            shutil.copy2(arquivo_mais_recente, destino_arquivo)
            logging.info(f"  [DEFENSE] Arquivo de backup copiado com sucesso: {arquivo_mais_recente.name}")
            return {"nome": nome, "status": "OK", "cameras": None}
        except Exception as e:
            logging.error(f"  [DEFENSE] Erro ao copiar arquivo de backup: {e}")
            return {"nome": nome, "status": "ERRO", "cameras": None}

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
    arquivo_dump = pasta_destino / f"DUMP_{nome.replace(' ', '_')}_{data_atual}.sql"

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
            subprocess.run(comando, env=env, stdout=f_out, stderr=subprocess.PIPE, text=True, check=True)
            
        logging.info(f"  [DEFENSE] Dump gerado com sucesso: {arquivo_dump.name}")
        return {"nome": nome, "status": "OK", "cameras": None}
        
    except FileNotFoundError:
        logging.error("  Erro: Utilitário 'mysqldump' não encontrado. Verifique se o MySQL Client está instalado e no PATH do sistema.")
        return {"nome": nome, "status": "ERRO", "cameras": None}
    except subprocess.CalledProcessError as e:
        logging.error(f"  Erro ao executar mysqldump (Código {e.returncode}): {e.stderr.strip()}")
        if arquivo_dump.exists():
            arquivo_dump.unlink() # Remove o arquivo vazio/incompleto
        return {"nome": nome, "status": "ERRO", "cameras": None}
    except Exception as e:
        logging.error(f"  Erro inesperado durante o dump: {e}")
        return {"nome": nome, "status": "ERRO", "cameras": None}
