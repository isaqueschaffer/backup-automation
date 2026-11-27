import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.licenca_unm import licenca_da_config, parse_data


def test_formatos_de_data():
    assert parse_data("2026-12-31") == date(2026, 12, 31)
    assert parse_data("31/12/2026") == date(2026, 12, 31)
    assert parse_data("20261231") == date(2026, 12, 31)
    assert parse_data("31/02/2026") is None and parse_data("amanha") is None and parse_data(None) is None


def test_dias_restantes_e_vencida():
    hoje = date(2026, 11, 5)
    r = licenca_da_config({"licenca_inicio": "01/01/2026", "licenca_fim": "2026-11-15"}, hoje)
    assert r == {"inicio": "2026-01-01", "fim": "2026-11-15", "dias_restantes": 10}
    assert licenca_da_config({"licenca_fim": "2026-11-01"}, hoje)["dias_restantes"] == -4


def test_sem_data_nao_ha_licenca():
    assert licenca_da_config({"licenca_inicio": "2026-01-01"}) is None
    assert licenca_da_config(None) is None
