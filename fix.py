import re
with open(r'C:\Users\Helena\Documents\novo_cliente\agent\src\backup\file_manager\manager.py', 'r', encoding='utf-8') as f:
    text = f.read()

new_block = '''            logging.info("  [DIGIFORT] Buscando status de gravacoes e CSV localmente...")
            try:
                from src.application.webhook_digifort import get_status_cameras, get_caminho_csv
                
                status_dict = get_status_cameras()
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
                        "mapa": "OK" if is_ok else "FALHA"
                    })
                logging.info("  [DIGIFORT] Status das cameras obtido com sucesso.")
                
                arquivo_log = get_caminho_csv()
                import os, shutil
                if os.path.isfile(arquivo_log):
                    caminho_csv = pasta_eq / "quedas_cameras.csv"
                    shutil.copy2(arquivo_log, caminho_csv)
                    arquivos_copiados.append("quedas_cameras.csv")
                    logging.info("  [DIGIFORT] CSV adicionado ao backup.")
            except Exception as e:
                logging.warning(f"  [DIGIFORT] Falha ao processar status: {e}")'''

text = re.sub(
    r'            logging\.info\(\"  \[DIGIFORT\] Buscando status de gravacoes e CSV do Agente Webhook\.\.\.\"\).*?logging\.warning\(f\"  \[DIGIFORT\] Falha ao comunicar com o agente webhook: \{e\}\"\)',
    new_block,
    text,
    flags=re.DOTALL
)

with open(r'C:\Users\Helena\Documents\novo_cliente\agent\src\backup\file_manager\manager.py', 'w', encoding='utf-8') as f:
    f.write(text)
