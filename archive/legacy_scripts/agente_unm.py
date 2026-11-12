# -*- coding: utf-8 -*-

import os
import re
import shutil
import datetime
try:
    import tkinter as tk
    from tkinter import messagebox as tkMessageBox
    from tkinter import filedialog
except ImportError:
    import Tkinter as tk
    import tkMessageBox
    import tkFileDialog as filedialog


# ============================================================
# CONFIGURACAO
# ============================================================

PASTA_BACKUP = r"C:\Users\Helena\Documents"

# Pasta raiz dos clientes
PASTA_ONEDRIVE = r"C:\Users\Helena\OneDrive - Trilan"

# Arquivo de log
ARQUIVO_LOG = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "agente_unm.log"
)

def encontrar_onedrive():

    candidatos = [
        os.environ.get("OneDrive"),
        os.environ.get("OneDriveCommercial"),
        os.environ.get("OneDriveConsumer")
    ]

    for caminho in candidatos:
        if caminho and os.path.isdir(caminho):
            return os.path.abspath(caminho)

    return None


# ============================================================
# LOG
# ============================================================

def registrar_log(mensagem):

    agora = datetime.datetime.now()

    data_hora = agora.strftime(
        "%d-%m-%Y %H:%M:%S"
    )

    linha = "[{}] {}\n".format(
        data_hora,
        mensagem
    )

    try:
        arquivo = open(
            ARQUIVO_LOG,
            "a"
        )

        arquivo.write(linha)
        arquivo.close()

    except Exception:
        pass

    print(linha.strip())


# ============================================================
# DATA ATUAL
# ============================================================

def data_atual():

    return datetime.datetime.now().strftime(
        "%Y%m%d"
    )


# ============================================================
# IDENTIFICA DATA/HORA DENTRO DO NOME
# ============================================================

def extrair_data_backup(nome_arquivo):
    """
    Procura dentro do nome um trecho no formato:

        YYYYMMDD_HHMMSS

    Exemplos aceitos:

        20260910_030154_allback.zip
        backup_agerip_20260910_030154_allback.zip
        UNM_backup_20260910_030154.zip
        backup_cliente_20260910_030154_qualquercoisa.zip
    """

    padrao = r'(\d{8})_(\d{6})'

    resultado = re.search(padrao, nome_arquivo)

    if not resultado:
        return None

    data_str = resultado.group(1)
    hora_str = resultado.group(2)

    try:
        return datetime.datetime.strptime(
            data_str + "_" + hora_str,
            "%Y%m%d_%H%M%S"
        )

    except ValueError:
        return None




# ============================================================
# LOCALIZAR BACKUPS
# ============================================================

def encontrar_backups(pasta_origem=None):
    if not pasta_origem:
        pasta_origem = PASTA_BACKUP

    backups = []

    if not os.path.isdir(pasta_origem):
        registrar_log(
            "ERRO: pasta de origem nao existe: {}".format(
                pasta_origem
            )
        )
        return backups

    for nome in os.listdir(pasta_origem):

        caminho = os.path.join(
            pasta_origem,
            nome
        )

        if not os.path.isfile(caminho):
            continue

        # Aceita ZIP e outros formatos de arquivo
        extensoes = [
            ".zip",
            ".tar",
            ".gz",
            ".7z"
        ]

        extensao = os.path.splitext(nome)[1].lower()

        if extensao not in extensoes:
            continue

        data_backup = extrair_data_backup(nome)

        if data_backup is None:
            continue

        backups.append({
            "nome": nome,
            "caminho": caminho,
            "data": data_backup
        })

    backups.sort(
        key=lambda x: x["data"],
        reverse=True
    )

    return backups


# ============================================================
# CONVERTE O NOME DO BACKUP
#
# 20260910_080532_allback.zip
#
# para
#
# 10-09-2026_08_05_32.zip
# ============================================================

