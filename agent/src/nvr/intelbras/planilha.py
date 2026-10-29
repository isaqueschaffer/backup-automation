import logging
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from requests.auth import HTTPDigestAuth

from src.nvr.planilha_comum import (
    COR_AGENDA, COR_IMAGEM, COR_MOVIMENTO, COR_STREAM, aba, aba_resumo, consolidar_cameras, eh_sensivel,
    novo_workbook,
)

TIMEOUT_S = 25
PAUSA_S = 0.2
LIMITE_TOTAL_S = 300  # NVR travado nao pode prender o backup: depois disso as consultas restantes sao puladas

_DIAS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Feriado"]  # indice do TimeSection no Dahua: 0 = domingo, 7 = feriado
_MODO_GRAVACAO = {"0": "Automático", "1": "Manual", "2": "Desligado"}
_DIA_NOITE = {"0": "Colorido", "1": "Automático", "2": "Preto e branco"}
_IP_INVALIDOS = ("", "192.168.0.0", "0.0.0.0", "ff:ff:ff:ff:ff:ff")

# Configuracoes simples (chave=valor) que entram na aba 'Sistema (config)': (secao, nome do getConfig)
_CONFIG_SISTEMA = [
    ("Geral", "General"), ("Hora (NTP)", "NTP"), ("Região e horário", "Locales"), ("Idioma", "Language"),
    ("Padrão de vídeo", "VideoStandard"), ("Serviço DVRIP", "DVRIP"), ("RTSP", "RTSP"), ("SSH", "SSHD"),
    ("UPnP", "UPnP"), ("DDNS", "DDNS"), ("E-mail", "Email"), ("Filtro de acesso", "AccessFilter"),
    ("Grupo de armazenamento", "StorageGroup"), ("Servidor de alarme", "AlarmServer"),
]
# Eventos do sistema: (rotulo, nome do getConfig)
_EVENTOS_SISTEMA = [
    ("Sem disco", "StorageNotExist"), ("Falha de disco", "StorageFailure"), ("Pouco espaço em disco", "StorageLowSpace"),
    ("Rede desconectada", "NetAbort"), ("Conflito de IP", "IPConflict"), ("Tentativas de login inválidas", "LoginFailureAlarm"),
]
_ACOES = [("RecordEnable", "Grava"), ("SnapshotEnable", "Snapshot"), ("MailEnable", "E-mail"),
          ("MessageEnable", "Mensagem/push"), ("BeepEnable", "Buzzer"), ("AlarmOutEnable", "Saída de alarme"),
          ("TipEnable", "Aviso na tela"), ("LogEnable", "Log")]


class _Dahua:
    """Consultas GET ao CGI Dahua numa sessao Digest; guarda o resultado de cada recurso (aba 'Comandos')."""

    def __init__(self, nvr_ip, usuario, senha):
        self.ip = nvr_ip
        self.sessao = requests.Session()
        self.sessao.auth = HTTPDigestAuth(usuario, senha)
        self.sessao.verify = False
        self.comandos = []  # (recurso, resultado)
        self._limite = time.monotonic() + LIMITE_TOTAL_S

    def obter(self, recurso, timeout=TIMEOUT_S, com_credenciais=False):
        """Retorna {chave: valor} (sem o prefixo 'table.') ou None. Nunca levanta excecao.
        Usuario e senha so ficam no resultado com `com_credenciais` (usado so no RemoteDevice, das cameras)."""
        if time.monotonic() > self._limite:
            self.comandos.append((recurso, "pulado: tempo total esgotado"))
            return None
        try:
            for tentativa in (1, 2):  # o NVR as vezes derruba a conexao: uma nova tentativa resolve
                try:
                    resp = self.sessao.get(f"http://{self.ip}/cgi-bin/{recurso}", timeout=timeout)
                    break
                except requests.ConnectionError:
                    if tentativa == 2:
                        raise
                    time.sleep(2)
            if resp.status_code != 200:
                self.comandos.append((recurso, f"HTTP {resp.status_code}"))
                return None
            dados = {}
            for linha in resp.text.splitlines():
                chave, igual, valor = linha.strip().partition("=")
                if not igual or (eh_sensivel(chave) and not com_credenciais):
                    continue
                dados[chave[6:] if chave.startswith("table.") else chave] = valor.strip()
            self.comandos.append((recurso, "sucesso" if dados else "sucesso, sem conteúdo"))
            return dados or None
        except Exception as e:
            self.comandos.append((recurso, f"erro: {type(e).__name__}"))
            return None
        finally:
            time.sleep(PAUSA_S)

    def config(self, nome, com_credenciais=False):
        return self.obter(f"configManager.cgi?action=getConfig&name={nome}", com_credenciais=com_credenciais)


