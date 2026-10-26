"""
Router de Equipamentos.
Substitui o antigo router de NVRs, agora suportando múltiplos tipos:
NVR, OLT, ONU, PABX (e futuros).
"""
import asyncio
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from auth import verify_admin_token
from database import get_db
from models import Machine, NVR, NVRCamera, NVRPlanilha
from routers.agent import mascarar_credenciais, pending_rtsp_tasks
from schemas import (
    NVRCreate, NVRUpdate, NVRResponse, TIPOS_EQUIPAMENTO, NVRCameraResponse,
    NVRCameraSetPerfect, NVRCameraBulkImport, NVRCameraConfigItem, RTSPTestResponse,
    NVRPlanilhaEntrada, NVRPlanilhaResposta,
)
from services.crypto_service import encrypt, decrypt
from services.galeria_vms import (
    canal_int as _canal_int,
    ip_valido,
    parear_cameras,
    ips_compartilhados,
    bloqueada_por_ip_compartilhado,
)
from services.planilha_vms import (
    colunas_senha,
    mascarar_senhas,
    empacotar,
    desempacotar,
)

TIPOS_VMS = ("DIGIFORT", "DEFENSE")

router = APIRouter(prefix="/api/v1/machines/{machine_id}/equipamentos", tags=["Equipamentos"])


def _get_machine_or_404(machine_id: UUID, db: Session) -> Machine:
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Máquina não encontrada")
    return machine


@router.get("", response_model=List[NVRResponse], dependencies=[Depends(verify_admin_token)])
def list_equipamentos(
    machine_id: UUID,
    tipo: Optional[str] = Query(None, description="Filtrar por tipo: NVR, OLT, ONU, PABX"),
    db: Session = Depends(get_db),
):
    """Lista todos os equipamentos de uma máquina, com filtro opcional por tipo."""
    _get_machine_or_404(machine_id, db)
    q = db.query(NVR).filter(NVR.machine_id == machine_id)
    if tipo:
        if tipo.upper() not in TIPOS_EQUIPAMENTO:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo inválido. Tipos suportados: {TIPOS_EQUIPAMENTO}",
            )
        q = q.filter(NVR.tipo == tipo.upper())
    return q.all()


@router.post(
    "",
    response_model=NVRResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_token)],
)
def create_equipamento(machine_id: UUID, body: NVRCreate, db: Session = Depends(get_db)):
    """Cadastra um novo equipamento para uma máquina."""
    _get_machine_or_404(machine_id, db)

    tipo = (body.tipo or "NVR").upper()
    if tipo not in TIPOS_EQUIPAMENTO:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo inválido. Tipos suportados: {TIPOS_EQUIPAMENTO}",
        )

    equipamento = NVR(
        machine_id=machine_id,
        tipo=tipo,
        name=body.name,
        ip=body.ip,
        username=body.username,
        password=encrypt(body.password),
        config_extra=body.config_extra,
        active=body.active,
    )
    db.add(equipamento)
    db.commit()
    db.refresh(equipamento)
    return equipamento


@router.put(
    "/{equipamento_id}",
    response_model=NVRResponse,
    dependencies=[Depends(verify_admin_token)],
)
def update_equipamento(
    machine_id: UUID,
    equipamento_id: UUID,
    body: NVRUpdate,
    db: Session = Depends(get_db),
):
    """Atualiza um equipamento existente."""
    eq = db.query(NVR).filter(NVR.id == equipamento_id, NVR.machine_id == machine_id).first()
    if not eq:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")

    for field, value in body.model_dump(exclude_none=True).items():
        if field == "password" and value:
            eq.password = encrypt(value)
        elif field == "tipo" and value:
            if value.upper() not in TIPOS_EQUIPAMENTO:
                raise HTTPException(
                    status_code=400,
                    detail=f"Tipo inválido. Tipos suportados: {TIPOS_EQUIPAMENTO}",
                )
            eq.tipo = value.upper()
        else:
            setattr(eq, field, value)

    db.commit()
    db.refresh(eq)
    return eq


@router.delete(
    "/{equipamento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_admin_token)],
)
def delete_equipamento(machine_id: UUID, equipamento_id: UUID, db: Session = Depends(get_db)):
    """Remove um equipamento."""
    eq = db.query(NVR).filter(NVR.id == equipamento_id, NVR.machine_id == machine_id).first()
    if not eq:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    db.delete(eq)
    db.commit()


