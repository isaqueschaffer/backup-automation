import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

from config import settings

SEM_CLIENTE_DIR = "_sem_cliente"


def _sanitize_name(name: str) -> str:
    """Sanitiza o nome removendo caracteres inválidos para sistema de arquivos."""
    clean = re.sub(r'[\\/*?:"<>|]', "_", name.strip())
    clean = re.sub(r"\s+", "_", clean)
    return clean or "cliente"


def _get_machine_dir_name(machine_id: UUID, machine_name: str) -> str:
    """Retorna o nome padronizado da pasta da máquina: NOME_MAQUINA_UUID."""
    return f"{_sanitize_name(machine_name)}_{machine_id}"


def _dir_por_uuid(pai: Path, uid) -> Path | None:
    """Subpasta de `pai` cujo nome termina com _<uuid> (sobrevive a renomear Cliente/Máquina)."""
    sufixo = f"_{uid}"
    if not pai.is_dir():
        return None
    for entrada in pai.iterdir():
        if entrada.is_dir() and entrada.name.endswith(sufixo):
            return entrada
    return None


def _pasta_do_cliente(customer) -> Path:
    """Retorna a pasta do cliente ou a pasta padronizada _sem_cliente."""
    base = Path(settings.BACKUP_STORAGE_PATH)
    if customer is None:
        return base / SEM_CLIENTE_DIR
    return _dir_por_uuid(base, customer.id) or base / f"{_sanitize_name(customer.name)}_{customer.id}"


def pasta_canonica_da_maquina(machine_id: UUID, machine_name: str, customer=None) -> Path:
    """Pasta ideal da máquina: <CLIENTE>_<uuid>/<MAQUINA>_<uuid> (ou _sem_cliente/<MAQUINA>_<uuid>). Não cria."""
    cliente_dir = _pasta_do_cliente(customer)
    return _dir_por_uuid(cliente_dir, machine_id) or cliente_dir / _get_machine_dir_name(machine_id, machine_name)


def pastas_da_maquina(machine_id: UUID, machine_name: str, customer=None) -> list[Path]:
    """Todas as pastas existentes da máquina, a canônica primeiro (raiz legada, outro Cliente, _sem_cliente...)."""
    base = Path(settings.BACKUP_STORAGE_PATH)
    achadas: list[Path] = []

    def _add(p):
        if p is not None and p.is_dir() and p not in achadas:
            achadas.append(p)

    _add(pasta_canonica_da_maquina(machine_id, machine_name, customer))
    clean_name = _sanitize_name(machine_name)
    for legado in (
        base / _get_machine_dir_name(machine_id, machine_name),
        base / f"{clean_name}_{machine_id}",
        base / f"{machine_name}_{machine_id}",
        base / str(machine_id),
    ):
        _add(legado)
    _add(_dir_por_uuid(base, machine_id))
    if base.is_dir():
        for sub in base.iterdir():
            if sub.is_dir() and sub.name != "lixeira":
                _add(_dir_por_uuid(sub, machine_id))
    return achadas


def get_backup_dir(
    machine_id: UUID,
    machine_name: str,
    date_str: str,
    device_type: str,
    customer=None,
) -> Path:
    """Retorna (e cria se necessário) o diretório de armazenamento para o backup da máquina.

    Estrutura nova: BACKUP_STORAGE_PATH / <CLIENTE>_<UUID> / <MAQUINA>_<UUID>
    Sem cliente: BACKUP_STORAGE_PATH / _sem_cliente / <MAQUINA>_<UUID>
    Se a máquina já possui pasta existente (ex.: raiz legada), reutiliza para não duplicar.
    """
    canonica = pasta_canonica_da_maquina(machine_id, machine_name, customer)
    if canonica.is_dir():
        return canonica
    existentes = pastas_da_maquina(machine_id, machine_name, customer)
    if existentes:
        return existentes[0]
    canonica.mkdir(parents=True, exist_ok=True)
    return canonica


class UploadTooLargeError(Exception):
    """Upload excedeu o limite de tamanho configurado."""


def sanitize_zip_filename(filename: str | None, fallback: str) -> str:
    """Reduz um nome de arquivo vindo de fora a um nome simples e seguro (sem diretórios)."""
    raw = (filename or "").replace("\\", "/")
    base = Path(raw).name
    clean = _sanitize_name(base) if base else ""
    if clean in ("", ".", "..", "cliente"):
        clean = _sanitize_name(fallback)
    return clean


def _is_safe_lookup_name(name: str) -> bool:
    """Nome de busca válido: sem separadores de caminho nem metacaracteres de glob."""
    if not name or name in (".", ".."):
        return False
    return not any(ch in name for ch in ("/", "\\", "*", "?", "[", "]", chr(0)))


