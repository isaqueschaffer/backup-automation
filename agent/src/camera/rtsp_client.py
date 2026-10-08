import os
import cv2
import base64
import urllib.parse
from typing import Dict, Any

def test_rtsp_camera(task: Dict[str, Any]) -> Dict[str, Any]:
    """Testa a conexao RTSP da camera localmente pelo agente e retorna a imagem em base64."""
    senha_pura = task.get("password", "navarro@123")
    senha_enc = urllib.parse.quote(senha_pura, safe='')
    usuario = task.get("username", "admin")
    modelo = task.get("modelo", "")
    ip = task.get("ip", "").strip()

    if "Grandstream" in modelo:
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/4"
    elif "Intelbras" in modelo:
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/cam/realmonitor?channel=1&subtype=1"
    elif "ONVIF" in modelo:
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/profile2"
    else:
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/Streaming/Channels/102"
    
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"
    
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    
    if not cap.isOpened():
        return {"success": False, "error_message": "FALHA (401/404): Não foi possivel conectar ao RTSP localmente (Verifique IP, Senha ou Caminho)."}
    
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
            return {"success": True, "error_message": None, "image_base64": b64_str}
        else:
            return {"success": False, "error_message": "FALHA: Conectou localmente, mas a imagem retornou vazia ou corrompida."}
    except Exception as e:
        cap.release()
        return {"success": False, "error_message": f"ERRO INTERNO NO AGENTE: {str(e)}"}
