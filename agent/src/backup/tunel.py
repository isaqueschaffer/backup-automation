"""
Backup em TÚNEL (agente do Mikrotik): lê o backup do cliente por SMB e já o envia ao servidor, sem gravar nada no
roteador (nem arquivo temporário). O Mikrotik só empurra os bytes:

    pasta de rede do cliente --SMB--> [montador do ZIP em memória] --fila de poucos MB--> PUT em pedaços --> servidor

- O ZIP global (com a senha da máquina) e o ZIP de cada equipamento são montados em fluxo: o destino só aceita
  `write()` (zipfile grava "data descriptors" quando não dá para voltar atrás). Estrutura idêntica à do agente
  Windows: `<TIPO>/backup_<tipo>_<nome>/backup.zip`.
- A fila é pequena e bloqueia quem escreve quando o envio está lento: a memória fica em poucos MB, não importa o
  tamanho do backup.
- Compressão desligada por padrão (os backups já são ZIP/TAR comprimidos e a CPU do roteador é pouca);
  `TRILAN_TUNEL_COMPRESSAO=deflate` liga.
- A verificação é pelo tamanho lido contra o tamanho do arquivo no cliente (não existe cópia local para conferir o
  hash). Se divergir, o envio é abortado: o servidor descarta o que chegou e o equipamento vira CORROMPIDO.
"""
import logging
import os
import queue
import threading
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import pyzipper

BLOCO = 1024 * 1024          # leitura do SMB
LOTE = 256 * 1024            # tamanho do pedaço que entra na fila
FILA_PEDACOS = 8             # ~2 MB parados na fila (mais o que o zipfile segura)
TENTATIVAS_ENVIO = 2
PASTA_NENHUMA = Path(os.devnull)   # a preparação não grava nada; o caminho só é exigido pela assinatura


class _Abortado(Exception):
    """Quem consome (o envio) desistiu; o montador para de escrever."""


class _Divergente(Exception):
    """Arquivo lido com tamanho diferente do que o cliente informa: backup não confiável."""
    def __init__(self, item, detalhe):
        super().__init__(detalhe)
        self.item = item


class _FalhaLeitura(Exception):
    def __init__(self, item, detalhe):
        super().__init__(detalhe)
        self.item = item


class FilaSaida:
    """Destino só-escrita do ZIP (o que o zipfile enxerga como arquivo) e, do outro lado, o iterador de bytes
    que alimenta o corpo do PUT. Bloqueia quem escreve quando a fila enche (contrapressão)."""

    def __init__(self):
        self._fila: "queue.Queue" = queue.Queue(maxsize=FILA_PEDACOS)
        self._lote = bytearray()
        self._abortado = threading.Event()
        self.total = 0

    # --- lado do montador (thread produtora) ---
    def write(self, dados) -> int:
        n = len(dados)
        if self._abortado.is_set():
            return n                # envio desistiu: descarta em silêncio (o zipfile fecha sem erro; a leitura para)
        self._lote += dados
        self.total += n
        while len(self._lote) >= LOTE:
            self._colocar(bytes(self._lote[:LOTE]))
            del self._lote[:LOTE]
        return n

    def flush(self) -> None:
        pass

    def encerrar(self, erro: Optional[BaseException] = None) -> None:
        """Fim do fluxo: manda o resto e o sinal de término (ou o erro, que derruba o envio)."""
        if erro is None and self._lote:
            self._colocar(bytes(self._lote))
        self._lote.clear()
        self._colocar(erro if erro is not None else None)

    def _colocar(self, item) -> None:
        while not self._abortado.is_set():
            try:
                self._fila.put(item, timeout=1)
                return
            except queue.Full:
                continue
        # abortado: ninguém mais consome, o pedaço é descartado

    # --- lado do envio (thread principal) ---
    def abortar(self) -> None:
        self._abortado.set()

    def abortado(self) -> bool:
        return self._abortado.is_set()

    def pedacos(self):
        while True:
            item = self._fila.get()
            if item is None:
                return
            if isinstance(item, BaseException):
                raise item          # a conexão cai no meio: o servidor descarta o que recebeu
            yield item


