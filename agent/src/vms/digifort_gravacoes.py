"""Tempo de gravacao das cameras do Digifort, calculado a partir dos arquivos de indice (.dix).

Estrutura em disco (observada nos arquivos de exemplo):
    <raiz>/<nome da camera>/Dados/AAAAMMDD_NN.dar     video
    <raiz>/<nome da camera>/Indices/AAAAMMDD_NN.dix   indice
NN e a meia hora do dia, de 1 a 48 (1 = 00:00-00:30). Uma pasta com Dados e Indices direto tambem e aceita
(camera unica; o nome da camera e o nome da pasta).

O .dix tem um cabecalho de 26 bytes ("DGFDB2...") e registros de 69 bytes, um por quadro gravado:
marcador '-REG-' (5), data (double, TDateTime do Delphi) (8), hora (double, fracao do dia) (8),
hash (32) e 16 bytes com tamanho/posicao no .dar. Os horarios sao locais (os mesmos do nome do arquivo).
O tempo gravado e a soma dos trechos em que um quadro segue o outro em ate TOLERANCIA_S segundos;
um salto maior e uma interrupcao da gravacao.
"""
import hashlib
import json
import logging
import os
import re
import struct
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

from src.application.webhook_digifort import normalizar_texto

TAM_CABECALHO = 26
TAM_REGISTRO = 69
ASSINATURA = b"DGFDB2"
MARCADOR = b"-REG-"
TOLERANCIA_S = 30       # salto maior que isso entre dois quadros = interrupcao
PASSO_AMOSTRA = 600     # 1 registro a cada 600 (~20 s a 30 fps): so le tudo onde ha salto
DIAS_PADRAO = 15
LIMIAR_PARCIAL = 0.9    # abaixo de 90% do dia (ou do tempo ja decorrido, no dia de hoje) = parcial
LIMITE_TOTAL_S = 900    # tempo maximo de leitura por execucao; o que sobrar fica no cache para a proxima
VERSAO_CACHE = 1

MAPA_GRAVOU = "█"
MAPA_PARCIAL = "▒"
MAPA_SEM_GRAVACAO = "░"
MAPA_SEM_HISTORICO = "·"   # dia anterior a primeira gravacao encontrada (retencao ou camera nova)

_REGISTRO = struct.Struct("<5x2d48x")   # 69 bytes: pula o marcador, le data e hora, pula o resto
_NOME_INDICE = re.compile(r"^(\d{8})_(\d{1,2})\.dix$", re.IGNORECASE)
_EPOCA_DELPHI = date(1899, 12, 30)


class IndiceInvalido(Exception):
    """Arquivo .dix de formato desconhecido ou corrompido."""


def _tempo(f, i):
    """Horario do registro `i`, em dias desde 30/12/1899 (TDateTime)."""
    f.seek(TAM_CABECALHO + i * TAM_REGISTRO + 5)
    dados = f.read(16)
    if len(dados) < 16:
        raise IndiceInvalido("registro truncado")
    dia, fracao = struct.unpack("<dd", dados)
    if not 36500 < dia < 80000:  # entre 1999 e 2118: fora disso nao e uma data de gravacao
        raise IndiceInvalido(f"data fora do esperado ({dia})")
    return dia + fracao


