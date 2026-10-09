import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.nvr.hikvision.cameras import buscar_cameras_nvr, buscar_cameras_dvr
from src.nvr.motorola.cameras import buscar_cameras as buscar_cameras_motorola
from src.nvr.motorola.recordings import buscar_datas_gravacao_motorola
from src.nvr.hikvision.recordings import tem_gravacao_no_dia

DIAS_VERIFICAR = 15

def buscar_cameras(nvr_ip, usuario, senha, marca=None):
    if marca:
        marca = marca.upper()
        if marca == "MOTOROLA":
            cameras, sessao = buscar_cameras_motorola(nvr_ip, usuario, senha)
            return cameras, "MOTOROLA", sessao
        elif marca == "HIKVISION":
            cameras_nvr = buscar_cameras_nvr(nvr_ip, usuario, senha)
            cameras_dvr = buscar_cameras_dvr(nvr_ip, usuario, senha)
            if cameras_nvr and cameras_dvr:
                cameras_nvr.update(cameras_dvr)
                return cameras_nvr, "NVR", None
            if cameras_nvr: return cameras_nvr, "NVR", None
            if cameras_dvr: return cameras_dvr, "DVR", None
            return {}, "DESCONHECIDO", None

    # Fallback: probe both
    cameras_nvr = buscar_cameras_nvr(nvr_ip, usuario, senha)
    cameras_dvr = buscar_cameras_dvr(nvr_ip, usuario, senha)

    if cameras_nvr and cameras_dvr:
        logging.info(f"  [{nvr_ip}] NVR híbrido detectado: {len(cameras_nvr)} câmera(s) IP + {len(cameras_dvr)} canal(is) analógico(s).")
        cameras_nvr.update(cameras_dvr)
        return cameras_nvr, "NVR", None

    if cameras_nvr:
        return cameras_nvr, "NVR", None

    if cameras_dvr:
        return cameras_dvr, "DVR", None

    cameras, sessao = buscar_cameras_motorola(nvr_ip, usuario, senha)
    if cameras:
        return cameras, "MOTOROLA", sessao

    return {}, "DESCONHECIDO", None

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
                    "canal": canal_id,
                    "nome": camera["nome"],
                    "ip": camera["ip"],
                    "online": camera["online"],
                    "status_comunicacao": status_comunicacao,
                    "status_gravacao": status_gravacao,
                    "total_dias": len(dias_com_gravacao),
                    "mapa": gerar_mapa_dias(dias_com_gravacao)
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
