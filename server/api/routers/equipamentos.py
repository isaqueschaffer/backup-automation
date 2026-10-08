"""
Router de Equipamentos.
Substitui o antigo router de NVRs, agora suportando múltiplos tipos:
NVR, OLT, ONU, PABX (e futuros).
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from auth import verify_admin_token
from database import get_db
from models import Client, NVR
from schemas import NVRCreate, NVRUpdate, NVRResponse, TIPOS_EQUIPAMENTO
from services.crypto_service import encrypt

router = APIRouter(prefix="/api/v1/clients/{client_id}/equipamentos", tags=["equipamentos"])


def _get_client_or_404(client_id: UUID, db: Session) -> Client:
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.get("", response_model=List[NVRResponse], dependencies=[Depends(verify_admin_token)])
def list_equipamentos(
    client_id: UUID,
    tipo: Optional[str] = Query(None, description="Filtrar por tipo: NVR, OLT, ONU, PABX"),
    db: Session = Depends(get_db),
):
    """Lista todos os equipamentos de um cliente, com filtro opcional por tipo."""
    _get_client_or_404(client_id, db)
    q = db.query(NVR).filter(NVR.client_id == client_id)
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
def create_equipamento(client_id: UUID, body: NVRCreate, db: Session = Depends(get_db)):
    """Cadastra um novo equipamento para um cliente."""
    _get_client_or_404(client_id, db)

    tipo = (body.tipo or "NVR").upper()
    if tipo not in TIPOS_EQUIPAMENTO:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo inválido. Tipos suportados: {TIPOS_EQUIPAMENTO}",
        )

    equipamento = NVR(
        client_id=client_id,
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
    client_id: UUID,
    equipamento_id: UUID,
    body: NVRUpdate,
    db: Session = Depends(get_db),
):
    """Atualiza um equipamento existente."""
    eq = db.query(NVR).filter(NVR.id == equipamento_id, NVR.client_id == client_id).first()
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
def delete_equipamento(client_id: UUID, equipamento_id: UUID, db: Session = Depends(get_db)):
    """Remove um equipamento."""
    eq = db.query(NVR).filter(NVR.id == equipamento_id, NVR.client_id == client_id).first()
    if not eq:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    db.delete(eq)
    db.commit()

from schemas import RTSPTestResponse
@router.post(
    "/{equipamento_id}/test-rtsp",
    response_model=RTSPTestResponse,
    dependencies=[Depends(verify_admin_token)],
)
def test_equipamento_rtsp(client_id: UUID, equipamento_id: UUID, db: Session = Depends(get_db)):
    """Testa a conexǜo RTSP de uma cǽmera (ou NVR) usando as credenciais salvas no BD."""
    eq = db.query(NVR).filter(NVR.id == equipamento_id, NVR.client_id == client_id).first()
    if not eq:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    
    from services.crypto_service import decrypt
    import urllib.parse
    import os
    import cv2
    import base64

    try:
        senha_pura = decrypt(eq.password) if eq.password else "navarro@123"
    except:
        senha_pura = eq.password or "navarro@123"
        
    senha_enc = urllib.parse.quote(senha_pura, safe='')
    usuario = eq.username or "admin"
    modelo = (eq.config_extra or {}).get("modelo", "")
    ip = eq.ip.strip()

    if "Grandstream" in modelo:
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/4"
    elif "Intelbras" in modelo:
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/cam/realmonitor?channel=1&subtype=1"
    elif "ONVIF" in modelo:
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/profile2"
    else:
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/Streaming/Channels/102"
    
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"
    
    import socket
    def pre_check_rtsp(url: str) -> str:
        try:
            parsed = urllib.parse.urlparse(url)
            ip_host = parsed.hostname
            port = parsed.port or 554
            user = parsed.username or ""
            pwd = parsed.password or ""
            
            pwd_decoded = urllib.parse.unquote(pwd)
            auth_b64 = base64.b64encode(f"{user}:{pwd_decoded}".encode()).decode()
            
            req = f"DESCRIBE {url} RTSP/1.0\r\nCSeq: 1\r\nAuthorization: Basic {auth_b64}\r\nUser-Agent: Python\r\nAccept: application/sdp\r\n\r\n"
            
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3.0)
            s.connect((ip_host, port))
            s.sendall(req.encode())
            resp = s.recv(1024).decode(errors='ignore')
            s.close()
            
            if resp.startswith("RTSP/1.0 ") or resp.startswith("RTSP/1.1 "):
                status_line = resp.split("\r\n")[0]
                parts = status_line.split(" ", 2)
                if len(parts) >= 2:
                    code = parts[1]
                    if code == "401":
                        return "FALHA 401: Não Autorizado. A senha ou usuário estão incorretos."
                    elif code == "404":
                        return "FALHA 404: Não Encontrado. O caminho RTSP ou Modelo configurado estão incorretos."
                    elif int(code) >= 400:
                        return f"FALHA {code}: {parts[2] if len(parts)>2 else 'Erro retornado pela câmera'}."
        except socket.timeout:
            return "FALHA: Tempo limite excedido (Timeout). A câmera pode estar desligada, firewall bloqueando, ou IP inacessível."
        except ConnectionRefusedError:
            return "FALHA: Conexão recusada (Porta 554 fechada). A câmera pode não suportar RTSP."
        except Exception as e:
            pass
        return None

    detalhe_erro = pre_check_rtsp(rtsp_url)
    if detalhe_erro:
        return RTSPTestResponse(success=False, error_message=detalhe_erro)
    
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    
    if not cap.isOpened():
        return RTSPTestResponse(success=False, error_message="FALHA DESCONHECIDA: Não foi possível conectar ao RTSP ou ler o vídeo.")
    
    try:
        for _ in range(2):
            cap.grab()
        sucesso, frame = cap.retrieve()
        cap.release()
        
        if sucesso:
            height, width = frame.shape[:2]
            new_width = 640
            new_height = int((new_width / width) * height)
            frame_resized = cv2.resize(frame, (new_width, new_height))
            _, buffer = cv2.imencode('.jpg', frame_resized, [cv2.IMWRITE_JPEG_QUALITY, 70])
            b64_str = base64.b64encode(buffer).decode('utf-8')
            return RTSPTestResponse(success=True, error_message=None, image_base64=b64_str)
        else:
            return RTSPTestResponse(success=False, error_message="FALHA: Conectou, mas a imagem retornou vazia ou corrompida.")
    except Exception as e:
        cap.release()
        return RTSPTestResponse(success=False, error_message=f"ERRO INTERNO: {str(e)}")