@router.post(
    "/{equipamento_id}/test-rtsp",
    response_model=RTSPTestResponse,
    dependencies=[Depends(verify_admin_token)],
)
async def test_equipamento_rtsp(
    machine_id: UUID,
    equipamento_id: UUID,
    canal: Optional[int] = Query(None),
    modo: str = Query("ao_vivo", pattern="^(ao_vivo|referencia|noite)$"),
    nome: Optional[str] = Query(None, max_length=200),
    db: Session = Depends(get_db),
):
    """Captura um frame delegando a tarefa ao agente local via long-polling.

    modo "ao_vivo": frame ao vivo (teste de conexão).
    modo "referencia": ao vivo; se a câmera estiver offline, o frame mais recente da gravação (agente >= 1.1.6).
    modo "noite": madrugada mais recente com gravação; o servidor já salva como imagem da noite do canal.
    """
    eq = db.query(NVR).filter(NVR.id == equipamento_id, NVR.machine_id == machine_id).first()
    if not eq:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    is_vms = (eq.tipo or "NVR").upper() in TIPOS_VMS
    if is_vms and not canal:
        raise HTTPException(status_code=422, detail="Informe o canal da câmera.")
    if modo != "ao_vivo" and not canal:
        raise HTTPException(status_code=422, detail="Informe o canal para capturar da gravação.")

    machine_id_str = str(machine_id)

    # Só 1 teste RTSP por máquina por vez (o dicionário é indexado pela máquina).
    # LIMITAÇÃO: o estado fica na memória do processo; requer 1 worker uvicorn.
    if machine_id_str in pending_rtsp_tasks:
        raise HTTPException(
            status_code=409,
            detail="Já existe um teste RTSP em andamento para esta máquina. Aguarde a conclusão e tente novamente.",
        )

    cam_db = None
    if is_vms:
        cam_db = db.query(NVRCamera).filter(NVRCamera.nvr_id == equipamento_id, NVRCamera.canal == canal).first()
        if not cam_db or not cam_db.ip:
            # Câmera detectada pelo agente e ainda sem IP na Galeria: usa o IP do relatório
            todas = db.query(NVRCamera).filter(NVRCamera.nvr_id == equipamento_id).all()
            st_cam = next((st for _, st, c, ch in parear_cameras(todas, eq.last_recording_status or [])
                           if ch == canal and st is not None), None)
            ip_recup = ip_valido(st_cam.get("ip")) if st_cam else ""
            if ip_recup:
                mod_recup = (st_cam.get("modelo") or "").strip() or "Hikvision"
                if not cam_db:
                    cam_db = NVRCamera(
                        nvr_id=equipamento_id,
                        canal=canal,
                        nome=st_cam.get("nome") or f"Canal {canal}",
                        ip=ip_recup,
                        username="admin",
                        password=encrypt("navarro@123"),
                        modelo=mod_recup
                    )
                    db.add(cam_db)
                else:
                    cam_db.ip = ip_recup
                db.commit()
                db.refresh(cam_db)
            else:
                return RTSPTestResponse(success=False, error_message="Câmera sem endereço IP configurado na galeria. Importe o CSV ou configure o IP da câmera.")

        todas = db.query(NVRCamera).filter(NVRCamera.nvr_id == equipamento_id).all()
        if bloqueada_por_ip_compartilhado(cam_db, todas):
            return RTSPTestResponse(
                success=False,
                error_message=f"O IP {cam_db.ip} é usado por mais de uma câmera (gravador ou encoder com vários canais). Edite a câmera e informe o canal dela no equipamento.",
            )

        try:
            cam_password = decrypt(cam_db.password) if cam_db.password else "navarro@123"
        except Exception:
            cam_password = cam_db.password or "navarro@123"
        task_data = {
            "equipamento_id": str(eq.id),
            "ip": cam_db.ip.strip(),
            "modelo": cam_db.modelo or "Hikvision",
            "marca": cam_db.modelo or "Hikvision",
            "username": cam_db.username or "admin",
            "password": cam_password,
            "canal": cam_db.canal_rtsp or 1,
            "stream_principal": True,
            "direct_camera": True,
            "modo": modo,
        }
    else:
        try:
            senha_pura = decrypt(eq.password) if eq.password else "navarro@123"
        except Exception:
            senha_pura = eq.password or "navarro@123"

        marca = (eq.config_extra or {}).get("marca", "") or ""
        if not marca and any(isinstance(st, dict) and st.get("canal_guid") for st in (eq.last_recording_status or [])):
            # NVR sem marca cadastrada: o backup detecta sozinho, mas o teste RTSP precisa saber.
            # Só NVR Motorola (NVMS-9000) reporta `canal_guid` no relatório de gravação.
            marca = "Motorola"

        task_data = {
            "equipamento_id": str(eq.id),
            "ip": eq.ip.strip(),
            "modelo": (eq.config_extra or {}).get("modelo", ""),
            "marca": marca,
            "username": eq.username or "admin",
            "password": senha_pura,
            "canal": canal,
            "modo": modo,  # agentes < 1.1.6 ignoram e capturam ao vivo
        }

    event = asyncio.Event()

    entry = {
        "task": task_data,
        "event": event,
        "result": None,
        "sent": False
    }
    pending_rtsp_tasks[machine_id_str] = entry
    # Libera a conexão do banco durante a espera (a captura pela gravação pode levar ~2 min)
    db.close()

    # Ao vivo: até 35s. Pela gravação: busca dia a dia no NVR (o agente desiste em ~100s + envio).
    espera = 35.0 if modo == "ao_vivo" else 130.0
    try:
        await asyncio.wait_for(event.wait(), timeout=espera)
    except asyncio.TimeoutError:
        return RTSPTestResponse(success=False, error_message="FALHA: O Agente local não respondeu ao comando a tempo. Verifique se o agente está online.")
    finally:
        # Sempre remove a tarefa (timeout, cancelamento ou sucesso); pop evita KeyError
        if pending_rtsp_tasks.get(machine_id_str) is entry:
            pending_rtsp_tasks.pop(machine_id_str, None)

    result = entry.get("result")
    if not result:
        return RTSPTestResponse(success=False, error_message="FALHA: Agente respondeu, mas sem dados válidos.")

    if modo == "noite" and result.success:
        if not result.horario:
            if is_vms:
                # Câmera direta (DIGIFORT/DEFENSE): capturada ao vivo pelo agente, sem horário de gravação
                result.horario = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
            else:
                # Agente antigo capturou ao vivo: não é imagem da noite
                return RTSPTestResponse(success=False, error_message="Atualize o agente desta máquina para a versão 1.1.6 ou superior para capturar a imagem da noite pelo painel.")
        _salvar_imagem_noite(db, equipamento_id, canal, (cam_db.nome if cam_db else None) or nome, result)
    elif modo == "noite":
        # Mostra o motivo na galeria (a imagem anterior, se houver, é mantida)
        nvr = db.query(NVR).filter(NVR.id == equipamento_id).first()
        if nvr is not None:
            _marcar_imagem_noite(db, nvr, canal, {"status": "FALHA", "motivo": mascarar_credenciais(result.error_message), "horario": None},
                                 (cam_db.nome if cam_db else None) or nome)
            db.commit()

    return result


