import base64
import logging
import re
import urllib.parse
import subprocess
import time
from datetime import timezone
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

    marca = task.get("marca") or ""

    if "motorola" in marca.lower() or "motorola" in modelo.lower():
        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/chID={canal or 1}&streamType=main"
    elif "Grandstream" in modelo:
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

def _mascarar(txt: str) -> str:
    """Oculta credenciais de URLs (rtsp://user:senha@host) antes de logar/enviar stderr do ffmpeg."""
    return re.sub(r'//[^@/\s]*@', '//***@', txt or "")


def _motivo_ffmpeg(stderr: str) -> str:
    stderr = _mascarar(stderr)
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

# Interpretação do horário de playback que funcionou por NVR: "local" ou "utc"
_MODO_HORARIO_MOTOROLA = {}


def _frame_motorola(ffmpeg_exe, ip, usuario, senha_enc, canal, alvo, timeout=15):
    """Lê um frame do playback RTSP Motorola em `alvo` (datetime local). Retorna (jpeg|None, stderr)."""
    rtsp_url = (
        f"rtsp://{usuario}:{senha_enc}@{ip}:554/chID={canal}"
        f"&date={alvo.strftime('%Y-%m-%d')}&time={alvo.strftime('%H:%M:%S')}&timelen=10&streamType=main"
    )
    cmd = [
        ffmpeg_exe, "-y", "-rtsp_transport", "tcp",
        "-i", rtsp_url, "-vframes", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "-"
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if result.returncode == 0 and len(result.stdout) > 1000:
        return result.stdout, ""
    return None, _mascarar(result.stderr.decode('utf-8', errors='ignore'))


def capture_night_image_motorola(ip: str, usuario: str, senha_pura: str, canal: int, date_str: str, sessao=None,
                                 prazo=None) -> dict:
    """
    Captura um frame da madrugada (00h-06h) via playback RTSP de um NVR Motorola (NVMS-9000).
    Busca os trechos reais com queryChlRecLog e usa 02:00 limitado ao trecho (como no Hikvision).
    Horário sem gravação faz o NVR segurar a conexão; por isso, se a busca falhar, o fallback
    por horários fixos usa timeout curto.
    `prazo` (time.monotonic) interrompe as tentativas (captura pedida pelo painel).
    """
    import imageio_ffmpeg
    import logging
    from datetime import datetime, timedelta
    from src.nvr.motorola.recordings import buscar_trechos_motorola

    result_dict = {"image": None, "horario": None, "status": "FALHA", "motivo": None}

    try:
        data_obj = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        result_dict["motivo"] = "Data inválida"
        return result_dict

    senha_enc = urllib.parse.quote(senha_pura, safe='')
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    ideal = data_obj.replace(hour=2)

    inicio_madrugada = data_obj
    fim_madrugada = data_obj.replace(hour=6)

    # (modo, alvos): "local" = horário exibido no NVR é o do fuso local (padrão);
    # "utc" = NVR cujo relógio exibido coincide com o horário UTC cru devolvido pela busca.
    tentativas = []
    buscou_trechos = False
    if sessao is not None:
        # Janela larga, para cobrir qualquer diferença de fuso entre NVR e agente
        brutos = buscar_trechos_motorola(
            ip, sessao, canal, data_obj - timedelta(hours=6), data_obj + timedelta(hours=18), max_results=None)
        if brutos is not None:
            buscou_trechos = True
            modos = ["local", "utc"]
            if _MODO_HORARIO_MOTOROLA.get(ip) == "utc":
                modos.reverse()
            for modo in modos:
                exibidos = []
                for st_utc, en_utc in brutos:
                    # buscar_trechos_motorola devolve horário local do agente; recupera o UTC cru
                    if modo == "local":
                        exibidos.append((st_utc, en_utc))
                    else:
                        exibidos.append((st_utc.astimezone(timezone.utc).replace(tzinfo=None),
                                         en_utc.astimezone(timezone.utc).replace(tzinfo=None)))
                na_madrugada = [t for t in exibidos if t[0] < fim_madrugada and t[1] > inicio_madrugada]
                if not na_madrugada:
                    continue

                def distancia(t):
                    if t[0] <= ideal <= t[1]:
                        return 0
                    return min(abs((t[0] - ideal).total_seconds()), abs((t[1] - ideal).total_seconds()))
                alvos = []
                for st, en in sorted(na_madrugada, key=distancia)[:2]:
                    alvo = min(max(ideal, st + timedelta(seconds=1)), max(st, en - timedelta(seconds=3)))
                    alvos.append(alvo)
                tentativas.append((modo, alvos))

    if buscou_trechos:
        if not tentativas:
            result_dict["status"] = "SEM_GRAVACAO"
            result_dict["motivo"] = "Sem gravação na madrugada (00h-06h)"
            return result_dict
    else:
        tentativas = [("local", [data_obj.replace(hour=h) for h in (2, 3, 4, 1, 5, 0)])]

    for modo, alvos in tentativas:
        for alvo in alvos:
            if prazo is not None and time.monotonic() > prazo:
                result_dict["motivo"] = result_dict["motivo"] or "Tempo limite da captura esgotado"
                return result_dict
            try:
                jpeg, stderr_text = _frame_motorola(ffmpeg_exe, ip, usuario, senha_enc, canal, alvo)
                if jpeg:
                    _MODO_HORARIO_MOTOROLA[ip] = modo
                    result_dict["image"] = base64.b64encode(jpeg).decode('utf-8')
                    result_dict["horario"] = alvo.strftime("%Y-%m-%dT%H:%M:%S")
                    result_dict["status"] = "OK"
                    result_dict["motivo"] = None
                    return result_dict
                result_dict["motivo"] = _motivo_ffmpeg(stderr_text)
                logging.warning(f"FFmpeg Motorola canal {canal} ({alvo:%H:%M:%S}, {modo}): {stderr_text[-300:]}")
            except subprocess.TimeoutExpired:
                result_dict["motivo"] = "NVR não entregou vídeo na madrugada (tempo esgotado)"
                logging.warning(f"FFmpeg Motorola timeout no canal {canal} ({alvo:%H:%M:%S}, {modo})")
            except Exception as e:
                result_dict["motivo"] = f"Erro no agente: {str(e)[:100]}"
                logging.error(f"FFmpeg Motorola exception no canal {canal}: {e}")

    return result_dict


def capture_night_image(ip: str, usuario: str, senha_pura: str, canal: int, date_str: str, prazo=None) -> dict:
    """
    Tenta conectar via RTSP no stream de playback do NVR Hikvision
    e captura um frame da madrugada. Retorna um dicionário com o status e motivo.
    """
    import imageio_ffmpeg
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
        if prazo is not None and time.monotonic() > prazo:
            result_dict["motivo"] = result_dict["motivo"] or "Tempo limite da captura esgotado"
            break
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
                stderr_text = _mascarar(result.stderr.decode('utf-8', errors='ignore'))
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


# ─── Captura pela gravação (pedida pelo painel) ────────────────────────────
# Câmera offline não tem vídeo ao vivo, mas o NVR pode ter gravação. O servidor espera
# até 130s pela resposta; o agente encerra as tentativas em PRAZO_GRAVACAO_S.
PRAZO_GRAVACAO_S = 100
DIAS_BUSCA = 15


def _eh_motorola(task: Dict[str, Any]) -> bool:
    return "motorola" in (task.get("marca") or "").lower() or "motorola" in (task.get("modelo") or "").lower()


def _sem_playback(task: Dict[str, Any]) -> bool:
    """Equipamentos sem playback RTSP suportado (câmeras avulsas/outras marcas)."""
    modelo = task.get("modelo") or ""
    return any(m in modelo for m in ("Grandstream", "Intelbras", "ONVIF"))


def _resultado(r: dict, origem: str) -> Dict[str, Any]:
    if r.get("status") == "OK" and r.get("image"):
        return {"success": True, "error_message": None, "image_base64": r["image"],
                "horario": r.get("horario"), "origem": origem}
    return {"success": False, "error_message": r.get("motivo") or "Falha ao capturar da gravação."}


def _frame_hikvision(ffmpeg_exe, ip, usuario, senha_enc, canal, alvo, fim_trecho):
    """Lê um frame do playback Hikvision em `alvo` (horário exibido no NVR). Retorna (jpeg|None, stderr)."""
    from datetime import timedelta
    fim = max(alvo, min(alvo + timedelta(seconds=10), fim_trecho))
    rtsp_url = (
        f"rtsp://{usuario}:{senha_enc}@{ip}:554/Streaming/tracks/{canal}01"
        f"?starttime={alvo:%Y%m%dT%H%M%S}Z&endtime={fim:%Y%m%dT%H%M%S}Z"
    )
    cmd = [ffmpeg_exe, "-y", "-rtsp_transport", "tcp",
           "-i", rtsp_url, "-vframes", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "-"]
    result = subprocess.run(cmd, capture_output=True, timeout=25)
    if result.returncode == 0 and len(result.stdout) > 1000:
        return result.stdout, ""
    return None, _mascarar(result.stderr.decode('utf-8', errors='ignore'))


def _gravacao_recente_hikvision(task, prazo) -> dict:
    """Frame do fim do trecho gravado mais recente, buscando em janelas de 6h do agora para trás."""
    import imageio_ffmpeg
    from datetime import datetime, timedelta
    from src.nvr.hikvision.recordings import buscar_trechos

    ip, usuario, senha = task.get("ip", "").strip(), task.get("username", "admin"), task.get("password", "")
    canal = int(task["canal"])
    r = {"image": None, "horario": None, "status": "FALHA", "motivo": None}
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    senha_enc = urllib.parse.quote(senha, safe='')

    fim_janela = datetime.now().replace(microsecond=0)
    limite = fim_janela - timedelta(days=DIAS_BUSCA)
    while fim_janela > limite:
        if time.monotonic() > prazo:
            r["motivo"] = r["motivo"] or "Tempo limite da busca na gravação esgotado"
            return r
        inicio_janela = max(limite, fim_janela - timedelta(hours=6))
        trechos = buscar_trechos(ip, usuario, senha, canal, inicio_janela, fim_janela, max_results=100)
        if trechos is None:
            r["motivo"] = "NVR não respondeu à busca de gravações"
            return r
        validos = []
        for st, en in trechos:
            try:
                validos.append((datetime.strptime(st.replace("Z", "")[:19], "%Y-%m-%dT%H:%M:%S"),
                                datetime.strptime(en.replace("Z", "")[:19], "%Y-%m-%dT%H:%M:%S")))
            except ValueError:
                continue
        for st, en in sorted(validos, key=lambda t: t[1], reverse=True)[:2]:
            if time.monotonic() > prazo:
                break
            en = min(en, fim_janela)
            alvo = max(st + timedelta(seconds=1), en - timedelta(seconds=5))
            try:
                jpeg, stderr = _frame_hikvision(ffmpeg_exe, ip, usuario, senha_enc, canal, alvo, en)
            except subprocess.TimeoutExpired:
                jpeg, stderr = None, "TIMEOUT_25S"
            if jpeg:
                return {"image": base64.b64encode(jpeg).decode('utf-8'), "horario": alvo.strftime("%Y-%m-%dT%H:%M:%S"),
                        "status": "OK", "motivo": None}
            r["motivo"] = _motivo_ffmpeg(stderr)
            logging.warning(f"Captura da gravação canal {canal} ({alvo}): {stderr[-300:]}")
        if validos:
            return r  # havia gravação, mas o NVR não entregou o vídeo
        fim_janela = inicio_janela
    r["status"] = "SEM_GRAVACAO"
    r["motivo"] = f"Sem gravação nos últimos {DIAS_BUSCA} dias"
    return r


def _gravacao_recente_motorola(task, sessao, prazo) -> dict:
    """Frame do fim do trecho gravado mais recente (queryChlRecLog dos últimos DIAS_BUSCA dias)."""
    import imageio_ffmpeg
    from datetime import datetime, timedelta
    from src.nvr.motorola.recordings import buscar_trechos_motorola

    ip, usuario, senha = task.get("ip", "").strip(), task.get("username", "admin"), task.get("password", "")
    canal = int(task["canal"])
    r = {"image": None, "horario": None, "status": "FALHA", "motivo": None}
    agora = datetime.now().replace(microsecond=0)
    brutos = buscar_trechos_motorola(ip, sessao, canal, agora - timedelta(days=DIAS_BUSCA), agora, max_results=None)
    if brutos is None:
        r["motivo"] = "NVR não respondeu à busca de gravações"
        return r
    if not brutos:
        r["status"] = "SEM_GRAVACAO"
        r["motivo"] = f"Sem gravação nos últimos {DIAS_BUSCA} dias"
        return r

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    senha_enc = urllib.parse.quote(senha, safe='')
    modos = ["local", "utc"]
    if _MODO_HORARIO_MOTOROLA.get(ip) == "utc":
        modos.reverse()
    for modo in modos:
        for st, en in sorted(brutos, key=lambda t: t[1], reverse=True)[:2]:
            if modo == "utc":  # mesma conversão de capture_night_image_motorola
                st = st.astimezone(timezone.utc).replace(tzinfo=None)
                en = en.astimezone(timezone.utc).replace(tzinfo=None)
            if time.monotonic() > prazo:
                r["motivo"] = r["motivo"] or "Tempo limite da busca na gravação esgotado"
                return r
            alvo = max(st + timedelta(seconds=1), en - timedelta(seconds=5))
            try:
                jpeg, stderr = _frame_motorola(ffmpeg_exe, ip, usuario, senha_enc, canal, alvo)
            except subprocess.TimeoutExpired:
                jpeg, stderr = None, "NVR não entregou o vídeo (tempo esgotado)"
            if jpeg:
                _MODO_HORARIO_MOTOROLA[ip] = modo
                return {"image": base64.b64encode(jpeg).decode('utf-8'), "horario": alvo.strftime("%Y-%m-%dT%H:%M:%S"),
                        "status": "OK", "motivo": None}
            r["motivo"] = _motivo_ffmpeg(stderr)
            logging.warning(f"Captura da gravação Motorola canal {canal} ({alvo}, {modo}): {stderr[-300:]}")
    return r


def _noite_recente(task, sessao, prazo) -> dict:
    """Imagem da madrugada (00h-06h) da noite mais recente com gravação, voltando até DIAS_BUSCA dias."""
    from datetime import datetime, timedelta
    ip, usuario, senha = task.get("ip", "").strip(), task.get("username", "admin"), task.get("password", "")
    canal = int(task["canal"])
    agora = datetime.now()
    dia = agora if agora.hour >= 6 else agora - timedelta(days=1)  # madrugada de hoje só depois das 06h
    r = {"image": None, "horario": None, "status": "SEM_GRAVACAO",
         "motivo": f"Sem gravação na madrugada (00h-06h) nos últimos {DIAS_BUSCA} dias"}
    falhas = 0
    for _ in range(DIAS_BUSCA):
        if time.monotonic() > prazo:
            if r["status"] != "FALHA":
                r = {**r, "status": "FALHA", "motivo": "Tempo limite da busca na gravação esgotado"}
            return r
        data_str = dia.strftime("%Y-%m-%d")
        if _eh_motorola(task):
            ret = capture_night_image_motorola(ip, usuario, senha, canal, data_str, sessao=sessao, prazo=prazo)
        else:
            ret = capture_night_image(ip, usuario, senha, canal, data_str, prazo=prazo)
        if ret["status"] == "OK":
            return ret
        if ret["status"] == "FALHA":
            r = ret
            falhas += 1
            if falhas >= 2:  # havia gravação mas o NVR não entregou o vídeo duas vezes: desiste
                return r
        dia -= timedelta(days=1)
    return r


def executar_tarefa_rtsp(task: Dict[str, Any]) -> Dict[str, Any]:
    """Tarefa de captura pedida pelo painel.
    modo "ao_vivo" (padrão): frame ao vivo. "referencia": ao vivo e, se falhar (câmera offline),
    o frame mais recente da gravação. "noite": madrugada mais recente com gravação."""
    modo = task.get("modo") or "ao_vivo"
    if modo == "ao_vivo":
        return test_rtsp_camera(task)
    if not task.get("canal"):
        return {"success": False, "error_message": "Canal não informado."}

    erro_vivo = None
    if modo == "referencia":
        vivo = test_rtsp_camera(task)
        if vivo.get("success"):
            vivo.update(origem="ao_vivo", horario=None)
            return vivo
        erro_vivo = vivo.get("error_message")
        logging.info(f"Ao vivo falhou no canal {task.get('canal')} ({erro_vivo}); buscando na gravação...")

    if _sem_playback(task):
        return {"success": False, "error_message": erro_vivo or "Captura pela gravação não suportada neste equipamento."}

    prazo = time.monotonic() + PRAZO_GRAVACAO_S
    sessao = None
    if _eh_motorola(task):
        from src.nvr.motorola.cameras import buscar_cameras as login_motorola
        _, sessao = login_motorola(task.get("ip", "").strip(), task.get("username", "admin"), task.get("password", ""))
        if sessao is None:
            return {"success": False, "error_message": "Falha no login do NVR Motorola."}

    if modo == "noite":
        return _resultado(_noite_recente(task, sessao, prazo), "gravacao")

    ret = (_gravacao_recente_motorola(task, sessao, prazo) if _eh_motorola(task)
           else _gravacao_recente_hikvision(task, prazo))
    res = _resultado(ret, "gravacao")
    if not res["success"]:
        res["error_message"] = f"Ao vivo: câmera sem vídeo. Gravação: {ret.get('motivo') or 'falhou'}"
    return res