def intervalos_do_indice(caminho, tolerancia_s=TOLERANCIA_S, passo=PASSO_AMOSTRA):
    """Trechos gravados de um .dix: [(inicio, fim)] em dias TDateTime.
    Le 1 registro a cada `passo`; so varre tudo entre duas amostras quando o salto passa da tolerancia
    (os horarios sao crescentes, entao uma interrupcao sempre aparece como salto entre amostras)."""
    tol = tolerancia_s / 86400
    with open(caminho, "rb") as f:
        cabecalho = f.read(TAM_CABECALHO + len(MARCADOR))
        if cabecalho[:len(ASSINATURA)] != ASSINATURA:
            raise IndiceInvalido("cabecalho desconhecido")
        n = (os.fstat(f.fileno()).st_size - TAM_CABECALHO) // TAM_REGISTRO
        if n <= 0:  # arquivo recem-criado, so com o cabecalho
            return []
        if cabecalho[TAM_CABECALHO:] != MARCADOR:
            raise IndiceInvalido("registros em formato desconhecido")
        inicio = anterior_t = _tempo(f, 0)
        anterior_i = 0
        amostras = list(range(passo, n, passo))
        if n > 1 and (not amostras or amostras[-1] != n - 1):
            amostras.append(n - 1)
        intervalos = []
        for i in amostras:
            t = _tempo(f, i)
            if t - anterior_t <= tol:
                anterior_t, anterior_i = max(anterior_t, t), i
                continue
            f.seek(TAM_CABECALHO + anterior_i * TAM_REGISTRO)
            bloco = f.read((i - anterior_i + 1) * TAM_REGISTRO)
            bloco = bloco[:len(bloco) - len(bloco) % TAM_REGISTRO]
            for dia, fracao in _REGISTRO.iter_unpack(bloco):
                t_reg = dia + fracao
                if t_reg - anterior_t > tol:
                    intervalos.append((inicio, anterior_t))
                    inicio = t_reg
                anterior_t = max(anterior_t, t_reg)
            anterior_i = i
        intervalos.append((inicio, anterior_t))
    return intervalos


def segundos_por_dia(intervalos, destino=None):
    """Soma os trechos por dia (um trecho que atravessa a meia-noite e dividido)."""
    destino = {} if destino is None else destino
    for inicio, fim in intervalos:
        dia = int(inicio)
        while dia <= int(fim):
            sobreposto = (min(fim, dia + 1) - max(inicio, dia)) * 86400
            if sobreposto > 0:
                chave = _EPOCA_DELPHI + timedelta(days=dia)
                destino[chave] = destino.get(chave, 0.0) + sobreposto
            dia += 1
    return destino


def listar_pastas_cameras(raiz):
    """{nome da pasta: Path} das cameras em `raiz`. Aceita <raiz>/<camera>/{Dados,Indices} ou a pasta
    de uma camera so (com Dados e Indices direto, o nome e o da propria pasta)."""
    raiz = Path(raiz)
    if not raiz.is_dir():
        return {}
    if (raiz / "Indices").is_dir():
        return {raiz.name: raiz}
    pastas = {}
    try:
        for filho in sorted(raiz.iterdir()):
            if filho.is_dir() and (filho / "Indices").is_dir():
                pastas[filho.name] = filho
    except OSError as e:
        logging.warning(f"  [DIGIFORT] Nao foi possivel listar {raiz}: {e}")
    return pastas


def _carregar_cache(caminho):
    if not caminho:
        return {}
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        if dados.get("versao") == VERSAO_CACHE and dados.get("tolerancia_s") == TOLERANCIA_S:
            return dados.get("arquivos", {})
    except (OSError, ValueError):
        pass
    return {}


def _salvar_cache(caminho, arquivos):
    if not caminho:
        return
    try:
        tmp = Path(str(caminho) + ".tmp")
        tmp.write_text(json.dumps({"versao": VERSAO_CACHE, "tolerancia_s": TOLERANCIA_S, "arquivos": arquivos}),
                       encoding="utf-8")
        tmp.replace(caminho)
    except OSError as e:
        logging.warning(f"  [DIGIFORT] Nao foi possivel gravar o cache de gravacoes: {e}")


def caminho_cache(raiz, pasta_agente):
    """Arquivo de cache desta pasta de gravacoes (um por raiz, para equipamentos nao se misturarem)."""
    chave = hashlib.md5(str(raiz).lower().encode("utf-8")).hexdigest()[:8]
    return Path(pasta_agente) / f"cache_gravacoes_digifort_{chave}.json"


