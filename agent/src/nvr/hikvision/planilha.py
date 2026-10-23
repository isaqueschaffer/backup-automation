import logging
import time
from datetime import datetime
from pathlib import Path

import requests
from requests.auth import HTTPDigestAuth

from src.nvr.planilha_comum import (
    COR_AGENDA, COR_EVENTOS, COR_IMAGEM, COR_MOVIMENTO, COR_STREAM, SMART_NOMES, aba, aba_resumo, consolidar_cameras,
    eh_sensivel, novo_workbook,
)
from src.utils.xml_parser import parse_xml_seguro

TIMEOUT_S = 20
PAUSA_S = 0.2
LIMITE_TOTAL_S = 300  # NVR travado nao pode prender o backup: depois disso as consultas restantes sao puladas
MAX_CANAIS = 64

_DIAS = {"monday": "Seg", "tuesday": "Ter", "wednesday": "Qua", "thursday": "Qui", "friday": "Sex",
         "saturday": "Sáb", "sunday": "Dom"}
_DIAS_NUM = {"1": "Seg", "2": "Ter", "3": "Qua", "4": "Qui", "5": "Sex", "6": "Sáb", "7": "Dom"}
_EVENTOS_CAMERA = [
    ("VMD", "Movimento"), ("videoloss", "Perda de vídeo"), ("tamperdetection", "Máscara/obstrução"),
    ("defocus", "Desfoque"), ("scenechangedetection", "Mudança de cena"), ("fielddetection", "Intrusão"),
    ("linedetection", "Cruzamento de linha"), ("regionEntrance", "Entrada em região"),
    ("regionExiting", "Saída de região"), ("unattendedBaggage", "Objeto abandonado"),
    ("attendedBaggage", "Objeto retirado"), ("facedetection", "Detecção de rosto"),
]
_EVENTOS_SISTEMA = {
    "diskfull": "Disco cheio", "diskerror": "Erro de disco", "nicbroken": "Rede desconectada",
    "ipconflict": "Conflito de IP", "illaccess": "Acesso ilegal (login inválido)",
    "recordingfailure": "Falha de gravação", "audioexception": "Exceção de áudio",
}
_STATUS_CONEXAO = {"connect": "Conectada", "netUnreachable": "Câmera inacessível na rede"}

# Rotulo -> caminho dos recursos de configuracao do NVR que entram na aba 'Sistema (config)'
_CONFIG_SISTEMA = [
    ("Hora", "/ISAPI/System/time"), ("NTP", "/ISAPI/System/time/ntpServers"),
    ("Portas e serviços", "/ISAPI/Security/adminAccesses"), ("UPnP", "/ISAPI/System/Network/UPnP"),
    ("DDNS", "/ISAPI/System/Network/dns"), ("Servidor de log", "/ISAPI/System/logServer"),
    ("Notificação HTTP", "/ISAPI/Event/notification/httpHosts"), ("Áudio", "/ISAPI/System/Audio/channels"),
    ("Entradas de alarme (IO)", "/ISAPI/System/IO/inputs"), ("Saídas de alarme (IO)", "/ISAPI/System/IO/outputs"),
    ("Armazenamento", "/ISAPI/ContentMgmt/Storage"),
]


class _Isapi:
    """Consultas GET ao ISAPI numa sessao Digest; guarda o resultado de cada recurso (aba 'Comandos')."""

    def __init__(self, nvr_ip, usuario, senha):
        self.ip = nvr_ip
        self.sessao = requests.Session()
        self.sessao.auth = HTTPDigestAuth(usuario, senha)
        self.sessao.verify = False
        self.comandos = []  # (recurso, resultado)
        self._limite = time.monotonic() + LIMITE_TOTAL_S

    def obter(self, caminho, timeout=TIMEOUT_S):
        """Retorna a raiz do XML (sem namespaces) ou None se falhou. Nunca levanta excecao."""
        if time.monotonic() > self._limite:
            self.comandos.append((caminho, "pulado: tempo total esgotado"))
            return None
        try:
            for tentativa in (1, 2):  # o NVR as vezes derruba a conexao: uma nova tentativa resolve
                try:
                    resp = self.sessao.get(f"http://{self.ip}{caminho}", timeout=timeout)
                    break
                except requests.ConnectionError:
                    if tentativa == 2:
                        raise
                    time.sleep(2)
            if resp.status_code != 200:
                self.comandos.append((caminho, f"HTTP {resp.status_code}"))
                return None
            raiz = parse_xml_seguro(resp.content)
            for el in raiz.iter():
                if isinstance(el.tag, str):
                    el.tag = el.tag.rsplit("}", 1)[-1]
            self.comandos.append((caminho, "sucesso"))
            return raiz
        except Exception as e:
            self.comandos.append((caminho, f"erro: {type(e).__name__}"))
            return None
        finally:
            time.sleep(PAUSA_S)


