import base64
import logging
import re
import socket
import urllib.parse
import subprocess
import time
from datetime import datetime, timezone
from typing import Dict, Any

def _mascarar(txt: str) -> str:
    """Oculta credenciais de URLs (rtsp://user:senha@host) antes de logar/enviar stderr do ffmpeg."""
    return re.sub(r'//[^@/\s]*@', '//***@', txt or "")


def _capturar_frame_ffmpeg(ffmpeg_exe: str, rtsp_url: str, transport: str = "tcp",
                           skip_nokey: bool = True, timeout: int = 6) -> tuple:
    """Executa o ffmpeg para capturar 1 frame via RTSP. Retorna (bytes_jpeg | None, stderr_str)."""
    cmd = [
        ffmpeg_exe, "-y",
        "-rtsp_transport", transport,
        "-timeout", "5000000",
    ]
    if skip_nokey:
        cmd.extend(["-skip_frame", "nokey"])
    cmd.extend([
        "-i", rtsp_url,
        "-vframes", "1",
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "-"
    ])
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if res.returncode == 0 and len(res.stdout) > 1000:
            return res.stdout, ""
        stderr_txt = _mascarar(res.stderr.decode('utf-8', errors='ignore')) if res.stderr else "ffmpeg retornou vazio"
        return None, stderr_txt
    except subprocess.TimeoutExpired:
        return None, f"Tempo esgotado ({timeout}s) via {transport.upper()}"
    except Exception as e:
        return None, _mascarar(str(e))


