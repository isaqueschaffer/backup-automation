import logging
import time
from datetime import datetime
from pathlib import Path

import requests

from src.nvr.motorola.cameras import abrir_sessao_motorola
from src.nvr.planilha_comum import (
    COR_AGENDA, COR_MOVIMENTO, COR_STREAM, SMART_NOMES, aba, aba_resumo, consolidar_cameras, eh_sensivel, novo_workbook,
)
from src.utils.xml_parser import parse_xml_seguro

TIMEOUT_S = 30         # os DVR respondem em ate 30 s
TIMEOUT_SMART_S = 40   # queryDiskSmartInfo e lento em alguns firmwares
PAUSA_S = 0.5          # pausa entre consultas, como na telemetria (o NVR atende melhor)
LIMITE_TOTAL_S = 300   # NVR travado nao pode prender o backup: depois disso as consultas restantes sao puladas

# Campos de ruido; usuario/senha das cameras (o queryDevList os devolve em texto puro) saem por eh_sensivel()
_RUIDO = {"AndroidAppAddress", "IOSAppAddress", "PCUI"}
_ATRIBUTOS_IGNORADOS = {"type", "note", "min", "max", "default"}

_TIPOS_GRAVACAO = [
    ("scheduleRec", "Contínua"), ("motionRec", "Movimento"), ("alarmRec", "Alarme"),
    ("intelligentRec", "Inteligente"), ("posRec", "POS"),
]
_CAMPOS_STREAM = "<requireField><name/><chlType/><mainCaps/><subCaps/><main/><sub/><an/><ae/></requireField>"
_CAMPOS_MOVIMENTO = "<requireField><param/><trigger/></requireField>"


class _Nvr:
    """Consultas NVMS-9000 numa sessao ja autenticada; guarda o resultado de cada comando (aba 'Comandos')."""

    def __init__(self, sessao, nvr_ip):
        self.sessao = sessao
        self.ip = nvr_ip
        self.comandos = []  # (comando, envelope, resultado)
        self._limite = time.monotonic() + LIMITE_TOTAL_S

    def consultar(self, comando, extra="", envelope="padrao", timeout=TIMEOUT_S):
        """Retorna o <content> da resposta, ou None se falhou ou veio vazio."""
        if time.monotonic() > self._limite:
            self.comandos.append((comando, envelope, "pulado: tempo total esgotado"))
            return None
        token = getattr(self.sessao, "tvt_token", "") or ""
        token_xml = f"<token>{token}</token>" if token else ""
        corpo = (
            '<?xml version="1.0" encoding="utf-8" ?>'
            f'<request version="1.0" systemType="NVMS-9000" clientType="WEB">{token_xml}{extra}</request>'
        )
        try:
            for tentativa in (1, 2):  # o NVR as vezes derruba a conexao: uma nova tentativa resolve
                try:
                    resp = self.sessao.post(
                        f"http://{self.ip}/{comando}", data=corpo.encode("utf-8"),
                        headers={"Content-Type": "application/xml"}, timeout=timeout, verify=False,
                    )
                    break
                except requests.ConnectionError:
                    if tentativa == 2:
                        raise
                    time.sleep(2)
            if resp.status_code != 200:
                self.comandos.append((comando, envelope, f"HTTP {resp.status_code}"))
                return None
            raiz = parse_xml_seguro(resp.content)
        except Exception as e:
            self.comandos.append((comando, envelope, f"erro: {type(e).__name__}"))
            return None
        finally:
            time.sleep(PAUSA_S)

        if raiz.findtext("status") != "success":
            self.comandos.append((comando, envelope, f"status={raiz.findtext('status')}"))
            return None
        conteudo = raiz.find("content")
        vazio = conteudo is None or (len(conteudo) == 0 and not (conteudo.text or "").strip())
        self.comandos.append((comando, envelope, "sucesso, sem conteúdo" if vazio else "sucesso"))
        return None if vazio else conteudo


def _achatar(elemento, prefixo=""):
    """Lista (caminho, valor) de todas as folhas, sem types/itemType e sem campos sensiveis."""
    saida = []
    for filho in elemento:
        if filho.tag in ("types", "itemType") or eh_sensivel(filho.tag) or filho.tag in _RUIDO:
            continue
        nome = f"{prefixo}{filho.tag}"
        if filho.tag == "item" and filho.get("id") is not None:
            nome = f"{prefixo}item[{filho.get('id')}]"
        if len(filho):
            saida += _achatar(filho, nome + ".")
            continue
        valor = (filho.text or "").strip()
        attrs = " ".join(
            f"{k}={v}" for k, v in filho.attrib.items()
            if k not in _ATRIBUTOS_IGNORADOS and not eh_sensivel(k)
            and not (k == "id" and filho.tag == "item")
        )
        saida.append((nome, f"{valor} ({attrs})" if valor and attrs else (valor or attrs)))
    return saida