def _indexados(dados, raiz, padrao=None):
    """{indice: {subchave: valor}} das chaves 'raiz[i].subchave'. `padrao` troca o regex (grupos: indice, subchave)."""
    regex = re.compile(padrao or rf"^{re.escape(raiz)}\[(\d+)\]\.(.*)$")
    saida = {}
    for chave, valor in (dados or {}).items():
        m = regex.match(chave)
        if m:
            saida.setdefault(int(m.group(1)), {})[m.group(2)] = valor
    return saida


def _sim_nao(valor):
    return "Sim" if str(valor).strip().lower() == "true" else ("Não" if str(valor).strip() else "")


def _gb(bytes_txt):
    try:
        return round(float(bytes_txt) / 1024 ** 3, 1)
    except (ValueError, TypeError):
        return ""


def _tipos_gravacao(mascara):
    m = int(mascara) if str(mascara).isdigit() else 0
    return "+".join(n for bit, n in ((1, "Contínua"), (2, "Movimento"), (4, "Alarme")) if m & bit)


def _agenda(sub, prefixo="TimeSection", com_tipos=True):
    """Resume 'TimeSection[dia][faixa]=<mascara> HH:MM:SS-HH:MM:SS' de um canal ('24x7' quando cobre tudo)."""
    faixas = {}
    for chave, valor in sub.items():
        m = re.match(rf"^{prefixo}\[(\d+)\]\[(\d+)\]$", chave)
        if not m:
            continue
        mascara, _, horario = valor.partition(" ")
        if not mascara.isdigit() or int(mascara) == 0:
            continue
        ini, _, fim = horario.partition("-")
        faixas.setdefault(int(m.group(1)), []).append((int(m.group(2)), ini[:5], fim[:5], mascara))
    if not faixas:
        return ""
    por_dia = {d: sorted(f) for d, f in faixas.items()}
    feriado = por_dia.pop(7, None)
    unicas = {tuple(f[1:] for f in lista) for lista in por_dia.values()}
    partes = []
    if len(por_dia) == 7 and len(unicas) == 1 and len(next(iter(unicas))) == 1             and next(iter(unicas))[0][0] == "00:00" and next(iter(unicas))[0][1] in ("23:59", "24:00"):
        mascara = next(iter(unicas))[0][2]
        partes.append(f"24x7 ({_tipos_gravacao(mascara)})" if com_tipos else "24x7")
    else:
        for dia in sorted(por_dia):
            faixas_dia = ", ".join(f"{i}-{f}" + (f" {_tipos_gravacao(m)}" if com_tipos else "")
                                   for _, i, f, m in por_dia[dia])
            partes.append(f"{_DIAS[dia]} {faixas_dia}")
    if feriado:
        partes.append("Feriado " + ", ".join(f"{i}-{f}" + (f" {_tipos_gravacao(m)}" if com_tipos else "")
                                              for _, i, f, m in feriado))
    return " | ".join(partes)


def _cobertura_regiao(sub, linhas, colunas):
    """% da grade marcada. Firmware V3.0 guarda as areas em MotionDetectWindow[n].Region[i]; o antigo, em Region[i]."""
    try:
        linhas, colunas = int(linhas), int(colunas)
        mascara = (1 << colunas) - 1
        por_linha = [0] * linhas
        for chave, valor in sub.items():
            m = re.match(r"^(?:MotionDetectWindow\[\d+\]\.)?Region\[(\d+)\]$", chave)
            if m and int(m.group(1)) < linhas:
                por_linha[int(m.group(1))] |= int(valor) & mascara
        return round(sum(bin(v).count("1") for v in por_linha) / (linhas * colunas) * 100)
    except (ValueError, ZeroDivisionError):
        return ""


def _senha_camera(senha):
    """O NVR devolve a senha da camera mascarada ('******'); so repassa se vier algo diferente."""
    return "(mascarada pelo NVR)" if senha and set(senha) == {"*"} else senha


