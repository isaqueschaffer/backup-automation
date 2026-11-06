import os
import shutil
import sys
import tempfile
import types
import uuid
from pathlib import Path

# Adiciona server/api ao path
API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

# Mock settings antes de importar storage_service
os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
os.environ["FERNET_KEY"] = "dGVzdF9mZXJuZXRfa2V5XzMyX2J5dGVzX2xvbmdfIQ=="
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("ADMIN_PASSWORD", "senha_de_teste")

from config import settings
from services.storage_service import (
    SEM_CLIENTE_DIR,
    _sanitize_name,
    get_zip_path,
    pasta_canonica_da_maquina,
    renomear_pasta_do_cliente,
    reorganizar_maquina,
    save_zip,
)


def test_save_zip_com_cliente():
    print("Testing save_zip com cliente...")
    with tempfile.TemporaryDirectory() as tmpdir:
        settings.BACKUP_STORAGE_PATH = tmpdir
        customer = types.SimpleNamespace(id=uuid.uuid4(), name="Cliente Alpha")
        m_id = uuid.uuid4()
        m_name = "NVR Sede"
        conteudo = b"dados_zip_alpha"

        saved = save_zip(m_id, m_name, "23-10-2026", "NVR", "backup_sede.zip", conteudo, customer=customer)

        expected_cliente = f"{_sanitize_name(customer.name)}_{customer.id}"
        expected_maquina = f"{_sanitize_name(m_name)}_{m_id}"
        expected_path = Path(tmpdir) / expected_cliente / expected_maquina / "backup_sede.zip"

        assert saved == expected_path, f"Esperado {expected_path}, obtido {saved}"
        assert saved.is_file()
        assert saved.read_bytes() == conteudo
    print("  [OK] save_zip com cliente gravou na hierarquia correta.")


def test_save_zip_sem_cliente():
    print("Testing save_zip sem cliente...")
    with tempfile.TemporaryDirectory() as tmpdir:
        settings.BACKUP_STORAGE_PATH = tmpdir
        m_id = uuid.uuid4()
        m_name = "OLT Filial"
        conteudo = b"dados_zip_sem_cliente"

        saved = save_zip(m_id, m_name, "23-10-2026", "OLT", "backup_olt.zip", conteudo, customer=None)

        expected_maquina = f"{_sanitize_name(m_name)}_{m_id}"
        expected_path = Path(tmpdir) / SEM_CLIENTE_DIR / expected_maquina / "backup_olt.zip"

        assert saved == expected_path, f"Esperado {expected_path}, obtido {saved}"
        assert saved.is_file()
        assert saved.read_bytes() == conteudo
    print("  [OK] save_zip sem cliente gravou em _sem_cliente.")


def test_get_zip_path_pasta_legada_raiz():
    print("Testing get_zip_path em pasta legada na raiz com cliente informado...")
    with tempfile.TemporaryDirectory() as tmpdir:
        settings.BACKUP_STORAGE_PATH = tmpdir
        customer = types.SimpleNamespace(id=uuid.uuid4(), name="Cliente Beta")
        m_id = uuid.uuid4()
        m_name = "NVR Fabrica"

        # Cria pasta legada na raiz: <MAQUINA>_<uuid>/backup_x.zip
        legado_dir = Path(tmpdir) / f"{_sanitize_name(m_name)}_{m_id}"
        legado_dir.mkdir(parents=True, exist_ok=True)
        legado_file = legado_dir / "backup_fabrica.zip"
        legado_file.write_bytes(b"conteudo_legado_raiz")

        # Busca informando o cliente novo
        found = get_zip_path(m_id, m_name, "backup_fabrica.zip", customer=customer)

        assert found == legado_file, f"Esperado {legado_file}, obtido {found}"
        assert found.read_bytes() == b"conteudo_legado_raiz"
    print("  [OK] get_zip_path localizou arquivo na pasta legada da raiz.")