def _itens(conteudo):
    return conteudo.findall("item") if conteudo is not None else []


def _resolucoes(caps):
    return ", ".join(f"{r.text}@{r.get('fps')}" for r in caps.findall("res")) if caps is not None else ""


def _coletar_cameras(nvr):
    """Retorna (linhas da aba Câmeras, nomes por canal, ordem por canal)."""
    dev = nvr.consultar("queryDevList")
    status = nvr.consultar("queryChlStatus")
    ids_online = {i.get("id") for i in _itens(nvr.consultar("queryOnlineChlList"))}
    ids_gravacao = {i.get("id") for i in _itens(nvr.consultar("queryChlsExistRec"))}

    estados = {}
    for i in _itens(status):
        chl = i.find("chl")
        if chl is not None:
            estados[chl.get("id")] = i

    linhas = []
    for i in _itens(dev):
        cid = i.get("id")
        est = estados.get(cid)
        tem_ip = bool(i.findtext("ip"))
        modelo = i.find("productModel")
        valor = lambda tag: (est.findtext(tag) or "") if est is not None else ""
        linhas.append([
            i.findtext("chlNum"), i.findtext("name"), i.findtext("chlType"), i.findtext("ip") or "",
            i.findtext("port") if tem_ip else "", modelo.text if modelo is not None else "",
            i.findtext("manufacturer") or "", i.findtext("protocolType") or "", i.findtext("addType") or "",
            "Sim" if cid in ids_online else "Não", valor("recStatus"), valor("motionStatus"),
            valor("intelligentStatus"), "Sim" if cid in ids_gravacao else "Não", cid,
        ])
    nomes = {i.get("id"): i.findtext("name") for i in _itens(dev)}
    ordem = {i.get("id"): i.findtext("chlNum") for i in _itens(dev)}
    return linhas, nomes, ordem


def _coletar_stream(nvr, nomes, ordem):
    linhas = []
    for i in _itens(nvr.consultar("queryNodeEncodeInfo", _CAMPOS_STREAM, "requireField")):
        cid = i.get("id")
        main, sub, an, ae = i.find("main"), i.find("sub"), i.find("an"), i.find("ae")
        mcaps, scaps = i.find("mainCaps"), i.find("subCaps")
        d = lambda e, k: e.get(k, "") if e is not None else ""
        linhas.append([
            ordem.get(cid), nomes.get(cid) or i.findtext("name"), d(main, "enct"), d(main, "mGOP"),
            _resolucoes(mcaps), d(mcaps, "supEnct"), d(mcaps, "bitType"),
            d(sub, "res"), d(sub, "fps"), d(sub, "QoI"), d(sub, "enct"), d(sub, "bitType"), d(sub, "level"),
            _resolucoes(scaps),
            d(an, "res"), d(an, "fps"), d(an, "QoI"), d(an, "bitType"), d(an, "level"), d(an, "audio"),
            d(ae, "res"), d(ae, "fps"), d(ae, "QoI"), d(ae, "bitType"), d(ae, "level"), d(ae, "audio"),
            d(main, "aGOP"), d(sub, "GOP"), d(scaps, "supEnct"), d(scaps, "bitType"),
        ])
    return linhas


def _coletar_agendamento(nvr, ordem):
    linhas = []
    for i in _itens(nvr.consultar("queryRecordScheduleList")):
        linha = [ordem.get(i.get("id")), i.findtext("name")]
        for tag, _ in _TIPOS_GRAVACAO:
            bloco = i.find(tag)
            ligado = bloco is not None and bloco.findtext("switch") == "true"
            agenda = bloco.find("schedule") if bloco is not None else None
            linha += ["Ligado" if ligado else "Desligado",
                      (agenda.text or "") if (agenda is not None and ligado) else ""]
        linhas.append(linha)
    return linhas


