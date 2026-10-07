import pymysql
import argparse

def explorar_banco(host, porta, usuario, senha, banco="defense"):
    print(f"[{host}:{porta}] Conectando ao MySQL do Defense...")
    try:
        conn = pymysql.connect(
            host=host,
            port=porta,
            user=usuario,
            password=senha,
            database=banco,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5
        )
        with conn.cursor() as cursor:
            print("Conexão bem-sucedida! Buscando tabelas...")
            cursor.execute("SHOW TABLES;")
            tables = cursor.fetchall()
            
            target_tables = []
            for t in tables:
                t_name = list(t.values())[0]
                # Busca por palavras chave nas tabelas
                if any(x in t_name.lower() for x in ["camera", "channel", "device", "record", "status", "video", "dss"]):
                    target_tables.append(t_name)
                    
            print(f"\nForam encontradas {len(target_tables)} tabelas potenciais:")
            for t in target_tables:
                print(f" - {t}")
            
            # Vamos mostrar a estrutura de uma tabela comum no DSS (dss_channel ou similar) se existir
            for t in target_tables:
                if "channel" in t.lower() or "camera" in t.lower():
                    print(f"\n--- Estrutura da tabela {t} ---")
                    cursor.execute(f"DESCRIBE {t};")
                    colunas = cursor.fetchall()
                    for col in colunas:
                        print(f"  {col['Field']} ({col['Type']})")
                    break # Mostrar só da primeira relevante para não poluir
                    
    except Exception as e:
        print(f"Erro ao conectar ou consultar: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Explorar DB do Defense")
    parser.add_argument("--ip", default="127.0.0.1", help="IP do Defense")
    parser.add_argument("--port", type=int, default=3307, help="Porta do MySQL")
    parser.add_argument("--user", default="root", help="Usuário do MySQL")
    parser.add_argument("--password", default="", help="Senha do MySQL")
    parser.add_argument("--db", default="defense", help="Nome do Banco de Dados")
    
    args = parser.parse_args()
    explorar_banco(args.ip, args.port, args.user, args.password, args.db)
