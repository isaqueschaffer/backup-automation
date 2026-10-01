import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add server/api to path
API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

# Mock settings before importing storage_service
os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
os.environ["FERNET_KEY"] = "dGVzdF9mZXJuZXRfa2V5XzMyX2J5dGVzX2xvbmdfIQ=="
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from config import settings
from services.storage_service import (
    _get_client_dir_name,
    _sanitize_name,
    get_backup_dir,
    save_zip,
    get_zip_path,
    delete_old_backups,
)
from schemas import TIPOS_EQUIPAMENTO


def test_sanitize_and_client_dir_name():
    print("Testing _sanitize_name and _get_client_dir_name...")
    c_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
    
    name = "Teste 3"
    dir_name = _get_client_dir_name(c_id, name)
    assert dir_name == "550e8400-e29b-41d4-a716-446655440000_Teste_3", f"Got: {dir_name}"

    name_special = 'Empresa / Comércio: "Alpha" <SP>?'
    sanitized = _sanitize_name(name_special)
    assert "/" not in sanitized and ":" not in sanitized and "<" not in sanitized
    print("  [OK] Sanitization passed.")


def test_get_backup_dir_and_save_zip():
    print("Testing get_backup_dir and save_zip...")
    with tempfile.TemporaryDirectory() as tmpdir:
        settings.BACKUP_STORAGE_PATH = tmpdir
        c_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
        c_name = "Teste 3"
        date_str = "17-09-2026"
        
        for tipo in ["NVR", "OLT", "ONU", "PABX"]:
            target_dir = get_backup_dir(c_id, c_name, date_str, tipo)
            expected_dir = (
                Path(tmpdir)
                / "550e8400-e29b-41d4-a716-446655440000_Teste_3"
                / "17-09-2026"
                / tipo
            )
            assert target_dir == expected_dir, f"Expected {expected_dir}, got {target_dir}"
            assert target_dir.is_dir()

            # Test save_zip
            file_data = b"PK\x03\x04fake_zip_content"
            filename = f"backup_{tipo.lower()}.zip"
            saved_path = save_zip(c_id, c_name, date_str, tipo, filename, file_data)
            assert saved_path == target_dir / filename
            assert saved_path.read_bytes() == file_data

    print("  [OK] get_backup_dir and save_zip passed.")


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
    print("Testing delete_old_backups...")
    with tempfile.TemporaryDirectory() as tmpdir:
        settings.BACKUP_STORAGE_PATH = tmpdir
        c_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
        c_name = "Teste 3"

        # Create old backup: 40 days ago
        dt_old = datetime.now(timezone.utc) - timedelta(days=40)
        old_date_str = dt_old.strftime("%d-%m-%Y")
        save_zip(c_id, c_name, old_date_str, "NVR", "backup_nvr.zip", b"old_nvr")
        save_zip(c_id, c_name, old_date_str, "OLT", "backup_olt.zip", b"old_olt")

        # Create recent backup: 5 days ago
        dt_recent = datetime.now(timezone.utc) - timedelta(days=5)
        recent_date_str = dt_recent.strftime("%d-%m-%Y")
        save_zip(c_id, c_name, recent_date_str, "NVR", "backup_nvr.zip", b"recent_nvr")
        save_zip(c_id, c_name, recent_date_str, "OLT", "backup_olt.zip", b"recent_olt")

        old_dir = Path(tmpdir) / f"{c_id}_Teste_3" / old_date_str
        recent_dir = Path(tmpdir) / f"{c_id}_Teste_3" / recent_date_str
        assert old_dir.exists()
        assert recent_dir.exists()

        # Delete with keep_days=30
        deleted_count = delete_old_backups(c_id, c_name, keep_days=30)
        assert deleted_count == 1, f"Expected 1 deleted, got {deleted_count}"
        assert not old_dir.exists(), "Old date dir should have been removed entirely"
        assert recent_dir.exists(), "Recent date dir should have been preserved"
        assert (recent_dir / "NVR" / "backup_nvr.zip").exists()
        assert (recent_dir / "OLT" / "backup_olt.zip").exists()

    print("  [OK] delete_old_backups passed.")


def test_upload_device_type_validation():
    print("Testing upload device_type normalization and validation...")
    for tipo in ["NVR", "OLT", "ONU", "PABX"]:
        normalized = tipo.strip().upper()
        assert normalized in TIPOS_EQUIPAMENTO, f"{tipo} should be valid"

    for invalid in ["ROUTER", "SWITCH", "FIREWALL", ""]:
        assert invalid.strip().upper() not in TIPOS_EQUIPAMENTO, f"{invalid} should be invalid"

    print("  [OK] Device type validation passed.")


def run_all():
    test_sanitize_and_client_dir_name()
    test_get_backup_dir_and_save_zip()
    test_get_zip_path_new_and_legacy()
    test_delete_old_backups()
    test_upload_device_type_validation()
    print("\nALL STORAGE TESTS PASSED SUCCESSFULLY! [OK]")


if __name__ == "__main__":
    run_all()