def _salvar_imagem_noite(db: Session, nvr_id: UUID, canal: int, nome: Optional[str], result: RTSPTestResponse) -> None:
    """Salva a imagem da noite capturada pelo painel, como o envio do backup faria."""
    try:
        horario = datetime.fromisoformat(result.horario)  # horário exibido no NVR (naive), igual ao backup
    except ValueError:
        horario = None
    nvr = db.query(NVR).filter(NVR.id == nvr_id).first()
    if nvr is None:
        return
    camera = db.query(NVRCamera).filter(NVRCamera.nvr_id == nvr_id, NVRCamera.canal == canal).first()
    if camera is None:
        camera = NVRCamera(nvr_id=nvr_id, canal=canal, nome=nome or f"Canal {canal}")
        db.add(camera)
    elif nome:
        camera.nome = nome
    camera.night_image_base64 = result.image_base64
    camera.night_image_date = horario

    _marcar_imagem_noite(db, nvr, canal, {"status": "OK", "motivo": None, "horario": result.horario}, camera.nome)
    db.commit()


def _marcar_imagem_noite(db: Session, nvr: NVR, canal: int, info: dict, nome: Optional[str] = None) -> None:
    """Grava o status da captura da noite do canal em `last_recording_status` (lido pela galeria).
    Em DIGIFORT/DEFENSE o canal é o da Galeria: a entrada do relatório vem do pareamento por nome/IP."""
    relatorio = list(nvr.last_recording_status or [])
    if (nvr.tipo or "NVR").upper() in TIPOS_VMS:
        cameras_db = db.query(NVRCamera).filter(NVRCamera.nvr_id == nvr.id).all()
        alvo = next((i for i, st, c, ch in parear_cameras(cameras_db, relatorio) if i is not None and ch == canal), None)
        if alvo is not None:
            relatorio[alvo] = {**relatorio[alvo], "imagem_noite": info}
        elif nome:
            relatorio.append({"canal": canal, "nome": nome, "imagem_noite": info})
    else:
        relatorio = [{**st, "imagem_noite": info} if isinstance(st, dict) and _canal_int(st.get("canal")) == canal else st
                     for st in relatorio]
    nvr.last_recording_status = relatorio