def _smbclient():
    from src.backup import smb_storage
    if smb_storage.smbclient is None:
        raise RuntimeError("biblioteca de SMB (smbprotocol) indisponível neste agente")
    return smb_storage.smbclient


def _tipo_compressao() -> int:
    return zipfile.ZIP_DEFLATED if os.environ.get("TRILAN_TUNEL_COMPRESSAO", "").strip().lower() in (
        "deflate", "deflated", "1", "true") else zipfile.ZIP_STORED


def _copiar_arquivo(smb, zf_interno: zipfile.ZipFile, remoto: str, nome_no_zip: str, item: str, parar=None) -> int:
    try:
        esperado = smb.stat(remoto).st_size
        lidos = 0
        with smb.open_file(remoto, mode="rb") as origem:
            with zf_interno.open(nome_no_zip, "w", force_zip64=True) as destino:
                while True:
                    if parar is not None and parar():
                        raise _Abortado()
                    bloco = origem.read(BLOCO)
                    if not bloco:
                        break
                    destino.write(bloco)
                    lidos += len(bloco)
    except (_Abortado, _Divergente):
        raise
    except Exception as e:
        raise _FalhaLeitura(item, f"falha ao ler {remoto}: {e}") from e
    if lidos != esperado:
        raise _Divergente(item, f"{remoto}: leu {lidos} bytes, o cliente informa {esperado}")
    return lidos


def _copiar_pasta(smb, zf_interno: zipfile.ZipFile, remoto: str, prefixo: str, item: str, parar=None) -> int:
    total = 0
    try:
        entradas = list(smb.scandir(remoto))
    except Exception as e:
        raise _FalhaLeitura(item, f"falha ao listar {remoto}: {e}") from e
    for entrada in entradas:
        sub_remoto = remoto.rstrip("\\") + "\\" + entrada.name
        sub_zip = f"{prefixo}/{entrada.name}"
        if entrada.is_dir():
            total += _copiar_pasta(smb, zf_interno, sub_remoto, sub_zip, item, parar)
        else:
            total += _copiar_arquivo(smb, zf_interno, sub_remoto, sub_zip, item, parar)
    return total


def _copiar_arquivo_local(zf_interno: zipfile.ZipFile, local: Path, nome_no_zip: str, item: str, parar=None) -> int:
    """Lê um arquivo local (ex.: download de NVR) direto para o ZIP interno."""
    try:
        esperado = local.stat().st_size
        lidos = 0
        with open(local, "rb") as origem:
            with zf_interno.open(nome_no_zip, "w", force_zip64=True) as destino:
                while True:
                    if parar is not None and parar():
                        raise _Abortado()
                    bloco = origem.read(BLOCO)
                    if not bloco:
                        break
                    destino.write(bloco)
                    lidos += len(bloco)
    except (_Abortado, _Divergente):
        raise
    except Exception as e:
        raise _FalhaLeitura(item, f"falha ao ler {local}: {e}") from e
    if lidos != esperado:
        raise _Divergente(item, f"{local}: leu {lidos} bytes, esperava {esperado}")
    return lidos


def montar_zip(saida, prontos: List[dict], senha: Optional[str]) -> None:
    """Escreve em `saida` (só `write`) o ZIP global com um `backup.zip` por equipamento. `prontos` = resultados da
    preparação (`nome`, `tipo`, `pasta_zip`, `arquivos_origem` = [(BackupFile, nome_no_zip)])."""
    comp = _tipo_compressao()
    parar = getattr(saida, "abortado", None)
    if senha:
        ext = pyzipper.AESZipFile(saida, "w", compression=comp, encryption=pyzipper.WZ_AES)
        ext.setpassword(senha.encode())
    else:
        ext = zipfile.ZipFile(saida, "w", compression=comp)
    with ext:
        smb = None   # carrega só na primeira necessidade de SMB
        for res in prontos:
            nome = res["nome"]
            with ext.open(f"{res['pasta_zip']}/backup.zip", "w", force_zip64=True) as dentro:
                with zipfile.ZipFile(dentro, "w", compression=comp) as interno:
                    for origem, nome_no_zip in res["arquivos_origem"]:
                        remoto = origem.remote_path or str(origem.path)
                        if not origem.is_smb:
                            _copiar_arquivo_local(interno, origem.path, nome_no_zip, nome, parar)
                        else:
                            if smb is None:
                                smb = _smbclient()
                            if origem.file_type == "DIGIFORT_DIR":
                                _copiar_pasta(smb, interno, remoto, nome_no_zip, nome, parar)
                            else:
                                _copiar_arquivo(smb, interno, remoto, nome_no_zip, nome, parar)
            logging.info(f"  [TUNEL] {nome}: enviado ao fluxo")


