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
    antigo = proteger_segredos({"telnet_senha": "abc", "telnet_enable": "xyz"})
    # o painel devolve o que recebeu: marcadores e campos em branco
    novo = proteger_segredos({"telnet_usuario": "G2", "telnet_senha": "", "telnet_senha_definida": True, "telnet_enable": "nova"}, antigo)
    assert novo["telnet_senha_enc"] == antigo["telnet_senha_enc"]
    assert novo["telnet_enable_enc"] != antigo["telnet_enable_enc"]
    assert "telnet_senha_definida" not in novo
    assert config_extra_para_agente(novo)["telnet_enable"] == "nova"


def test_config_sem_segredos_passa_igual():
    cfg = {"pasta_origem": "C:/backups"}
    assert proteger_segredos(cfg) == cfg and mascarar_segredos(cfg) == cfg and config_extra_para_agente(cfg) == cfg
    assert proteger_segredos(None) is None