# ─── NVR Cameras Gallery ───────────────────────────────────────────────────

@router.get("/{id}/cameras", response_model=List[NVRCameraResponse])
def get_nvr_cameras(
    machine_id: UUID,
    id: UUID,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin_token)
):
    """Retorna todas as câmeras de um NVR específico (com suas imagens)."""
    nvr = db.query(NVR).filter(NVR.id == id, NVR.machine_id == machine_id).first()
    if not nvr:
        raise HTTPException(status_code=404, detail="NVR não encontrado")

    cameras_db = db.query(NVRCamera).filter(NVRCamera.nvr_id == id).order_by(NVRCamera.canal).all()
    report_status = nvr.last_recording_status or []
    is_vms = (nvr.tipo or "NVR").upper() in TIPOS_VMS

    if is_vms:
        # Pareia relatório do agente e Galeria por nome/IP (o canal do agente não é o da Galeria)
        merged_cameras = []
        compartilhados = ips_compartilhados(cameras_db)
        for _, st, c_db, ch in parear_cameras(cameras_db, report_status):
            st = st or {}
            ip_item = (c_db.ip if c_db and c_db.ip else None) or ip_valido(st.get("ip")) or None
            obj = {
                "id": c_db.id if c_db else None,
                "nvr_id": id,
                "canal": ch,
                "nome": (c_db.nome if c_db and c_db.nome else None) or (st.get("nome") or "").strip() or f"Canal {ch}",
                "ip": ip_item,
                "username": c_db.username if c_db else None,
                "modelo": c_db.modelo if c_db else st.get("modelo"),
                "canal_rtsp": c_db.canal_rtsp if c_db else None,
                "ip_compartilhado": (ip_item or "").strip() in compartilhados,
                "has_password": bool(c_db and c_db.password),
                "perfect_image_base64": c_db.perfect_image_base64 if c_db else None,
                "night_image_base64": c_db.night_image_base64 if c_db else None,
                "night_image_date": c_db.night_image_date if c_db else None,
                "updated_at": c_db.updated_at if c_db else None,
                "status_comunicacao": st.get("status_comunicacao"),
                "status_gravacao": st.get("status_gravacao"),
                "captura_status": None,
                "captura_motivo": None,
                "captura_horario": None,
            }
            if "imagem_noite" in st:
                obj["captura_status"] = st["imagem_noite"].get("status")
                obj["captura_motivo"] = mascarar_credenciais(st["imagem_noite"].get("motivo"))
                obj["captura_horario"] = st["imagem_noite"].get("horario")
            elif obj["night_image_base64"]:
                obj["captura_status"] = "OK"
            merged_cameras.append(obj)
        return sorted(merged_cameras, key=lambda x: x["canal"])

    # NVR tradicional (Intelbras/Hikvision/Motorola): canais físicos de hardware
    db_dict = {c.canal: c for c in cameras_db}
    report_by_ch = {}
    for st in report_status:
        ch_int = _canal_int(st.get("canal"))
        if ch_int is not None:
            report_by_ch[ch_int] = st

    canais_set = set(db_dict.keys()) | set(report_by_ch.keys())

    merged_cameras = []
    for ch in sorted(canais_set):
        c_db = db_dict.get(ch)
        c_report = report_by_ch.get(ch)

        obj = {
            "id": c_db.id if c_db else None,
            "nvr_id": id,
            "canal": ch,
            "nome": (c_report.get("nome") if c_report else None) or (c_db.nome if c_db else f"Canal {ch}"),
            "ip": c_db.ip if c_db else None,
            "username": c_db.username if c_db else None,
            "modelo": c_db.modelo if c_db else None,
            "canal_rtsp": None,
            "ip_compartilhado": False,
            "has_password": bool(c_db and c_db.password),
            "perfect_image_base64": c_db.perfect_image_base64 if c_db else None,
            "night_image_base64": c_db.night_image_base64 if c_db else None,
            "night_image_date": c_db.night_image_date if c_db else None,
            "updated_at": c_db.updated_at if c_db else None,
            "status_comunicacao": c_report.get("status_comunicacao") if c_report else None,
            "status_gravacao": c_report.get("status_gravacao") if c_report else None,
            "captura_status": None,
            "captura_motivo": None,
            "captura_horario": None,
        }

        if c_report and "imagem_noite" in c_report:
            obj["captura_status"] = c_report["imagem_noite"].get("status")
            obj["captura_motivo"] = mascarar_credenciais(c_report["imagem_noite"].get("motivo"))
            obj["captura_horario"] = c_report["imagem_noite"].get("horario")
        else:
            if obj["night_image_base64"]:
                obj["captura_status"] = "OK"

        merged_cameras.append(obj)

    return merged_cameras