def _produtor(fila: FilaSaida, prontos: List[dict], senha: Optional[str], falha: dict) -> None:
    try:
        montar_zip(fila, prontos, senha)
    except _Abortado:
        return
    except BaseException as e:      # leitura, tamanho ou qualquer outro erro derruba o envio: nunca sai ZIP incompleto
        if fila.abortado():
            return              # o envio já tinha desistido; o que sobrou aqui é só consequência
        falha["erro"] = e
        fila.encerrar(e)
        return
    fila.encerrar()


def enviar_em_tunel(conf: dict, backup_id: str, nome_zip: str, prontos: List[dict],
                    senha: Optional[str]) -> Tuple[bool, Optional[BaseException]]:
    """Monta e envia o ZIP de uma vez. Devolve (ok, erro_do_montador). `erro_do_montador` é preenchido quando foi a
    leitura do cliente que falhou (e não a rede/servidor): aí o equipamento culpado pode ser excluído e tentado de novo."""
    from src.application.api_client import upload_zip_stream
    fila = FilaSaida()
    falha: dict = {}
    thread = threading.Thread(target=_produtor, args=(fila, prontos, senha, falha), daemon=True, name="tunel-zip")
    thread.start()
    try:
        ok = upload_zip_stream(conf, backup_id, nome_zip, fila.pedacos())
    finally:
        fila.abortar()
        thread.join(timeout=30)
    if ok:
        logging.info(f"  [TUNEL] {fila.total / (1024 * 1024):.1f} MB enviados, nada gravado no agente")
    return ok, falha.get("erro")


def _status_da_falha(erro: BaseException) -> str:
    return "CORROMPIDO" if isinstance(erro, _Divergente) else "ERRO"


def _preparar_nvr_tunel(eq: dict) -> dict:
    """Baixa a config do NVR diretamente do device (HTTP) para arquivo temporário no agente."""
    from src.backup.file_manager.models import BackupFile
    from src.core.config import DIR_AGENT, parse_config_extra

    nome = eq.get("name", "NVR")
    ip = eq.get("ip", "")
    user = eq.get("username", "admin")
    pwd = eq.get("password", "")
    config_extra = parse_config_extra(eq)
    marca = (config_extra.get("marca") or "").upper()

    if not ip:
        return {"nome": nome, "status": "ERRO", "cameras": None}

    if marca != "INTELBRAS":
        logging.warning(f"  [NVR] {nome}: marca '{marca or 'desconhecida'}' não suportada no túnel (somente Intelbras).")
        return {"nome": nome, "status": "TIPO_NAO_SUPORTADO", "cameras": None}

    from src.nvr.intelbras.backup import baixar_configuracao_intelbras

    pasta_tmp = DIR_AGENT / "data" / "tmp_nvr"
    pasta_tmp.mkdir(parents=True, exist_ok=True)
    data_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    # nome_seguro importado lazily via backup_job abaixo no preparar_equipamentos
    import re as _re
    nome_safe = _re.sub(r"[^\w.-]", "_", nome)
    arquivo = pasta_tmp / f"CONFIG_INTELBRAS_{nome_safe}_{data_str}.backup"

    ok = baixar_configuracao_intelbras(ip, user, pwd, arquivo)
    if not ok or not arquivo.exists():
        return {"nome": nome, "status": "ERRO", "cameras": None}

    bf = BackupFile(path=arquivo, file_type="NVR_CONFIG", is_smb=False)
    logging.info(f"  [NVR] {nome}: config baixada ({arquivo.stat().st_size:,} bytes)")
    return {
        "nome": nome,
        "status": "PRONTO",
        "arquivos_origem": [(bf, arquivo.name)],
        "_tmp_files": [arquivo],
        "cameras": None,
    }