def _coletar_cameras(dahua):
    """Retorna (linhas da aba Câmeras, {canal: nome}, [canais com camera habilitada])."""
    titulos = _indexados(dahua.config("ChannelTitle"), "ChannelTitle")
    remotos = _indexados(dahua.config("RemoteDevice", com_credenciais=True), "", r"^RemoteDevice\.uuid:System_CONFIG_NETCAMERA_INFO_(\d+)\.(.*)$")
    total = max(len(titulos), len(remotos))
    linhas, nomes, ativos = [], {}, []
    for i in range(total):
        titulo = titulos.get(i, {}).get("Name", "")
        r = remotos.get(i, {})
        ip = r.get("Address", "").strip()
        ip = "" if ip in _IP_INVALIDOS else ip
        habilitada = r.get("Enable") == "true" and bool(ip)
        nomes[i + 1] = titulo
        if habilitada:
            ativos.append(i + 1)
        linhas.append([
            i + 1, titulo, _sim_nao(r.get("Enable")) if r else "", ip, r.get("Port", "") if ip else "",
            r.get("HttpPort", "") if ip else "", r.get("RtspPort", "") if ip else "",
            r.get("HttpsPort", "") if ip else "", r.get("Mac", "") if ip else "",
            r.get("ProtocolType", "") if ip else "", r.get("DeviceType", "") if ip else "",
            r.get("VideoInputs[0].Name", "") if ip else "", r.get("Vendor", "") if ip else "",
            r.get("SerialNo", "") if ip else "", r.get("Version", "") if ip else "",
            r.get("VideoInputChannels", "") if ip else "", r.get("AudioInputChannels", "") if ip else "",
            r.get("AlarmInChannels", "") if ip else "", r.get("Encryption", "") if ip else "",
            r.get("UserName", "") if ip else "", _senha_camera(r.get("Password", "")) if ip else "",
        ])
    return linhas, nomes, ativos


def _celulas_formato(f):
    """8 colunas de um MainFormat/ExtraFormat: ligado, codec, resolucao, controle, bitrate, FPS, GOP, audio."""
    if not f:
        return [""] * 8
    audio = f.get("AudioEnable", "")
    return [
        _sim_nao(f.get("VideoEnable")), f.get("Video.Compression", ""), f.get("Video.resolution", ""),
        f.get("Video.BitRateControl", ""), f.get("Video.BitRate", ""), f.get("Video.FPS", ""), f.get("Video.GOP", ""),
        (f"Sim ({f.get('Audio.Compression', '')})" if audio == "true" else _sim_nao(audio)),
    ]


_FORMATOS = [("Principal contínuo", "MainFormat[0]."), ("Principal movimento", "MainFormat[1]."),
             ("Principal alarme", "MainFormat[2]."), ("Sub 1", "ExtraFormat[0]."), ("Sub 2", "ExtraFormat[1].")]


def _coletar_stream(dahua, nomes, ativos):
    codificacao = _indexados(dahua.config("Encode"), "Encode")
    linhas = []
    for i in sorted(codificacao):
        sub = codificacao[i]
        linha = [i + 1, nomes.get(i + 1, "")]
        for _, prefixo in _FORMATOS:
            f = {k[len(prefixo):]: v for k, v in sub.items() if k.startswith(prefixo)}
            linha += _celulas_formato(f)
        linhas.append(linha)
    return linhas


def _coletar_gravacao(dahua, nomes):
    modos = _indexados(dahua.config("RecordMode"), "RecordMode")
    gravacoes = _indexados(dahua.config("Record"), "Record")
    destinos = _indexados(dahua.config("RecordStoragePoint"), "RecordStoragePoint")
    linhas = []
    for i in sorted(set(modos) | set(gravacoes)):
        m, g, d = modos.get(i, {}), gravacoes.get(i, {}), destinos.get(i, {})
        linhas.append([
            i + 1, nomes.get(i + 1, ""), _MODO_GRAVACAO.get(m.get("Mode", ""), m.get("Mode", "")),
            _MODO_GRAVACAO.get(m.get("ModeExtra1", ""), m.get("ModeExtra1", "")), _agenda(g),
            g.get("PreRecord", ""), _sim_nao(g.get("Redundancy")), g.get("Format", ""), g.get("MaxRecordTime", ""),
            _sim_nao(g.get("HolidayEnable")), "Local" if d.get("TimingRecord.Local") == "1" else "",
        ])
    return linhas


