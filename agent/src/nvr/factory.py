import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.nvr.hikvision.cameras import buscar_cameras_nvr, buscar_cameras_dvr
from src.nvr.motorola.cameras import buscar_cameras as buscar_cameras_motorola
from src.nvr.motorola.recordings import buscar_datas_gravacao_motorola
from src.nvr.hikvision.recordings import tem_gravacao_no_dia
from src.nvr.hikvision.telemetry import coletar_telemetria_hikvision
from src.nvr.motorola.telemetry import coletar_telemetria_motorola
try:
    from src.nvr.intelbras.telemetry import coletar_telemetria_intelbras
except Exception:
    # pysnmp ausente ou incompatível: só a telemetria Intelbras fica indisponível (o backup segue normal)
    logging.warning("Telemetria SNMP (Intelbras) indisponível: falha ao carregar o pysnmp.", exc_info=True)
    coletar_telemetria_intelbras = None

DIAS_VERIFICAR = 15

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
        elif marca in ("HIKVISION", "INTELBRAS"):
            # NVR Intelbras usa o mesmo protocolo ISAPI do Hikvision para cameras/gravacoes.
            cameras, tipo = _probe_hikvision(nvr_ip, usuario, senha)
            return (cameras, tipo, None) if cameras else ({}, "DESCONHECIDO", None)

    # Fallback: probe both
    cameras, tipo = _probe_hikvision(nvr_ip, usuario, senha)
    if cameras:
        return cameras, tipo, None

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

    if tipo_nvr not in ("NVR", "DVR"):
        return None
    try:
        if marca_up == "INTELBRAS":
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

def gerar_mapa_dias(dias_com_gravacao):
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    datas_set = set(d.strftime("%Y-%m-%d") for d in dias_com_gravacao)
    mapa = ""
    for i in range(DIAS_VERIFICAR - 1, -1, -1):
        data = hoje - timedelta(days=i)
        if data.strftime("%Y-%m-%d") in datas_set:
            mapa += "█"
        else:
            mapa += "░"
    return mapa

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
                    "dias_com_gravacao": [d.strftime("%Y-%m-%d") for d in dias_com_gravacao]
                })
            return resultados, tipo

        # Demais Marcas (Hikvision)
        with ThreadPoolExecutor(max_workers=10) as executor:
            for canal_id, camera in cameras.items():
                nome = camera["nome"]
                ip = camera["ip"]
                online = camera["online"]

                future_to_day = {
                    executor.submit(tem_gravacao_no_dia, nvr_ip, usuario, senha, canal_id, hoje - timedelta(days=i)): (hoje - timedelta(days=i))
                    for i in range(DIAS_VERIFICAR)
                }

                dias_com_gravacao = []
                teve_erro_hoje = False
                
                for future in as_completed(future_to_day):
                    data_ref = future_to_day[future]
                    try:
                        res = future.result()
                        if res is True:
                            dias_com_gravacao.append(data_ref)
                        elif res is None:
                            if data_ref == hoje:
                                teve_erro_hoje = True
                    except Exception:
                        if data_ref == hoje:
                            teve_erro_hoje = True

                if online is None:
                    online = len(dias_com_gravacao) > 0

                status_comunicacao = "ONLINE" if online else "OFFLINE"

                if teve_erro_hoje:
                    status_gravacao = "NAO_VERIFICADO"
                else:
                    status_gravacao = "COM_GRAVACAO" if hoje in dias_com_gravacao else "SEM_GRAVACAO"

                resultados.append({
                    "canal": canal_id,
                    "nome": nome,
                    "ip": ip,
                    "online": online,
                    "status_comunicacao": status_comunicacao,
                    "status_gravacao": status_gravacao,
                    "total_dias": len(dias_com_gravacao),
                    "mapa": gerar_mapa_dias(dias_com_gravacao),
                    "dias_com_gravacao": [d.strftime("%Y-%m-%d") for d in dias_com_gravacao]
                })

        return resultados, tipo
    except Exception as e:
        logging.error(f"  Erro ao verificar gravação no NVR {nvr_ip}: {e}")
        return [], "DESCONHECIDO"
