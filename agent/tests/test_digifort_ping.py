"""
Testes unitários para o monitoramento de câmeras Digifort via Ping ICMP.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.application.webhook_digifort import (
    ping_camera,
    testar_cameras_por_ping,
    get_status_cameras,
    get_detalhes_cameras,
    registrar_queda,
    get_caminho_csv,
    _ultimo_status_cameras,
)
from src.backup.file_manager.copier import calculate_sha256
from src.backup.file_manager.manager import _gerar_mapa_vms


class TestDigifortPing(unittest.TestCase):
    def test_ping_camera_localhost(self):
        """127.0.0.1 deve sempre responder ao ping."""
        self.assertTrue(ping_camera("127.0.0.1", timeout_ms=1000))

    def test_ping_camera_invalido(self):
        """IPs inválidos, vazios ou N/A devem retornar False imediatamente."""
        self.assertFalse(ping_camera(""))
        self.assertFalse(ping_camera("   "))
        self.assertFalse(ping_camera("N/A"))
        self.assertFalse(ping_camera("None"))
        self.assertFalse(ping_camera("0.0.0.0"))
        self.assertFalse(ping_camera("999.999.999.999"))
        self.assertFalse(ping_camera("ip_com_caracteres_invalidos;rm -rf"))
        # Proteção contra CLI argument injection (strings iniciando com hífen)
        self.assertFalse(ping_camera("-t"))
        self.assertFalse(ping_camera("-n 1 127.0.0.1"))

    def test_ping_camera_inacessivel(self):
        """IP não roteável / inexistente (TEST-NET-1: 192.0.2.1) deve retornar False."""
        self.assertFalse(ping_camera("192.0.2.1", timeout_ms=300))

    def test_testar_cameras_por_ping(self):
        """Testa o ping concorrente em lote."""
        cameras = [
            {"Nome": "Cam Local", "IP": "127.0.0.1"},
            {"Nome": "Cam Inexistente", "IP": "192.0.2.1"},
            {"Nome": "Cam Sem IP", "IP": ""},
        ]
        res = testar_cameras_por_ping(cameras, timeout_ms=300)
        self.assertTrue(res.get("Cam Local"))
        self.assertFalse(res.get("Cam Inexistente"))
        self.assertFalse(res.get("Cam Sem IP"))

    def test_get_status_cameras_com_ping(self):
        """Testa o status_dict carregando de um CSV simulado de exportação com ping ativo."""
        csv_conteudo = (
            "Endereço;Nome;Descrição\n"
            "127.0.0.1;01;Camera Local OK\n"
            "192.0.2.1;02;Camera Offline\n"
        )
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv", encoding="utf-8") as f:
            f.write(csv_conteudo)
            f_path = f.name

        try:
            status_dict = get_status_cameras(caminho_export=f_path, realizar_ping=True)
            self.assertEqual(status_dict.get("Camera Local OK"), "OK")
            self.assertEqual(status_dict.get("Camera Offline"), "FALHA")

            # Testa get_detalhes_cameras passando status_dict pré-calculado
            detalhes = get_detalhes_cameras(caminho_export=f_path, status_dict=status_dict)
            self.assertEqual(len(detalhes), 2)
            self.assertEqual(detalhes[0]["nome"], "Camera Local OK")
            self.assertEqual(detalhes[0]["status"], "OK")
            self.assertEqual(detalhes[1]["nome"], "Camera Offline")
            self.assertEqual(detalhes[1]["status"], "FALHA")
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_registrar_queda_no_op(self):
        """Valida que registrar_queda não realiza escritas nem gera arquivos em disco."""
        caminho_alvo = Path(tempfile.gettempdir()) / "arquivo_nao_deve_existir.csv"
        if caminho_alvo.exists():
            caminho_alvo.unlink()
        
        # Invocação da função descontinuada
        registrar_queda("Camera Teste", "Queda de Comunicacao")
        
        # O arquivo nunca deve ser criado
        self.assertFalse(caminho_alvo.exists())

    def test_get_status_cameras_modo_memoria(self):
        """Valida que get_status_cameras(realizar_ping=False) obtém status em memória sem ler arquivos."""
        _ultimo_status_cameras["Camera Memoria 01"] = "OK"
        _ultimo_status_cameras["Camera Memoria 02"] = "FALHA"
        
        # CSV de exportação simulado
        csv_conteudo = (
            "Endereço;Nome;Descrição\n"
            "10.0.0.1;01;Camera Memoria 01\n"
            "10.0.0.2;02;Camera Memoria 02\n"
        )
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv", encoding="utf-8") as f:
            f.write(csv_conteudo)
            f_path = f.name

        try:
            status = get_status_cameras(caminho_export=f_path, caminho_log="arquivo_inexistente.csv", realizar_ping=False)
            self.assertEqual(status.get("Camera Memoria 01"), "OK")
            self.assertEqual(status.get("Camera Memoria 02"), "FALHA")
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_get_caminho_csv_vazio(self):
        """Valida que get_caminho_csv() sempre retorna string vazia."""
        self.assertEqual(get_caminho_csv(), "")
        self.assertEqual(get_caminho_csv("caminho_qualquer.csv"), "")

    def test_copier_calculate_sha256_1mb_chunk(self):
        """Valida que o cálculo de SHA-256 com chunk de 1MB funciona com exatidão."""
        import hashlib
        dados = b"x" * (2 * 1024 * 1024 + 123)  # > 2MB de dados
        hash_esperado = hashlib.sha256(dados).hexdigest()
        
        with tempfile.NamedTemporaryFile("wb", delete=False) as f:
            f.write(dados)
            temp_path = Path(f.name)
            
        try:
            hash_calculado = calculate_sha256(temp_path)
            self.assertEqual(hash_calculado, hash_esperado)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_gerar_mapa_vms_online_e_offline(self):
        """Verifica se câmeras offline (FALHA) geram 0 dias e mapa vazio no backup."""
        # Câmera OK
        total_ok, mapa_ok, dias_ok = _gerar_mapa_vms(True)
        self.assertEqual(total_ok, 15)
        self.assertEqual(mapa_ok, "█" * 15)
        self.assertEqual(len(dias_ok), 15)

        # Câmera Falha (offline)
        total_falha, mapa_falha, dias_falha = _gerar_mapa_vms(False)
        self.assertEqual(total_falha, 0)
        self.assertEqual(mapa_falha, "░" * 15)
        self.assertEqual(dias_falha, [])


if __name__ == "__main__":
    unittest.main()