def _t(el, caminho, padrao=""):
    """Texto de um sub-elemento (sem espacos), ou `padrao`."""
    if el is None:
        return padrao
    alvo = el.find(caminho)
    return (alvo.text or "").strip() if alvo is not None and alvo.text is not None else padrao


def _numero(txt):
    try:
        return float(str(txt).strip())
    except (ValueError, TypeError):
        return None


def _sim_nao(txt):
    return "Sim" if str(txt).strip().lower() == "true" else ("Não" if str(txt).strip() else "")


def _achatar(elemento, prefixo=""):
    """Lista (caminho, valor) das folhas; itens repetidos viram tag[id]. Descarta usuario/senha."""
    saida = []
    contagem = {}
    for filho in elemento:
        if not isinstance(filho.tag, str) or eh_sensivel(filho.tag):
            continue
        n = contagem[filho.tag] = contagem.get(filho.tag, 0) + 1
        irmaos = sum(1 for f in elemento if f.tag == filho.tag)
        nome = f"{prefixo}{filho.tag}"
        if irmaos > 1:
            nome += f"[{_t(filho, 'id') or n}]"
        if len(filho):
            saida += _achatar(filho, nome + ".")
        else:
            saida.append((nome, (filho.text or "").strip()))
    return saida


def _agenda_blocos(blocos):
    """Resume blocos (dia, inicio, fim): '24x7' se todos os dias cobrem 00:00-24:00."""
    cobertura = {(d, i, f) for d, i, f in blocos}
    if cobertura and {d for d, _, _ in cobertura} == set(_DIAS_NUM.values()) and \
            all(i == "00:00" and f in ("24:00", "23:59") for _, i, f in cobertura) and len(cobertura) == 7:
        return "24x7"
    return " | ".join(f"{d} {i}-{f}" for d, i, f in blocos)


def _formatar_uptime(segundos):
    s = _numero(segundos)
    if s is None:
        return ""
    dias, resto = divmod(int(s), 86400)
    return f"{dias} dia(s) {resto // 3600:02d}:{resto % 3600 // 60:02d}"