def test_rtsp_camera(task: Dict[str, Any]) -> Dict[str, Any]:
    """Testa a conexão RTSP da câmera localmente pelo agente e retorna a imagem em base64.
    Tenta até 4 URLs candidatas via TCP (com fallback seletivo para UDP em falhas de conexão/tempo)
    e acumula os motivos das tentativas, respeitando prazo total e interrompendo em 401."""
    senha_pura = task.get("password", "navarro@123")
    senha_enc = urllib.parse.quote(senha_pura, safe='')
    usuario = task.get("username", "admin")
    modelo = task.get("modelo", "")
    ip = task.get("ip", "").strip()
    canal = task.get("canal")

    if not ip or ip == "N/A":
        return {"success": False, "error_message": "Câmera sem endereço IP configurado."}

    nvr_canal = bool(canal) or bool(task.get("stream_principal"))
    marca = task.get("marca") or ""

    direct_cam = task.get("direct_camera", False)
    mod_upper = modelo.upper()
    marca_upper = marca.upper()

    eh_motorola = "MOTOROLA" in marca_upper or "MOTOROLA" in mod_upper or mod_upper.startswith("MTI")
    eh_onvif = "ONVIF" in mod_upper or "ONVIF" in marca_upper
    eh_grandstream = "GRANDSTREAM" in mod_upper or "GRANDSTREAM" in marca_upper or mod_upper.startswith("GXV")
    eh_intelbras = "INTELBRAS" in mod_upper or "INTELBRAS" in marca_upper or mod_upper.startswith("VIP")

    urls_candidatas = []
    if eh_motorola and not direct_cam and canal and int(canal) > 1:
        # NVR tradicional Motorola (NVMS-9000) com canais de hardware
        urls_candidatas.append(f"rtsp://{usuario}:{senha_enc}@{ip}:554/chID={canal}&streamType=main")
        urls_candidatas.append(f"rtsp://{usuario}:{senha_enc}@{ip}:554/?chID={canal}&streamType=main")
        urls_candidatas.append(f"rtsp://{usuario}:{senha_enc}@{ip}:554/profile{canal}")
    elif eh_motorola or eh_onvif:
        # Câmera IP Motorola (ex: MTIDM022603) ou ONVIF Profile S padrão
        ch = canal if canal else 1
        urls_candidatas.append(f"rtsp://{usuario}:{senha_enc}@{ip}:554/profile1")
        urls_candidatas.append(f"rtsp://{usuario}:{senha_enc}@{ip}:554/profile2")
        urls_candidatas.append(f"rtsp://{usuario}:{senha_enc}@{ip}:554/live/ch0")
        urls_candidatas.append(f"rtsp://{usuario}:{senha_enc}@{ip}:554/live/ch1")
        urls_candidatas.append(f"rtsp://{usuario}:{senha_enc}@{ip}:554/?chID={ch}&streamType=main")
        urls_candidatas.append(f"rtsp://{usuario}:{senha_enc}@{ip}:554/chID={ch}&streamType=main")
        urls_candidatas.append(f"rtsp://{usuario}:{senha_enc}@{ip}:554/onvif1")
        urls_candidatas.append(f"rtsp://{usuario}:{senha_enc}@{ip}:554/cam/realmonitor?channel={ch}&subtype=0")
    elif eh_grandstream:
        urls_candidatas.append(f"rtsp://{usuario}:{senha_enc}@{ip}:554/4")
        urls_candidatas.append(f"rtsp://{usuario}:{senha_enc}@{ip}:554/0")
    elif eh_intelbras:
        ch = canal if canal else 1
        subtype = 0 if nvr_canal else 1
        urls_candidatas.append(f"rtsp://{usuario}:{senha_enc}@{ip}:554/cam/realmonitor?channel={ch}&subtype={subtype}")
        if subtype == 0:
            urls_candidatas.append(f"rtsp://{usuario}:{senha_enc}@{ip}:554/cam/realmonitor?channel={ch}&subtype=1")
    else:
        # Hikvision e genéricos com fallback ONVIF
        ch_num = canal if canal else 1
        ch_str = f"{ch_num}01" if nvr_canal else f"{ch_num}02"
        urls_candidatas.append(f"rtsp://{usuario}:{senha_enc}@{ip}:554/Streaming/Channels/{ch_str}")
        if nvr_canal:
            urls_candidatas.append(f"rtsp://{usuario}:{senha_enc}@{ip}:554/Streaming/Channels/{ch_num}02")
        urls_candidatas.append(f"rtsp://{usuario}:{senha_enc}@{ip}:554/cam/realmonitor?channel={ch_num}&subtype=0")
        urls_candidatas.append(f"rtsp://{usuario}:{senha_enc}@{ip}:554/profile1")
        urls_candidatas.append(f"rtsp://{usuario}:{senha_enc}@{ip}:554/Streaming/Channels/{ch_num}")

    # Garante remoção de URLs duplicadas preservando a ordem
    urls_candidatas = list(dict.fromkeys(urls_candidatas))

    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    # Sem esta checagem, IP errado ou câmera desligada só falha depois de esgotar todas as tentativas
    try:
        socket.create_connection((ip, 554), timeout=5).close()
    except OSError:
        return {"success": False, "error_message": f"Porta RTSP 554 inacessível em {ip} (IP incorreto, câmera desligada ou bloqueio de rede)"}

    # Limite rigoroso de segurança: no máximo 4 URLs diferentes
    urls = urls_candidatas[:4]
    prazo_max = time.monotonic() + 40.0
    motivos = []

    for url in urls:
        caminho_curto = url.split(":554", 1)[-1]
        if prazo_max - time.monotonic() < 4.0:
            break

        # 1. Tentativa TCP
        timeout_tcp_desejado = 18 if url == urls[0] else 8
        timeout_efetivo = min(timeout_tcp_desejado, max(1, int(prazo_max - time.monotonic())))
        jpeg_bytes, stderr_txt = _capturar_frame_ffmpeg(
            ffmpeg_exe, url, transport="tcp", skip_nokey=True, timeout=timeout_efetivo
        )
        if jpeg_bytes:
            b64_str = base64.b64encode(jpeg_bytes).decode('utf-8')
            return {"success": True, "error_message": None, "image_base64": b64_str}

        stderr_txt = stderr_txt or "Falha desconhecida"
        if "401 Unauthorized" in stderr_txt:
            logging.warning(f"Câmera {ip} retornou 401 Unauthorized. Abortando imediatamente para prevenir lockout.")
            motivos.append(f"TCP {caminho_curto}: Usuário ou senha RTSP recusados pela câmera (interrompido na 1ª tentativa para evitar bloqueio)")
            break

        motivo = stderr_txt if "Tempo esgotado" in stderr_txt else _motivo_ao_vivo(stderr_txt)
        if motivo.startswith("Caminho RTSP não encontrado"):
            motivo = "Caminho RTSP não encontrado"
        entrada_motivo = f"TCP {caminho_curto}: {motivo}"
        if not motivos or motivos[-1] != entrada_motivo:
            motivos.append(entrada_motivo)

        # Verificar se deve tentar UDP:
        # NÃO tentar UDP se erro for 401, 404 ("404 Not Found"), 400 ("400 Bad Request") ou 453/503.
        # Tentar UDP somente se a falha TCP for de tempo ("Tempo esgotado") ou de conexão.
        nao_tentar_udp = any(cod in stderr_txt for cod in [
            "401 Unauthorized", "404 Not Found", "400 Bad Request",
            "453 Not Enough Bandwidth", "503 Service Unavailable",
        ])
        erros_conexao = ["Connection reset", "Connection refused", "timed out", "Invalid data found"]
        eh_elegivel_udp = not nao_tentar_udp and ("Tempo esgotado" in stderr_txt or any(err in stderr_txt for err in erros_conexao))

        if eh_elegivel_udp:
            if prazo_max - time.monotonic() < 4.0:
                break
            timeout_udp_desejado = 8 if url == urls[0] else 6
            timeout_efetivo_udp = min(timeout_udp_desejado, max(1, int(prazo_max - time.monotonic())))
            jpeg_bytes_udp, stderr_txt_udp = _capturar_frame_ffmpeg(
                ffmpeg_exe, url, transport="udp", skip_nokey=True, timeout=timeout_efetivo_udp
            )
            if jpeg_bytes_udp:
                b64_str = base64.b64encode(jpeg_bytes_udp).decode('utf-8')
                return {"success": True, "error_message": None, "image_base64": b64_str}

            stderr_txt_udp = stderr_txt_udp or "Falha desconhecida"
            if "401 Unauthorized" in stderr_txt_udp:
                logging.warning(f"Câmera {ip} retornou 401 Unauthorized. Abortando imediatamente para prevenir lockout.")
                motivos.append(f"UDP {caminho_curto}: Usuário ou senha RTSP recusados pela câmera (interrompido na 1ª tentativa para evitar bloqueio)")
                break

            motivo_udp = stderr_txt_udp if "Tempo esgotado" in stderr_txt_udp else _motivo_ao_vivo(stderr_txt_udp)
            if motivo_udp.startswith("Caminho RTSP não encontrado"):
                motivo_udp = "Caminho RTSP não encontrado"
            entrada_udp = f"UDP {caminho_curto}: {motivo_udp}"
            if not motivos or motivos[-1] != entrada_udp:
                motivos.append(entrada_udp)

    if motivos:
        msg = "; ".join(motivos)
        if "Caminho RTSP não encontrado" in msg:
            msg += " (confira o modelo da câmera: Hikvision, Intelbras, Grandstream ou ONVIF)"
        msg = msg[:320]
        return {"success": False, "error_message": f"FALHA RTSP ({ip}): {msg}"}

    return {"success": False, "error_message": f"FALHA RTSP ({ip}): Falha ao conectar via RTSP."}


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