def _resolve_zip_target(
    machine_id: UUID,
    machine_name: str,
    date_str: str,
    device_type: str,
    filename: str,
    customer=None,
) -> Path:
    """Calcula o caminho final do ZIP garantindo que fica dentro do diretório da máquina."""
    target_dir = get_backup_dir(machine_id, machine_name, date_str, device_type, customer=customer)
    safe_name = sanitize_zip_filename(filename, fallback="backup.zip")
    target = (target_dir / safe_name).resolve()
    if target.parent != target_dir.resolve():
        raise ValueError("Nome de arquivo inválido")
    return target


def save_zip(
    machine_id: UUID,
    machine_name: str,
    date_str: str,
    device_type: str,
    filename: str,
    data: bytes,
    customer=None,
) -> Path:
    """Salva um arquivo ZIP no diretório correspondente e retorna seu caminho."""
    target = _resolve_zip_target(machine_id, machine_name, date_str, device_type, filename, customer=customer)
    target.write_bytes(data)
    return target


def save_zip_stream(
    machine_id: UUID,
    machine_name: str,
    date_str: str,
    device_type: str,
    filename: str,
    source,
    max_bytes: int,
    chunk_size: int = 1024 * 1024,
    customer=None,
) -> tuple[Path, int]:
    """Grava o ZIP em streaming (chunks) a partir de um file-like, sem carregar tudo em memória.

    Escreve em arquivo temporário e só substitui o destino ao concluir; se passar de
    `max_bytes` levanta UploadTooLargeError e remove o temporário.
    Retorna (caminho_final, tamanho_em_bytes).
    """
    target = _resolve_zip_target(machine_id, machine_name, date_str, device_type, filename, customer=customer)
    tmp = target.with_name(target.name + ".part")
    total = 0
    try:
        with open(tmp, "wb") as out:
            while True:
                chunk = source.read(chunk_size)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise UploadTooLargeError()
                out.write(chunk)
        tmp.replace(target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return target, total


def get_zip_path(
    machine_id: UUID,
    machine_name: str,
    zip_filename: str,
    date_str: str = None,
    customer=None,
) -> Path | None:
    """Encontra o arquivo ZIP armazenado para uma dada máquina.

    Procura primeiramente na pasta específica da data (se fornecida).
    Depois, procura recursivamente dentro da pasta da máquina, com compatibilidade para estruturas legadas.
    """
    # Nome vindo de fora: rejeita separadores e metacaracteres de glob (path traversal)
    if not _is_safe_lookup_name(zip_filename):
        return None

    storage_base = Path(settings.BACKUP_STORAGE_PATH)
    candidate_dirs = pastas_da_maquina(machine_id, machine_name, customer)

    def _find_by_name(root: Path) -> Path | None:
        # Compara por igualdade de nome (sem usar o nome como padrão de glob)
        for candidate in root.rglob("*"):
            if candidate.name == zip_filename and candidate.is_file():
                return candidate
        return None

    checked = set()

    # 1. Busca arquivo direto na raiz da máquina (nova estrutura)
    for base in candidate_dirs:
        if base.exists() and base.is_dir():
            target = base / zip_filename
            if target.exists() and target.is_file():
                return target

    # 2. Se tivermos a data, tentamos buscar na estrutura antiga (pasta da data)
    if date_str:
        for base in candidate_dirs:
            if base.exists() and base.is_dir():
                date_dir = base / f"backup_{date_str}"
                if date_dir.exists() and date_dir.is_dir():
                    found = _find_by_name(date_dir)
                    if found:
                        return found

    # 3. Fallback: procura recursivamente nas pastas candidatas
    for base in candidate_dirs:
        if base.exists() and base.is_dir() and base not in checked:
            checked.add(base)
            found = _find_by_name(base)
            if found:
                return found

    # 4. Fallback final: procura em qualquer pasta que contenha o UUID da máquina
    if storage_base.exists():
        for d in storage_base.iterdir():
            if not d.is_dir() or d.name == "lixeira":
                continue
            if str(machine_id) in d.name and d not in checked:
                checked.add(d)
                found = _find_by_name(d)
                if found:
                    return found
            # Subpastas de clientes
            for sub in d.iterdir():
                if sub.is_dir() and str(machine_id) in sub.name and sub not in checked:
                    checked.add(sub)
                    found = _find_by_name(sub)
                    if found:
                        return found

    return None


def delete_old_backups(machine_id: UUID, machine_name: str, keep_days: int) -> int:
    """Deleta os arquivos de backup mais antigos que keep_days para a máquina.

    Retorna a quantidade de arquivos apagados.
    """
    cutoff = datetime.utcnow() - timedelta(days=keep_days)
    candidate_dirs = pastas_da_maquina(machine_id, machine_name)

    deleted = 0
    checked = set()

    for base in candidate_dirs:
        if base.exists() and base.is_dir() and base not in checked:
            checked.add(base)
            for file_zip in base.glob("backup_*.zip"):
                try:
                    date_str = file_zip.name.replace("backup_", "").replace(".zip", "")
                    dt = datetime.strptime(date_str, "%d-%m-%Y")
                    if dt < cutoff:
                        file_zip.unlink()
                        deleted += 1
                except ValueError:
                    pass
    return deleted


def move_machine_to_trash(machine_id: UUID, machine_name: str) -> bool:
    """Move as pastas de backups da máquina para a lixeira."""
    storage_base = Path(settings.BACKUP_STORAGE_PATH)
    dirs = pastas_da_maquina(machine_id, machine_name)
    if not dirs:
        return False

    trash_base = storage_base / "lixeira"
    trash_base.mkdir(parents=True, exist_ok=True)
    moved_any = False

    for idx, machine_dir in enumerate(dirs):
        if not (machine_dir.exists() and machine_dir.is_dir()):
            continue
        target_dir = trash_base / machine_dir.name
        if target_dir.exists() or idx > 0:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            target_dir = trash_base / f"{machine_dir.name}_{timestamp}"
            c = 1
            while target_dir.exists():
                target_dir = trash_base / f"{machine_dir.name}_{timestamp}_{c}"
                c += 1

        shutil.move(str(machine_dir), str(target_dir))
        moved_any = True

    return moved_any


def _mesclar_pastas(origem: Path, destino: Path, conflitos: list[str]) -> None:
    """Move arquivos e subpastas de origem para destino sem sobrescrever.

    Apaga origem se ficar vazia.
    """
    destino.mkdir(parents=True, exist_ok=True)
    for entrada in list(origem.iterdir()):
        alvo = destino / entrada.name
        if alvo.exists():
            if entrada.is_dir() and alvo.is_dir():
                _mesclar_pastas(entrada, alvo, conflitos)
            else:
                conflitos.append(entrada.name)
        else:
            shutil.move(str(entrada), str(alvo))
    try:
        origem.rmdir()
    except OSError:
        pass


def reorganizar_maquina(
    machine_id: UUID,
    machine_name: str,
    customer=None,
    aplicar: bool = True,
) -> dict:
    """Reorganiza os diretórios de armazenamento da máquina para a pasta canônica."""
    try:
        dirs = pastas_da_maquina(machine_id, machine_name, customer)
        canonica = pasta_canonica_da_maquina(machine_id, machine_name, customer)

        if not dirs:
            return {
                "acao": "sem_pasta",
                "origem": None,
                "destino": str(canonica),
                "conflitos": [],
            }

        if dirs == [canonica]:
            return {
                "acao": "ja_ok",
                "origem": str(canonica),
                "destino": str(canonica),
                "conflitos": [],
            }

        canonica_res = canonica.resolve()
        for d in dirs:
            d_res = d.resolve()
            if d_res != canonica_res and (canonica_res in d_res.parents or d_res in canonica_res.parents):
                return {"acao": "ignorado", "motivo": "pastas aninhadas"}

        conflitos: list[str] = []

        if canonica not in dirs:
            origem = dirs[0]
            if not aplicar:
                return {
                    "acao": "mover",
                    "origem": str(origem),
                    "destino": str(canonica),
                    "conflitos": [],
                }
            canonica.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(origem), str(canonica))
            for extra in dirs[1:]:
                if extra.exists() and extra.is_dir():
                    _mesclar_pastas(extra, canonica, conflitos)
            return {
                "acao": "mover",
                "origem": str(origem),
                "destino": str(canonica),
                "conflitos": conflitos,
            }
        else:
            outras = [d for d in dirs if d.resolve() != canonica_res]
            origem = outras[0] if outras else None
            if not aplicar:
                return {
                    "acao": "unir",
                    "origem": str(origem) if origem else None,
                    "destino": str(canonica),
                    "conflitos": [],
                }
            for extra in outras:
                if extra.exists() and extra.is_dir():
                    _mesclar_pastas(extra, canonica, conflitos)
            return {
                "acao": "unir",
                "origem": str(origem) if origem else None,
                "destino": str(canonica),
                "conflitos": conflitos,
            }
    except Exception as e:
        return {"acao": "erro", "motivo": str(e)}


def renomear_pasta_do_cliente(customer_id: UUID, novo_nome: str) -> bool:
    """Renomeia a pasta do cliente se o nome sanitizado for diferente do atual.

    Não sobrescreve se o destino já existir.
    """
    base = Path(settings.BACKUP_STORAGE_PATH)
    atual = _dir_por_uuid(base, customer_id)
    if not atual or not atual.is_dir():
        return False
    esperado_nome = f"{_sanitize_name(novo_nome)}_{customer_id}"
    if atual.name == esperado_nome:
        return False
    destino = base / esperado_nome
    if destino.exists():
        return False
    try:
        shutil.move(str(atual), str(destino))
        return True
    except Exception:
        return False


def remover_pasta_vazia_do_cliente(customer_id: UUID) -> bool:
    """Apaga a pasta do cliente (por UUID) somente se estiver totalmente vazia."""
    base = Path(settings.BACKUP_STORAGE_PATH)
    pasta = _dir_por_uuid(base, customer_id)
    if not pasta or not pasta.is_dir():
        return False
    try:
        if any(pasta.iterdir()):
            return False
        pasta.rmdir()
        return True
    except Exception:
        return False
