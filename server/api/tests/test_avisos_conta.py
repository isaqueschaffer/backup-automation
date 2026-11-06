"""Testes de marcos de avisos de vencimento das Contas (services/avisos_conta.py)."""
import os
import sys
from pathlib import Path

# Adiciona server/api ao path
API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

# Mock settings antes de importar o projeto
os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
os.environ["FERNET_KEY"] = "dGVzdF9mZXJuZXRfa2V5XzMyX2J5dGVzX2xvbmdfIQ=="
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("ADMIN_PASSWORD", "senha_de_teste")

from services.avisos_conta import marco_devido


def test_marcos_sem_vencimento_ou_longe():
    print("Testing marcos distantes ou sem expiração...")
    assert marco_devido(None, []) is None
    assert marco_devido(20, []) is None
    assert marco_devido(8, []) is None
    print("  [OK] Sem expiração ou > 7 dias não gera marco.")


def test_marcos_7_e_3_dias():
    print("Testing marcos de 7 e 3 dias...")
    assert marco_devido(7, []) == 7
    assert marco_devido(5, [7]) is None
    assert marco_devido(3, [7]) == 3
    # Conta criada perto do fim manda só o mais urgente
    assert marco_devido(2, []) == 3
    print("  [OK] Marcos de 7 e 3 dias validados.")


def test_marcos_1_dia_e_vencida():
    print("Testing marcos de 1 dia e vencida (0)...")
    assert marco_devido(1, [7, 3]) == 1
    assert marco_devido(0, [7, 3, 1]) == 0
    assert marco_devido(-5, [7, 3, 1]) == 0
    assert marco_devido(-5, [7, 3, 1, 0]) is None
    print("  [OK] Marcos de 1 dia e vencida (0) validados.")


def run_all():
    test_marcos_sem_vencimento_ou_longe()
    test_marcos_7_e_3_dias()
    test_marcos_1_dia_e_vencida()
    print("\nTODOS OS TESTES DE MARCOS DE AVISOS DE CONTA PASSARAM COM SUCESSO! [OK]")


if __name__ == "__main__":
    run_all()
