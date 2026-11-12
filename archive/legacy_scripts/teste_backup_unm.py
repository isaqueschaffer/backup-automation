# -*- coding: utf-8 -*-

import os
import re
import shutil
from datetime import datetime

# ============================================================
# CONFIGURAÇÃO
# ============================================================

PASTA_ORIGEM = r"D:\unm2000\emsback"

# Pasta onde a cópia do backup será armazenada
PASTA_DESTINO = r"D:\backup_unm2000"

# ============================================================
# INÍCIO
# ============================================================

print("=" * 60)
print("      MONITOR E CÓPIA DE BACKUP - UNM 2000")
print("=" * 60)

print("")
print("Origem:")
print(PASTA_ORIGEM)

print("")
print("Destino:")
print(PASTA_DESTINO)

print("")

# ============================================================
# VERIFICA A PASTA DE ORIGEM
# ============================================================

if not os.path.exists(PASTA_ORIGEM):

    print("[ERRO] A pasta de origem nao existe!")
    print(PASTA_ORIGEM)
    exit()

# ============================================================
# CRIA A PASTA DE DESTINO
# ============================================================

if not os.path.exists(PASTA_DESTINO):

    print("[INFO] Criando pasta de destino...")

    try:
        os.makedirs(PASTA_DESTINO)

    except Exception as erro:

        print("[ERRO] Nao foi possivel criar a pasta.")
        print(str(erro))
        exit()

# ============================================================
# PROCURA OS BACKUPS
# ============================================================

backups = []

padrao = re.compile(
    r"^([0-9]{8})_([0-9]{6})_allback\.zip$",
    re.IGNORECASE
)

for nome in os.listdir(PASTA_ORIGEM):

    caminho = os.path.join(PASTA_ORIGEM, nome)

    if not os.path.isfile(caminho):
        continue

    if not nome.lower().endswith(".zip"):
        continue

    resultado = padrao.match(nome)

    if resultado:

        data = resultado.group(1)
        hora = resultado.group(2)

        backups.append({
            "nome": nome,
            "data": data,
            "hora": hora,
            "caminho": caminho
        })


# ============================================================
# VERIFICA SE ENCONTROU BACKUPS
# ============================================================

if len(backups) == 0:

    print("[ALERTA] Nenhum backup encontrado!")

    exit()

# ============================================================
# ORDENA OS BACKUPS
# ============================================================

backups.sort(
    key=lambda x: x["data"] + x["hora"]
)

# O último será o mais recente
backup = backups[-1]

nome_backup = backup["nome"]
caminho_origem = backup["caminho"]

print("[OK] Backup encontrado!")
print("")
print("Backup mais recente:")
print(nome_backup)

print("")
print("Data: " + backup["data"])
print("Hora: " + backup["hora"])

# ============================================================
# CAMINHO DO ARQUIVO DE DESTINO
# ============================================================

caminho_destino = os.path.join(
    PASTA_DESTINO,
    nome_backup
)

# ============================================================
# VERIFICA SE JÁ EXISTE
# ============================================================

if os.path.exists(caminho_destino):

    print("")
    print("[INFO] Esse backup ja existe no destino.")
    print(caminho_destino)

    exit()

# ============================================================
# COPIA O BACKUP
# ============================================================

print("")
print("[INFO] Copiando backup...")
print("")

try:

    shutil.copy2(
        caminho_origem,
        caminho_destino
    )

except Exception as erro:

    print("[ERRO] Falha ao copiar o backup.")
    print(str(erro))

    exit()

# ============================================================
# CONFIRMAÇÃO
# ============================================================

if os.path.exists(caminho_destino):

    tamanho = os.path.getsize(caminho_destino)

    print("[OK] Backup copiado com sucesso!")
    print("")
    print("Arquivo:")
    print(caminho_destino)

    print("")
    print("Tamanho:")
    print(str(tamanho) + " bytes")

else:

    print("[ERRO] O arquivo nao foi encontrado no destino.")

print("")
print("=" * 60)