import os
import base64
import urllib.parse
import subprocess
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
    
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    
    try:
        cmd = [
            ffmpeg_exe, "-y", "-rtsp_transport", "tcp",
            "-i", rtsp_url, "-vframes", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "-"
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=15)
        
        if result.returncode == 0 and len(result.stdout) > 1000:
            b64_str = base64.b64encode(result.stdout).decode('utf-8')
            return {"success": True, "error_message": None, "image_base64": b64_str}
        else:
            return {"success": False, "error_message": "FALHA: ffmpeg retornou vazio ou erro ao capturar."}
    except Exception as e:
        return {"success": False, "error_message": f"ERRO INTERNO NO AGENTE (FFmpeg): {str(e)}"}

def capture_night_image(ip: str, usuario: str, senha_pura: str, canal: int, date_str: str) -> str:
    """
    Tenta conectar via RTSP no stream de playback do NVR Hikvision
    e captura um frame da madrugada.
    Se a câmera gravar apenas por movimento, tentará vários horários (02:00, 03:00, etc)
    """
    import urllib.parse
    import imageio_ffmpeg
    import subprocess
    import base64
    import logging

    senha_enc = urllib.parse.quote(senha_pura, safe='')
    date_clean = date_str.replace("-", "")
    canal_str = f"{canal}01"
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    # Horários da madrugada para tentar, em ordem de preferência
    horarios = ["020000", "030000", "040000", "010000", "000000", "050000"]

    for hr in horarios:
        start_time = f"{date_clean}T{hr}Z"
        # Cria a janela de 5 segundos
        hr_end = hr[:4] + "05"
        end_time = f"{date_clean}T{hr_end}Z"
        
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/Streaming/tracks/{canal_str}?starttime={start_time}&endtime={end_time}"
        
        try:
            cmd = [
                ffmpeg_exe, "-y", "-rtsp_transport", "tcp",
                "-i", rtsp_url, "-vframes", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "-"
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=15)
            
            if result.returncode == 0 and len(result.stdout) > 1000:
                # Sucesso! Achamos uma gravação
                return base64.b64encode(result.stdout).decode('utf-8')
            else:
                stderr_text = result.stderr.decode('utf-8', errors='ignore')
                if "400 Bad Request" in stderr_text:
                    # Significa que não há gravação de vídeo nesse horário exato (ex: câmera por movimento). Tenta o próximo.
                    continue
                else:
                    logging.warning(f"FFmpeg canal {canal} ({hr}): stdout len: {len(result.stdout)}, stderr: {stderr_text}")
        except subprocess.TimeoutExpired:
            logging.warning(f"FFmpeg timeout no canal {canal} ({hr})")
        except Exception as e:
            logging.error(f"FFmpeg exception no canal {canal}: {e}")
            
    return None