def _camera_response_dict(c: NVRCamera) -> dict:
    return {
        "id": c.id,
        "nvr_id": c.nvr_id,
        "canal": c.canal,
        "nome": c.nome,
        "ip": c.ip,
        "username": c.username,
        "modelo": c.modelo,
        "canal_rtsp": c.canal_rtsp,
        "ip_compartilhado": False,
        "has_password": bool(c.password),
        "perfect_image_base64": c.perfect_image_base64,
        "night_image_base64": c.night_image_base64,
        "night_image_date": c.night_image_date,
        "updated_at": c.updated_at,
    }


@router.post("/{id}/cameras/import", response_model=List[NVRCameraResponse])
def import_cameras(
    machine_id: UUID,
    id: UUID,
    payload: NVRCameraBulkImport,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin_token)
):
    """Importa/sincroniza em lote as câmeras RTSP da Galeria de um equipamento DIGIFORT/DEFENSE.

    `sync_from_machine=True` copia as câmeras avulsas (tipo == "CAMERA") da máquina, em vez de usar `cameras`.
    `replace_existing=True` remove as câmeras da galeria que não vieram nesta importação."""
    nvr = db.query(NVR).filter(NVR.id == id, NVR.machine_id == machine_id).first()
    if not nvr:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    if (nvr.tipo or "NVR").upper() not in TIPOS_VMS:
        raise HTTPException(status_code=400, detail="Importação de câmeras RTSP só é suportada para DIGIFORT e DEFENSE.")

    if payload.sync_from_machine:
        machine = _get_machine_or_404(machine_id, db)
        machine_cams = [e for e in machine.equipamentos if (e.tipo or "").upper() == "CAMERA" and e.active and e.ip]
        if not machine_cams:
            raise HTTPException(status_code=400, detail="Nenhuma câmera (tipo CAMERA) cadastrada na máquina para sincronizar.")
        itens = [
            NVRCameraConfigItem(
                nome=mc.name,
                ip=mc.ip,
                username=mc.username or "admin",
                password=decrypt(mc.password) if mc.password else "navarro@123",
                modelo=(mc.config_extra or {}).get("modelo") or "Hikvision",
            )
            for mc in machine_cams
        ]
    else:
        itens = payload.cameras
        if not itens:
            raise HTTPException(status_code=400, detail="Nenhuma câmera para importar.")

    cameras_db = db.query(NVRCamera).filter(NVRCamera.nvr_id == id).all()
    by_canal = {c.canal: c for c in cameras_db}
    by_nome = {(c.nome or "").strip().lower(): c for c in cameras_db}
    by_ip = {(c.ip or "").strip(): c for c in cameras_db if c.ip}

    usados = set()
    atualizadas = []
    for idx, item in enumerate(itens, start=1):
        nome_key = (item.nome or "").strip().lower()
        ip_key = (item.ip or "").strip()

        # Prioriza encontrar a câmera existente pelo nome ou pelo IP!
        camera = None
        if nome_key and nome_key in by_nome:
            camera = by_nome[nome_key]
        elif ip_key and ip_key in by_ip:
            camera = by_ip[ip_key]
        elif item.canal and item.canal in by_canal:
            camera = by_canal[item.canal]

        canal = camera.canal if camera else (item.canal or idx)
        while canal in usados:
            canal += 1
        usados.add(canal)

        if camera is None:
            camera = NVRCamera(nvr_id=id, canal=canal, nome=item.nome)
            db.add(camera)
        else:
            camera.canal = canal
            camera.nome = item.nome
        if item.canal_rtsp is not None:
            camera.canal_rtsp = item.canal_rtsp
        camera.ip = item.ip
        camera.username = item.username or "admin"
        camera.modelo = item.modelo or "Hikvision"
        if item.password:
            camera.password = encrypt(item.password)
        elif not camera.password:
            camera.password = encrypt("navarro@123")
        atualizadas.append(camera)

    if payload.replace_existing:
        for c in cameras_db:
            if c not in atualizadas:
                db.delete(c)

    db.commit()
    for c in atualizadas:
        db.refresh(c)
    return [_camera_response_dict(c) for c in sorted(atualizadas, key=lambda c: c.canal)]