def _coletar_cameras(isapi):
    """Retorna (linhas da aba Câmeras, {canal: nome}, [canais configurados], [canais online])."""
    canais = isapi.obter("/ISAPI/ContentMgmt/InputProxy/channels")
    status = isapi.obter("/ISAPI/ContentMgmt/InputProxy/channels/status")
    estados = {_t(s, "id"): s for s in status.findall("InputProxyChannelStatus")} if status is not None else {}

    linhas, nomes, configurados, online = [], {}, [], []
    if canais is not None:
        for c in canais.findall("InputProxyChannel"):
            cid = _t(c, "id")
            if not cid.isdigit():
                continue
            origem = c.find("sourceInputPortDescriptor")
            ip = _t(origem, "ipAddress")
            st = estados.get(cid)
            conexao = _t(st, "chanDetectResult")
            nomes[int(cid)] = _t(c, "name")
            if ip and ip != "0.0.0.0":
                configurados.append(int(cid))
                if _t(st, "online") == "true":
                    online.append(int(cid))
            linhas.append([
                int(cid), _t(c, "name"), _t(origem, "proxyProtocol"), ip, _t(origem, "managePortNo"),
                _t(origem, "srcInputPort"), _t(origem, "connMode"), _t(origem, "streamType"),
                _t(origem, "model"), _t(origem, "serialNumber"), _t(origem, "firmwareVersion"),
                _sim_nao(_t(c, "enableAnr")), _sim_nao(_t(c, "enableTiming")),
                _sim_nao(_t(st, "online")), _STATUS_CONEXAO.get(conexao, conexao),
                _t(st, "SecurityStatus/PasswordStatus"), _t(c, "devIndex"),
            ])
    if not linhas:  # DVR analogico: os canais vem das entradas de video
        entradas = isapi.obter("/ISAPI/System/Video/inputs/channels")
        if entradas is not None:
            for c in entradas.findall("VideoInputChannel"):
                cid = _t(c, "id")
                if not cid.isdigit():
                    continue
                nomes[int(cid)] = _t(c, "name")
                configurados.append(int(cid))
                sem_video = _t(c, "resDesc").upper() == "NO VIDEO"
                if not sem_video:
                    online.append(int(cid))
                linhas.append([int(cid), _t(c, "name"), "ANALÓGICO", "", "", cid, "", "", "", "", "", "", "",
                               "Não" if sem_video else "Sim", _t(c, "resDesc"), "", ""])
    return linhas, nomes, configurados, online


def _linha_stream(canal_id, elemento):
    if elemento is None:
        return [""] * 8
    video = elemento.find("Video")
    audio = elemento.find("Audio")
    controle = _t(video, "videoQualityControlType")
    bitrate = _t(video, "constantBitRate") if controle == "CBR" else _t(video, "vbrUpperCap")
    fps = _numero(_t(video, "maxFrameRate"))
    fps = (fps / 100 if fps >= 100 else fps) if fps is not None else ""
    largura, altura = _t(video, "videoResolutionWidth"), _t(video, "videoResolutionHeight")
    return [
        _t(video, "videoCodecType"), f"{largura}x{altura}" if largura else "", controle, bitrate, fps,
        _t(video, "GovLength"), _sim_nao(_t(video, "SmartCodec/enabled")), _sim_nao(_t(audio, "enabled")),
    ]


