import base64
import os
import sys
import uuid
from pathlib import Path

# Add server/api to path
API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

os.environ["SECRET_KEY"] = "test_secret_key_1234567890123456789012"
os.environ["FERNET_KEY"] = "dGVzdF9mZXJuZXRfa2V5XzMyX2J5dGVzX2xvbmdfIQ=="
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("ADMIN_PASSWORD", "test")

from models import NVR, NVRCamera
from services import email_service
from services.email_service import MAX_OFFLINE_IMAGES, send_backup_report, send_customer_report


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeQuery:
    """Simula db.query(...).filter(...).first()/.all() para NVR e NVRCamera."""

    def __init__(self, rows, model):
        self.rows, self.model = rows, model

    def filter(self, *criteria):
        rows = self.rows
        for c in criteria:
            col = c.left.key if hasattr(c.left, "key") else c.left.name
            val = c.right.value
            attr = {"client_id": "machine_id"}.get(col, col)
            rows = [r for r in rows if getattr(r, attr) == val]
        return _FakeQuery(rows, self.model)

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)


class _FakeDB:
    def __init__(self, nvrs, cams):
        self.data = {NVR: nvrs, NVRCamera: cams}

    def query(self, model):
        return _FakeQuery(self.data.get(model, []), model)


JPEG = b"\xff\xd8\xff\xe0fake-jpeg"
B64 = base64.b64encode(JPEG).decode()


def _setup(n_cams, with_image=lambda ch: True):
    machine_id = uuid.uuid4()
    nvr = _Obj(id=uuid.uuid4(), machine_id=machine_id, name="NVR Portaria")
    cams_db = [
        _Obj(nvr_id=nvr.id, canal=ch, perfect_image_base64=B64 if with_image(ch) else None)
        for ch in range(1, n_cams + 1)
    ]
    results = [{
        "nome": "NVR Portaria",
        "status": "OK",
        "cameras": [
            {"canal": ch, "nome": f"Cam {ch}", "status_comunicacao": "OFFLINE"} for ch in range(1, n_cams + 1)
        ] + [{"canal": 99, "nome": "Online", "status_comunicacao": "ONLINE"}],
    }]
    return machine_id, _FakeDB([nvr], cams_db), results


def _capture():
    sent = {"messages": []}
    email_service._smtp_config = lambda db: {"server": "x", "port": 25, "email": "a@b.com", "password": None}

    def _fake_send(msg, cfg, rcpt):
        sent["messages"].append(msg)
        sent.setdefault("msg", msg)
        return True

    email_service._smtp_send = _fake_send
    return sent


def _images(msg):
    return [(p.get_filename(), p.get_content()) for p in msg.iter_attachments() if p.get_content_maintype() == "image"]


def test_offline_images_threading_over_limit():
    machine_id, db, results = _setup(12)
    sent = _capture()
    assert send_backup_report("Maq", "14-10-2026", results, ["t@x.com"], db, machine_id=machine_id)
    assert len(sent["messages"]) == 2

    # E-mail 1 (principal)
    main_msg = sent["messages"][0]
    imgs_main = _images(main_msg)
    assert len(imgs_main) == MAX_OFFLINE_IMAGES == 10
    assert imgs_main[0] == ("Cam 1.jpg", JPEG)
    assert "Online.jpg" not in [f for f, _ in imgs_main]
    body = main_msg.get_body().get_content()
    assert "10 de 12 em anexo" in body and "2 imagem(ns) foram enviadas em resposta" in body

    # E-mail 2 (resposta encadeada)
    reply_msg = sent["messages"][1]
    imgs_reply = _images(reply_msg)
    assert len(imgs_reply) == 2
    assert imgs_reply[0] == ("Cam 11.jpg", JPEG)
    assert imgs_reply[1] == ("Cam 12.jpg", JPEG)
    assert reply_msg["In-Reply-To"] == main_msg["Message-ID"]
    assert reply_msg["References"] == main_msg["Message-ID"]
    assert reply_msg["Subject"] == f"Re: {main_msg['Subject']}"
    assert "11 a 12 de 12 em anexo" in reply_msg.get_body().get_content()


def test_without_image_and_filename_sanitize():
    machine_id, db, results = _setup(3, with_image=lambda ch: ch != 2)
    results[0]["cameras"][0]["nome"] = 'Entrada/Rua: "1"'
    sent = _capture()
    send_backup_report("Maq", "14-10-2026", results, ["t@x.com"], db, machine_id=machine_id)
    names = [f for f, _ in _images(sent["msg"])]
    assert names == ["Entrada_Rua_ _1_.jpg", "Cam 3.jpg"]
    assert "1 câmera(s) offline sem imagem" in sent["msg"].get_body().get_content()


def test_duplicate_names_and_customer_report():
    m1, db1, r1 = _setup(1)
    m2, db2, r2 = _setup(1)
    db = _FakeDB(db1.data[NVR] + db2.data[NVR], db1.data[NVRCamera] + db2.data[NVRCamera])
    sent = _capture()
    send_customer_report(
        "Cliente", str(uuid.uuid4()), "scheduled", None,
        [{"machine_id": m1, "name": "A", "status": "OK", "nvr_results": r1},
         {"machine_id": m2, "name": "B", "status": "OK", "nvr_results": r2}],
        ["t@x.com"], db,
    )
    assert [f for f, _ in _images(sent["msg"])] == ["Cam 1.jpg", "Cam 1 (2).jpg"]


def test_customer_report_threading_over_limit():
    m1, db1, r1 = _setup(8)
    m2, db2, r2 = _setup(6)
    db = _FakeDB(db1.data[NVR] + db2.data[NVR], db1.data[NVRCamera] + db2.data[NVRCamera])
    sent = _capture()
    send_customer_report(
        "Cliente", str(uuid.uuid4()), "scheduled", None,
        [{"machine_id": m1, "name": "A", "status": "OK", "nvr_results": r1},
         {"machine_id": m2, "name": "B", "status": "OK", "nvr_results": r2}],
        ["t@x.com"], db,
    )
    assert len(sent["messages"]) == 2
    assert len(_images(sent["messages"][0])) == 10
    assert len(_images(sent["messages"][1])) == 4
    assert sent["messages"][1]["In-Reply-To"] == sent["messages"][0]["Message-ID"]
    assert sent["messages"][1]["References"] == sent["messages"][0]["Message-ID"]
    assert sent["messages"][1]["Subject"] == f"Re: {sent['messages'][0]['Subject']}"


def test_no_offline_no_note():
    machine_id, db, results = _setup(0)
    sent = _capture()
    send_backup_report("Maq", "14-10-2026", results, ["t@x.com"], db, machine_id=machine_id)
    assert _images(sent["msg"]) == []
    assert "Imagens de referência" not in sent["msg"].get_body().get_content()


def run_all():
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK  {name}")


if __name__ == "__main__":
    run_all()