@router.put("/{id}/cameras/{canal}", response_model=NVRCameraResponse)
def set_camera_rtsp(
    machine_id: UUID,
    id: UUID,
    canal: int,
    payload: NVRCameraConfigItem,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin_token)
):
    """Cria ou atualiza a conexão RTSP (nome, ip, usuário, senha, modelo) de um canal da galeria."""
    nvr = db.query(NVR).filter(NVR.id == id, NVR.machine_id == machine_id).first()
    if not nvr:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")

    camera = db.query(NVRCamera).filter(NVRCamera.nvr_id == id, NVRCamera.canal == canal).first()
    if not camera:
        camera = NVRCamera(nvr_id=id, canal=canal, nome=payload.nome)
        db.add(camera)
    else:
        camera.nome = payload.nome
    camera.canal_rtsp = payload.canal_rtsp
    camera.ip = payload.ip
    camera.username = payload.username or "admin"
    camera.modelo = payload.modelo or "Hikvision"
    if payload.password:
        camera.password = encrypt(payload.password)
    elif not camera.password:
        camera.password = encrypt("navarro@123")

    db.commit()
    db.refresh(camera)
    return _camera_response_dict(camera)


@router.delete("/{id}/cameras/{canal}", status_code=status.HTTP_204_NO_CONTENT)
def delete_camera(
    machine_id: UUID,
    id: UUID,
    canal: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin_token)
):
    """Remove o canal da galeria (a conexão RTSP e as imagens salvas)."""
    nvr = db.query(NVR).filter(NVR.id == id, NVR.machine_id == machine_id).first()
    if not nvr:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    camera = db.query(NVRCamera).filter(NVRCamera.nvr_id == id, NVRCamera.canal == canal).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Câmera não encontrada")
    db.delete(camera)
    db.commit()


@router.post("/{id}/cameras/perfect-image", response_model=NVRCameraResponse)
def set_perfect_image(
    machine_id: UUID,
    id: UUID,
    payload: NVRCameraSetPerfect,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin_token)
):
    """Salva a 'Imagem Perfeita' de um canal específico."""
    nvr = db.query(NVR).filter(NVR.id == id, NVR.machine_id == machine_id).first()
    if not nvr:
        raise HTTPException(status_code=404, detail="NVR não encontrado")

    camera = db.query(NVRCamera).filter(NVRCamera.nvr_id == id, NVRCamera.canal == payload.canal).first()
    if not camera:
        camera = NVRCamera(
            nvr_id=id,
            canal=payload.canal,
            nome=payload.nome,
            perfect_image_base64=payload.image_base64
        )
        db.add(camera)
    else:
        camera.nome = payload.nome
        camera.perfect_image_base64 = payload.image_base64

    db.commit()
    db.refresh(camera)
    return camera


