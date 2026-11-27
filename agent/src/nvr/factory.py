import logging
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.nvr.hikvision.cameras import buscar_cameras_nvr, buscar_cameras_dvr
from src.nvr.motorola.cameras import buscar_cameras as buscar_cameras_motorola
from src.nvr.motorola.recordings import buscar_datas_gravacao_motorola
from src.nvr.hikvision.recordings import tem_gravacao_no_dia, tem_gravacao_entre
from src.nvr.hikvision.telemetry import coletar_telemetria_hikvision
from src.nvr.motorola.telemetry import coletar_telemetria_motorola
from src.nvr.intelbras.cameras import buscar_cameras as buscar_cameras_intelbras
from src.nvr.intelbras.recordings import tem_gravacao_no_dia as tem_gravacao_no_dia_intelbras, tem_gravacao_entre as tem_gravacao_entre_intelbras
try:
    from src.nvr.intelbras.telemetry import coletar_telemetria_intelbras
except Exception:
    # pysnmp ausente ou incompatível: só a telemetria Intelbras fica indisponível (o backup segue normal)
    logging.warning("Telemetria SNMP (Intelbras) indisponível: falha ao carregar o pysnmp.", exc_info=True)
    coletar_telemetria_intelbras = None

DIAS_VERIFICAR = 15
DIAS_MAX_RETENCAO = 730  # limite da busca da gravacao mais antiga (Hikvision/Intelbras)
# Buscas de gravacao simultaneas no mesmo NVR. Eram 10 no Hikvision: o DS-7616NI-K2 da Horizontes travava o
# servico web no meio da verificacao (canais NAO_VERIFICADO e configuracao sem baixar, 23 e 25/11/2026).
WORKERS_GRAVACAO_HIKVISION = 4
WORKERS_GRAVACAO_INTELBRAS = 5
# Pausa antes de refazer as buscas que falharam (dá tempo de o serviço web do NVR voltar). A rodada N espera N x a
# pausa; depois de NOVAS_VERIFICACOES rodadas o que ainda falhar fica como "não verificado" (nunca "sem gravação").
PAUSA_NOVA_VERIFICACAO_S = 60
NOVAS_VERIFICACOES = 2
# Numa nova verificação, quantos canais seguidos sem nenhuma resposta indicam que o NVR parou de vez (encerra a rodada)
CANAIS_SEGUIDOS_SEM_RESPOSTA = 2
# Dia do mapa de 15 dias cuja busca o NVR não respondeu
DIA_NAO_VERIFICADO = "?"

def _probe_hikvision(nvr_ip, usuario, senha):
    """Sonda NVR (IP) e DVR (analogico). Retorna (cameras, tipo) ou ({}, None) se nenhum respondeu."""
    cameras_nvr = buscar_cameras_nvr(nvr_ip, usuario, senha)
    cameras_dvr = buscar_cameras_dvr(nvr_ip, usuario, senha)

    if cameras_nvr and cameras_dvr:
        logging.info(f"  [{nvr_ip}] NVR híbrido detectado: {len(cameras_nvr)} câmera(s) IP + {len(cameras_dvr)} canal(is) analógico(s).")
        cameras_nvr.update(cameras_dvr)
        return cameras_nvr, "NVR"
    if cameras_nvr:
        return cameras_nvr, "NVR"
    if cameras_dvr:
        return cameras_dvr, "DVR"
    return {}, None


def buscar_cameras(nvr_ip, usuario, senha, marca=None):
    if marca:
        marca = marca.upper()
        if marca == "MOTOROLA":
            cameras, sessao = buscar_cameras_motorola(nvr_ip, usuario, senha)
            return cameras, "MOTOROLA", sessao
        elif marca == "INTELBRAS":
            cameras = buscar_cameras_intelbras(nvr_ip, usuario, senha)
            if cameras:
                return cameras, "INTELBRAS", None
            # Fallback para ISAPI caso seja um modelo Intelbras antigo/rebranded Hikvision
            cameras, tipo = _probe_hikvision(nvr_ip, usuario, senha)
            if cameras:
                return cameras, tipo, None
            return {}, "INTELBRAS", None
        elif marca == "HIKVISION":
            cameras, tipo = _probe_hikvision(nvr_ip, usuario, senha)
            return (cameras, tipo, None) if cameras else ({}, "DESCONHECIDO", None)

    # Fallback sem marca informada:
    # 1. Tenta Hikvision ISAPI
    cameras, tipo = _probe_hikvision(nvr_ip, usuario, senha)
    if cameras:
        return cameras, tipo, None

    # 2. Tenta Intelbras Dahua CGI
    cameras = buscar_cameras_intelbras(nvr_ip, usuario, senha)
    if cameras:
        return cameras, "INTELBRAS", None

    # 3. Tenta Motorola
    cameras, sessao = buscar_cameras_motorola(nvr_ip, usuario, senha)
    if cameras:
        return cameras, "MOTOROLA", sessao

    return {}, "DESCONHECIDO", None

