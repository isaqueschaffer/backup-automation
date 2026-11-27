import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# Add server/api to path
API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

# Mock settings before importing storage_service
os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
os.environ["FERNET_KEY"] = "dHJpbGFuLWNoYXZlLWRlLXRlc3RlLTMyLWJ5dGVzISE="
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from config import settings
from services.storage_service import (
    _get_machine_dir_name,
    _sanitize_name,
    get_backup_dir,
    save_zip,
    get_zip_path,
    delete_old_backups,
)
from schemas import TIPOS_EQUIPAMENTO


def test_sanitize_and_machine_dir_name():
    """Pasta da máquina: <NOME>_<UUID> (estrutura em uso desde out/2026; a antiga era <UUID>_<NOME>)."""
    c_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
    assert _get_machine_dir_name(c_id, "Teste 3") == "Teste_3_550e8400-e29b-41d4-a716-446655440000"

    sanitized = _sanitize_name('Empresa / Comércio: "Alpha" <SP>?')
    assert "/" not in sanitized and ":" not in sanitized and "<" not in sanitized


def test_get_backup_dir_and_save_zip():
    """Sem Cliente: BACKUP_STORAGE_PATH/_sem_cliente/<NOME>_<UUID>; data e tipo não viram subpasta (o nome do
    arquivo já carrega a data). A estrutura com Cliente é coberta em test_storage_hierarquia.py."""
    with tempfile.TemporaryDirectory() as tmpdir:
        settings.BACKUP_STORAGE_PATH = tmpdir
        c_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
        esperado = Path(tmpdir) / "_sem_cliente" / "Teste_3_550e8400-e29b-41d4-a716-446655440000"

        for tipo in ["NVR", "OLT", "ONU", "PABX"]:
            target_dir = get_backup_dir(c_id, "Teste 3", "17-09-2026", tipo)
            assert target_dir.resolve() == esperado.resolve(), f"Esperado {esperado}, obtido {target_dir}"
            assert target_dir.is_dir()

            dados = b"PKfake_zip_content"
            salvo = save_zip(c_id, "Teste 3", "17-09-2026", tipo, f"backup_{tipo.lower()}.zip", dados)
            assert salvo.resolve() == (esperado / f"backup_{tipo.lower()}.zip").resolve()
            assert salvo.read_bytes() == dados


def test_get_zip_path_new_and_legacy():
    print("Testing get_zip_path across new and legacy structures...")
    with tempfile.TemporaryDirectory() as tmpdir:
        settings.BACKUP_STORAGE_PATH = tmpdir
        c_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
        c_name = "Teste 3"

        # 1. New structure: UUID_NOME / DATA / TIPO / file.zip
        p1 = save_zip(c_id, c_name, "17-09-2026", "OLT", "backup_vsol.zip", b"vsol_data")
        found1 = get_zip_path(c_id, c_name, "backup_vsol.zip")
        assert found1 == p1, f"Expected {p1}, got {found1}"

        # 2. Legacy structure: NOME_UUID / DATA / TIPO / file.zip
        legacy_dir = Path(tmpdir) / f"{c_name}_{c_id}" / "10-09-2026" / "NVR"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        legacy_file = legacy_dir / "backup_antigo_1.zip"
        legacy_file.write_bytes(b"antigo_1")
        found2 = get_zip_path(c_id, c_name, "backup_antigo_1.zip")
        assert found2 == legacy_file, f"Expected {legacy_file}, got {found2}"

        # 3. Oldest structure: UUID / DATA / file.zip
        uuid_only_dir = Path(tmpdir) / str(c_id) / "01-09-2026"
        uuid_only_dir.mkdir(parents=True, exist_ok=True)
        uuid_file = uuid_only_dir / "backup_antigo_2.zip"
        uuid_file.write_bytes(b"antigo_2")
        found3 = get_zip_path(c_id, c_name, "backup_antigo_2.zip")
        assert found3 == uuid_file, f"Expected {uuid_file}, got {found3}"

        # 4. Non-existent file
        assert get_zip_path(c_id, c_name, "inexistente.zip") is None

    print("  [OK] get_zip_path passed.")


def test_delete_old_backups():
    """Apaga os backup_<DD-MM-AAAA>.zip da pasta da máquina mais antigos que keep_days e preserva o resto."""
    with tempfile.TemporaryDirectory() as tmpdir:
        settings.BACKUP_STORAGE_PATH = tmpdir
        c_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
        antigo = (datetime.utcnow() - timedelta(days=40)).strftime("%d-%m-%Y")
        recente = (datetime.utcnow() - timedelta(days=5)).strftime("%d-%m-%Y")
        p_antigo = save_zip(c_id, "Teste 3", antigo, "NVR", f"backup_{antigo}.zip", b"old")
        p_recente = save_zip(c_id, "Teste 3", recente, "NVR", f"backup_{recente}.zip", b"recent")
        outro = save_zip(c_id, "Teste 3", antigo, "OLT", "backup_vsol.zip", b"sem data no nome")

        assert delete_old_backups(c_id, "Teste 3", keep_days=30) == 1
        assert not p_antigo.exists()
        assert p_recente.exists()
        assert outro.exists(), "arquivo sem data no nome não é apagado"


def test_upload_device_type_validation():
    print("Testing upload device_type normalization and validation...")
    for tipo in ["NVR", "OLT", "ONU", "PABX"]:
        normalized = tipo.strip().upper()
        assert normalized in TIPOS_EQUIPAMENTO, f"{tipo} should be valid"

    for invalid in ["ROUTER", "SWITCH", "FIREWALL", ""]:
        assert invalid.strip().upper() not in TIPOS_EQUIPAMENTO, f"{invalid} should be invalid"

    print("  [OK] Device type validation passed.")


def run_all():
    test_sanitize_and_machine_dir_name()
    test_get_backup_dir_and_save_zip()
    test_get_zip_path_new_and_legacy()
    test_delete_old_backups()
    test_upload_device_type_validation()
    print("\nALL STORAGE TESTS PASSED SUCCESSFULLY! [OK]")


if __name__ == "__main__":
    run_all()
