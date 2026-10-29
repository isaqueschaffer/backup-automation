"""Teste de integração e isolamento entre Contas multi-inquilino.

AVISO:
- Roda EXCLUSIVAMENTE em container contra o PostgreSQL do ambiente local (server/docker-compose.local.yml).
- Exige TRILAN_TESTE_ISOLAMENTO=1 e o pacote httpx (instalado no container de teste).
- Cria registros de teste com sufixo UUID aleatório e apaga tudo no bloco `finally`.
- NUNCA executar contra o banco de produção!
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

# Adiciona server/api ao path
API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

# Não sobrescrever DATABASE_URL, SECRET_KEY, FERNET_KEY, ADMIN_PASSWORD (vêm do container)

def _ambiente_habilitado() -> bool:
    return os.environ.get("TRILAN_TESTE_ISOLAMENTO") == "1"


def test_isolamento_contas():
    if not _ambiente_habilitado():
        return

    from fastapi.testclient import TestClient
    from main import app
    from database import SessionLocal
    from models import Plano, Conta, Usuario, Customer, Machine, NVR, Backup, AgentLog, Setting
    from services import senhas
    from auth import generate_api_key
    from services.crypto_service import encrypt
    from config import settings

    sufixo = uuid4().hex[:8]

    contaA_id = uuid4()
    contaB_id = uuid4()
    contaV_id = uuid4()
    cA_id = uuid4()
    cB_id = uuid4()
    mA_id = uuid4()
    mB_id = uuid4()
    mV_id = uuid4()
    nvrV_id = uuid4()
    usr_adminA_id = uuid4()
    usr_leituraA_id = uuid4()
    usr_adminB_id = uuid4()
    usr_adminV_id = uuid4()
    plano_criado_id = None

    raw_key_A, hash_A = generate_api_key()
    raw_key_B, hash_B = generate_api_key()
    raw_key_V, hash_V = generate_api_key()

    # 1. Montagem dos dados
    with SessionLocal() as db:
        plano = db.query(Plano).filter(Plano.ativo == True).first()
        if not plano:
            plano = Plano(id=uuid4(), nome=f"Plano-{sufixo}", duracao_dias=30, ativo=True)
            db.add(plano)
            db.commit()
            db.refresh(plano)
            plano_criado_id = plano.id

        contaA = Conta(
            id=contaA_id,
            nome=f"ContaA-{sufixo}",
            tipo="INTEGRADOR",
            email_contato=f"contato-a-{sufixo}@teste.local",
            plano_id=plano.id,
            expira_em=datetime.utcnow() + timedelta(days=30),
            ativo=True,
            avisos_enviados=[],
        )
        contaB = Conta(
            id=contaB_id,
            nome=f"ContaB-{sufixo}",
            tipo="CLIENTE_FINAL",
            email_contato=f"contato-b-{sufixo}@teste.local",
            plano_id=plano.id,
            expira_em=datetime.utcnow() + timedelta(days=30),
            ativo=True,
            avisos_enviados=[],
        )
        contaV = Conta(
            id=contaV_id,
            nome=f"ContaV-{sufixo}",
            tipo="INTEGRADOR",
            email_contato=f"contato-v-{sufixo}@teste.local",
            plano_id=plano.id,
            expira_em=datetime.utcnow() - timedelta(days=1),
            ativo=True,
            avisos_enviados=[],
        )
        db.add_all([contaA, contaB, contaV])

        email_adminA = f"admina-{sufixo}@teste.local"
        email_leituraA = f"leituraa-{sufixo}@teste.local"
        email_adminB = f"adminb-{sufixo}@teste.local"
        email_adminV = f"adminv-{sufixo}@teste.local"
        senha_hash = senhas.gerar_hash("SenhaTeste123")

        u_adminA = Usuario(
            id=usr_adminA_id,
            conta_id=contaA_id,
            nome="adminA",
            email=email_adminA,
            senha_hash=senha_hash,
            papel="ADMIN",
            ativo=True,
        )
        u_leituraA = Usuario(
            id=usr_leituraA_id,
            conta_id=contaA_id,
            nome="leituraA",
            email=email_leituraA,
            senha_hash=senha_hash,
            papel="LEITURA",
            ativo=True,
        )
        u_adminB = Usuario(
            id=usr_adminB_id,
            conta_id=contaB_id,
            nome="adminB",
            email=email_adminB,
            senha_hash=senha_hash,
            papel="ADMIN",
            ativo=True,
        )
        u_adminV = Usuario(
            id=usr_adminV_id,
            conta_id=contaV_id,
            nome="adminV",
            email=email_adminV,
            senha_hash=senha_hash,
            papel="ADMIN",
            ativo=True,
        )
        db.add_all([u_adminA, u_leituraA, u_adminB, u_adminV])

        cA = Customer(
            id=cA_id,
            conta_id=contaA_id,
            name=f"ClienteA-{sufixo}",
            active=True,
        )
        cB = Customer(
            id=cB_id,
            conta_id=contaB_id,
            name=f"ClienteB-{sufixo}",
            active=True,
        )
        db.add_all([cA, cB])

        mA = Machine(
            id=mA_id,
            conta_id=contaA_id,
            customer_id=cA_id,
            name=f"MachineA-{sufixo}",
            api_key_hash=hash_A,
            api_key_prefix=raw_key_A[:10],
            active=True,
        )
        mB = Machine(
            id=mB_id,
            conta_id=contaB_id,
            customer_id=cB_id,
            name=f"MachineB-{sufixo}",
            api_key_hash=hash_B,
            api_key_prefix=raw_key_B[:10],
            active=True,
        )
        mV = Machine(
            id=mV_id,
            conta_id=contaV_id,
            customer_id=None,
            name=f"MachineV-{sufixo}",
            api_key_hash=hash_V,
            api_key_prefix=raw_key_V[:10],
            active=True,
        )
        db.add_all([mA, mB, mV])

        nvrV = NVR(
            id=nvrV_id,
            machine_id=mV_id,
            name=f"NVR-V-{sufixo}",
            tipo="NVR",
            ip="10.0.0.1",
            username="u",
            password=encrypt("p"),
            active=True,
        )
        db.add(nvrV)

        # Senha super admin legado
        setting_pwd = db.query(Setting).filter(Setting.key == "admin_password_hash").first()
        super_pw = setting_pwd.value if (setting_pwd and setting_pwd.value) else settings.ADMIN_PASSWORD

        db.commit()

    try:
        client = TestClient(app)

        # Logins
        r_login_A = client.post("/api/v1/auth/login", json={"email": email_adminA, "password": "SenhaTeste123"})
        assert r_login_A.status_code == 200, f"Falha no login adminA: {r_login_A.text}"
        headers_A = {"Authorization": f"Bearer {r_login_A.json()['access_token']}"}

        r_login_leituraA = client.post("/api/v1/auth/login", json={"email": email_leituraA, "password": "SenhaTeste123"})
        assert r_login_leituraA.status_code == 200, f"Falha no login leituraA: {r_login_leituraA.text}"
        headers_leituraA = {"Authorization": f"Bearer {r_login_leituraA.json()['access_token']}"}

        r_login_B = client.post("/api/v1/auth/login", json={"email": email_adminB, "password": "SenhaTeste123"})
        assert r_login_B.status_code == 200, f"Falha no login adminB: {r_login_B.text}"
        headers_B = {"Authorization": f"Bearer {r_login_B.json()['access_token']}"}

        r_login_V = client.post("/api/v1/auth/login", json={"email": email_adminV, "password": "SenhaTeste123"})
        assert r_login_V.status_code == 200, f"Falha no login adminV: {r_login_V.text}"
        headers_V = {"Authorization": f"Bearer {r_login_V.json()['access_token']}"}

        r_login_super = client.post("/api/v1/auth/login", json={"password": super_pw})
        assert r_login_super.status_code == 200, f"Falha no login super admin: {r_login_super.text}"
        headers_super = {"Authorization": f"Bearer {r_login_super.json()['access_token']}"}

        # 1. adminA GET /api/v1/clients -> contém cA e NÃO contém cB
        r = client.get("/api/v1/clients", headers=headers_A)
        assert r.status_code == 200, f"adminA list clients falhou: {r.status_code}"
        ids_A = [c["id"] for c in r.json()]
        assert str(cA_id) in ids_A, "cA deve constar na listagem de adminA"
        assert str(cB_id) not in ids_A, "cB NÃO deve constar na listagem de adminA"

        # 2. adminA cross-account: GET /clients/{cB} -> 404, /machines/{mB} -> 404, /machines/{mB}/equipamentos -> 404, /backups?machine_id={mB} -> 200 items=[]
        r = client.get(f"/api/v1/clients/{cB_id}", headers=headers_A)
        assert r.status_code == 404, f"Esperado 404 para cliente de outra conta, obteve {r.status_code}"

        r = client.get(f"/api/v1/machines/{mB_id}", headers=headers_A)
        assert r.status_code == 404, f"Esperado 404 para máquina de outra conta, obteve {r.status_code}"

        r = client.get(f"/api/v1/machines/{mB_id}/equipamentos", headers=headers_A)
        assert r.status_code == 404, f"Esperado 404 para equipamentos de máquina de outra conta, obteve {r.status_code}"

        r = client.get(f"/api/v1/backups?machine_id={mB_id}", headers=headers_A)
        assert r.status_code == 200, f"Esperado 200 para listagem de backups, obteve {r.status_code}"
        assert r.json().get("items") == [], f"Esperado items vazio para backups de outra conta, obteve {r.json().get('items')}"

        # 3. adminA POST /api/v1/clients/{cA}/machines/{mB} -> 404
        r = client.post(f"/api/v1/clients/{cA_id}/machines/{mB_id}", headers=headers_A)
        assert r.status_code == 404, f"Esperado 404 ao vincular máquina de outra conta, obteve {r.status_code}"

        # 4. leituraA GET /api/v1/clients -> 200; POST /api/v1/clients -> 403
        r = client.get("/api/v1/clients", headers=headers_leituraA)
        assert r.status_code == 200, f"leituraA GET /clients falhou: {r.status_code}"
        r = client.post("/api/v1/clients", headers=headers_leituraA, json={"name": f"NovoCli-{sufixo}"})
        assert r.status_code == 403, f"Esperado 403 para leituraA criar cliente, obteve {r.status_code}"

        # 5. adminV POST /api/v1/clients -> 403 com "vencida" no detail; GET /auth/me -> status VENCIDA e somente_leitura is True
        r = client.post("/api/v1/clients", headers=headers_V, json={"name": f"CliVencido-{sufixo}"})
        assert r.status_code == 403, f"Esperado 403 para adminV criar cliente, obteve {r.status_code}"
        assert "vencida" in r.json().get("detail", "").lower(), f"Esperado 'vencida' no detail de erro, obteve {r.json()}"

        r = client.get("/api/v1/auth/me", headers=headers_V)
        assert r.status_code == 200, f"adminV GET /auth/me falhou: {r.status_code}"
        me_v = r.json()
        assert me_v.get("conta", {}).get("status") == "VENCIDA", f"Esperado status VENCIDA, obteve {me_v.get('conta')}"
        assert me_v.get("somente_leitura") is True, f"Esperado somente_leitura=True para conta vencida, obteve {me_v.get('somente_leitura')}"

        # 6. adminB GET /api/v1/auth/me -> rotulos.grupo_plural == "Setores"
        r = client.get("/api/v1/auth/me", headers=headers_B)
        assert r.status_code == 200, f"adminB GET /auth/me falhou: {r.status_code}"
        rotulos_b = r.json().get("rotulos", {})
        assert rotulos_b.get("grupo_plural") == "Setores", f"Esperado grupo_plural 'Setores', obteve {rotulos_b.get('grupo_plural')}"

        # 7. Super admin sem X-Conta-ID fica na conta da plataforma (não vê cA nem cB); com X-Conta-ID vê só a conta escolhida
        r = client.get("/api/v1/clients", headers=headers_super)
        assert r.status_code == 200, f"super admin GET /clients falhou: {r.status_code}"
        ids_super = [c["id"] for c in r.json()]
        assert str(cA_id) not in ids_super and str(cB_id) not in ids_super, "Super admin sem conta escolhida fica na conta da plataforma e NÃO deve ver cA nem cB"

        r = client.get("/api/v1/auth/me", headers=headers_super)
        assert r.status_code == 200, f"super admin GET /auth/me falhou: {r.status_code}"
        assert (r.json().get("conta") or {}).get("plataforma") is True, "Super admin sem conta escolhida deve estar na conta da plataforma"

        headers_super_A = {**headers_super, "X-Conta-ID": str(contaA_id)}
        r = client.get("/api/v1/clients", headers=headers_super_A)
        assert r.status_code == 200, f"super admin filtrado GET /clients falhou: {r.status_code}"
        ids_super_A = [c["id"] for c in r.json()]
        assert str(cA_id) in ids_super_A, "Super admin filtrado para A deve ver cA"
        assert str(cB_id) not in ids_super_A, "Super admin filtrado para A NÃO deve ver cB"

        headers_super_B = {**headers_super, "X-Conta-ID": str(contaB_id)}
        r = client.get("/api/v1/clients", headers=headers_super_B)
        assert r.status_code == 200, f"super admin filtrado para B GET /clients falhou: {r.status_code}"
        ids_super_B = [c["id"] for c in r.json()]
        assert str(cB_id) in ids_super_B and str(cA_id) not in ids_super_B, "Super admin filtrado para B deve ver só cB"

        # 8. adminA GET /api/v1/admin/contas -> 403
        r = client.get("/api/v1/admin/contas", headers=headers_A)
        assert r.status_code == 403, f"Esperado 403 para adminA em /admin/contas, obteve {r.status_code}"

        # 9. Agente de mV (X-Client-ID / X-API-Key): GET /agent/config -> equipamentos=[]; POST /agent/backup/report -> 403
        headers_agent = {"X-Client-ID": str(mV_id), "X-API-Key": raw_key_V}
        r = client.get("/api/v1/agent/config", headers=headers_agent)
        assert r.status_code == 200, f"Agente mV GET /agent/config falhou: {r.status_code}"
        assert r.json().get("equipamentos") == [], f"Esperado equipamentos=[] para máquina de conta vencida, obteve {r.json().get('equipamentos')}"

        agora_iso = datetime.utcnow().isoformat()
        report_minimo = {
            "started_at": agora_iso,
            "finished_at": agora_iso,
            "status": "OK",
            "nvr_results": [],
        }
        r = client.post("/api/v1/agent/backup/report", headers=headers_agent, json=report_minimo)
        assert r.status_code == 403, f"Esperado 403 para /agent/backup/report de conta vencida, obteve {r.status_code}"

        # 10. adminA POST /api/v1/auth/trocar-senha -> 200; token ANTIGO em GET /auth/me -> 401
        r = client.post(
            "/api/v1/auth/trocar-senha",
            headers=headers_A,
            json={"senha_atual": "SenhaTeste123", "senha_nova": "OutraSenha456"},
        )
        assert r.status_code == 200, f"Falha na troca de senha de adminA: {r.status_code} {r.text}"

        r = client.get("/api/v1/auth/me", headers=headers_A)
        assert r.status_code == 401, f"Esperado 401 para token antigo após troca de senha, obteve {r.status_code}"

        print("\nTODAS AS 10 ASSERÇÕES DE ISOLAMENTO DE CONTAS PASSARAM COM SUCESSO! [OK]")

    finally:
        with SessionLocal() as db_clean:
            try:
                db_clean.query(NVR).filter(NVR.machine_id.in_([mA_id, mB_id, mV_id])).delete(synchronize_session=False)
                db_clean.query(Backup).filter(Backup.machine_id.in_([mA_id, mB_id, mV_id])).delete(synchronize_session=False)
                db_clean.query(AgentLog).filter(AgentLog.machine_id.in_([mA_id, mB_id, mV_id])).delete(synchronize_session=False)
                db_clean.query(Machine).filter(Machine.id.in_([mA_id, mB_id, mV_id])).delete(synchronize_session=False)
                db_clean.query(Customer).filter(Customer.id.in_([cA_id, cB_id])).delete(synchronize_session=False)
                db_clean.query(Usuario).filter(Usuario.id.in_([usr_adminA_id, usr_leituraA_id, usr_adminB_id, usr_adminV_id])).delete(synchronize_session=False)
                db_clean.query(Conta).filter(Conta.id.in_([contaA_id, contaB_id, contaV_id])).delete(synchronize_session=False)
                if plano_criado_id is not None:
                    db_clean.query(Plano).filter(Plano.id == plano_criado_id).delete(synchronize_session=False)
                db_clean.commit()
            except Exception as e:
                db_clean.rollback()
                print(f"Erro na limpeza dos testes de isolamento: {e}")


if __name__ == "__main__":
    if not _ambiente_habilitado():
        print("Pulado: defina TRILAN_TESTE_ISOLAMENTO=1 (só no banco local)")
        sys.exit(0)
    test_isolamento_contas()
