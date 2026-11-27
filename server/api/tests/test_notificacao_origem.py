"""Teste da identificação de origem (cliente ou máquina) nas notificações de equipamentos."""
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
os.environ["FERNET_KEY"] = "dHJpbGFuLWNoYXZlLWRlLXRlc3RlLTMyLWJ5dGVzISE="
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("ADMIN_PASSWORD", "senha_de_teste")

from database import Base, engine, SessionLocal
from models import Conta, Customer, Machine, Notificacao, NVR, NVRCamera
from services.notificacoes import (
    _origem_equipamento,
    verificar_cameras_offline,
    situacoes_alarme,
    situacoes_antena,
    _texto_alerta_olt,
)

AGORA = datetime(2026, 11, 16, 12, 0, 0)
_TABELAS = [Base.metadata.tables[n] for n in ("contas", "client_groups", "clients", "nvrs", "nvr_cameras", "notificacoes")]


def _db():
    Base.metadata.create_all(bind=engine, tables=_TABELAS)
    return SessionLocal()


def test_origem_equipamento_com_cliente():
    db = _db()
    try:
        conta = Conta(id=uuid.uuid4(), nome="Conta Teste", tipo="INTEGRADOR")
        customer = Customer(id=uuid.uuid4(), conta_id=conta.id, name="Condomínio Solar")
        mid = uuid.uuid4()
        machine = Machine(id=mid, conta_id=conta.id, customer_id=customer.id, name="Servidor Portaria",
                          api_key_hash=mid.hex, api_key_prefix="sk_t", active=True)
        nvr = NVR(id=uuid.uuid4(), machine_id=machine.id, tipo="DEFENSE", name="NVR Principal",
                  ip="127.0.0.1", username="admin", password="enc", active=True)
        db.add_all([conta, customer, machine, nvr])
        db.commit()

        nvr = db.get(NVR, nvr.id)
        assert _origem_equipamento(nvr) == "do cliente 'Condomínio Solar'"
    finally:
        db.close()


def test_origem_equipamento_sem_cliente_com_maquina():
    db = _db()
    try:
        conta = Conta(id=uuid.uuid4(), nome="Conta Teste", tipo="INTEGRADOR")
        mid = uuid.uuid4()
        machine = Machine(id=mid, conta_id=conta.id, name="Servidor Portaria",
                          api_key_hash=mid.hex, api_key_prefix="sk_t", active=True)
        nvr = NVR(id=uuid.uuid4(), machine_id=machine.id, tipo="DEFENSE", name="NVR Principal",
                  ip="127.0.0.1", username="admin", password="enc", active=True)
        db.add_all([conta, machine, nvr])
        db.commit()

        nvr = db.get(NVR, nvr.id)
        assert _origem_equipamento(nvr) == "da máquina 'Servidor Portaria'"
    finally:
        db.close()


def test_origem_equipamento_sem_maquina():
    nvr = NVR(id=uuid.uuid4(), tipo="DEFENSE", name="NVR Isolado", ip="127.0.0.1", username="admin", password="enc", active=True)
    assert _origem_equipamento(nvr) == ""


