import io
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.backup.file_manager.models import BackupFile, BackupStatus
from src.backup.file_manager.parsers import UNM2000Parser
from src.backup.smb_storage import (
    SmbEntry,
    SmbStorage,
    SmbTarget,
    is_smb_path,
    parse_smb_target,
)


class TestSmbStorage(unittest.TestCase):

    def test_parse_drive_letter_with_host(self):
        target = parse_smb_target("D:UNM2000/emsback", host="192.168.1.50")
        self.assertEqual(target.host, "192.168.1.50")
        self.assertEqual(target.share, "D$")
        self.assertEqual(target.subpath, r"UNM2000\emsback")
        self.assertEqual(target.unc_path, r"\\192.168.1.50\D$\UNM2000\emsback")

    def test_parse_drive_letter_backslash(self):
        target = parse_smb_target(r"D:\UNM2000\emsback", host="10.0.0.1")
        self.assertEqual(target.unc_path, r"\\10.0.0.1\D$\UNM2000\emsback")

    def test_parse_host_colon_drive(self):
        target = parse_smb_target("192.168.1.100:D:UNM2000/emsback")
        self.assertEqual(target.host, "192.168.1.100")
        self.assertEqual(target.share, "D$")
        self.assertEqual(target.unc_path, r"\\192.168.1.100\D$\UNM2000\emsback")

    def test_parse_unc_path(self):
        target = parse_smb_target(r"\\192.168.1.50\emsback\backups")
        self.assertEqual(target.host, "192.168.1.50")
        self.assertEqual(target.share, "emsback")
        self.assertEqual(target.subpath, "backups")
        self.assertEqual(target.unc_path, r"\\192.168.1.50\emsback\backups")

    def test_parse_smb_uri(self):
        target = parse_smb_target("smb://usuario:senha123@192.168.1.50:445/D$/UNM2000/emsback")
        self.assertEqual(target.host, "192.168.1.50")
        self.assertEqual(target.username, "usuario")
        self.assertEqual(target.password, "senha123")
        self.assertEqual(target.share, "D$")
        self.assertEqual(target.unc_path, r"\\192.168.1.50\D$\UNM2000\emsback")

    def test_is_smb_path_detection(self):
        self.assertTrue(is_smb_path(r"\\servidor\share"))
        self.assertTrue(is_smb_path("//servidor/share"))
        self.assertTrue(is_smb_path("smb://servidor/share"))
        self.assertTrue(is_smb_path("192.168.1.50:D:path"))
        self.assertTrue(is_smb_path("D:UNM2000/emsback", config_extra={"smb_host": "192.168.1.50"}))

    @patch("src.backup.smb_storage.smbclient")
    def test_copy_file_streaming_and_hash(self, mock_smbclient):
        conteudo_fake = b"X" * 2048
        stat_mock = MagicMock()
        stat_mock.st_size = len(conteudo_fake)
        mock_smbclient.stat.return_value = stat_mock

        file_mock = io.BytesIO(conteudo_fake)
        mock_smbclient.open_file.return_value.__enter__.return_value = file_mock

        storage = SmbStorage()
        dest = Path("tests_tmp_backup.zip")
        try:
            ok, status = storage.copy_file(r"\\server\D$\backup.zip", dest, check_hash=True)
            self.assertTrue(ok)
            self.assertEqual(status, BackupStatus.OK)
            self.assertTrue(dest.exists())
            self.assertEqual(dest.stat().st_size, len(conteudo_fake))
        finally:
            if dest.exists():
                dest.unlink()

    @patch.object(SmbStorage, "scandir")
    def test_unm2000_parser_smb(self, mock_scandir):
        mock_scandir.return_value = [
            SmbEntry(name="unm_20261117_083000.zip", unc_path=r"\\server\D$\unm_20261117_083000.zip", is_dir=False, size=1024),
            SmbEntry(name="outros_arquivos.txt", unc_path=r"\\server\D$\outros_arquivos.txt", is_dir=False, size=50),
        ]
        parser = UNM2000Parser()
        target = parse_smb_target("D:UNM2000/emsback", host="192.168.1.50")
        grupos = parser.find_backups(target)

        self.assertEqual(len(grupos), 1)
        self.assertEqual(grupos[0].files[0].file_type, "ZIP")
        self.assertTrue(grupos[0].files[0].is_smb)
        self.assertEqual(grupos[0].files[0].remote_path, r"\\server\D$\unm_20261117_083000.zip")

    def test_parse_smb_uri_unquote(self):
        target = parse_smb_target("smb://user%20name:p%40ss@192.168.1.50/Share%20Name/Pasta%201")
        self.assertEqual(target.username, "user name")
        self.assertEqual(target.password, "p@ss")
        self.assertEqual(target.share, "Share Name")
        self.assertEqual(target.unc_path, r"\\192.168.1.50\Share Name\Pasta 1")

    @patch("src.backup.smb_storage.smbclient")
    def test_copy_directory_smb(self, mock_smbclient):
        # Mock item no diretório
        mock_item = MagicMock()
        mock_item.name = "arquivo1.dar"
        mock_item.is_dir.return_value = False
        mock_smbclient.scandir.return_value = [mock_item]

        file_mock = io.BytesIO(b"conteudo_dar")
        mock_smbclient.open_file.return_value.__enter__.return_value = file_mock

        storage = SmbStorage()
        dest_dir = Path("tests_tmp_dir_dest")
        try:
            ok, status = storage.copy_directory(r"\\server\D$\Digifort\20261117", dest_dir)
            self.assertTrue(ok)
            self.assertEqual(status, BackupStatus.OK)
            self.assertTrue(dest_dir.is_dir())
            self.assertTrue((dest_dir / "arquivo1.dar").exists())
        finally:
            import shutil
            if dest_dir.exists():
                shutil.rmtree(dest_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