def _coletar_stream(isapi, nomes):
    todos = isapi.obter("/ISAPI/Streaming/channels")
    por_id = {_t(s, "id"): s for s in todos.findall("StreamingChannel")} if todos is not None else {}
    canais = sorted(set(nomes) | {int(i) // 100 for i in por_id if i.isdigit()})
    linhas = []
    for n in canais:
        linha = [n, nomes.get(n, "")]
        for fluxo in (1, 2, 3):
            linha += _linha_stream(n, por_id.get(str(n * 100 + fluxo)))
        linhas.append(linha)
    return linhas


def _resumo_trilha(trilha):
    """Retorna (modos usados na agenda, resumo da agenda) de uma trilha de gravacao."""
    acoes = []
    for a in trilha.findall(".//ScheduleAction"):
        if _t(a, "Actions/Record") != "true":
            continue
        dia = _DIAS.get(_t(a, "ScheduleActionStartTime/DayOfWeek").lower(), "?")
        fim_dia = _DIAS.get(_t(a, "ScheduleActionEndTime/DayOfWeek").lower(), "?")
        ini, fim = _t(a, "ScheduleActionStartTime/TimeOfDay")[:5], _t(a, "ScheduleActionEndTime/TimeOfDay")[:5]
        acoes.append((dia, ini, fim_dia, fim, _t(a, "Actions/ActionRecordingMode")))
    if not acoes:
        return "", ""
    modos = ", ".join(sorted({m for *_, m in acoes if m}))
    unicos = {(ini, fim, m) for _, ini, _, fim, m in acoes}
    if len({d for d, *_ in acoes}) == 7 and len(unicos) == 1:
        ini, fim, m = next(iter(unicos))
        return modos, f"Todos os dias {ini}→{fim} {m}".strip()
    return modos, " | ".join(f"{d} {ini}→{fd} {fim} {m}".strip() for d, ini, fd, fim, m in acoes)


def _coletar_gravacao(isapi, nomes):
    raiz = isapi.obter("/ISAPI/ContentMgmt/record/tracks")
    linhas = []
    if raiz is None:
        return linhas
    for t in raiz.findall("Track"):
        tid = _t(t, "id")
        if not tid.isdigit() or int(tid) % 100 != 1:  # so a trilha do fluxo principal (N01) de cada canal
            continue
        canal = int(tid) // 100
        modos, agenda = _resumo_trilha(t)
        linhas.append([canal, nomes.get(canal, ""), _sim_nao(_t(t, "Enable")), _t(t, "DefaultRecordingMode"),
                       modos, agenda, _t(t, "Description")])
    return sorted(linhas)


def _cobertura_grade(mapa, linhas, colunas):
    """% de celulas marcadas no gridMap (cada linha ocupa colunas/4 arredondado para cima digitos hex)."""
    try:
        linhas, colunas = int(linhas), int(colunas)
        hex_por_linha = (colunas + 3) // 4
        marcadas = 0
        for i in range(linhas):
            trecho = mapa[i * hex_por_linha:(i + 1) * hex_por_linha]
            bits = bin(int(trecho, 16))[2:].zfill(hex_por_linha * 4)[:colunas]
            marcadas += bits.count("1")
        return round(marcadas / (linhas * colunas) * 100)
    except (ValueError, ZeroDivisionError):
        return ""


def _coletar_movimento(isapi, nomes, canais, eventos):
    linhas = []
    for n in canais:
        md = isapi.obter(f"/ISAPI/System/Video/inputs/channels/{n}/motionDetection")
        agenda = isapi.obter(f"/ISAPI/Event/schedules/motionDetections/VMD_video{n}")
        if md is None:
            continue
        grade = md.find("Grid")
        layout = md.find("MotionDetectionLayout")
        blocos = []
        if agenda is not None:
            for b in agenda.findall(".//TimeBlock"):
                blocos.append((_DIAS_NUM.get(_t(b, "dayOfWeek"), _t(b, "dayOfWeek")),
                               _t(b, "TimeRange/beginTime")[:5], _t(b, "TimeRange/endTime")[:5]))
        linhas.append([
            n, nomes.get(n, ""), _sim_nao(_t(md, "enabled")), _t(layout, "sensitivityLevel"),
            _cobertura_grade(_t(layout, "layout/gridMap"), _t(grade, "rowGranularity"),
                             _t(grade, "columnGranularity")),
            _t(md, "samplingInterval"), _t(md, "startTriggerTime"), _t(md, "endTriggerTime"),
            _sim_nao(_t(md, "enableHighlight")), _agenda_blocos(blocos),
            ", ".join(sorted(eventos.get((n, "VMD"), []))),
        ])
    return linhas


def _coletar_eventos(isapi):
    """Retorna ({(canal, tipo): metodos}, linhas dos eventos do sistema)."""
    raiz = isapi.obter("/ISAPI/Event/triggers")
    por_canal, sistema = {}, []
    if raiz is None:
        return por_canal, sistema
    for t in raiz.findall("EventTrigger"):
        tipo = _t(t, "eventType")
        metodos = sorted({_t(n, "notificationMethod") for n in t.findall(".//EventTriggerNotification")} - {""})
        canal = _t(t, "dynVideoInputChannelID") or _t(t, "videoInputChannelID")
        if canal.isdigit():
            por_canal.setdefault((int(canal), tipo), set()).update(metodos)
        elif tipo == "IO":
            if metodos:  # entradas de alarme sem acao so poluem a aba (o estado delas esta em Sistema (config))
                sistema.append([f"Entrada de alarme {_t(t, 'inputIOPortID')}", ", ".join(metodos)])
        elif tipo in _EVENTOS_SISTEMA:
            sistema.append([_EVENTOS_SISTEMA[tipo], ", ".join(metodos) or "(nenhuma)"])
        elif tipo:
            sistema.append([tipo, ", ".join(metodos) or "(nenhuma)"])
    return por_canal, sistema


def _linhas_eventos_camera(nomes, canais, eventos):
    """Uma linha por camera, uma coluna por tipo de evento (celula = acoes ligadas a ele)."""
    todos = sorted(set(canais) | {c for c, _ in eventos})
    linhas = []
    for n in todos:
        linha = [n, nomes.get(n, "")]
        for tipo, _ in _EVENTOS_CAMERA:
            metodos = eventos.get((n, tipo))
            linha.append("" if metodos is None else (", ".join(sorted(metodos)) or "(nenhuma)"))
        linhas.append(linha)
    return linhas


def _coletar_imagem(isapi, nomes, canais):
    linhas = []
    for n in canais:
        img = isapi.obter(f"/ISAPI/Image/channels/{n}")
        osd = isapi.obter(f"/ISAPI/System/Video/inputs/channels/{n}/overlays")
        if img is None and osd is None:
            continue
        linhas.append([
            n, nomes.get(n, ""), _t(img, "WDR/mode"), _t(img, "WDR/WDRLevel"), _sim_nao(_t(img, "BLC/enabled")),
            _t(img, "Color/brightnessLevel"), _t(img, "Color/contrastLevel"), _t(img, "Color/saturationLevel"),
            _sim_nao(_t(osd, "channelNameOverlay/enabled")), _sim_nao(_t(osd, "DateTimeOverlay/enabled")),
            _t(osd, "DateTimeOverlay/dateStyle"), _t(osd, "DateTimeOverlay/timeStyle"),
        ])
    return linhas


def _coletar_discos(isapi):
    """Retorna (linhas da aba Discos, linhas da aba SMART)."""
    raiz = isapi.obter("/ISAPI/ContentMgmt/Storage/hdd")
    discos, atributos = [], []
    if raiz is None:
        return discos, atributos
    for h in raiz.findall("hdd"):
        hid = _t(h, "id")
        smart = isapi.obter(f"/ISAPI/ContentMgmt/Storage/hdd/{hid}/SMARTTest/status", timeout=10)
        capacidade = _numero(_t(h, "capacity"))  # MB
        livre = _numero(_t(h, "freeSpace"))
        dias = _numero(_t(smart, "powerOnDay"))
        temp = _numero(_t(smart, "temprature"))
        avaliacao = f"autoavaliação={_t(smart, 'selfEvaluaingStatus')}; geral={_t(smart, 'allEvaluaingStatus')}; "                     f"teste={_t(smart, 'selfTestStatus')}" if smart is not None else ""
        discos.append([
            hid, _t(h, "hddName"), _t(h, "hddType"), _t(h, "status"), _t(h, "property"),
            round(capacidade / 1024, 1) if capacidade else "", round(livre / 1024, 1) if livre is not None else "",
            int(dias) if dias is not None and dias >= 0 else "",
            int(temp) if temp is not None and -20 <= temp <= 120 else "", avaliacao,
        ])
        if smart is not None:
            for r in smart.findall(".//TestResult"):
                aid = _t(r, "attributeID")
                if aid in ("", "0") or _t(r, "status") == "illegal":
                    continue
                atributos.append([hid, aid, SMART_NOMES.get(aid, ""), _t(r, "value"), _t(r, "worst"),
                                  _t(r, "thresholds"), _t(r, "rawValue"), _t(r, "status")])
    return discos, atributos


def _coletar_rede(isapi):
    raiz = isapi.obter("/ISAPI/System/Network/interfaces")
    linhas = []
    if raiz is None:
        return linhas
    for nic in raiz.findall("NetworkInterface"):
        ip = nic.find("IPAddress")
        link = nic.find("Link")
        linhas.append([
            _t(nic, "id"), _t(ip, "addressingType"), _t(ip, "ipAddress"), _t(ip, "subnetMask"),
            _t(ip, "DefaultGateway/ipAddress"), _t(ip, "PrimaryDNS/ipAddress"), _t(ip, "SecondaryDNS/ipAddress"),
            _t(link, "MACAddress"), _t(link, "speed"), _t(link, "duplex"), _t(link, "MTU"),
            _sim_nao(_t(link, "autoNegotiation")), _t(ip, "ipv6Address"),
        ])
    return linhas


def _tentar(rotulo, padrao, funcao, *args):
    """Uma secao com erro de leitura vira vazia, sem derrubar o resto da planilha."""
    try:
        return funcao(*args)
    except Exception:
        logging.warning(f"  Planilha Hikvision: falha ao coletar '{rotulo}'.", exc_info=True)
        return padrao


def _coletar_sistema(isapi):
    linhas = []
    for secao, caminho in _CONFIG_SISTEMA:
        raiz = isapi.obter(caminho)
        if raiz is not None:
            linhas += [(secao, k, v) for k, v in _achatar(raiz)]
    return linhas


def _montar_planilha(isapi, nvr_ip, info):
    wb = novo_workbook()
    status = isapi.obter("/ISAPI/System/status")
    cameras, nomes, configurados, online = _tentar("câmeras", ([], {}, [], []), _coletar_cameras, isapi)
    canais = online[:MAX_CANAIS]  # as configuracoes por canal so respondem para cameras online
    stream = _tentar("stream", [], _coletar_stream, isapi, nomes)
    gravacao = _tentar("gravação", [], _coletar_gravacao, isapi, nomes)
    eventos_canal, eventos_sistema = _tentar("eventos", ({}, []), _coletar_eventos, isapi)
    movimento = _tentar("movimento", [], _coletar_movimento, isapi, nomes, canais, eventos_canal)
    imagem = _tentar("imagem", [], _coletar_imagem, isapi, nomes, canais)
    discos, smart = _tentar("discos", ([], []), _coletar_discos, isapi)
    rede = _tentar("rede", [], _coletar_rede, isapi)
    sistema = _tentar("sistema", [], _coletar_sistema, isapi)

    uso, livre = _numero(_t(status, ".//memoryUsage")), _numero(_t(status, ".//memoryAvailable"))
    ram = round(uso / (uso + livre) * 100) if uso is not None and livre is not None and uso + livre > 0 else ""
    capacidade_gb = sum(d[5] for d in discos if isinstance(d[5], (int, float)))
    aba_resumo(wb, (
        ("IP consultado", nvr_ip),
        ("Coletado em", datetime.now().strftime("%d/%m/%Y %H:%M:%S")),
        ("Marca", "Hikvision (ISAPI)"),
        ("Nome do equipamento", _t(info, "deviceName")),
        ("Tipo", _t(info, "deviceType")),
        ("Modelo", _t(info, "model")),
        ("Série", _t(info, "serialNumber")),
        ("MAC", _t(info, "macAddress")),
        ("Firmware", f"{_t(info, 'firmwareVersion')} {_t(info, 'firmwareReleasedDate')}".strip()),
        ("Versão do encoder", f"{_t(info, 'encoderVersion')} {_t(info, 'encoderReleasedDate')}".strip()),
        ("Hardware", _t(info, "hardwareVersion")),
        ("Tempo ligado", _formatar_uptime(_t(status, "deviceUpTime"))),
        ("CPU (%)", _t(status, ".//cpuUtilization")),
        ("Memória usada (%)", ram),
        ("Canais cadastrados", len(cameras)),
        ("Canais com câmera configurada", len(configurados)),
        ("Canais online", sum(1 for c in cameras if c[13] == "Sim")),
        ("Discos", len(discos)),
        ("Capacidade dos discos (GB)", round(capacidade_gb, 1) if capacidade_gb else ""),
        ("Nota", "Inventário da configuração: não é o arquivo de backup restaurável do NVR (esse vem do backup normal)."),
        ("Nota", "Usuário e senha das câmeras são descartados e não aparecem em nenhuma aba."),
        ("Nota", "Recursos que o firmware não oferece ficam em branco; a aba Comandos mostra o resultado de cada consulta."),
    ))

    cab_stream = ["Canal", "Nome"]
    for rotulo in ("Principal", "Sub", "Terceiro"):
        cab_stream += [f"{rotulo}: codec", f"{rotulo}: resolução", f"{rotulo}: controle de bitrate",
                       f"{rotulo}: bitrate (kbps)", f"{rotulo}: FPS", f"{rotulo}: GOP", f"{rotulo}: Smart Codec",
                       f"{rotulo}: áudio"]
    aba(wb, "Câmeras", ["Canal", "Nome", "Protocolo", "IP", "Porta de gestão", "Canal de origem", "Modo de conexão",
                        "Tipo de stream", "Modelo", "Série", "Firmware da câmera", "ANR", "Sincroniza hora",
                        "Online", "Estado da conexão", "Força da senha da câmera", "ID do canal"], cameras)
    aba(wb, "Stream", cab_stream, stream)
    aba(wb, "Gravação", ["Canal", "Nome", "Trilha habilitada (Enable)", "Modo padrão", "Modos na agenda",
                         "Agenda de gravação", "Descrição da trilha"], gravacao)
    aba(wb, "Movimento", ["Canal", "Nome", "Detecção ligada", "Sensibilidade", "Área monitorada (%)",
                          "Intervalo de amostragem", "Tempo para iniciar (ms)", "Tempo para encerrar (ms)",
                          "Realçar movimento", "Agenda", "Ações ao detectar"], movimento)
    aba(wb, "Eventos por câmera", ["Canal", "Nome"] + [rotulo for _, rotulo in _EVENTOS_CAMERA],
        _linhas_eventos_camera(nomes, canais, eventos_canal))
    aba(wb, "Imagem", ["Canal", "Nome", "WDR", "Nível WDR", "BLC", "Brilho", "Contraste", "Saturação",
                       "Nome na imagem", "Data/hora na imagem", "Formato da data", "Formato da hora"], imagem)
    aba(wb, "Eventos do sistema", ["Evento", "Ações"], eventos_sistema)
    aba(wb, "Discos", ["ID", "Nome", "Tipo", "Estado", "Propriedade", "Capacidade (GB)", "Livre (GB)",
                       "Dias ligado", "Temperatura (°C)", "Avaliação SMART"], discos)
    aba(wb, "SMART", ["Disco", "Atributo", "Nome", "Valor", "Pior", "Limite", "Raw", "Estado"], smart)
    aba(wb, "Rede", ["Interface", "Endereçamento", "IP", "Máscara", "Gateway", "DNS primário", "DNS secundário",
                     "MAC", "Velocidade", "Duplex", "MTU", "Autonegociação", "IPv6"], rede)
    aba(wb, "Sistema (config)", ["Seção", "Campo", "Valor"], sistema)
    aba(wb, "Comandos", ["Recurso", "Resultado"], isapi.comandos)
    consolidar_cameras(wb, [("Stream | ", "Stream", COR_STREAM), ("Gravação | ", "Gravação", COR_AGENDA),
                            ("Movimento | ", "Movimento", COR_MOVIMENTO),
                            ("Eventos | ", "Eventos por câmera", COR_EVENTOS), ("Imagem | ", "Imagem", COR_IMAGEM)])
    return wb, len(cameras)


def gerar_planilha_hikvision(nvr_ip, usuario, senha, destino: Path) -> bool:
    """Coleta a configuracao de um NVR/DVR Hikvision (ISAPI) e grava a planilha .xlsx em `destino`.
    Retorna True se gravou; nunca levanta excecao (o backup dos outros equipamentos nao pode parar)."""
    try:
        isapi = _Isapi(nvr_ip, usuario, senha)
        info = isapi.obter("/ISAPI/System/deviceInfo")
        if info is None:  # login recusado ou equipamento fora do ar: nao insiste (evita bloquear a conta)
            logging.warning(f"  Planilha Hikvision: sem resposta do ISAPI em {nvr_ip}.")
            return False
        wb, n_canais = _montar_planilha(isapi, nvr_ip, info)
        destino.parent.mkdir(parents=True, exist_ok=True)
        wb.save(destino)
        logging.info(f"  Planilha Hikvision OK ({n_canais} canal(is) -> {destino.name}).")
        return True
    except Exception:
        logging.warning(f"  Falha ao gerar a planilha do NVR Hikvision {nvr_ip}.", exc_info=True)
        return False
