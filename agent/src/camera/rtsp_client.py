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
    canal = task.get("canal")

    if "Grandstream" in modelo:
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/4"
    elif "Intelbras" in modelo:
        ch = canal if canal else 1
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/cam/realmonitor?channel={ch}&subtype=1"
    elif "ONVIF" in modelo:
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/profile2"
    else:
        ch_str = f"{canal}02" if canal else "102"
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/Streaming/Channels/{ch_str}"
    
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

def capture_night_image(ip: str, usuario: str, senha_pura: str, canal: int, date_str: str) -> str:
    """
    Tenta conectar via RTSP no stream de playback do NVR Hikvision
    e captura um frame da madrugada (02:00:00) da data fornecida (YYYY-MM-DD).
    Retorna a string base64 da imagem em caso de sucesso, ou None.
    """
    import time
    senha_enc = urllib.parse.quote(senha_pura, safe='')
    
    # Hikvision uses YYYYMMDDTHHMMSSZ for starttime
    date_clean = date_str.replace("-", "")
    start_time = f"{date_clean}T020000Z"
    end_time = f"{date_clean}T020005Z"
    
    # Channel ID for Hikvision is usually {canal}01 (e.g. canal 1 -> 101)
    canal_str = f"{canal}01"
    
    rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/Streaming/tracks/{canal_str}?starttime={start_time}&endtime={end_time}"
    
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    
    if not cap.isOpened():
        return None
        
    try:
        # Pula alguns frames para garantir que o decoder iniciou corretamente
        for _ in range(5):
            cap.grab()
            time.sleep(0.1)
        sucesso, frame = cap.retrieve()
        cap.release()
        
        if sucesso:
            height, width = frame.shape[:2]
            new_width = 640
            new_height = int((new_width / width) * height)
            frame_resized = cv2.resize(frame, (new_width, new_height))
            _, buffer = cv2.imencode('.jpg', frame_resized, [cv2.IMWRITE_JPEG_QUALITY, 60])
            return base64.b64encode(buffer).decode('utf-8')
    except Exception:
        cap.release()
        
    return None
