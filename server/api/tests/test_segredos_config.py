import os
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

os.environ.setdefault("SECRET_KEY", "test_secret_key_1234567890123456789012")
from cryptography.fernet import Fernet

os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ADMIN_PASSWORD", "senha_de_teste")

from services.segredos_config import config_extra_para_agente, mascarar_segredos, proteger_segredos


def test_senha_vai_criptografada_e_volta_para_o_agente():
    gravado = proteger_segredos({"olts": "10.0.0.1", "telnet_usuario": "GEPON", "telnet_senha": "abc", "telnet_enable": "xyz"})
    assert "telnet_senha" not in gravado and gravado["telnet_senha_enc"] != "abc"
    agente = config_extra_para_agente(gravado)
    assert agente["telnet_senha"] == "abc" and agente["telnet_enable"] == "xyz"
    assert "telnet_senha_enc" not in agente and agente["olts"] == "10.0.0.1"


def test_painel_nunca_recebe_a_senha():
    gravado = proteger_segredos({"telnet_usuario": "GEPON", "telnet_senha": "abc"})
    painel = mascarar_segredos(gravado)
    assert painel == {"telnet_usuario": "GEPON", "telnet_senha_definida": True}


def test_em_branco_mantem_a_senha_anterior():
    antigo = proteger_segredos({"telnet_senha": "abc", "telnet_enable": "xyz", "smb_senha": "senha_antiga"})
    # o painel devolve o que recebeu: marcadores e campos em branco
    novo = proteger_segredos({
        "telnet_usuario": "G2",
        "telnet_senha": "",
        "telnet_senha_definida": True,
        "telnet_enable": "nova",
        "smb_senha": "",
        "smb_senha_definida": True,
    }, antigo)
    assert novo["telnet_senha_enc"] == antigo["telnet_senha_enc"]
    assert novo["telnet_enable_enc"] != antigo["telnet_enable_enc"]
    assert novo["smb_senha_enc"] == antigo["smb_senha_enc"]
    assert "telnet_senha_definida" not in novo
    assert "smb_senha_definida" not in novo
    assert config_extra_para_agente(novo)["telnet_enable"] == "nova"
    assert config_extra_para_agente(novo)["smb_senha"] == "senha_antiga"


def test_smb_senha_criptografada_e_mascarada():
    gravado = proteger_segredos({
        "pasta_origem": "D:UNM2000/emsback",
        "smb_host": "192.168.1.50",
        "smb_usuario": "admin",
        "smb_senha": "smb_secret_password",
    })
    assert "smb_senha" not in gravado
    assert "smb_senha_enc" in gravado
    assert gravado["smb_senha_enc"] != "smb_secret_password"

    # Painel recebe apenas marcador smb_senha_definida
    painel = mascarar_segredos(gravado)
    assert painel == {
        "pasta_origem": "D:UNM2000/emsback",
        "smb_host": "192.168.1.50",
        "smb_usuario": "admin",
        "smb_senha_definida": True,
    }

    # Agente recebe a senha descriptografada
    agente = config_extra_para_agente(gravado)
    assert agente["smb_senha"] == "smb_secret_password"
    assert "smb_senha_enc" not in agente
    assert agente["pasta_origem"] == "D:UNM2000/emsback"
    assert agente["smb_host"] == "192.168.1.50"


def test_config_sem_segredos_passa_igual():
    cfg = {"pasta_origem": "C:/backups"}
    assert proteger_segredos(cfg) == cfg and mascarar_segredos(cfg) == cfg and config_extra_para_agente(cfg) == cfg
    assert proteger_segredos(None) is None