def coletar_telemetria_nvr(nvr_ip, usuario, senha, tipo_nvr, marca=None, snmp_community=None):
    """Coleta CPU/RAM/discos/rede do NVR.
    - Motorola: HTTP XML (NVMS-9000 / TVT)
    - Intelbras: SNMP (porta 161)
    - Hikvision e demais compativeis: ISAPI (HTTP)"""
    marca_up = (marca or "").upper()
    if tipo_nvr == "MOTOROLA" or marca_up == "MOTOROLA":
        try:
            return coletar_telemetria_motorola(nvr_ip, usuario, senha)
        except Exception:
            logging.warning(f"  Falha ao coletar telemetria do NVR Motorola {nvr_ip}.", exc_info=True)
            return None

    if tipo_nvr not in ("NVR", "DVR", "INTELBRAS") and marca_up not in ("HIKVISION", "INTELBRAS"):
        return None
    try:
        if marca_up == "INTELBRAS" or tipo_nvr == "INTELBRAS":
            if coletar_telemetria_intelbras is None:
                return None
            if snmp_community:
                return coletar_telemetria_intelbras(nvr_ip, snmp_community)
            return coletar_telemetria_intelbras(nvr_ip)
        return coletar_telemetria_hikvision(nvr_ip, usuario, senha)
    except Exception:
        logging.warning(f"  Falha ao coletar telemetria do NVR {nvr_ip}.", exc_info=True)
        return None

def _canal_numerico_motorola(canal_id):
    try:
        return int(str(canal_id).strip("{}").split("-")[0], 16)
    except ValueError:
        return canal_id

def gerar_mapa_dias(dias_com_gravacao, dias_nao_verificados=()):
    """█ gravou, ░ não gravou (o NVR respondeu sem trecho), ? não verificado (a busca do dia falhou)."""
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    datas_set = set(d.strftime("%Y-%m-%d") for d in dias_com_gravacao)
    falhas_set = set(d.strftime("%Y-%m-%d") for d in dias_nao_verificados)
    mapa = ""
    for i in range(DIAS_VERIFICAR - 1, -1, -1):
        chave = (hoje - timedelta(days=i)).strftime("%Y-%m-%d")
        if chave in datas_set:
            mapa += "█"
        elif chave in falhas_set:
            mapa += DIA_NAO_VERIFICADO
        else:
            mapa += "░"
    return mapa

def descobrir_dias_gravados(existe_ate, hoje):
    """Dias corridos desde a gravacao mais antiga ate `hoje` (inclusive os dois dias).
    `existe_ate(dia)` -> True/False/None: ha gravacao entre o inicio da janela
    (hoje - DIAS_MAX_RETENCAO + 1) e o fim de `dia`. Busca binaria: o predicado e monotono,
    entao funciona mesmo com buracos e sem depender da ordem dos resultados do NVR.
    Retorna 0 se nao ha gravacao, None se alguma consulta falhou."""
    limite = hoje - timedelta(days=DIAS_MAX_RETENCAO - 1)
    r = existe_ate(hoje)
    if r is None:
        return None
    if not r:
        return 0
    lo, hi = 0, DIAS_MAX_RETENCAO - 1  # deslocamento em dias a partir de `limite`; existe_ate(limite + hi) e True
    while lo < hi:
        meio = (lo + hi) // 2
        r = existe_ate(limite + timedelta(days=meio))
        if r is None:
            return None
        if r:
            hi = meio
        else:
            lo = meio + 1
    return DIAS_MAX_RETENCAO - lo