def _preparar_defense_tunel(eq: dict) -> dict:
    """Provisiona acesso SSH→SMB na máquina Windows e acha o arquivo de backup mais recente do Defense IA."""
    from src.backup.file_manager.models import BackupFile
    from src.backup.smb_ssh_provisioner import alvo_por_ssh, usa_provisionamento_ssh
    from src.core.config import parse_config_extra
    from pathlib import Path as _Path

    nome = eq.get("name", "Defense")
    config_extra = parse_config_extra(eq)
    pasta_origem = config_extra.get("pasta_origem", "")
    host = config_extra.get("smb_host") or eq.get("ip", "")

    if not pasta_origem:
        logging.warning(f"  [DEFENSE] {nome}: pasta_origem não configurada (necessário no túnel).")
        return {"nome": nome, "status": "TIPO_NAO_SUPORTADO", "cameras": None}

    if not usa_provisionamento_ssh(config_extra):
        logging.warning(f"  [DEFENSE] {nome}: acesso SSH não configurado (necessário no túnel do MikroTik).")
        return {"nome": nome, "status": "TIPO_NAO_SUPORTADO", "cameras": None}

    alvo, msg = alvo_por_ssh(pasta_origem, host, config_extra)
    if not alvo:
        logging.warning(f"  [DEFENSE] {nome}: falha ao obter acesso SMB: {msg}")
        return {"nome": nome, "status": "ERRO", "cameras": None}

    try:
        smb = _smbclient()
        smb.register_session(server=alvo.host, username=alvo.username, password=alvo.password, port=alvo.port)

        EXTS_BACKUP = {".enc", ".zip", ".dbk", ".bak"}
        arquivos = [
            e for e in smb.scandir(alvo.unc_path)
            if not e.is_dir() and _Path(e.name).suffix.lower() in EXTS_BACKUP
        ]
        if not arquivos:
            logging.warning(f"  [DEFENSE] {nome}: nenhum arquivo de backup em {alvo.unc_path}")
            return {"nome": nome, "status": "SEM_ARQUIVOS", "cameras": None}

        mais_recente = max(arquivos, key=lambda e: e.stat().st_mtime)
        unc_arquivo = alvo.unc_path.rstrip("\\") + "\\" + mais_recente.name
        bf = BackupFile(path=_Path(unc_arquivo), file_type="DEFENSE_BACKUP",
                        remote_path=unc_arquivo, is_smb=True)
        logging.info(f"  [DEFENSE] {nome}: arquivo encontrado — {mais_recente.name}")
        return {
            "nome": nome,
            "status": "PRONTO",
            "arquivos_origem": [(bf, mais_recente.name)],
            "cameras": None,
        }
    except Exception as e:
        logging.error(f"  [DEFENSE] {nome}: falha ao acessar backup via SMB: {e}", exc_info=True)
        return {"nome": nome, "status": "ERRO", "cameras": None}


def preparar_equipamentos(equipamentos: list, conf: dict, trigger: str) -> List[dict]:
    """Fase 1 (sem gravar nada): acha o backup mais recente de cada equipamento na pasta de rede do cliente e valida
    (data, completude, estabilidade). Quem está pronto volta com status "PRONTO"."""
    from src.application import log_remoto
    from src.application.backup_job import LIMITE_EQUIPAMENTO_S, _executar_com_limite, nome_seguro, processar_olt

    resultados = []
    for eq in equipamentos:
        tipo = (eq.get("tipo") or "NVR").upper()
        nome = eq.get("name", "equipamento")
        try:
            if tipo in ("OLT", "DIGIFORT"):
                with log_remoto.equipamento_atual(nome):
                    res = _executar_com_limite(processar_olt, LIMITE_EQUIPAMENTO_S, eq, PASTA_NENHUMA, conf, trigger,
                                               somente_preparar=True)
            elif tipo == "NVR":
                res = _preparar_nvr_tunel(eq)
            elif tipo == "DEFENSE":
                res = _preparar_defense_tunel(eq)
            else:
                logging.warning(f"  Tipo '{tipo}' ({nome}) grava arquivos em disco: fora do túnel do Mikrotik "
                                f"(o backup dele fica com um agente Windows).")
                res = {"nome": nome, "status": "TIPO_NAO_SUPORTADO", "cameras": None}
        except Exception:
            logging.error(f"  Falha inesperada ao preparar o backup de {nome}. Seguindo para o próximo.",
                          exc_info=True, extra={"equipamento": nome})
            res = {"nome": nome, "status": "ERRO", "cameras": None}
        res["tipo"] = tipo
        res["pasta_zip"] = f"{tipo}/backup_{tipo.lower()}_{nome_seguro(nome)}"
        resultados.append(res)
    return resultados


