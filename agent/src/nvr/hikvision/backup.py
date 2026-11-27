"""Backup da configuração do NVR/DVR Hikvision pelo ISAPI: `.bin` cifrado (configurationData) e `.xls` das IPCAM
(ipcConfig), em memória. Comum ao agente Windows (`backup_job.processar_nvr`) e ao túnel do Mikrotik
(`tunel_preparo.preparar_nvr`), que antes tinham cada um a sua cópia do fluxo.

Ordem (desde 1.1.69): a configuração é baixada ANTES da verificação de gravação (`baixar_antes_da_gravacao`), numa
tentativa só, e depois completada com novas tentativas (`completar`) se faltou algo. A verificação de gravação é a
parte pesada e é ela que trava o serviço web dos NVR mais fracos (NVR 03 da Horizontes, DS-7616NI-K2, 23-26/11/2026):
com a configuração já salva, o backup de fato não se perde mesmo se o NVR parar de responder depois.
"""
import logging

import requests
from requests.auth import HTTPDigestAuth

from src.backup.crypto import gerar_secretkey
from src.backup import downloader
from src.backup.downloader import LIMITE_MEMORIA

MIN_BYTES_BIN = 100_000  # .bin menor que isso = resposta de erro/autenticação, não a configuração
ARQUIVOS = {
    "bin": "configuração do NVR (.bin)",
    "xls": "configuração das IPCAM (.xls)",
}


def _sessao(usuario, senha):
    sessao = requests.Session()
    sessao.auth = HTTPDigestAuth(usuario, senha)
    sessao.verify = False  # equipamento da rede local, certificado autoassinado
    return sessao


def _novo_resultado(anterior=None) -> dict:
    anterior = anterior or {}
    return {"bin": anterior.get("bin"), "xls": anterior.get("xls"), "motivos": dict(anterior.get("motivos") or {})}


def _baixar(ip, usuario, senha, zip_password, resultado, novas_tentativas, limite):
    def tentar(acao, descricao):
        return downloader.com_novas_tentativas(acao, descricao) if novas_tentativas else acao()

    sessao = _sessao(usuario, senha)
    if not tentar(lambda: downloader.isapi_responde(sessao, ip), "ISAPI do NVR"):
        motivo = downloader.motivo_da_falha() or "ISAPI sem resposta"
        for chave in ARQUIVOS:
            if not resultado[chave]:
                resultado["motivos"][chave] = motivo
        return resultado

    if not resultado["bin"]:
        sk, iv = gerar_secretkey(zip_password)
        url_bin = f"http://{ip}/ISAPI/System/configurationData?secretkey={sk}&security=1&iv={iv}"
        dados = tentar(lambda: downloader.baixar_bytes(sessao, url_bin, min_bytes=MIN_BYTES_BIN, valida_xml=True, limite=limite),
                       "Download da configuracao do NVR")
        if dados:
            resultado["bin"] = dados
            resultado["motivos"].pop("bin", None)
            logging.info("  Backup NVR OK.")
        else:
            resultado["motivos"]["bin"] = downloader.motivo_da_falha() or "sem resposta"

    if not resultado["xls"]:
        url_xls = f"http://{ip}/ISAPI/ContentMgmt/InputProxy/ipcConfig"
        dados = tentar(lambda: downloader.baixar_bytes(sessao, url_xls, limite=limite), "Download da configuracao das IPCAM")
        if dados:
            resultado["xls"] = dados
            resultado["motivos"].pop("xls", None)
            logging.info("  Backup IPCAM OK.")
        else:
            resultado["motivos"]["xls"] = downloader.motivo_da_falha() or "sem resposta"
    return resultado


def baixar_antes_da_gravacao(ip, usuario, senha, zip_password, limite=LIMITE_MEMORIA):
    """Uma tentativa de baixar a configuração antes da verificação de gravação. None se o ISAPI não respondeu
    (equipamento de outra marca, fora do ar ou ainda ocupado): aí `completar` tenta tudo depois, com novas tentativas.
    LimiteMemoriaExcedido sobe para quem chamou."""
    sessao = _sessao(usuario, senha)
    if not downloader.isapi_responde(sessao, ip):
        logging.info("  ISAPI não respondeu antes da verificação de gravação; a configuração será baixada depois.")
        return None
    logging.info("  Baixando a configuração antes da verificação de gravação (é a parte pesada e pode travar o NVR)...")
    return _baixar(ip, usuario, senha, zip_password, _novo_resultado(), novas_tentativas=False, limite=limite)


def completar(ip, usuario, senha, zip_password, anterior=None, limite=LIMITE_MEMORIA) -> dict:
    """Baixa o que faltou (`anterior` = resultado de `baixar_antes_da_gravacao`, ou None), com novas tentativas.
    Retorna {'bin': bytes|None, 'xls': bytes|None, 'motivos': {'bin'|'xls': motivo da falha}}."""
    resultado = _novo_resultado(anterior)
    if resultado["bin"] and resultado["xls"]:
        return resultado
    if anterior is not None:
        faltando = ", ".join(ARQUIVOS[k] for k in ARQUIVOS if not resultado[k])
        logging.info(f"  Tentando de novo o que faltou da configuração: {faltando}.")
    return _baixar(ip, usuario, senha, zip_password, resultado, novas_tentativas=True, limite=limite)


def descrever_falhas(config: dict | None, cameras=None, telemetria=None, telemetria_esperada=True) -> str:
    """Motivo legível do PARCIAL/ERRO para o log e o painel: o que não foi baixado e por quê, câmeras com a gravação
    não verificada e telemetria ausente. Vazio quando não houve falha."""
    partes = []
    for chave, rotulo in ARQUIVOS.items():
        if config is not None and not config.get(chave):
            motivo = (config.get("motivos") or {}).get(chave) or "sem resposta"
            partes.append(f"{rotulo} não baixada: {motivo}")
    nao_verificadas = [c.get("nome") or str(c.get("canal")) for c in (cameras or [])
                       if isinstance(c, dict) and c.get("status_gravacao") == "NAO_VERIFICADO"]
    if nao_verificadas:
        lista = ", ".join(nao_verificadas[:5]) + ("..." if len(nao_verificadas) > 5 else "")
        partes.append(f"{len(nao_verificadas)} câmera(s) com a gravação não verificada ({lista})")
    if telemetria_esperada and telemetria is None and (config is not None or cameras):
        partes.append("telemetria indisponível (o NVR não respondeu)")
    return "; ".join(partes)