def _consultar_canal(executor, nvr_ip, usuario, senha, canal_id, hoje, dias, com_dias_gravados,
                     fn_tem_gravacao, fn_tem_entre):
    """Consulta a gravação de um canal Hikvision/Intelbras nos `dias` pedidos e, se `com_dias_gravados`, os dias
    gravados desde a mais antiga. As buscas vão para `executor` (o número de workers limita a carga no NVR).
    Devolve (dias com gravação, dias cuja busca falhou, dias gravados ou None se não pedido/falhou)."""
    future_dias = None
    if com_dias_gravados:
        inicio_janela = hoje - timedelta(days=DIAS_MAX_RETENCAO - 1)
        future_dias = executor.submit(
            descobrir_dias_gravados,
            lambda dia, c=canal_id: fn_tem_entre(nvr_ip, usuario, senha, c, inicio_janela, dia.replace(hour=23, minute=59, second=59)),
            hoje,
        )
    future_to_day = {executor.submit(fn_tem_gravacao, nvr_ip, usuario, senha, canal_id, d): d for d in dias}

    com, falhou = set(), set()
    for future in as_completed(future_to_day):
        data_ref = future_to_day[future]
        try:
            res = future.result()
        except Exception:
            res = None
        if res is True:
            com.add(data_ref)
        elif res is None:
            # Busca sem resposta: o dia fica "não verificado", nunca "sem gravação". Antes só o dia de hoje era
            # tratado assim e os outros viravam ░ (NVR 03 da Horizontes: PLACAS VISITANTES e CASA ZANON com dias
            # "sem gravação" que o NVR tinha gravado, 27/11/2026).
            falhou.add(data_ref)

    dias_gravados = None
    if future_dias is not None:
        try:
            dias_gravados = future_dias.result()
        except Exception:
            logging.warning(f"  Falha ao descobrir os dias gravados do canal {canal_id} em {nvr_ip}.", exc_info=True)
    return com, falhou, dias_gravados


def _montar_resultado(canal_id, camera, hoje, estado):
    online = camera["online"]
    com, falhou = estado["com"], estado["falhou"]
    if online is None:
        online = len(com) > 0
    if hoje in falhou:
        status_gravacao = "NAO_VERIFICADO"
    else:
        status_gravacao = "COM_GRAVACAO" if hoje in com else "SEM_GRAVACAO"
    return {
        "canal": canal_id,
        "nome": camera["nome"],
        "ip": camera["ip"],
        "online": online,
        "status_comunicacao": "ONLINE" if online else "OFFLINE",
        "status_gravacao": status_gravacao,
        "total_dias": len(com),
        "mapa": gerar_mapa_dias(com, falhou),
        "dias_com_gravacao": [d.strftime("%Y-%m-%d") for d in sorted(com, reverse=True)],
        "dias_nao_verificados": [d.strftime("%Y-%m-%d") for d in sorted(falhou, reverse=True)],
        "dias_gravados": estado["dias_gravados"],
    }


def _pendente(estado):
    return bool(estado["falhou"]) or estado["dias_gravados"] is None


def _verificar_hikvision_intelbras(nvr_ip, usuario, senha, cameras, tipo, hoje):
    fn_tem_gravacao = tem_gravacao_no_dia_intelbras if tipo == "INTELBRAS" else tem_gravacao_no_dia
    fn_tem_entre = tem_gravacao_entre_intelbras if tipo == "INTELBRAS" else tem_gravacao_entre
    workers = WORKERS_GRAVACAO_INTELBRAS if tipo == "INTELBRAS" else WORKERS_GRAVACAO_HIKVISION
    canais = list(cameras.items())
    todos_os_dias = [hoje - timedelta(days=i) for i in range(DIAS_VERIFICAR)]

    estados = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for canal_id, _camera in canais:
            com, falhou, dias_gravados = _consultar_canal(executor, nvr_ip, usuario, senha, canal_id, hoje,
                                                          todos_os_dias, True, fn_tem_gravacao, fn_tem_entre)
            estados.append({"com": com, "falhou": falhou, "dias_gravados": dias_gravados})

    # Busca que falhou (qualquer um dos 15 dias, ou os dias gravados) = o NVR não respondeu: o NVR mais fraco trava o
    # serviço web no meio da verificação (NVR 03 da Horizontes, 23-27/11/2026). Depois de uma pausa, refaz só as
    # buscas que falharam, uma por vez; o que continuar sem resposta fica como "não verificado".
    for rodada in range(1, NOVAS_VERIFICACOES + 1):
        pendentes = [i for i, e in enumerate(estados) if _pendente(e)]
        if not pendentes:
            break
        pausa = PAUSA_NOVA_VERIFICACAO_S * rodada
        dias_pendentes = sum(len(estados[i]["falhou"]) for i in pendentes)
        logging.warning(f"  {len(pendentes)} câmera(s) de {nvr_ip} com {dias_pendentes} dia(s) sem a gravação verificada "
                        f"(o NVR pode ter parado de responder); nova verificação {rodada}/{NOVAS_VERIFICACOES} em "
                        f"{pausa} s, uma busca por vez.")
        time.sleep(pausa)
        sem_resposta_seguidos = 0
        with ThreadPoolExecutor(max_workers=1) as executor:
            for i in pendentes:
                canal_id = canais[i][0]
                e = estados[i]
                pedidos = sorted(e["falhou"])
                pedir_dias_gravados = e["dias_gravados"] is None
                com, falhou, dias_gravados = _consultar_canal(executor, nvr_ip, usuario, senha, canal_id, hoje,
                                                              pedidos, pedir_dias_gravados, fn_tem_gravacao, fn_tem_entre)
                e["com"] |= com
                e["falhou"] = falhou
                if pedir_dias_gravados:
                    e["dias_gravados"] = dias_gravados
                nada_respondeu = len(falhou) == len(pedidos) and (not pedir_dias_gravados or dias_gravados is None)
                sem_resposta_seguidos = sem_resposta_seguidos + 1 if nada_respondeu else 0
                if sem_resposta_seguidos >= CANAIS_SEGUIDOS_SEM_RESPOSTA:
                    logging.warning(f"  {nvr_ip} não respondeu a nenhuma busca de {sem_resposta_seguidos} câmera(s) "
                                    f"seguidas; nova verificação {rodada} encerrada.")
                    break
        restantes = sum(1 for i in pendentes if _pendente(estados[i]))
        sufixo = f"; {restantes} ainda com dia(s) sem verificar" if restantes else ""
        logging.info(f"  Nova verificação {rodada} em {nvr_ip}: {len(pendentes) - restantes} de {len(pendentes)} "
                     f"câmera(s) verificada(s) por completo{sufixo}.")

    for i, e in enumerate(estados):
        if e["falhou"]:
            dias = ", ".join(d.strftime("%d/%m") for d in sorted(e["falhou"]))
            logging.warning(f"  {canais[i][1]['nome']} (canal {canais[i][0]}) em {nvr_ip}: o NVR não respondeu à busca "
                            f"de {dias}; esses dias ficam como não verificados.")

    return [_montar_resultado(canal_id, camera, hoje, estados[i]) for i, (canal_id, camera) in enumerate(canais)]