def _coletar_movimento(dahua, nomes):
    movimento = _indexados(dahua.config("MotionDetect"), "MotionDetect")
    perda = _indexados(dahua.config("LossDetect"), "LossDetect")
    mascara = _indexados(dahua.config("BlindDetect"), "BlindDetect")
    linhas = []
    for i in sorted(movimento):
        m = movimento[i]
        eh = {k[len("EventHandler."):]: v for k, v in m.items() if k.startswith("EventHandler.")}
        linhas.append([
            i + 1, nomes.get(i + 1, ""), _sim_nao(m.get("Enable")), m.get("Level", ""),
            f"{m.get('Row', '')}x{m.get('Col', '')}" if m.get("Row") else "",
            _cobertura_regiao(m, m.get("Row"), m.get("Col")), _agenda(eh, com_tipos=False),
            eh.get("RecordLatch", ""),
        ] + [_sim_nao(eh.get(chave)) for chave, _ in _ACOES] + [
            _sim_nao(perda.get(i, {}).get("Enable")), _sim_nao(mascara.get(i, {}).get("Enable")),
        ])
    return linhas


def _coletar_imagem(dahua, nomes):
    opcoes = _indexados(dahua.config("VideoInOptions"), "VideoInOptions")
    osd = _indexados(dahua.config("VideoWidget"), "VideoWidget")
    linhas = []
    for i in sorted(set(opcoes) | set(osd)):
        o, w = opcoes.get(i, {}), osd.get(i, {})
        linhas.append([
            i + 1, nomes.get(i + 1, ""), _DIA_NOITE.get(o.get("DayNightColor", ""), o.get("DayNightColor", "")),
            o.get("WhiteBalance", ""), _sim_nao(o.get("Mirror")), _sim_nao(o.get("Flip")),
            _sim_nao(w.get("ChannelTitle.EncodeBlend")), _sim_nao(w.get("TimeTitle.EncodeBlend")),
        ])
    return linhas


def _coletar_eventos_sistema(dahua):
    linhas = []
    for rotulo, nome in _EVENTOS_SISTEMA:
        d = dahua.config(nome)
        if not d:
            continue
        extra = ""
        if d.get(f"{nome}.LowerLimit"):
            extra = f"limite {d[f'{nome}.LowerLimit']}%"
        elif d.get(f"{nome}.TryLoginTimes"):
            extra = f"{d[f'{nome}.TryLoginTimes']} tentativas"
        linhas.append([rotulo, _sim_nao(d.get(f"{nome}.Enable")), extra] +
                      [_sim_nao(d.get(f"{nome}.EventHandler.{chave}")) for chave, _ in _ACOES])
    return linhas


def _coletar_alarmes(dahua):
    linhas = []
    for rotulo, nome in (("Entrada local", "Alarm"), ("Entrada de rede", "NetAlarm"), ("Entrada expandida", "ExAlarm")):
        for i, a in sorted(_indexados(dahua.config(nome), nome).items()):
            linhas.append([rotulo, i + 1, a.get("Name", ""), _sim_nao(a.get("Enable")), a.get("SensorType", "")])
    saidas = _indexados(dahua.config("AlarmOut"), "AlarmOut")
    for i, s in sorted(saidas.items()):
        linhas.append(["Saída", i + 1, s.get("Name", ""), "", f"modo {s.get('Mode', '')}"])
    return linhas


def _coletar_discos(dahua):
    dados = dahua.obter("storageDevice.cgi?action=getDeviceAllInfo") or {}
    linhas = []
    for i, d in sorted(_indexados(dados, "list.info").items()):
        particoes = _indexados(d, "Detail")
        total = sum(float(p.get("TotalBytes", 0) or 0) for p in particoes.values())
        usado = sum(float(p.get("UsedBytes", 0) or 0) for p in particoes.values())
        linhas.append([
            i + 1, d.get("Name", ""), d.get("State", ""), len(particoes), _gb(total), _gb(usado),
            "Sim" if any(p.get("IsError") == "true" for p in particoes.values()) else "Não",
            ", ".join(sorted({p.get("Type", "") for p in particoes.values()} - {""})),
            "; ".join(f"{p.get('Path', '')}: {_gb(p.get('TotalBytes'))} GB" for _, p in sorted(particoes.items())),
        ])
    return linhas


def _coletar_rede(dahua):
    fisicas = _indexados(dahua.obter("netApp.cgi?action=getInterfaces"), "netInterface")
    config = dahua.config("Network") or {}
    linhas = []
    for _, nic in sorted(fisicas.items()):
        nome = nic.get("Name", "")
        pref = f"Network.{nome}."
        dns = ", ".join(v for k, v in sorted(config.items()) if k.startswith(pref + "DnsServers["))
        linhas.append([
            nome, nic.get("ConnStatus", ""), nic.get("Speed", ""), nic.get("PhysicalAddress", ""), nic.get("Type", ""),
            config.get(pref + "IPAddress", ""), config.get(pref + "SubnetMask", ""),
            config.get(pref + "DefaultGateway", ""), dns, _sim_nao(config.get(pref + "DhcpEnable")),
            config.get(pref + "MTU", ""), "Sim" if config.get("Network.DefaultInterface") == nome else "",
        ])
    return linhas