def _coletar_movimento(nvr, nomes, ordem):
    """queryMotion exige requireField + chlId neste firmware."""
    linhas = []
    for cid in nomes:
        conteudo = nvr.consultar(
            "queryMotion", f"<condition><chlId>{cid}</chlId></condition>{_CAMPOS_MOVIMENTO}", f"chlId={ordem.get(cid)}")
        chl = conteudo.find("chl") if conteudo is not None else None
        if chl is None:
            continue
        param, trig = chl.find("param"), chl.find("trigger")
        celulas = "".join((a.text or "").strip() for a in param.findall("area/item")) if param is not None else ""
        cobertura = round(celulas.count("1") / len(celulas) * 100) if celulas else ""
        sim = lambda tag: "Sim" if trig is not None and trig.findtext(tag) == "true" else "Não"
        agenda = trig.find("triggerSchedule/schedule") if trig is not None else None
        retencao = param.find("holdTime") if param is not None else None
        linhas.append([
            ordem.get(cid), nomes.get(cid),
            "Sim" if param is not None and param.findtext("switch") == "true" else "Não",
            param.findtext("sensitivity") if param is not None else "",
            retencao.text if retencao is not None else "", cobertura,
            agenda.text if agenda is not None else "", sim("sysRec/switch"), sim("sysSnap/switch"),
            sim("msgPushSwitch"), sim("buzzerSwitch"), sim("popVideoSwitch"), sim("emailSwitch"),
            sim("alarmOut/switch"),
        ])
    return linhas


def _coletar_discos(nvr):
    """Retorna (linhas da aba Discos, linhas da aba SMART). Os dois formatos de firmware (1.3.x e 1.4.x) sao aceitos."""
    discos, smart, ids = [], [], []
    for i in _itens(nvr.consultar("queryDiskStatus")):
        ids.append(i.get("id"))
        discos.append([len(ids), i.get("id"), i.findtext("diskStatus") or (i.text or "").strip()])
    for n, did in enumerate(ids, start=1):
        detalhes = []
        smart_cont = nvr.consultar(
            "queryDiskSmartInfo", f"<condition><diskId>{did}</diskId></condition>", f"disco{n}_diskId",
            timeout=TIMEOUT_SMART_S)
        if smart_cont is not None:
            for a in smart_cont.findall(".//smartItems/item"):
                aid = a.get("id")
                smart.append([n, aid, SMART_NOMES.get(aid, ""), a.findtext("value"), a.findtext("worstValue"),
                              a.findtext("threshold"), a.findtext("rawValue"), a.findtext("smartStatus")])
            detalhes += [f"{k}={v}" for k, v in _achatar(smart_cont)
                         if k in ("diskStatus", "smartStatus", "powerOnDays", "temperature")]
        for envelope, extra in (("diskId", f"<condition><diskId>{did}</diskId></condition>"),
                                ("itemId", f'<condition><item id="{did}"/></condition>')):
            det = nvr.consultar("queryDiskDetailInfo", extra, f"disco{n}_{envelope}")
            if det is not None:
                detalhes += [f"{k}={v}" for k, v in _achatar(det)]
                break
        discos[n - 1].append("; ".join(detalhes))
    return discos, smart


def _agendas_e_eventos(nvr):
    agendas = [[i.text, i.get("id")] for i in _itens(nvr.consultar("queryScheduleList"))]
    eventos = []
    for i in _itens(nvr.consultar("queryAbnormalTrigger")):
        sim = lambda t: "Sim" if i.findtext(t) == "true" else "Não"
        saida = i.find("triggerAlarmOut")
        eventos.append([i.findtext("abnormalType"), sim("msgPushSwitch"), sim("buzzerSwitch"), sim("popMsgSwitch"),
                        sim("emailSwitch"), "Sim" if saida is not None and saida.findtext("switch") == "true" else "Não"])
    return agendas, eventos


