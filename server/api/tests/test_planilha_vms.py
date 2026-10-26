import os
import sys
from pathlib import Path

# Adiciona server/api ao path
API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

# Mock settings antes de importar serviços
os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
from cryptography.fernet import Fernet

os.environ["FERNET_KEY"] = Fernet.generate_key().decode()
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("ADMIN_PASSWORD", "senha_de_teste")

from services.planilha_vms import (
    colunas_senha,
    mascarar_senhas,
    empacotar,
    desempacotar,
)


def test_deteccao_colunas_senha():
    # Cabeçalho no topo (índice 0)
    linhas = [
        ["Nome", "IP", "Senha", "Modelo"],
        ["Cam 1", "192.168.1.10", "pass@123", "Hikvision"],
    ]
    assert colunas_senha(linhas, 0) == [2]

    # Variações: "Password", "SENHA NVR"
    linhas_var = [
        ["Device", "User", "Password", "SENHA NVR", "Status"],
        ["Cam 2", "admin", "secret1", "secret2", "OK"],
    ]
    assert colunas_senha(linhas_var, 0) == [2, 3]

    # Cabeçalho fora do topo (linha_cabecalho=2)
    linhas_offset = [
        ["Exportado pelo Digifort"],
        ["Data: 2026-10-26"],
        ["Canal", "Nome", "Endereço", "Password"],
        ["1", "Portão", "192.168.1.20", "secreta123"],
    ]
    assert colunas_senha(linhas_offset, 2) == [3]

    # Índice fora dos limites devolve lista vazia
    assert colunas_senha(linhas, 99) == []
    assert colunas_senha(linhas, -1) == []


def test_mascara_senhas_preserva_estrutura_e_imuta_original():
    linhas_original = [
        ["Relatório de Equipamentos"],
        ["Data de emissão"],
        ["Nome", "IP", "Senha", "Password", "Obs"],
        ["Cam 1", "192.168.1.10", "123456", "admin123", ""],
        ["Cam 2", "192.168.1.11", "", "", "Sem senha"],
        ["Cam 3", "192.168.1.12", "navarro@123", "superpass", "Portaria"],
    ]
    copia_verificacao = [list(linha) for linha in linhas_original]

    linha_cabecalho = 2
    cols = [2, 3]
    mascaradas = mascarar_senhas(linhas_original, linha_cabecalho, cols)

    # 1. Lista original não foi alterada
    assert linhas_original == copia_verificacao

    # 2. Linhas anteriores ao cabeçalho preservadas
    assert mascaradas[0] == ["Relatório de Equipamentos"]
    assert mascaradas[1] == ["Data de emissão"]

    # 3. Cabeçalho preservado
    assert mascaradas[2] == ["Nome", "IP", "Senha", "Password", "Obs"]

    # 4. Linhas de dados com senhas mascaradas
    assert mascaradas[3] == ["Cam 1", "192.168.1.10", "••••••", "••••••", ""]

    # 5. Células vazias preservadas (não viram máscara)
    assert mascaradas[4] == ["Cam 2", "192.168.1.11", "", "", "Sem senha"]

    # 6. Outra linha de dados mascarada
    assert mascaradas[5] == ["Cam 3", "192.168.1.12", "••••••", "••••••", "Portaria"]


def test_empacotar_desempacotar_e_sigilo():
    linhas = [
        ["Nome da Câmera", "IP", "Senha secreta", "Localização"],
        ["Câmera Portão Entrada", "192.168.1.50", "SenhaForte@2026!", "São Paulo / Galpão nº 1"],
        ["Câmera Recepção", "192.168.1.51", "Trilan#Protegida$", "Curitiba / Escritório"],
    ]

    empacotado = empacotar(linhas)

    # Verifica tipo string
    assert isinstance(empacotado, str)

    # Sigilo: o texto criptografado NÃO deve conter senhas ou textos em claro
    assert "SenhaForte@2026!" not in empacotado
    assert "Trilan#Protegida$" not in empacotado
    assert "Portão" not in empacotado

    # Ida e volta: desempacotar recupera exatamente a estrutura com acentos preservados
    recuperado = desempacotar(empacotado)
    assert recuperado == linhas
    assert recuperado[1][0] == "Câmera Portão Entrada"
    assert recuperado[1][2] == "SenhaForte@2026!"
    assert recuperado[1][3] == "São Paulo / Galpão nº 1"


def run_all():
    test_deteccao_colunas_senha()
    test_mascara_senhas_preserva_estrutura_e_imuta_original()
    test_empacotar_desempacotar_e_sigilo()
    print("\nTODOS OS TESTES DE PLANILHA VMS PASSARAM COM SUCESSO! [OK]")


if __name__ == "__main__":
    run_all()