# ─────────────────────────────────────────────
# Planilha VMS (DIGIFORT / DEFENSE)
# ─────────────────────────────────────────────
@router.put("/{id}/planilha", response_model=NVRPlanilhaResposta)
def salvar_planilha(
    machine_id: UUID,
    id: UUID,
    payload: NVRPlanilhaEntrada,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin_token),
):
    """Cria ou substitui a planilha importada de um equipamento VMS (DIGIFORT/DEFENSE)."""
    nvr = db.query(NVR).filter(NVR.id == id, NVR.machine_id == machine_id).first()
    if not nvr:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    if (nvr.tipo or "NVR").upper() not in TIPOS_VMS:
        raise HTTPException(status_code=400, detail="Planilha só é suportada para DIGIFORT e DEFENSE.")

    planilha = db.query(NVRPlanilha).filter(NVRPlanilha.nvr_id == id).first()
    total = len(payload.linhas)
    dados_enc = empacotar(payload.linhas)
    agora = datetime.utcnow()

    if not planilha:
        planilha = NVRPlanilha(
            nvr_id=id,
            nome_arquivo=payload.nome_arquivo,
            linha_cabecalho=payload.linha_cabecalho,
            total_linhas=total,
            dados=dados_enc,
            importado_em=agora,
        )
        db.add(planilha)
    else:
        planilha.nome_arquivo = payload.nome_arquivo
        planilha.linha_cabecalho = payload.linha_cabecalho
        planilha.total_linhas = total
        planilha.dados = dados_enc
        planilha.importado_em = agora

    db.commit()
    db.refresh(planilha)

    cols = colunas_senha(payload.linhas, payload.linha_cabecalho)
    linhas_mascaradas = mascarar_senhas(payload.linhas, payload.linha_cabecalho, cols)

    return NVRPlanilhaResposta(
        nome_arquivo=planilha.nome_arquivo,
        linha_cabecalho=planilha.linha_cabecalho,
        total_linhas=planilha.total_linhas,
        importado_em=planilha.importado_em,
        colunas_senha=cols,
        senhas_ocultas=True,
        linhas=linhas_mascaradas,
    )


@router.get("/{id}/planilha", response_model=NVRPlanilhaResposta)
def obter_planilha(
    machine_id: UUID,
    id: UUID,
    mostrar_senhas: bool = Query(False),
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin_token),
):
    """Devolve a última planilha importada no equipamento, mascarando senhas por padrão."""
    nvr = db.query(NVR).filter(NVR.id == id, NVR.machine_id == machine_id).first()
    if not nvr:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    if (nvr.tipo or "NVR").upper() not in TIPOS_VMS:
        raise HTTPException(status_code=400, detail="Planilha só é suportada para DIGIFORT e DEFENSE.")

    planilha = db.query(NVRPlanilha).filter(NVRPlanilha.nvr_id == id).first()
    if not planilha:
        raise HTTPException(status_code=404, detail="Nenhuma planilha importada neste equipamento.")

    linhas = desempacotar(planilha.dados)
    cols = colunas_senha(linhas, planilha.linha_cabecalho)

    if not mostrar_senhas:
        linhas = mascarar_senhas(linhas, planilha.linha_cabecalho, cols)

    return NVRPlanilhaResposta(
        nome_arquivo=planilha.nome_arquivo,
        linha_cabecalho=planilha.linha_cabecalho,
        total_linhas=planilha.total_linhas,
        importado_em=planilha.importado_em,
        colunas_senha=cols,
        senhas_ocultas=not mostrar_senhas,
        linhas=linhas,
    )


@router.delete("/{id}/planilha", status_code=status.HTTP_204_NO_CONTENT)
def remover_planilha(
    machine_id: UUID,
    id: UUID,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin_token),
):
    """Remove a planilha guardada no equipamento."""
    nvr = db.query(NVR).filter(NVR.id == id, NVR.machine_id == machine_id).first()
    if not nvr:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    if (nvr.tipo or "NVR").upper() not in TIPOS_VMS:
        raise HTTPException(status_code=400, detail="Planilha só é suportada para DIGIFORT e DEFENSE.")

    planilha = db.query(NVRPlanilha).filter(NVRPlanilha.nvr_id == id).first()
    if not planilha:
        raise HTTPException(status_code=404, detail="Nenhuma planilha importada neste equipamento.")

    db.delete(planilha)
    db.commit()
    return None
