import pymysql

print("Conectando ao MySQL do Defense...")
try:
    conn = pymysql.connect(
        host="127.0.0.1",
        port=3307,
        user="root",
        password="",
        database="defense",
        cursorclass=pymysql.cursors.DictCursor
    )
    with conn.cursor() as cursor:
        cursor.execute("SHOW TABLES;")
        tables = cursor.fetchall()
        
        target_tables = []
        for t in tables:
            t_name = list(t.values())[0]
            if "camera" in t_name.lower() or "channel" in t_name.lower() or "device" in t_name.lower() or "record" in t_name.lower() or "status" in t_name.lower():
                target_tables.append(t_name)
                
        print(f"Tabelas encontradas: {target_tables}")
        
except Exception as e:
    print(f"Erro: {e}")
