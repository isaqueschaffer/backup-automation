from fastapi import APIRouter
from schemas import RTSPTestRequest, RTSPTestResponse
import urllib.parse
import os
import cv2

router = APIRouter(prefix="/api/v1/rtsp", tags=["rtsp"])

@router.post("/test-single", response_model=RTSPTestResponse)
def test_single_rtsp(req: RTSPTestRequest):
    senha_pura = req.senha.strip() if req.senha else "navarro@123"
    senha_enc = urllib.parse.quote(senha_pura, safe='')
    usuario = "admin"
    modelo = req.modelo.strip()
    ip = req.ip.strip()

    if "Grandstream" in modelo:
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/4"
    elif "Intelbras" in modelo:
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/cam/realmonitor?channel=1&subtype=1"
    elif "ONVIF" in modelo:
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/profile2"
    else:
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/Streaming/Channels/102"
    
    # Adicionamos timeout no ffmpeg (5 segundos) para nǜo travar a API se o IP nǜo existir
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"
    
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    
    if not cap.isOpened():
        return RTSPTestResponse(success=False, error_message="FALHA (401/404): Nǜo foi possvel conectar ao RTSP (Verifique IP, Senha ou Caminho).")
    
    try:
        # Puxa 2 frames apenas para limpar o buffer e testar a integridade
        for _ in range(2):
            cap.grab()
        sucesso, frame = cap.retrieve()
        
        cap.release()
        
        if sucesso:
            # Redimensionar para não enviar imagem muito pesada
            height, width = frame.shape[:2]
            new_width = 640
            new_height = int((new_width / width) * height)
            frame_resized = cv2.resize(frame, (new_width, new_height))
            
            # Converter para JPG em memória e depois para base64
            _, buffer = cv2.imencode('.jpg', frame_resized, [cv2.IMWRITE_JPEG_QUALITY, 70])
            import base64
            b64_str = base64.b64encode(buffer).decode('utf-8')
            
            return RTSPTestResponse(success=True, error_message=None, image_base64=b64_str)
        else:
            return RTSPTestResponse(success=False, error_message="FALHA: Conectou, mas a imagem retornou vazia ou corrompida.")
    except Exception as e:
        cap.release()
        return RTSPTestResponse(success=False, error_message=f"ERRO INTERNO: {str(e)}")