def _coletar_sistema(dahua):
    linhas = []
    for secao, nome in _CONFIG_SISTEMA:
        dados = dahua.config(nome)
        if dados:
            linhas += [(secao, k, v) for k, v in dados.items()]
    return linhas


def _tentar(rotulo, padrao, funcao, *args):
    """Uma secao com erro de leitura vira vazia, sem derrubar o resto da planilha."""
    try:
        return funcao(*args)
    except Exception:
        logging.warning(f"  Planilha Intelbras: falha ao coletar '{rotulo}'.", exc_info=True)
        return padrao


def _valor(dados, chave):
    return (dados or {}).get(chave, "")


def _montar_planilha(dahua, nvr_ip):
    wb = novo_workbook()
    info = dahua.obter("magicBox.cgi?action=getSystemInfo") or {}
    versao = (dahua.obter("magicBox.cgi?action=getSoftwareVersion") or {}).get("version", "")
    tipo = (dahua.obter("magicBox.cgi?action=getDeviceType") or {}).get("type", "")
    hardware = (dahua.obter("magicBox.cgi?action=getHardwareVersion") or {}).get("version", "")
    fabricante = (dahua.obter("magicBox.cgi?action=getVendor") or {}).get("vendor", "")
    hora = (dahua.obter("global.cgi?action=getCurrentTime") or {}).get("result", "")
    geral = dahua.config("General")
    ntp = dahua.config("NTP")

    cameras, nomes, ativos = _tentar("câmeras", ([], {}, []), _coletar_cameras, dahua)
    stream = _tentar("stream", [], _coletar_stream, dahua, nomes, ativos)
    gravacao = _tentar("gravação", [], _coletar_gravacao, dahua, nomes)
    movimento = _tentar("movimento", [], _coletar_movimento, dahua, nomes)
    imagem = _tentar("imagem", [], _coletar_imagem, dahua, nomes)
    eventos = _tentar("eventos do sistema", [], _coletar_eventos_sistema, dahua)
    alarmes = _tentar("alarmes", [], _coletar_alarmes, dahua)
    discos = _tentar("discos", [], _coletar_discos, dahua)
    rede = _tentar("rede", [], _coletar_rede, dahua)
    sistema = _tentar("sistema", [], _coletar_sistema, dahua)

    capacidade = sum(d[4] for d in discos if isinstance(d[4], (int, float)))
    aba_resumo(wb, (
        ("IP consultado", nvr_ip),
        ("Coletado em", datetime.now().strftime("%d/%m/%Y %H:%M:%S")),
        ("Marca", f"{fabricante or 'Intelbras'} (CGI Dahua)"),
        ("Nome do equipamento", _valor(geral, "General.MachineName")),
        ("Modelo", tipo or _valor(info, "updateSerial")),
        ("Série", _valor(info, "serialNumber")),
        ("Firmware", versao),
        ("Hardware", hardware),
        ("Processador", _valor(info, "processor")),
        ("Data/hora do equipamento", hora),
        ("Fuso horário", _valor(ntp, "NTP.TimeZoneDesc")),
        ("Canais", len(cameras)),
        ("Câmeras habilitadas", len(ativos)),
        ("Discos", len(discos)),
        ("Capacidade dos discos (GB)", round(capacidade, 1) if capacidade else ""),
        ("Bloqueio por login inválido", f"{_sim_nao(_valor(geral, 'General.LockLoginEnable'))} "
                                        f"({_valor(geral, 'General.LockLoginTimes')} tentativas, "
                                        f"{_valor(geral, 'General.LoginFailLockTime')} s)"),
        ("Nota", "Inventário da configuração: não é o arquivo de backup restaurável do NVR (esse vem do backup normal)."),
        ("Nota", "ATENÇÃO: a aba Câmeras tem o usuário de cada câmera. O CGI devolve a senha mascarada (aparece '(mascarada pelo NVR)'). Proteja este arquivo."),
        ("Nota", "Usuário e senha de serviços (e-mail, DDNS etc.) continuam descartados."),
        ("Nota", "A configuração lida pelo CGI não informa se a câmera está online: 'habilitada' = cadastrada com IP e ativa no NVR."),
        ("Nota", "Máscara de agenda: contínua+movimento+alarme conforme os bits do NVR; a aba Comandos mostra cada consulta."),
    ))

    cab_stream = ["Canal", "Nome"]
    for rotulo, _ in _FORMATOS:
        cab_stream += [f"{rotulo}: ligado", f"{rotulo}: codec", f"{rotulo}: resolução", f"{rotulo}: controle de bitrate",
                       f"{rotulo}: bitrate (kbps)", f"{rotulo}: FPS", f"{rotulo}: GOP", f"{rotulo}: áudio"]
    cab_acoes = [rotulo for _, rotulo in _ACOES]
    aba(wb, "Câmeras", ["Canal", "Nome", "Habilitada", "IP", "Porta TCP", "Porta HTTP", "Porta RTSP", "Porta HTTPS",
                        "MAC", "Protocolo", "Modelo", "Nome na câmera", "Fabricante", "Série", "Firmware da câmera",
                        "Entradas de vídeo", "Entradas de áudio", "Entradas de alarme", "Criptografia", "Usuário da câmera",
                        "Senha da câmera"], cameras)
    aba(wb, "Stream", cab_stream, stream)
    aba(wb, "Gravação", ["Canal", "Nome", "Modo de gravação", "Modo do sub-stream", "Agenda de gravação",
                         "Pré-gravação (s)", "Redundância", "Formato", "Tempo máx. de gravação (MaxRecordTime)",
                         "Gravar em feriados", "Destino"], gravacao)
    aba(wb, "Movimento", ["Canal", "Nome", "Detecção ligada", "Sensibilidade (nível)", "Grade", "Área monitorada (%)",
                          "Agenda", "Tempo de gravação após evento (s)"] + [f"Ação: {a}" for a in cab_acoes] +
        ["Perda de vídeo ligada", "Máscara de vídeo ligada"], movimento)
    aba(wb, "Imagem", ["Canal", "Nome", "Dia/noite", "Balanço de branco", "Espelhar", "Inverter",
                       "Nome na imagem (gravação)", "Data/hora na imagem (gravação)"], imagem)
    aba(wb, "Eventos do sistema", ["Evento", "Ligado", "Detalhe"] + cab_acoes, eventos)
    aba(wb, "Alarmes", ["Tipo", "Nº", "Nome", "Ligado", "Detalhe"], alarmes)
    aba(wb, "Discos", ["#", "Disco", "Estado", "Partições", "Capacidade (GB)", "Usado (GB)", "Com erro", "Tipo",
                       "Detalhe das partições"], discos)
    aba(wb, "Rede", ["Interface", "Conexão", "Velocidade (Mbps)", "MAC", "Tipo", "IP", "Máscara", "Gateway", "DNS",
                     "DHCP", "MTU", "Interface padrão"], rede)
    aba(wb, "Sistema (config)", ["Seção", "Campo", "Valor"], sistema)
    aba(wb, "Comandos", ["Recurso", "Resultado"], dahua.comandos)
    consolidar_cameras(wb, [("Stream | ", "Stream", COR_STREAM), ("Gravação | ", "Gravação", COR_AGENDA),
                            ("Movimento | ", "Movimento", COR_MOVIMENTO), ("Imagem | ", "Imagem", COR_IMAGEM)])
    return wb, len(cameras)


def gerar_planilha_intelbras(nvr_ip, usuario, senha, destino: Path) -> bool:
    """Coleta a configuracao de um NVR/DVR Intelbras (CGI Dahua) e grava a planilha .xlsx em `destino`.
    Retorna True se gravou; nunca levanta excecao (o backup dos outros equipamentos nao pode parar)."""
    try:
        dahua = _Dahua(nvr_ip, usuario, senha)
        if dahua.obter("magicBox.cgi?action=getSystemInfo") is None:
            # login recusado ou equipamento fora do ar: nao insiste (evita bloquear a conta)
            logging.warning(f"  Planilha Intelbras: sem resposta do CGI em {nvr_ip}.")
            return False
        wb, n_canais = _montar_planilha(dahua, nvr_ip)
        destino.parent.mkdir(parents=True, exist_ok=True)
        wb.save(destino)
        logging.info(f"  Planilha Intelbras OK ({n_canais} canal(is) -> {destino.name}).")
        return True
    except Exception:
        logging.warning(f"  Falha ao gerar a planilha do NVR Intelbras {nvr_ip}.", exc_info=True)
        return False