def novo_nome(nome_original):

    padrao = r'(\d{8})_(\d{6})'

    resultado = re.search(
        padrao,
        nome_original
    )

    if not resultado:
        raise Exception(
            "Formato de backup desconhecido:\n{}".format(
                nome_original
            )
        )

    data_str = resultado.group(1)
    hora_str = resultado.group(2)

    data_backup = datetime.datetime.strptime(
        data_str + "_" + hora_str,
        "%Y%m%d_%H%M%S"
    )

    return data_backup.strftime(
        "%d-%m-%Y_%H_%M_%S.zip"
    )

# ============================================================
# CRIA PASTA DO CLIENTE
# ============================================================

def criar_pasta_cliente(caminho_cliente):

    # ========================================================
    # DESCOBRE O ONEDRIVE DA MAQUINA
    # ========================================================

    pasta_onedrive = encontrar_onedrive()

    if not pasta_onedrive:
        raise Exception(
            "Nao foi possivel localizar o OneDrive nesta maquina."
        )

    registrar_log(
        "OneDrive encontrado: {}".format(
            pasta_onedrive
        )
    )

    # ========================================================
    # NORMALIZA O CAMINHO INFORMADO
    # ========================================================

    caminho_cliente = caminho_cliente.strip()

    caminho_cliente = caminho_cliente.replace(
        "/",
        "\\"
    )

    # Aceita:
    # /OneDrive/Agerip
    # /One Drive/Agerip
    # Agerip

    prefixos = [
        "OneDrive\\",
        "One Drive\\"
    ]

    for prefixo in prefixos:

        if caminho_cliente.lower().startswith(
            prefixo.lower()
        ):

            caminho_cliente = caminho_cliente[
                len(prefixo):
            ]

            break

    caminho_cliente = caminho_cliente.strip(
        "\\/"
    )

    if not caminho_cliente:

        raise Exception(
            "Nome do cliente nao foi informado."
        )

    # ========================================================
    # PROTECAO CONTRA CAMINHOS PERIGOSOS
    # ========================================================

    partes = caminho_cliente.split("\\")

    for parte in partes:

        if parte == "..":

            raise Exception(
                "Caminho invalido."
            )

    # ========================================================
    # MONTA O CAMINHO COMPLETO
    # ========================================================

    pasta_cliente = os.path.join(
        pasta_onedrive,
        caminho_cliente
    )

    pasta_unm = os.path.join(
        pasta_cliente,
        "UNM2000"
    )

    # ========================================================
    # CRIA AS PASTAS
    # ========================================================

    if not os.path.isdir(pasta_cliente):

        os.makedirs(
            pasta_cliente
        )

        registrar_log(
            "Pasta do cliente criada: {}".format(
                pasta_cliente
            )
        )

    if not os.path.isdir(pasta_unm):

        os.makedirs(
            pasta_unm
        )

        registrar_log(
            "Pasta UNM2000 criada: {}".format(
                pasta_unm
            )
        )

    # ========================================================
    # GARANTE QUE O CAMINHO E ABSOLUTO
    # ========================================================

    pasta_unm = os.path.abspath(
        pasta_unm
    )

    registrar_log(
        "Destino final: {}".format(
            pasta_unm
        )
    )

    return pasta_unm


# ============================================================
# VERIFICA SE O ARQUIVO JA FOI COPIADO
# ============================================================

def backup_ja_processado(arquivo_destino):

    return os.path.isfile(
        arquivo_destino
    )


# ============================================================
# TAMANHO DO ARQUIVO
# ============================================================

def tamanho_arquivo(caminho):

    tamanho = os.path.getsize(
        caminho
    )

    # MB
    return tamanho / float(
        1024 * 1024
    )


# ============================================================
# EXECUTA BACKUP
# ============================================================