def test_lookup_uuid_apos_renomear_cliente_e_mover_maquina():
    print("Testing lookup por UUID após renomear cliente e mover máquina...")
    with tempfile.TemporaryDirectory() as tmpdir:
        settings.BACKUP_STORAGE_PATH = tmpdir
        cust_a_id = uuid.uuid4()
        cust_a = types.SimpleNamespace(id=cust_a_id, name="Cliente Original")
        m_id = uuid.uuid4()
        m_name = "PABX Central"

        # Salva o arquivo sob Cliente Original
        saved = save_zip(m_id, m_name, "23-10-2026", "PABX", "backup_pabx.zip", b"pabx_data", customer=cust_a)
        assert saved.is_file()

        # 4a: Renomeia a pasta do cliente no disco (mantendo _<uuid>)
        pasta_antiga = Path(tmpdir) / f"Cliente_Original_{cust_a_id}"
        pasta_renomeada = Path(tmpdir) / f"Cliente_Novo_Nome_{cust_a_id}"
        shutil.move(str(pasta_antiga), str(pasta_renomeada))

        # Cliente com nome atualizado no banco/memória
        cust_a_atualizado = types.SimpleNamespace(id=cust_a_id, name="Cliente Novo Nome")
        found_apos_rename = get_zip_path(m_id, m_name, "backup_pabx.zip", customer=cust_a_atualizado)
        assert found_apos_rename is not None
        assert found_apos_rename.exists()
        assert found_apos_rename.read_bytes() == b"pabx_data"

        # 4b: Máquina migrada para outro cliente (cust_b) sem mover os arquivos fisicamente ainda
        cust_b = types.SimpleNamespace(id=uuid.uuid4(), name="Cliente Destino")
        found_outro_cliente = get_zip_path(m_id, m_name, "backup_pabx.zip", customer=cust_b)
        assert found_outro_cliente is not None
        assert found_outro_cliente.exists()
        assert found_outro_cliente.read_bytes() == b"pabx_data"
    print("  [OK] lookup por UUID funcionou após renomeação e troca de cliente.")


def test_escrita_continua_na_pasta_legada():
    print("Testing escrita em pasta legada existente sem dividir a máquina...")
    with tempfile.TemporaryDirectory() as tmpdir:
        settings.BACKUP_STORAGE_PATH = tmpdir
        customer = types.SimpleNamespace(id=uuid.uuid4(), name="Cliente Gama")
        m_id = uuid.uuid4()
        m_name = "Mikrotik Borda"

        # Cria pasta legada na raiz antes da escrita
        legado_dir = Path(tmpdir) / f"{_sanitize_name(m_name)}_{m_id}"
        legado_dir.mkdir(parents=True, exist_ok=True)

        canonica = pasta_canonica_da_maquina(m_id, m_name, customer)
        assert not canonica.exists()

        # Salva o arquivo passando o cliente
        saved = save_zip(m_id, m_name, "23-10-2026", "NVR", "backup_novo.zip", b"novo_legado", customer=customer)

        assert saved == legado_dir / "backup_novo.zip"
        assert saved.is_file()
        assert not canonica.exists(), "Não deve criar pasta canônica quando já existe pasta legada"
    print("  [OK] escrita manteve os arquivos na pasta legada existente.")


def test_reorganizar_maquina_mover():
    print("Testing reorganizar_maquina mover com aplicar=False e aplicar=True...")
    with tempfile.TemporaryDirectory() as tmpdir:
        settings.BACKUP_STORAGE_PATH = tmpdir
        customer = types.SimpleNamespace(id=uuid.uuid4(), name="Cliente Delta")
        m_id = uuid.uuid4()
        m_name = "NVR Deposito"

        # Cria pasta legada com arquivos
        legado_dir = Path(tmpdir) / f"{_sanitize_name(m_name)}_{m_id}"
        legado_dir.mkdir(parents=True, exist_ok=True)
        (legado_dir / "backup_1.zip").write_bytes(b"b1")
        (legado_dir / "backup_2.zip").write_bytes(b"b2")

        canonica = pasta_canonica_da_maquina(m_id, m_name, customer)

        # 6a: Simulação (aplicar=False)
        sim = reorganizar_maquina(m_id, m_name, customer=customer, aplicar=False)
        assert sim["acao"] == "mover"
        assert sim["origem"] == str(legado_dir)
        assert sim["destino"] == str(canonica)
        assert sim["conflitos"] == []
        assert legado_dir.is_dir()
        assert not canonica.exists()

        # 6b: Execução (aplicar=True)
        real = reorganizar_maquina(m_id, m_name, customer=customer, aplicar=True)
        assert real["acao"] == "mover"
        assert real["origem"] == str(legado_dir)
        assert real["destino"] == str(canonica)
        assert real["conflitos"] == []
        assert not legado_dir.exists()
        assert canonica.is_dir()
        assert (canonica / "backup_1.zip").read_bytes() == b"b1"
        assert (canonica / "backup_2.zip").read_bytes() == b"b2"

        # 6c: Chamada subsequente retorna ja_ok
        ja_ok = reorganizar_maquina(m_id, m_name, customer=customer, aplicar=True)
        assert ja_ok["acao"] == "ja_ok"
    print("  [OK] reorganizar_maquina moveu preservando arquivos e respeitou aplicar=False.")


