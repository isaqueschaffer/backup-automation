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

    # Com canal (galeria do NVR) a referência precisa ter a mesma origem da imagem da noite (stream principal,
    # {canal}01). O stream secundário ({canal}02 / subtype=1) tem resolução e proporção diferentes.
    nvr_canal = bool(canal)

    if "Grandstream" in modelo:
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/4"
    elif "Intelbras" in modelo:
        ch = canal if canal else 1
        subtype = 0 if nvr_canal else 1
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/cam/realmonitor?channel={ch}&subtype={subtype}"
    elif "ONVIF" in modelo:
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/profile2"
    else:
        ch_str = f"{canal}01" if nvr_canal else "102"
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

def _motivo_ffmpeg(stderr: str) -> str:
    if "401 " in stderr or "401 Unauthorized" in stderr:
        return "Usuário/senha RTSP recusados"
    if any(e in stderr for e in ["400 Bad Request", "404 Not Found", "453 Not Enough Bandwidth"]):
        return "NVR não entregou o trecho gravado"
    if any(e in stderr for e in ["454 Session Not Found", "503 Service Unavailable"]):
        return "NVR sem sessões de playback livres"
    if "Connection refused" in stderr or "timed out" in stderr:
        return "Porta RTSP 554 inacessível"
    if "TIMEOUT_25S" in stderr:
        return "Tempo esgotado ao ler o vídeo (25s)"
    
    linhas = [line.strip() for line in stderr.split('\n') if line.strip()]
    if linhas:
        ultima_linha = linhas[-1]
        return ultima_linha[:150]
    return "Erro desconhecido"

def capture_night_image(ip: str, usuario: str, senha_pura: str, canal: int, date_str: str) -> dict:
    """
    Tenta conectar via RTSP no stream de playback do NVR Hikvision
    e captura um frame da madrugada. Retorna um dicionário com o status e motivo.
    """
    import urllib.parse
    import imageio_ffmpeg
    import subprocess
    import base64
    import logging
    from datetime import datetime, timedelta
    from src.nvr.hikvision.recordings import buscar_trechos

    result_dict = {"image": None, "horario": None, "status": "FALHA", "motivo": None}

    senha_enc = urllib.parse.quote(senha_pura, safe='')
    date_clean = date_str.replace("-", "")
    canal_str = f"{canal}01"
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    try:
        data_obj = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        result_dict["motivo"] = "Data inválida"
        return result_dict

    inicio_madrugada = data_obj.replace(hour=0, minute=0, second=0)
    fim_madrugada = data_obj.replace(hour=6, minute=0, second=0)
    
    trechos = buscar_trechos(ip, usuario, senha_pura, canal, inicio_madrugada, fim_madrugada, max_results=40)
    
    horarios_tenta = []
    
    if trechos is not None:
        if len(trechos) == 0:
            result_dict["status"] = "SEM_GRAVACAO"
            result_dict["motivo"] = "Sem gravação na madrugada (00h-06h)"
            return result_dict
            
        trechos = [t for t in trechos if t[0] != "dummy"]
        if not trechos:
            result_dict["status"] = "SEM_GRAVACAO"
            result_dict["motivo"] = "Sem gravação na madrugada (00h-06h)"
            return result_dict
            
        for (st, end) in trechos:
            try:
                st_str = st.replace("Z", "")
                end_str = end.replace("Z", "")
                st_dt = datetime.strptime(st_str, "%Y-%m-%dT%H:%M:%S")
                end_dt = datetime.strptime(end_str, "%Y-%m-%dT%H:%M:%S")
                
                alvo = data_obj.replace(hour=2, minute=0, second=0)
                
                if alvo < st_dt + timedelta(seconds=2):
                    alvo = st_dt + timedelta(seconds=2)
                if alvo > end_dt - timedelta(seconds=5):
                    alvo = end_dt - timedelta(seconds=5)
                    
                if alvo < st_dt or alvo > end_dt:
                    continue
                    
                hr = alvo.strftime("%H%M%S")
                fim_alvo = alvo + timedelta(seconds=10)
                if fim_alvo > end_dt:
                    fim_alvo = end_dt
                hr_end = fim_alvo.strftime("%H%M%S")
                
                horarios_tenta.append((hr, hr_end, alvo.strftime("%Y-%m-%dT%H:%M:%S")))
            except ValueError:
                pass
    else:
        for hr in ["020000", "030000", "040000", "010000", "000000", "050000"]:
            hr_end = hr[:4] + "05"
            hr_date = f"{date_str}T{hr[:2]}:{hr[2:4]}:{hr[4:6]}"
            horarios_tenta.append((hr, hr_end, hr_date))

    if not horarios_tenta:
        result_dict["status"] = "SEM_GRAVACAO"
        result_dict["motivo"] = "Sem gravação na madrugada (00h-06h)"
        return result_dict

    for hr, hr_end, hr_date in horarios_tenta:
        start_time = f"{date_clean}T{hr}Z"
        end_time = f"{date_clean}T{hr_end}Z"
        
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/Streaming/tracks/{canal_str}?starttime={start_time}&endtime={end_time}"
        
        try:
            cmd = [
                ffmpeg_exe, "-y", "-rtsp_transport", "tcp",
                "-i", rtsp_url, "-vframes", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "-"
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=25)
            
            if result.returncode == 0 and len(result.stdout) > 1000:
                result_dict["image"] = base64.b64encode(result.stdout).decode('utf-8')
                result_dict["horario"] = hr_date
                result_dict["status"] = "OK"
                result_dict["motivo"] = None
                return result_dict
            else:
                stderr_text = result.stderr.decode('utf-8', errors='ignore')
                if "400 Bad Request" in stderr_text and trechos is None:
                    continue
                else:
                    motivo = _motivo_ffmpeg(stderr_text)
                    result_dict["motivo"] = motivo
                    result_dict["status"] = "FALHA"
                    logging.warning(f"FFmpeg canal {canal} ({hr}): stdout len: {len(result.stdout)}, stderr: {stderr_text}")
        except subprocess.TimeoutExpired:
            result_dict["motivo"] = _motivo_ffmpeg("TIMEOUT_25S")
            result_dict["status"] = "FALHA"
            logging.warning(f"FFmpeg timeout no canal {canal} ({hr})")
        except Exception as e:
            result_dict["motivo"] = f"Erro no agente: {str(e)[:100]}"
            result_dict["status"] = "FALHA"
            logging.error(f"FFmpeg exception no canal {canal}: {e}")
            
    return result_dict
