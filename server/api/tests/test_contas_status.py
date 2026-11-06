"""Testes de regras de status, validade e bloqueio de Contas (services/contas.py)."""
import os
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

# Adiciona server/api ao path
API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

# Mock settings antes de importar o projeto
os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
os.environ["FERNET_KEY"] = "dGVzdF9mZXJuZXRfa2V5XzMyX2J5dGVzX2xvbmdfIQ=="
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("ADMIN_PASSWORD", "senha_de_teste")

from services.contas import status_da_conta, conta_bloqueada, dias_restantes

AGORA = datetime(2026, 10, 27, 12, 0, 0)


def test_conta_vitalicia():
    print("Testing conta vitalícia...")
    conta = types.SimpleNamespace(ativo=True, expira_em=None)
    status, dias = status_da_conta(conta, AGORA)
    assert status == "VITALICIA", f"Esperado VITALICIA, obtido {status}"
    assert dias is None, f"Esperado None, obtido {dias}"
    assert dias_restantes(conta.expira_em, AGORA) is None
    print("  [OK] Conta vitalícia validada.")


def test_conta_suspensa():
    print("Testing conta suspensa...")
    conta = types.SimpleNamespace(ativo=False, expira_em=AGORA + timedelta(days=40))
    status, dias = status_da_conta(conta, AGORA)
    assert status == "SUSPENSA", f"Esperado SUSPENSA, obtido {status}"
    assert dias == 40, f"Esperado 40, obtido {dias}"
    assert conta_bloqueada(conta, AGORA) is True
    print("  [OK] Conta suspensa validada (bloqueada mesmo com plano no futuro).")


def test_conta_ok():
    print("Testing conta OK...")
    conta = types.SimpleNamespace(ativo=True, expira_em=AGORA + timedelta(days=40))
    status, dias = status_da_conta(conta, AGORA)
    assert status == "OK", f"Esperado OK, obtido {status}"
    assert dias == 40, f"Esperado 40, obtido {dias}"
    assert conta_bloqueada(conta, AGORA) is False
    print("  [OK] Conta com validade distante (40 dias) validada.")


def test_conta_aviso():
    print("Testing conta em aviso...")
    conta_15d = types.SimpleNamespace(ativo=True, expira_em=AGORA + timedelta(days=15))
    status_15d, dias_15d = status_da_conta(conta_15d, AGORA)
    assert status_15d == "AVISO", f"Esperado AVISO, obtido {status_15d}"
    assert dias_15d == 15, f"Esperado 15, obtido {dias_15d}"

    conta_15d_1h = types.SimpleNamespace(ativo=True, expira_em=AGORA + timedelta(days=15, hours=1))
    status_15d_1h, dias_15d_1h = status_da_conta(conta_15d_1h, AGORA)
    assert status_15d_1h == "OK", f"Esperado OK, obtido {status_15d_1h}"
    assert dias_15d_1h == 16, f"Esperado 16, obtido {dias_15d_1h}"
    print("  [OK] Limiar de 15 dias para aviso validado.")


def test_conta_critico():
    print("Testing conta em crítico...")
    conta_3d = types.SimpleNamespace(ativo=True, expira_em=AGORA + timedelta(days=3))
    status_3d, dias_3d = status_da_conta(conta_3d, AGORA)
    assert status_3d == "CRITICO", f"Esperado CRITICO, obtido {status_3d}"
    assert dias_3d == 3, f"Esperado 3, obtido {dias_3d}"

    conta_1h = types.SimpleNamespace(ativo=True, expira_em=AGORA + timedelta(hours=1))
    status_1h, dias_1h = status_da_conta(conta_1h, AGORA)
    assert status_1h == "CRITICO", f"Esperado CRITICO, obtido {status_1h}"
    assert dias_1h == 1, f"Esperado 1, obtido {dias_1h}"
    print("  [OK] Limiar crítico (<= 3 dias) validado.")


def test_conta_vencida():
    print("Testing conta vencida...")
    # Exatamente no vencimento
    conta_exata = types.SimpleNamespace(ativo=True, expira_em=AGORA)
    status_exata, dias_exata = status_da_conta(conta_exata, AGORA)
    assert status_exata == "VENCIDA", f"Esperado VENCIDA, obtido {status_exata}"
    assert dias_exata == 0, f"Esperado 0, obtido {dias_exata}"
    assert conta_bloqueada(conta_exata, AGORA) is True

    # Vencida há 1 hora (primeiras 24 horas: dias_restantes = 0)
    conta_1h_passada = types.SimpleNamespace(ativo=True, expira_em=AGORA - timedelta(hours=1))
    status_1h_passada, dias_1h_passada = status_da_conta(conta_1h_passada, AGORA)
    assert status_1h_passada == "VENCIDA", f"Esperado VENCIDA, obtido {status_1h_passada}"
    assert dias_1h_passada == 0, f"Esperado 0, obtido {dias_1h_passada}"
    assert conta_bloqueada(conta_1h_passada, AGORA) is True

    # Vencida há 25 horas (passou de 24h: dias_restantes = -1)
    conta_25h_passada = types.SimpleNamespace(ativo=True, expira_em=AGORA - timedelta(hours=25))
    status_25h_passada, dias_25h_passada = status_da_conta(conta_25h_passada, AGORA)
    assert status_25h_passada == "VENCIDA", f"Esperado VENCIDA, obtido {status_25h_passada}"
    assert dias_25h_passada == -1, f"Esperado -1, obtido {dias_25h_passada}"
    assert conta_bloqueada(conta_25h_passada, AGORA) is True
    print("  [OK] Conta vencida e cálculo regressivo de dias validados.")


def test_conta_bloqueada_status_permitidos():
    print("Testing não bloqueio de status normais/ativos...")
    c_ok = types.SimpleNamespace(ativo=True, expira_em=AGORA + timedelta(days=20))
    c_aviso = types.SimpleNamespace(ativo=True, expira_em=AGORA + timedelta(days=10))
    c_critico = types.SimpleNamespace(ativo=True, expira_em=AGORA + timedelta(days=2))
    c_vitalicia = types.SimpleNamespace(ativo=True, expira_em=None)

    assert conta_bloqueada(c_ok, AGORA) is False
    assert conta_bloqueada(c_aviso, AGORA) is False
    assert conta_bloqueada(c_critico, AGORA) is False
    assert conta_bloqueada(c_vitalicia, AGORA) is False
    print("  [OK] Status OK, AVISO, CRITICO e VITALICIA confirmados como não bloqueados.")


def run_all():
    test_conta_vitalicia()
    test_conta_suspensa()
    test_conta_ok()
    test_conta_aviso()
    test_conta_critico()
    test_conta_vencida()
    test_conta_bloqueada_status_permitidos()
    print("\nTODOS OS TESTES DE STATUS DE CONTAS PASSARAM COM SUCESSO! [OK]")


if __name__ == "__main__":
    run_all()
