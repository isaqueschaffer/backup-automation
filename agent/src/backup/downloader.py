import logging
import hashlib
import re
from pathlib import Path

TIMEOUT_NVR = 60
# Túnel do Mikrotik: configs pequenas ficam inteiras na memória até este limite; acima disso o download vira ERRO
# (arquivo grande tem de ir em blocos, nunca inteiro na RAM do roteador).
LIMITE_MEMORIA = 64 * 1024 * 1024


class LimiteMemoriaExcedido(Exception):
    pass


_RE_QUERY = re.compile(r"\?[^\s'\")]*")


def sem_query(texto) -> str:
    """Tira a query string de URLs dentro de um texto antes de ir para o log: a URL do backup Hikvision leva
    `secretkey=...&iv=...` (dá para recuperar a senha do ZIP com ela) e as exceções do requests repetem a URL."""
    return _RE_QUERY.sub("?…", str(texto))


def baixar_bytes(sessao, url, min_bytes=0, valida_xml=False, limite=LIMITE_MEMORIA, timeout=TIMEOUT_NVR):
    """Igual a `baixar_arquivo`, mas devolve os bytes (None se falhou) e não grava nada em disco.
    Passou de `limite` bytes: levanta LimiteMemoriaExcedido (o chamador transforma em ERRO com mensagem clara)."""
    try:
        buf = bytearray()
        with sessao.get(url, stream=True, timeout=timeout) as r:
            if r.status_code not in (200, 401):
                logging.error(f"HTTP {r.status_code}: {sem_query(url)}")
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
        logging.error(f"  Erro download {sem_query(url)}: {sem_query(e)}")
        return None


def baixar_arquivo(sessao, url, destino: Path, min_bytes=0, valida_xml=False) -> bool:
    try:
        with sessao.get(url, stream=True, timeout=TIMEOUT_NVR) as r:
            if r.status_code not in (200, 401):
                logging.error(f"HTTP {r.status_code}: {sem_query(url)}")
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
        logging.error(f"  Erro download {destino.name}: {sem_query(e)}")
        destino.unlink(missing_ok=True)
        return False