def calcular_gravacoes(raiz, hoje=None, dias=DIAS_PADRAO, cache=None, limite_s=LIMITE_TOTAL_S):
    """Segundos gravados por dia de cada camera de `raiz`, nos ultimos `dias` dias (ate `hoje`).
    Retorna {nome da pasta: {dia: segundos}}; None no lugar do dict se a camera ficou incompleta
    (tempo esgotado: o que ja foi lido fica no cache e a proxima execucao continua)."""
    hoje = hoje or date.today()
    primeiro = hoje - timedelta(days=dias - 1)
    arquivos_cache = _carregar_cache(cache)
    novos = {}
    limite = time.monotonic() + limite_s
    resultado = {}
    for nome, pasta in listar_pastas_cameras(raiz).items():
        indices = []
        try:
            for arq in (pasta / "Indices").iterdir():
                m = _NOME_INDICE.match(arq.name)
                if not m:
                    continue
                try:
                    data_arq = datetime.strptime(m.group(1), "%Y%m%d").date()
                except ValueError:
                    continue
                if primeiro <= data_arq <= hoje:
                    indices.append(arq)
        except OSError as e:
            logging.warning(f"  [DIGIFORT] Nao foi possivel listar {pasta / 'Indices'}: {e}")
            resultado[nome] = None
            continue

        por_dia, completo = {}, True
        for arq in sorted(indices):
            try:
                estado = arq.stat()
            except OSError:
                continue
            chave = str(arq)
            em_cache = arquivos_cache.get(chave)
            if em_cache and em_cache.get("tamanho") == estado.st_size and em_cache.get("mtime") == estado.st_mtime_ns:
                intervalos = [tuple(i) for i in em_cache["intervalos"]]
            elif time.monotonic() > limite:
                completo = False
                continue
            else:
                try:
                    intervalos = intervalos_do_indice(arq)
                except (IndiceInvalido, OSError) as e:
                    logging.warning(f"  [DIGIFORT] Indice ignorado ({arq.name}): {e}")
                    continue
            novos[chave] = {"tamanho": estado.st_size, "mtime": estado.st_mtime_ns, "intervalos": intervalos}
            segundos_por_dia(intervalos, por_dia)
        resultado[nome] = por_dia if completo else None
    _salvar_cache(cache, novos)
    return resultado


def resumir_camera(por_dia, hoje, agora=None, dias=DIAS_PADRAO, limiar=LIMIAR_PARCIAL):
    """Resume os segundos por dia de uma camera nos campos do relatorio:
    mapa de `dias` caracteres (o ultimo e hoje), dias_com_gravacao, total_dias e status_gravacao.
    Dia com algum tempo gravado conta como gravado; abaixo de `limiar` do dia (hoje: do tempo ja decorrido) e parcial."""
    agora = agora or datetime.now()
    inicio_hoje = datetime.combine(hoje, datetime.min.time())
    decorrido_hoje = max((agora - inicio_hoje).total_seconds(), 1.0)
    lista = [hoje - timedelta(days=dias - 1 - i) for i in range(dias)]
    com_gravacao = [d for d in lista if por_dia.get(d, 0) > 0]
    primeiro_dia = min(com_gravacao) if com_gravacao else None

    mapa = []
    for d in lista:
        segundos = por_dia.get(d, 0.0)
        esperado = decorrido_hoje if d == hoje else 86400.0
        if segundos <= 0:
            mapa.append(MAPA_SEM_HISTORICO if primeiro_dia and d < primeiro_dia else MAPA_SEM_GRAVACAO)
        elif segundos >= limiar * esperado:
            mapa.append(MAPA_GRAVOU)
        else:
            mapa.append(MAPA_PARCIAL)
    return {
        "mapa": "".join(mapa),
        "dias_com_gravacao": [d.strftime("%Y-%m-%d") for d in com_gravacao],
        "total_dias": len(com_gravacao),
        "status_gravacao": "COM_GRAVACAO" if hoje in com_gravacao else "SEM_GRAVACAO",
        "segundos_hoje": round(por_dia.get(hoje, 0.0)),
    }


def _normalizar(texto):
    """Sem acento, pontuacao, espacos extras e diferenca de maiusculas ('Câmera 01' == 'camera_01')."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", str(texto or "")) if not unicodedata.combining(c))
    return normalizar_texto(sem_acento)


def casar_pasta(nome_camera, pastas):
    """Nome da pasta que corresponde a camera, ou None. Primeiro pelo nome normalizado; se nao houver,
    ignorando tambem os espacos ('One Drive - Trilan' = 'OneDrive - Trilan'), desde que so uma pasta combine."""
    alvo = _normalizar(nome_camera)
    if not alvo:
        return None
    for nome_pasta in pastas:
        if _normalizar(nome_pasta) == alvo:
            return nome_pasta
    compacto = alvo.replace(" ", "")
    parecidas = [p for p in pastas if _normalizar(p).replace(" ", "") == compacto]
    return parecidas[0] if len(parecidas) == 1 else None