def _motivo_ao_vivo(stderr: str) -> str:
    """Motivo legível da falha de captura ao vivo de uma câmera (sem credenciais)."""
    stderr = _mascarar(stderr)
    if "401 Unauthorized" in stderr:
        return "Usuário/senha RTSP recusados pela câmera"
    if any(e in stderr for e in ["404 Not Found", "400 Bad Request"]):
        return "Caminho RTSP não encontrado: confira o modelo da câmera (Hikvision, Intelbras, Grandstream ou ONVIF)"
    if any(e in stderr for e in ["Connection refused", "timed out", "No route to host", "Network is unreachable"]):
        return "Porta RTSP 554 inacessível"
    linhas = [linha.strip() for linha in stderr.split('\n') if linha.strip()]
    if linhas:
        return "Falha ao capturar: " + linhas[-1][:150]
    return "Falha ao capturar: a câmera não retornou imagem"

# Falhas de vídeo seguidas (por câmera) antes de desistir da imagem da noite no backup
MAX_FALHAS_CAPTURA = 2

# Interpretação do horário de playback que funcionou por NVR: "local" ou "utc"
_MODO_HORARIO_MOTOROLA = {}


def _frame_motorola(ffmpeg_exe, ip, usuario, senha_enc, canal, alvo, timeout=15):
    """Lê um frame do playback RTSP Motorola em `alvo` (datetime local). Retorna (jpeg|None, stderr)."""
    rtsp_url = (
        f"rtsp://{usuario}:{senha_enc}@{ip}:554/chID={canal}"
        f"&date={alvo.strftime('%Y-%m-%d')}&time={alvo.strftime('%H:%M:%S')}&timelen=10&streamType=main"
    )
    cmd = [
        ffmpeg_exe, "-y", "-rtsp_transport", "tcp", "-skip_frame", "nokey",
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
            local_tinha = False
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
                if modo == "local":
                    local_tinha = bool(na_madrugada)
                if not na_madrugada:
                    continue
                # O modo "utc" só vale para NVR que exibe o relógio em UTC (já confirmado antes) ou quando a
                # gravação existe no horário local mas o NVR não entregou o vídeo. Sem gravação na madrugada
                # local, tentar "utc" só testa horários deslocados (~3h) onde não há gravação: cada
                # tentativa espera o timeout inteiro e falha.
                if modo == "utc" and _MODO_HORARIO_MOTOROLA.get(ip) != "utc" and not local_tinha:
                    continue

                def distancia(t):
                    if t[0] <= ideal <= t[1]:
                        return 0
                    return min(abs((t[0] - ideal).total_seconds()), abs((t[1] - ideal).total_seconds()))
                alvos = []
                for st, en in sorted(na_madrugada, key=distancia)[:1]:
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
    
    horarios_tenta = []  # (início, fim, horário exibido): datetimes do relógio do NVR

    if trechos is not None:
        if len(trechos) == 0:
            result_dict["status"] = "SEM_GRAVACAO"
            result_dict["motivo"] = "Sem gravação na madrugada (00h-06h)"
            return result_dict

        for (st, end) in trechos:
            try:
                st_dt = datetime.strptime(st.replace("Z", "")[:19], "%Y-%m-%dT%H:%M:%S")
                end_dt = datetime.strptime(end.replace("Z", "")[:19], "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                continue
            # Trecho que atravessa a meia-noite (ou o fim da madrugada): corta na janela, para o
            # início/fim da URL ficarem no dia certo e a imagem ser mesmo da madrugada.
            st_dt = max(st_dt, inicio_madrugada)
            end_dt = min(end_dt, fim_madrugada)

            alvo = data_obj.replace(hour=2, minute=0, second=0)
            if alvo < st_dt + timedelta(seconds=2):
                alvo = st_dt + timedelta(seconds=2)
            if alvo > end_dt - timedelta(seconds=5):
                alvo = end_dt - timedelta(seconds=5)
            if alvo < st_dt or alvo > end_dt:
                continue  # trecho curto demais para ler um quadro

            fim_alvo = min(alvo + timedelta(seconds=10), end_dt)
            horarios_tenta.append((alvo, fim_alvo, alvo.strftime("%Y-%m-%dT%H:%M:%S")))
    else:
        for h in (2, 3, 4, 1, 0, 5):
            alvo = data_obj.replace(hour=h)
            horarios_tenta.append((alvo, alvo + timedelta(seconds=5), alvo.strftime("%Y-%m-%dT%H:%M:%S")))

    if not horarios_tenta:
        result_dict["status"] = "SEM_GRAVACAO"
        result_dict["motivo"] = "Sem gravação na madrugada (00h-06h)"
        return result_dict

    falhas = 0
    for alvo, fim_alvo, hr_date in horarios_tenta:
        if prazo is not None and time.monotonic() > prazo:
            result_dict["motivo"] = result_dict["motivo"] or "Tempo limite da captura esgotado"
            break
        start_time = alvo.strftime("%Y%m%dT%H%M%SZ")
        end_time = fim_alvo.strftime("%Y%m%dT%H%M%SZ")

        rtsp_url = f"rtsp://{usuario}:{senha_enc}@{ip}:554/Streaming/tracks/{canal_str}?starttime={start_time}&endtime={end_time}"

        try:
            cmd = [
                ffmpeg_exe, "-y", "-rtsp_transport", "tcp", "-skip_frame", "nokey",
                "-i", rtsp_url, "-vframes", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "-"
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=25)

            if result.returncode == 0 and len(result.stdout) > 1000:
                result_dict["image"] = base64.b64encode(result.stdout).decode('utf-8')
                result_dict["horario"] = hr_date
                result_dict["status"] = "OK"
                result_dict["motivo"] = None
                return result_dict
            stderr_text = _mascarar(result.stderr.decode('utf-8', errors='ignore'))
            if "400 Bad Request" in stderr_text and trechos is None:
                continue  # NVR sem busca: horário fixo sem gravação responde 400 na hora; não conta como falha
            result_dict["motivo"] = _motivo_ffmpeg(stderr_text)
            result_dict["status"] = "FALHA"
            logging.warning(f"FFmpeg canal {canal} ({alvo:%H:%M:%S}): {result_dict['motivo']}")
        except subprocess.TimeoutExpired:
            result_dict["motivo"] = _motivo_ffmpeg("TIMEOUT_25S")
            result_dict["status"] = "FALHA"
            logging.warning(f"FFmpeg timeout no canal {canal} ({alvo:%H:%M:%S})")
        except Exception as e:
            result_dict["motivo"] = f"Erro no agente: {str(e)[:100]}"
            result_dict["status"] = "FALHA"
            logging.error(f"FFmpeg exception no canal {canal}: {e}")

        falhas += 1
        if falhas >= MAX_FALHAS_CAPTURA:
            # O NVR não está entregando o vídeo desta câmera: insistir só atrasa o backup (25 s cada)
            logging.warning(f"Canal {canal}: {falhas} falhas seguidas, passando para a próxima câmera.")
            break

    return result_dict


# ─── Captura pela gravação (pedida pelo painel) ────────────────────────────
# Câmera offline não tem vídeo ao vivo, mas o NVR pode ter gravação. O servidor espera
# até 130s pela resposta; o agente encerra as tentativas em PRAZO_GRAVACAO_S.
PRAZO_GRAVACAO_S = 100
DIAS_BUSCA = 15


def _eh_motorola(task: Dict[str, Any]) -> bool:
    if task.get("direct_camera"):
        return False
    return "motorola" in (task.get("marca") or "").lower() or "motorola" in (task.get("modelo") or "").lower()


def _sem_playback(task: Dict[str, Any]) -> bool:
    """Equipamentos sem playback RTSP suportado (câmeras avulsas/outras marcas)."""
    if task.get("direct_camera"):
        return True
    modelo = (task.get("modelo") or "").upper()
    return any(m in modelo for m in ("GRANDSTREAM", "INTELBRAS", "ONVIF", "MTI"))


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
    cmd = [ffmpeg_exe, "-y", "-rtsp_transport", "tcp", "-skip_frame", "nokey",
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

    if task.get("direct_camera"):
        # Câmera direta da galeria de DIGIFORT/DEFENSE: sem playback de NVR, captura sempre ao vivo
        vivo = test_rtsp_camera(task)
        if vivo.get("success"):
            return {**vivo, "origem": "ao_vivo", "horario": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}
        return vivo

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


# ─── Imagem da noite de equipamentos VMS (DIGIFORT/DEFENSE) no backup da madrugada ─────────
# Câmeras diretas (IP próprio) não têm playback de NVR: a "imagem da noite" é capturada ao vivo,
# no stream principal, durante o próprio backup — por isso tem um orçamento de tempo total.
LIMITE_IMAGENS_NVR_S = 20 * 60


def capturar_imagens_noite_vms(equipamento_nome: str, cameras_lista: list, conf: dict, prazo=None) -> None:
    """Captura (ao vivo, stream principal) e envia a imagem da noite de cada câmera com IP de um
    equipamento DIGIFORT/DEFENSE. Mutila cada item de `cameras_lista` com `imagem_noite` (status/motivo/horario),
    do mesmo jeito que o relatório de NVR comum."""
    from src.application.api_client import upload_night_image

    if prazo is None:
        prazo = time.monotonic() + LIMITE_IMAGENS_NVR_S

    for cam in cameras_lista:
        ip = (cam.get("ip") or "").strip()
        if "." not in ip:
            continue
        if time.monotonic() > prazo:
            cam["imagem_noite"] = {"status": "FALHA", "motivo": "Tempo limite da captura esgotado", "horario": None}
            continue

        if cam.get("ip_compartilhado") and not cam.get("canal_rtsp"):
            cam["imagem_noite"] = {"status": "FALHA", "motivo": "IP compartilhado por várias câmeras: informe o canal da câmera no equipamento, na Galeria", "horario": None}
            continue

        res = test_rtsp_camera({
            "ip": ip,
            "username": cam.get("username") or "admin",
            "password": cam.get("password") or "navarro@123",
            "modelo": cam.get("modelo") or "Hikvision",
            "canal": cam.get("canal_rtsp"),
            "stream_principal": True,
        })

        if res.get("success") and res.get("image_base64"):
            horario_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            enviado = upload_night_image(conf, {
                "nvr_name": equipamento_nome,
                "canal": cam.get("canal"),
                "nome": cam.get("nome") or f"Canal {cam.get('canal')}",
                "image_base64": res["image_base64"],
                "night_image_date": horario_iso,
                "ip": ip,
                "modelo": cam.get("modelo") or "Hikvision",
                "canal_rtsp": cam.get("canal_rtsp"),
            })
            cam["imagem_noite"] = (
                {"status": "OK", "motivo": None, "horario": horario_iso} if enviado
                else {"status": "FALHA", "motivo": "Falha ao enviar a imagem para o servidor", "horario": None}
            )
        else:
            cam["imagem_noite"] = {"status": "FALHA", "motivo": res.get("error_message") or "Falha ao capturar a imagem.", "horario": None}
