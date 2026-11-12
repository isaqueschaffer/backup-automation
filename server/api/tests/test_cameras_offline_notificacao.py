"""Teste da notificação de câmera offline (CAMERA_OFFLINE, services/notificacoes.py): opt-in por câmera
(NVRCamera.notificar_offline), para NVR/DIGIFORT/DEFENSE, com limiar de 15 minutos offline. DIGIFORT/DEFENSE
pareiam por nome (services.galeria_vms.parear_cameras); NVR tradicional pareia por canal físico.
Roda com SQLite em memória (como tests/test_contas_status.py); não precisa de Postgres."""
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
os.environ["FERNET_KEY"] = "dGVzdF9mZXJuZXRfa2V5XzMyX2J5dGVzX2xvbmdfIQ=="
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("ADMIN_PASSWORD", "senha_de_teste")

from database import Base, engine, SessionLocal
from models import Conta, Machine, Notificacao, NVR, NVRCamera
from services.notificacoes import verificar_cameras_offline

AGORA = datetime(2026, 11, 12, 12, 0, 0)

# Só as tabelas necessárias: evita o ARRAY de client_groups.email_to, que o SQLite não suporta
_TABELAS = [Base.metadata.tables[n] for n in ("contas", "clients", "nvrs", "nvr_cameras", "notificacoes")]


def _montar_cenario(db, offline_desde=None, status_comunicacao="OFFLINE", notificar=True):
    conta = Conta(id=uuid.uuid4(), nome="Conta Teste")
    machine = Machine(id=uuid.uuid4(), conta_id=conta.id, name="Maquina Teste", backup_hour=2, backup_minute=0,
                       active=True)
    nvr = NVR(id=uuid.uuid4(), machine_id=machine.id, tipo="DEFENSE", name="Defense Teste", ip="127.0.0.1",
              username="x", password="x", active=True)
    camera = NVRCamera(id=uuid.uuid4(), nvr_id=nvr.id, canal=1, nome="Cam Portaria", notificar_offline=notificar)
    status = {"nome": "Cam Portaria", "status_comunicacao": status_comunicacao}
    if offline_desde is not None:
        status["offline_desde"] = offline_desde.strftime("%Y-%m-%dT%H:%M:%S")
    nvr.last_recording_status = [status]
    db.add_all([conta, machine, nvr, camera])
    db.commit()
    return conta, machine, nvr, camera


def _preparar_db():
    Base.metadata.create_all(bind=engine, tables=_TABELAS)
    return SessionLocal()


def _notificacao_camera(db, camera_id):
    return db.query(Notificacao).filter(
        Notificacao.tipo == "CAMERA_OFFLINE", Notificacao.camera_id == camera_id, Notificacao.resolvido_em.is_(None),
    ).first()


def test_camera_nao_marcada_nao_notifica():
    db = _preparar_db()
    try:
        _, _, _, camera = _montar_cenario(db, offline_desde=AGORA - timedelta(minutes=30), notificar=False)
        verificar_cameras_offline(db, agora=AGORA)
        db.commit()
        assert _notificacao_camera(db, camera.id) is None
    finally:
        db.close()


def test_camera_offline_abaixo_do_limiar_nao_notifica():
    db = _preparar_db()
    try:
        _, _, _, camera = _montar_cenario(db, offline_desde=AGORA - timedelta(minutes=5), notificar=True)
        verificar_cameras_offline(db, agora=AGORA)
        db.commit()
        assert _notificacao_camera(db, camera.id) is None
    finally:
        db.close()


def test_camera_offline_acima_do_limiar_notifica():
    db = _preparar_db()
    try:
        conta, _, nvr, camera = _montar_cenario(db, offline_desde=AGORA - timedelta(minutes=20), notificar=True)
        verificar_cameras_offline(db, agora=AGORA)
        db.commit()
        notif = _notificacao_camera(db, camera.id)
        assert notif is not None
        assert notif.conta_id == conta.id
        assert notif.nvr_id == nvr.id
        assert "Cam Portaria" in notif.titulo
    finally:
        db.close()


def test_camera_volta_online_resolve_notificacao():
    db = _preparar_db()
    try:
        _, _, nvr, camera = _montar_cenario(db, offline_desde=AGORA - timedelta(minutes=20), notificar=True)
        verificar_cameras_offline(db, agora=AGORA)
        db.commit()
        assert _notificacao_camera(db, camera.id) is not None

        nvr.last_recording_status = [{"nome": "Cam Portaria", "status_comunicacao": "ONLINE"}]
        db.commit()
        verificar_cameras_offline(db, agora=AGORA + timedelta(minutes=1))
        db.commit()
        assert _notificacao_camera(db, camera.id) is None
    finally:
        db.close()


def test_camera_nvr_tradicional_pareia_por_canal():
    # NVR tradicional (Intelbras/Hikvision/Motorola): o relatorio do agente identifica a camera pelo canal
    # fisico, nao pelo nome (ao contrario de DIGIFORT/DEFENSE) — services.galeria_vms.status_por_camera
    # tem que escolher essa regra sozinho a partir de `nvr.tipo`.
    db = _preparar_db()
    try:
        conta = Conta(id=uuid.uuid4(), nome="Conta Teste NVR")
        machine = Machine(id=uuid.uuid4(), conta_id=conta.id, name="Maquina NVR", backup_hour=2, backup_minute=0,
                           active=True)
        nvr = NVR(id=uuid.uuid4(), machine_id=machine.id, tipo="NVR", name="NVR Teste", ip="127.0.0.1",
                  username="x", password="x", active=True)
        camera = NVRCamera(id=uuid.uuid4(), nvr_id=nvr.id, canal=3, nome="Nome Qualquer Na Galeria",
                            notificar_offline=True)
        # O nome do relatorio e diferente do nome salvo na Galeria de proposito: so o canal pareia aqui
        nvr.last_recording_status = [{
            "canal": 3, "nome": "CAM03", "status_comunicacao": "OFFLINE",
            "offline_desde": (AGORA - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%S"),
        }]
        db.add_all([conta, machine, nvr, camera])
        db.commit()

        verificar_cameras_offline(db, agora=AGORA)
        db.commit()
        notif = _notificacao_camera(db, camera.id)
        assert notif is not None
        assert notif.nvr_id == nvr.id
    finally:
        db.close()


if __name__ == "__main__":
    test_camera_nao_marcada_nao_notifica()
    test_camera_offline_abaixo_do_limiar_nao_notifica()
    test_camera_offline_acima_do_limiar_notifica()
    test_camera_volta_online_resolve_notificacao()
    test_camera_nvr_tradicional_pareia_por_canal()
    print("OK")