def realizar_backup(caminho_cliente, pasta_origem=None):

    if not pasta_origem:
        pasta_origem = PASTA_BACKUP

    registrar_log(
        "Inicio da verificacao."
    )

    # --------------------------------------------------------
    # Verifica origem
    # --------------------------------------------------------

    if not os.path.isdir(pasta_origem):

        raise Exception(
            "Pasta de backup nao encontrada:\n{}".format(
                pasta_origem
            )
        )

    # --------------------------------------------------------
    # Cria destino
    # --------------------------------------------------------

    pasta_destino = criar_pasta_cliente(
        caminho_cliente
    )

    # --------------------------------------------------------
    # Procura backups
    # --------------------------------------------------------

    backups = encontrar_backups(pasta_origem)

    if not backups:

        raise Exception(
            "Nenhum backup no formato esperado foi encontrado."
        )

    # --------------------------------------------------------
    # Procura o backup mais recente que ainda nao existe
    # --------------------------------------------------------

    backup_pendente = None

    for backup in backups:

        nome_original = backup["nome"]

        nome_destino = novo_nome(
            nome_original
        )

        arquivo_destino = os.path.join(
            pasta_destino,
            nome_destino
        )

        if not os.path.isfile(
            arquivo_destino
        ):

            backup_pendente = backup
            break

        registrar_log(
            "Arquivo ja existe no destino: {}".format(
                arquivo_destino
            )
        )

    # --------------------------------------------------------
    # Nenhum backup novo
    # --------------------------------------------------------

    if backup_pendente is None:

        registrar_log(
            "Todos os backups encontrados ja existem no destino."
        )

        return {
            "status": "ja_processado",
            "destino": pasta_destino
        }

    # --------------------------------------------------------
    # Dados
    # --------------------------------------------------------

    nome_original = backup_pendente["nome"]

    arquivo_origem = backup_pendente["caminho"]

    data_backup = backup_pendente["data"]

    # --------------------------------------------------------
    # Nome destino
    # --------------------------------------------------------

    nome_destino = novo_nome(
        nome_original
    )

    arquivo_destino = os.path.join(
        pasta_destino,
        nome_destino
    )

    registrar_log(
        "Novo backup encontrado: {}".format(
            nome_original
        )
    )

    registrar_log(
        "Copiando backup..."
    )

    # --------------------------------------------------------
    # Copia
    # --------------------------------------------------------

    shutil.copy2(
        arquivo_origem,
        arquivo_destino
    )

    registrar_log(
        "Backup copiado com sucesso."
    )

    registrar_log(
        "Origem: {}".format(
            arquivo_origem
        )
    )

    registrar_log(
        "Destino: {}".format(
            arquivo_destino
        )
    )

    return {
        "status": "copiado",
        "origem": arquivo_origem,
        "destino": arquivo_destino,
        "nome": nome_destino,
        "tamanho": tamanho_arquivo(
            arquivo_origem
        ),
        "data": data_backup
    }


# ============================================================
# INTERFACE
# ============================================================

# ============================================================
# SELECAO DE PASTA DE ORIGEM
# ============================================================

def escolher_pasta_origem():
    """
    Abre uma janela para o usuário escolher manualmente
    a pasta onde estão os backups da UNM2000.
    """

    pasta_inicial = PASTA_BACKUP
    if "entrada_origem" in globals() and entrada_origem.get().strip():
        pasta_atual = entrada_origem.get().strip()
        if os.path.isdir(pasta_atual):
            pasta_inicial = pasta_atual

    parent = globals().get("janela", None)

    if parent is not None:
        pasta = filedialog.askdirectory(
            parent=parent,
            title="Selecione a pasta onde estão os backups da UNM2000",
            initialdir=pasta_inicial
        )
    else:
        root = tk.Tk()
        root.withdraw()
        pasta = filedialog.askdirectory(
            title="Selecione a pasta onde estão os backups da UNM2000",
            initialdir=pasta_inicial
        )
        root.destroy()

    if pasta:
        pasta = os.path.abspath(pasta)
        print("Pasta de origem selecionada:")
        print(pasta)
        registrar_log(
            "Pasta de origem selecionada: {}".format(pasta)
        )
        if "entrada_origem" in globals() and entrada_origem:
            entrada_origem.delete(0, tk.END)
            entrada_origem.insert(0, pasta)
        return pasta

    print("Nenhuma pasta foi selecionada.")
    return None


# ============================================================
# INTERFACE
# ============================================================