def executar_backup_tunel(trigger: str = "scheduled") -> None:
    """Backup completo em túnel: prepara, reporta, envia em fluxo e corrige o que falhou no caminho."""
    from src.core.config import load_conf
    from src.application.api_client import corrigir_resultado, fetch_server_config, post_report
    from src.application.backup_job import nome_seguro
    from src.backup.archiver import data_hoje

    logging.info(f"\n{'=' * 60}\nINICIANDO BACKUP EM TÚNEL — {trigger.upper()}\n{'=' * 60}")
    conf = load_conf()
    try:
        server_cfg = fetch_server_config(conf)
    except Exception as e:
        logging.error(f"Falha ao buscar config: {e}")
        return

    equipamentos = server_cfg.get("equipamentos") or server_cfg.get("nvrs") or []
    equipamentos = [eq for eq in equipamentos if str(eq.get("tipo")).upper() not in ("CAMERA", "ANTENA")]
    senha = server_cfg.get("zip_password")
    if not senha:
        logging.warning("AVISO DE SEGURANCA: zip_password nao configurado no servidor para este cliente. O ZIP sera criado sem senha.")
    client_name = server_cfg["client_name"]
    logging.info(f"Cliente      : {client_name}")
    logging.info(f"Equipamentos : {len(equipamentos)}")

    started_at = datetime.utcnow()
    resultados = preparar_equipamentos(equipamentos, conf, trigger)
    # Coleta arquivos temporários (ex.: downloads de NVR) para limpar após o envio
    tmp_files: List[Path] = [f for r in resultados for f in r.pop("_tmp_files", [])]
    prontos = [r for r in resultados if r["status"] == "PRONTO"]
    for r in prontos:
        r["status"] = "OK"          # provisório: o relatório sai antes do envio; corrigido abaixo se algo falhar

    finished_at = datetime.utcnow()
    for r in resultados:
        logging.info(f"  {r['status']} [{r['tipo']}] {r['nome']}", extra={"equipamento": r["nome"]})
    backup_id = post_report(conf, started_at, finished_at, resultados, trigger)
    if not backup_id:
        logging.error("Relatório não enviado: nada será transmitido.")
        return

    pendentes = list(prontos)
    nome_zip = f"backup_{nome_seguro(client_name)}_{data_hoje()}.zip"
    tentativas_rede = 0
    while pendentes:
        logging.info(f"  [TUNEL] Enviando {len(pendentes)} equipamento(s) em {nome_zip}")
        ok, erro_leitura = enviar_em_tunel(conf, backup_id, nome_zip, pendentes, senha)
        if ok:
            break
        if erro_leitura is not None and getattr(erro_leitura, "item", None):
            culpado = erro_leitura.item
            status = _status_da_falha(erro_leitura)
            logging.error(f"  [TUNEL] {culpado}: {erro_leitura}", extra={"equipamento": culpado})
            corrigir_resultado(conf, backup_id, culpado, status)
            for r in resultados:
                if r["nome"] == culpado:
                    r["status"] = status
            pendentes = [r for r in pendentes if r["nome"] != culpado]
            continue                # refaz o ZIP sem o equipamento que falhou (o servidor já descartou o parcial)
        tentativas_rede += 1
        if tentativas_rede >= TENTATIVAS_ENVIO:
            logging.error("  [TUNEL] Envio ao servidor falhou; backups não entregues.")
            for r in pendentes:
                corrigir_resultado(conf, backup_id, r["nome"], "ERRO")
                r["status"] = "ERRO"
            break
        logging.warning("  [TUNEL] Envio falhou; tentando de novo.")

    for f in tmp_files:
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass

    logging.info(f"\nBackup em túnel concluído em {(datetime.utcnow() - started_at).total_seconds():.1f}s",
                 extra={"enviar_servidor": True})
