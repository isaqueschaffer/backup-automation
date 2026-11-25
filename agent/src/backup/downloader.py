import logging
import hashlib
import time
from pathlib import Path

TIMEOUT_NVR = 60
# NVR Hikvision mais fraco (ex.: DS-7616NI-K2) às vezes trava o serviço web por alguns minutos depois da
# verificação de gravação; a configuração é tentada de novo depois de uma pausa antes de virar PARCIAL.
TENTATIVAS_NVR = 3
PAUSA_NOVA_TENTATIVA_NVR_S = 60
# Túnel do Mikrotik: configs pequenas ficam inteiras na memória até este limite; acima disso o download vira ERRO
# (arquivo grande tem de ir em blocos, nunca inteiro na RAM do roteador).
LIMITE_MEMORIA = 64 * 1024 * 1024


class LimiteMemoriaExcedido(Exception):
    pass


def com_novas_tentativas(acao, descricao, tentativas=None, pausa=None):
    """Chama `acao()` até ela devolver algo verdadeiro (True/bytes), com `pausa` segundos entre as tentativas.
    Devolve o último resultado (falso se todas falharam). Exceção de `acao` não é engolida."""
    tentativas = TENTATIVAS_NVR if tentativas is None else tentativas
    pausa = PAUSA_NOVA_TENTATIVA_NVR_S if pausa is None else pausa
    resultado = None
    for n in range(1, tentativas + 1):
        resultado = acao()
        if resultado:
            if n > 1:
                logging.info(f"  {descricao}: deu certo na tentativa {n}/{tentativas}.")
            return resultado
        if n < tentativas:
            logging.warning(f"  {descricao} falhou (tentativa {n}/{tentativas}); nova tentativa em {pausa} s.")
            time.sleep(pausa)
    logging.warning(f"  {descricao} falhou nas {tentativas} tentativas.")
    return resultado


def isapi_responde(sessao, ip) -> bool:
    """True se o NVR Hikvision responde ao /ISAPI/System/status (sem levantar exceção)."""
    try:
        sessao.get(f"http://{ip}/ISAPI/System/status", timeout=10).raise_for_status()
        return True
    except Exception as e:
        logging.info(f"  ISAPI de {ip} sem resposta: {e}")
        return False


def baixar_bytes(sessao, url, min_bytes=0, valida_xml=False, limite=LIMITE_MEMORIA, timeout=TIMEOUT_NVR):
    """Igual a `baixar_arquivo`, mas devolve os bytes (None se falhou) e não grava nada em disco.
    Passou de `limite` bytes: levanta LimiteMemoriaExcedido (o chamador transforma em ERRO com mensagem clara)."""
    try:
        buf = bytearray()
        with sessao.get(url, stream=True, timeout=timeout) as r:
            if r.status_code not in (200, 401):
                logging.error(f"HTTP {r.status_code}: {url}")
                return None
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    buf += chunk
                    if len(buf) > limite:
                        raise LimiteMemoriaExcedido(
                            f"o equipamento enviou mais de {limite // (1024 * 1024)} MB; acima disso o Mikrotik não "
                            f"guarda em memória (use um agente Windows para este equipamento)")
        dados = bytes(buf)
        if len(dados) < min_bytes:
            raise ValueError("Arquivo muito pequeno (falha de autenticacao).")
        if valida_xml and b"<ResponseStatus" in dados[:500]:
            raise ValueError("Resposta de erro XML recebida.")
        logging.info(f"  Baixado em memoria: {len(dados)/1024:.1f} KB SHA-256: {hashlib.sha256(dados).hexdigest()[:16]}...")
        return dados
    except LimiteMemoriaExcedido:
        raise
    except Exception as e:
        logging.error(f"  Erro download {url.split('?')[0]}: {e}")
        return None


def baixar_arquivo(sessao, url, destino: Path, min_bytes=0, valida_xml=False) -> bool:
    try:
        with sessao.get(url, stream=True, timeout=TIMEOUT_NVR) as r:
            if r.status_code not in (200, 401):
                logging.error(f"HTTP {r.status_code}: {url}")
                return False
            with open(destino, "wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    if chunk:
                        f.write(chunk)
        dados = destino.read_bytes()
        if len(dados) < min_bytes:
            raise ValueError("Arquivo muito pequeno (falha de autenticacao).")
        if valida_xml and b"<ResponseStatus" in dados[:500]:
            raise ValueError("Resposta de erro XML recebida.")
        sha256 = hashlib.sha256(dados).hexdigest()
        logging.info(f"  Salvo: {destino.name} ({len(dados)/1024:.1f} KB) SHA-256: {sha256[:16]}...")
        return True
    except Exception as e:
        logging.error(f"  Erro download {destino.name}: {e}")
        destino.unlink(missing_ok=True)
        return False