def test_reorganizar_maquina_unir_conflito():
    print("Testing reorganizar_maquina unir com resolução de conflito...")
    with tempfile.TemporaryDirectory() as tmpdir:
        settings.BACKUP_STORAGE_PATH = tmpdir
        customer = types.SimpleNamespace(id=uuid.uuid4(), name="Cliente Epsilon")
        m_id = uuid.uuid4()
        m_name = "NVR Recepcao"

        # Canônica já existe com arquivo comum e arquivo exclusivo
        canonica = pasta_canonica_da_maquina(m_id, m_name, customer)
        canonica.mkdir(parents=True, exist_ok=True)
        (canonica / "backup_comum.zip").write_bytes(b"versao_canonica")
        (canonica / "exclusivo_canonica.zip").write_bytes(b"canonica_only")

        # Pasta legada na raiz com mesmo arquivo comum e arquivo exclusivo legado
        legado_dir = Path(tmpdir) / f"{_sanitize_name(m_name)}_{m_id}"
        legado_dir.mkdir(parents=True, exist_ok=True)
        (legado_dir / "backup_comum.zip").write_bytes(b"versao_legada")
        (legado_dir / "exclusivo_legado.zip").write_bytes(b"legado_only")

        resultado = reorganizar_maquina(m_id, m_name, customer=customer, aplicar=True)

        assert resultado["acao"] == "unir"
        assert "backup_comum.zip" in resultado["conflitos"]

        # Não sobrescreveu o arquivo da canônica
        assert (canonica / "backup_comum.zip").read_bytes() == b"versao_canonica"
        assert (canonica / "exclusivo_canonica.zip").read_bytes() == b"canonica_only"

        # Moveu o arquivo não conflitante
        assert (canonica / "exclusivo_legado.zip").read_bytes() == b"legado_only"

        # Origem não foi apagada porque continha o arquivo em conflito
        assert legado_dir.exists()
        assert (legado_dir / "backup_comum.zip").read_bytes() == b"versao_legada"
        assert not (legado_dir / "exclusivo_legado.zip").exists()
    print("  [OK] reorganizar_maquina unir preservou arquivos conflitantes e moveu os demais.")


def test_renomear_pasta_do_cliente():
    print("Testing renomear_pasta_do_cliente preservando sufixo UUID...")
    with tempfile.TemporaryDirectory() as tmpdir:
        settings.BACKUP_STORAGE_PATH = tmpdir
        c_id = uuid.uuid4()
        pasta_antiga = Path(tmpdir) / f"Nome_Antigo_{c_id}"
        pasta_antiga.mkdir(parents=True, exist_ok=True)
        (pasta_antiga / "marcador.txt").write_text("ok", encoding="utf-8")

        renomeado = renomear_pasta_do_cliente(c_id, "Nome Novo")
        assert renomeado is True
        assert not pasta_antiga.exists()

        esperada_nova = Path(tmpdir) / f"Nome_Novo_{c_id}"
        assert esperada_nova.is_dir()
        assert esperada_nova.name.endswith(f"_{c_id}")
        assert (esperada_nova / "marcador.txt").read_text(encoding="utf-8") == "ok"

        # Renomear para o mesmo nome retorna False
        repetido = renomear_pasta_do_cliente(c_id, "Nome Novo")
        assert repetido is False

        # Cliente inexistente retorna False
        inexistente = renomear_pasta_do_cliente(uuid.uuid4(), "Outro")
        assert inexistente is False
    print("  [OK] renomear_pasta_do_cliente renomeou e preservou o UUID.")


def run_all():
    test_save_zip_com_cliente()
    test_save_zip_sem_cliente()
    test_get_zip_path_pasta_legada_raiz()
    test_lookup_uuid_apos_renomear_cliente_e_mover_maquina()
    test_escrita_continua_na_pasta_legada()
    test_reorganizar_maquina_mover()
    test_reorganizar_maquina_unir_conflito()
    test_renomear_pasta_do_cliente()
    print("\nTODOS OS TESTES DE HIERARQUIA PASSARAM COM SUCESSO! [OK]")


if __name__ == "__main__":
    run_all()