def test_camera_offline_titulo_e_mensagem_com_cliente():
    db = _db()
    try:
        conta = Conta(id=uuid.uuid4(), nome="Conta Teste", tipo="INTEGRADOR")
        customer = Customer(id=uuid.uuid4(), conta_id=conta.id, name="Condomínio Solar")
        mid = uuid.uuid4()
        machine = Machine(id=mid, conta_id=conta.id, customer_id=customer.id, name="Servidor Portaria",
                          api_key_hash=mid.hex, api_key_prefix="sk_t", active=True)
        nvr = NVR(id=uuid.uuid4(), machine_id=machine.id, tipo="NVR", name="NVR 01",
                  ip="127.0.0.1", username="admin", password="enc", active=True)
        camera = NVRCamera(id=uuid.uuid4(), nvr_id=nvr.id, canal=1, nome="PERIMETRO 21", notificar_offline=True)
        nvr.last_recording_status = [{
            "canal": 1, "nome": "PERIMETRO 21", "status_comunicacao": "OFFLINE",
            "offline_desde": (AGORA - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%S"),
        }]
        db.add_all([conta, customer, machine, nvr, camera])
        db.commit()

        verificar_cameras_offline(db, agora=AGORA)
        db.commit()

        notif = db.query(Notificacao).filter_by(camera_id=camera.id).one()
        assert notif.titulo == "Câmera 'PERIMETRO 21' offline em 'NVR 01' do cliente 'Condomínio Solar'"
        assert notif.mensagem == "A câmera 'PERIMETRO 21' do equipamento 'NVR 01' do cliente 'Condomínio Solar' está offline há 5h."
    finally:
        db.close()


def test_camera_offline_titulo_e_mensagem_sem_cliente_com_maquina():
    db = _db()
    try:
        conta = Conta(id=uuid.uuid4(), nome="Conta Teste", tipo="INTEGRADOR")
        mid = uuid.uuid4()
        machine = Machine(id=mid, conta_id=conta.id, name="Maquina X",
                          api_key_hash=mid.hex, api_key_prefix="sk_t", active=True)
        nvr = NVR(id=uuid.uuid4(), machine_id=machine.id, tipo="NVR", name="NVR 01",
                  ip="127.0.0.1", username="admin", password="enc", active=True)
        camera = NVRCamera(id=uuid.uuid4(), nvr_id=nvr.id, canal=1, nome="PERIMETRO 21", notificar_offline=True)
        nvr.last_recording_status = [{
            "canal": 1, "nome": "PERIMETRO 21", "status_comunicacao": "OFFLINE",
            "offline_desde": (AGORA - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%S"),
        }]
        db.add_all([conta, machine, nvr, camera])
        db.commit()

        verificar_cameras_offline(db, agora=AGORA)
        db.commit()

        notif = db.query(Notificacao).filter_by(camera_id=camera.id).one()
        assert notif.titulo == "Câmera 'PERIMETRO 21' offline em 'NVR 01' da máquina 'Maquina X'"
        assert notif.mensagem == "A câmera 'PERIMETRO 21' do equipamento 'NVR 01' da máquina 'Maquina X' está offline há 5h."
    finally:
        db.close()


def test_alarmes_antenas_e_olts_incluem_origem():
    db = _db()
    try:
        conta = Conta(id=uuid.uuid4(), nome="Conta Teste", tipo="INTEGRADOR")
        customer = Customer(id=uuid.uuid4(), conta_id=conta.id, name="Empresa Alfa")
        mid = uuid.uuid4()
        machine = Machine(id=mid, conta_id=conta.id, customer_id=customer.id, name="Host 1",
                          api_key_hash=mid.hex, api_key_prefix="sk_t", active=True)

        nvr_alarm = NVR(id=uuid.uuid4(), machine_id=machine.id, tipo="DEFENSE", name="Defense 1",
                        ip="127.0.0.1", username="admin", password="enc", active=True,
                        alarmes_notificar=["10"])
        nvr_alarm.last_alarm_status = {
            "atualizado_em": AGORA.strftime("%Y-%m-%dT%H:%M:%S"),
            "alarmes": [{"id": 10, "nome": "Central Principal", "status": 0, "particoes": []}]
        }

        nvr_antena = NVR(id=uuid.uuid4(), machine_id=machine.id, tipo="ANTENA", name="MikroTik Sede",
                         ip="127.0.0.1", username="admin", password="enc", active=True)
        nvr_antena.antena_status = {
            "atualizado_em": AGORA.strftime("%Y-%m-%dT%H:%M:%S"),
            "antenas": [{"mac": "AA:BB:CC:DD:EE:FF", "nome": "Setor A", "status": "OFFLINE", "notificar": True,
                         "offline_desde": (AGORA - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%S")}]
        }

        nvr_olt = NVR(id=uuid.uuid4(), machine_id=machine.id, tipo="OLT", name="OLT Core",
                      ip="127.0.0.1", username="admin", password="enc", active=True)

        db.add_all([conta, customer, machine, nvr_alarm, nvr_antena, nvr_olt])
        db.commit()

        sit_alarme = situacoes_alarme(db.get(NVR, nvr_alarm.id))
        assert "10:DESCONECTADA" in sit_alarme
        tit_alarme, msg_alarme = sit_alarme["10:DESCONECTADA"]
        assert "do cliente 'Empresa Alfa'" in tit_alarme
        assert "do cliente 'Empresa Alfa'" in msg_alarme

        sit_antena = situacoes_antena(db.get(NVR, nvr_antena.id), AGORA)
        tit_ant, msg_ant = sit_antena["AA:BB:CC:DD:EE:FF"]
        assert "do cliente 'Empresa Alfa'" in tit_ant
        assert "do cliente 'Empresa Alfa'" in msg_ant

        tit_olt, msg_olt = _texto_alerta_olt("onu", db.get(NVR, nvr_olt.id), "OLT Core", [{"slot": 1, "pon": 1, "onu": 1, "estado": "OFFLINE"}])
        assert tit_olt == "1 ONU(s) offline na OLT 'OLT Core' do cliente 'Empresa Alfa'"
        assert "na OLT 'OLT Core' do cliente 'Empresa Alfa'" in msg_olt
    finally:
        db.close()


if __name__ == "__main__":
    test_origem_equipamento_com_cliente()
    test_origem_equipamento_sem_cliente_com_maquina()
    test_origem_equipamento_sem_maquina()
    test_camera_offline_titulo_e_mensagem_com_cliente()
    test_camera_offline_titulo_e_mensagem_sem_cliente_com_maquina()
    test_alarmes_antenas_e_olts_incluem_origem()
    print("ALL TESTS PASSED")
