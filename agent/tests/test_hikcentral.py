"""Backup do HikCentral (VSM): pasta VSM_V<versão>_BACKUP_<AAAAMMDDHHMMSS>_<n> na pasta de origem, como o UNM2000."""
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.backup.file_manager.manager import FileManager
from src.backup.file_manager.parsers import HikCentralParser
from src.backup.file_manager.utils import parse_backup_date

NOME = "VSM_V2.6.0.0_BACKUP_20261127123703_42904"
AGORA = datetime(2026, 11, 27, 15, 0, 0)


def _criar_backup(raiz: Path, nome: str = NOME) -> Path:
    pasta = raiz / nome
    (pasta / "db").mkdir(parents=True)
    (pasta / "db" / "dados.sql").write_text("select 1;")
    (pasta / "config.ini").write_text("a=1")
    return pasta


class TestHikCentral(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.origem = Path(self._tmp.name) / "BACKUP HIKCENTRAL"
        self.origem.mkdir()
        self.destino = Path(self._tmp.name) / "saida"

    def _equipamento(self):
        return {"name": "HikCentral Matriz", "tipo": "HIKCENTRAL", "ip": "127.0.0.1",
                "config_extra": {"pasta_origem": str(self.origem)}}

    def _backup(self):
        with mock.patch("src.backup.file_manager.manager.get_agent_date", return_value=AGORA), \
                mock.patch("time.sleep"):
            return FileManager().process_equipment(self._equipamento(), self.destino, "HIKCENTRAL")

    def test_data_de_14_digitos(self):
        self.assertEqual(parse_backup_date("20261127123703"), datetime(2026, 11, 27, 12, 37, 3))
        self.assertIsNone(parse_backup_date("20261399123703"))

    def test_acha_a_pasta_pelo_nome_e_ordena_pela_mais_recente(self):
        _criar_backup(self.origem)
        _criar_backup(self.origem, "VSM_V2.6.0.0_BACKUP_20261126123703_42903")
        (self.origem / "outra_pasta").mkdir()
        (self.origem / "VSM_V2.6.0.0_BACKUP_20261120000000_1.log").write_text("x")  # não é pasta nem compactado
        grupos = HikCentralParser().find_backups(self.origem)
        self.assertEqual([g.group_id for g in grupos], [NOME, "VSM_V2.6.0.0_BACKUP_20261126123703_42903"])
        self.assertEqual(grupos[0].date, datetime(2026, 11, 27, 12, 37, 3))
        self.assertEqual(grupos[0].files[0].file_type, "DIGIFORT_DIR")

    def test_arquivo_compactado_com_o_mesmo_nome_tambem_vale(self):
        (self.origem / (NOME + ".zip")).write_bytes(b"PK")
        grupos = HikCentralParser().find_backups(self.origem)
        self.assertEqual(len(grupos), 1)
        self.assertEqual(grupos[0].files[0].file_type, "ZIP")

    def test_copia_a_pasta_inteira_com_o_nome_original(self):
        _criar_backup(self.origem)
        res = self._backup()
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["arquivos"], [NOME])
        self.assertEqual((self.destino / NOME / "db" / "dados.sql").read_text(), "select 1;")
        self.assertEqual((self.destino / NOME / "config.ini").read_text(), "a=1")

    def test_segunda_rodada_ja_processado(self):
        _criar_backup(self.origem)
        self._backup()
        self.assertEqual(self._backup()["status"], "JA_PROCESSADO")

    def test_backup_de_ha_dias_e_antigo(self):
        _criar_backup(self.origem, "VSM_V2.6.0.0_BACKUP_20261120123703_1")
        self.assertEqual(self._backup()["status"], "BACKUP_ANTIGO")

    def test_sem_nenhum_backup_na_pasta(self):
        self.assertEqual(self._backup()["status"], "BACKUP_NAO_ENCONTRADO")

    def test_pasta_inexistente_nao_levanta_erro(self):
        self.origem.rmdir()
        self.assertEqual(self._backup()["status"], "BACKUP_NAO_ENCONTRADO")

    def test_despacho_do_backup_job_e_do_tunel(self):
        from src.application import backup_job
        _criar_backup(self.origem)
        with mock.patch("src.backup.file_manager.manager.get_agent_date", return_value=AGORA), \
                mock.patch("time.sleep"):
            res = backup_job.processar_equipamento(self._equipamento(), "senha", self.destino)
        self.assertEqual(res["status"], "OK")
        with mock.patch("src.backup.file_manager.manager.get_agent_date", return_value=AGORA), \
                mock.patch("time.sleep"):
            pronto = backup_job.processar_hikcentral(self._equipamento(), Path("."), None, "scheduled",
                                                     somente_preparar=True)
        self.assertEqual(pronto["status"], "PRONTO")
        self.assertEqual([nome for _, nome in pronto["arquivos_origem"]], [NOME])


if __name__ == "__main__":
    unittest.main()