def _montar_planilha(nvr, nvr_ip):
    wb = novo_workbook()

    sistema = []
    for secao, comando in (("Sistema", "queryBasicCfg"), ("Modo de gravação", "queryRecordDistributeInfo"),
                           ("Notificações", "queryEventNotifyParam")):
        conteudo = nvr.consultar(comando)
        if conteudo is not None:
            sistema += [(secao, k, v) for k, v in _achatar(conteudo)]
    basico = {k: v for s, k, v in sistema if s == "Sistema"}

    cameras, nomes, ordem = _coletar_cameras(nvr)
    stream = _coletar_stream(nvr, nomes, ordem)
    agendamento = _coletar_agendamento(nvr, ordem)
    movimento = _coletar_movimento(nvr, nomes, ordem)
    agendas, eventos = _agendas_e_eventos(nvr)
    discos, smart = _coletar_discos(nvr)
    rede = []
    for comando in ("queryNetCfg", "queryNetStatus"):
        conteudo = nvr.consultar(comando)
        if conteudo is not None:
            rede += [(comando, k, v) for k, v in _achatar(conteudo)]

    aba_resumo(wb, (
        ("IP consultado", nvr_ip),
        ("Coletado em", datetime.now().strftime("%d/%m/%Y %H:%M:%S")),
        ("Nome do NVR", basico.get("name", "")),
        ("Modelo", basico.get("TVTProductModel", "") or basico.get("productModel", "")),
        ("Série", basico.get("sn", "")),
        ("Firmware", basico.get("softwareVersion", "")),
        ("Data do firmware", basico.get("launchDate", "")),
        ("Canais", len(cameras)),
        ("Canais online", sum(1 for c in cameras if c[9] == "Sim")),
        ("Canais gravando agora", sum(1 for c in cameras if c[10] == "recording")),
        ("Discos", len(discos)),
        ("Nota", "Inventário da configuração: não é um arquivo de backup restaurável pelo NVR."),
        ("Nota", "Colunas an/ae do stream são os nomes do firmware; a leitura 'normal/evento' é uma interpretação."),
        ("Nota", "userName/password das câmeras são descartados e não aparecem em nenhuma aba."),
    ))
    

    cab_agenda = ["Canal", "Câmera"]
    for _, rotulo in _TIPOS_GRAVACAO:
        cab_agenda += [f"{rotulo} (estado)", f"{rotulo} (agenda)"]

    aba(wb, "Câmeras", ["Canal", "Nome", "Tipo", "IP", "Porta", "Modelo", "Fabricante", "Protocolo", "Adição",
                         "Online", "Gravação agora", "Movimento agora", "Inteligente agora", "Tem gravação",
                         "ID do canal"], cameras)
    aba(wb, "Stream", ["Canal", "Nome", "Principal: codec", "Principal: GOP", "Principal: resoluções suportadas",
                        "Principal: codecs suportados", "Principal: tipos de bitrate", "Sub: resolução", "Sub: FPS",
                        "Sub: bitrate (kbps)", "Sub: codec", "Sub: tipo bitrate", "Sub: qualidade",
                        "Sub: resoluções suportadas", "Grav. normal (an): resolução", "an: FPS", "an: bitrate (kbps)",
                        "an: tipo bitrate", "an: qualidade", "an: áudio", "Grav. evento (ae): resolução", "ae: FPS",
                        "ae: bitrate (kbps)", "ae: tipo bitrate", "ae: qualidade", "ae: áudio",
                        "Principal: GOP automático", "Sub: GOP", "Sub: codecs suportados",
                        "Sub: tipos de bitrate suportados"], stream)
    aba(wb, "Agendamento", cab_agenda, agendamento)
    aba(wb, "Agendas cadastradas", ["Nome", "ID"], agendas)
    aba(wb, "Eventos do sistema", ["Evento", "Push no celular", "Buzzer", "Pop-up", "E-mail", "Saída de alarme"],
         eventos)
    aba(wb, "Discos", ["#", "ID", "Estado", "Detalhes"], discos)
    aba(wb, "SMART", ["Disco", "Atributo", "Nome", "Valor", "Pior", "Limite", "Raw", "Estado"], smart)
    aba(wb, "Rede", ["Comando", "Campo", "Valor"], rede)
    aba(wb, "NVR (config)", ["Seção", "Campo", "Valor"], sistema)
    aba(wb, "Movimento", ["Canal", "Câmera", "Detecção ligada", "Sensibilidade", "Tempo de retenção (s)",
                           "Área monitorada (%)", "Agenda", "Grava", "Snapshot", "Push no celular", "Buzzer",
                           "Pop-up", "E-mail", "Saída de alarme"], movimento)
    aba(wb, "Comandos", ["Comando", "Envelope", "Resultado"], nvr.comandos)
    consolidar_cameras(wb, [("Stream | ", "Stream", COR_STREAM), ("Agenda | ", "Agendamento", COR_AGENDA),
                            ("Movimento | ", "Movimento", COR_MOVIMENTO)])
    return wb, len(cameras)


def gerar_planilha_motorola(nvr_ip, usuario, senha, destino: Path) -> bool:
    """Coleta a configuracao de um NVR/DVR Motorola (NVMS-9000) e grava a planilha .xlsx em `destino`.
    Retorna True se gravou; nunca levanta excecao (o backup dos outros equipamentos nao pode parar)."""
    try:
        sessao = abrir_sessao_motorola(nvr_ip, usuario, senha)
        if sessao is None:
            logging.warning(f"  Planilha Motorola: login falhou em {nvr_ip}.")
            return False
        wb, n_canais = _montar_planilha(_Nvr(sessao, nvr_ip), nvr_ip)
        destino.parent.mkdir(parents=True, exist_ok=True)
        wb.save(destino)
        logging.info(f"  Planilha Motorola OK ({n_canais} canal(is) -> {destino.name}).")
        return True
    except Exception:
        logging.warning(f"  Falha ao gerar a planilha do NVR Motorola {nvr_ip}.", exc_info=True)
        return False