def verificar_gravacao_nvr(nvr_ip, usuario, senha, marca=None):
    logging.info(f"  Verificando gravação para {nvr_ip}...")
    try:
        cameras, tipo, sessao = buscar_cameras(nvr_ip, usuario, senha, marca)
        if not cameras:
            logging.info(f"  Nenhuma câmera encontrada para verificação de gravação.")
            return [], tipo

        hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        resultados = []
        
        if tipo == "MOTOROLA":
            # Motorola: Processamento agrupado por datas
            for canal_id, camera in cameras.items():
                datas_gravadas, query_sucesso = buscar_datas_gravacao_motorola(nvr_ip, sessao, canal_id)
                if not query_sucesso:
                    dias_gravados = None
                elif datas_gravadas:
                    dias_gravados = max((hoje - min(datas_gravadas)).days + 1, 0)
                else:
                    dias_gravados = 0
                dias_com_gravacao = []
                for dt in datas_gravadas:
                    if (hoje - timedelta(days=DIAS_VERIFICAR - 1)) <= dt <= hoje:
                        dias_com_gravacao.append(dt)
                        
                if camera["online"] is True:
                    status_comunicacao = "ONLINE"
                elif camera["online"] is False:
                    status_comunicacao = "OFFLINE"
                else:
                    status_comunicacao = "ERRO_COMUNICACAO"

                if query_sucesso:
                    status_gravacao = "COM_GRAVACAO" if hoje in dias_com_gravacao else "SEM_GRAVACAO"
                else:
                    status_gravacao = "NAO_VERIFICADO"
                        
                resultados.append({
                    # O canal Motorola é um GUID "{0000000N-0000-...}"; o número N é o chID do RTSP
                    # e a chave usada pela galeria (nvr_cameras.canal é inteiro).
                    "canal": _canal_numerico_motorola(canal_id),
                    "canal_guid": canal_id,
                    "nome": camera["nome"],
                    "ip": camera["ip"],
                    "online": camera["online"],
                    "status_comunicacao": status_comunicacao,
                    "status_gravacao": status_gravacao,
                    "total_dias": len(dias_com_gravacao),
                    "mapa": gerar_mapa_dias(dias_com_gravacao),
                    "dias_com_gravacao": [d.strftime("%Y-%m-%d") for d in dias_com_gravacao],
                    "dias_gravados": dias_gravados
                })
            return resultados, tipo

        # Demais Marcas (Hikvision e Intelbras)
        resultados = _verificar_hikvision_intelbras(nvr_ip, usuario, senha, cameras, tipo, hoje)
        return resultados, tipo
    except Exception as e:
        logging.error(f"  Erro ao verificar gravação no NVR {nvr_ip}: {e}")
        return [], "DESCONHECIDO"