def executar():

    pasta_origem = entrada_origem.get().strip()
    caminho_cliente = entrada.get().strip()

    if not pasta_origem:
        tkMessageBox.showwarning(
            "Atencao",
            "Informe ou selecione a pasta de origem dos backups."
        )
        return

    if not os.path.isdir(pasta_origem):
        tkMessageBox.showerror(
            "Erro",
            "A pasta de origem informada nao existe:\n{}".format(pasta_origem)
        )
        return

    if not caminho_cliente:
        tkMessageBox.showwarning(
            "Atencao",
            "Informe o caminho do cliente."
        )
        return

    try:
        resultado = realizar_backup(
            caminho_cliente,
            pasta_origem
        )

        if resultado["status"] == "copiado":
            tamanho = resultado.get("tamanho", 0.0)

            mensagem = (
                "BACKUP REALIZADO COM SUCESSO\n\n"
                "Arquivo:\n{}\n\n"
                "Tamanho: {:.2f} MB\n\n"
                "Destino:\n{}"
            ).format(
                resultado["nome"],
                tamanho,
                resultado["destino"]
            )

            tkMessageBox.showinfo(
                "Backup realizado",
                mensagem
            )

        elif resultado["status"] == "ja_processado":

            mensagem = (
                "BACKUP JA PROCESSADO\n\n"
                "O arquivo ja existe no destino:\n\n{}"
            ).format(
                resultado["destino"]
            )

            tkMessageBox.showinfo(
                "Backup ja existente",
                mensagem
            )

    except Exception as erro:

        registrar_log(
            "ERRO: {}".format(
                str(erro)
            )
        )

        tkMessageBox.showerror(
            "Erro / Alerta",
            str(erro)
        )


# ============================================================
# JANELA
# ============================================================

janela = tk.Tk()

janela.title(
    "Agente de Backup - UNM 2000"
)

janela.geometry(
    "600x340"
)

janela.resizable(
    False,
    False
)


titulo = tk.Label(
    janela,
    text="Agente de Backup UNM 2000",
    font=("Arial", 16)
)

titulo.pack(
    pady=(12, 10)
)

# --- Origem ---
lbl_origem = tk.Label(
    janela,
    text="Informe ou selecione a pasta de origem:",
    font=("Arial", 10)
)
lbl_origem.pack(
    anchor="w",
    padx=30
)

frame_origem = tk.Frame(janela)
frame_origem.pack(
    fill="x",
    padx=30,
    pady=(3, 10)
)

entrada_origem = tk.Entry(
    frame_origem,
    font=("Arial", 10)
)
entrada_origem.insert(
    0,
    PASTA_BACKUP
)
entrada_origem.pack(
    side="left",
    fill="x",
    expand=True,
    padx=(0, 6)
)

btn_origem = tk.Button(
    frame_origem,
    text="Procurar...",
    font=("Arial", 9),
    command=escolher_pasta_origem
)
btn_origem.pack(
    side="right"
)

# --- Destino (Cliente) ---
lbl_destino = tk.Label(
    janela,
    text="Informe o caminho do cliente (OneDrive):",
    font=("Arial", 10)
)
lbl_destino.pack(
    anchor="w",
    padx=30
)

entrada = tk.Entry(
    janela,
    font=("Arial", 10)
)
entrada.insert(
    0,
    "\\Cliente\\"
)
entrada.pack(
    fill="x",
    padx=30,
    pady=(3, 12)
)

entrada_cliente = entrada

# --- Botão de Ação ---
botao = tk.Button(
    janela,
    text="Verificar e realizar backup",
    width=26,
    height=2,
    command=executar
)
botao.pack(
    pady=6
)

# --- Informações ---
info = tk.Label(
    janela,
    text=(
        "Origem: pasta onde estão os backups da UNM 2000 (.zip)\n"
        "Destino: OneDrive\\<cliente>\\UNM2000"
    ),
    font=("Arial", 9)
)
info.pack(
    pady=(5, 10)
)

registrar_log(
    "Agente iniciado."
)

janela.mainloop()