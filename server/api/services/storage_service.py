import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from config import settings


def _sanitize_name(name: str) -> str:
    """Sanitiza o nome removendo caracteres inválidos para sistema de arquivos."""
    clean = re.sub(r'[\\/*?:"<>|]', "_", name.strip())
    clean = re.sub(r"\s+", "_", clean)
    return clean or "cliente"


def _get_machine_dir_name(machine_id: UUID, machine_name: str) -> str:
    """Retorna o nome padronizado da pasta da máquina: NOME_MAQUINA_UUID."""
    return f"{_sanitize_name(machine_name)}_{machine_id}"


def get_backup_dir(machine_id: UUID, machine_name: str, date_str: str, device_type: str) -> Path:
    """Retorna (e cria) o diretório de armazenamento para o backup da máquina.

    Estrutura: BACKUP_STORAGE_PATH / NOME_MAQUINA_UUID / backup_DD-MM-YYYY / DEVICE_TYPE
    """
    path = (
        Path(settings.BACKUP_STORAGE_PATH)
        / _get_machine_dir_name(machine_id, machine_name)
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


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
    machine_id: UUID, machine_name: str, date_str: str, device_type: str, filename: str
) -> Path:
    """Calcula o caminho final do ZIP garantindo que fica dentro do diretório da máquina."""
    target_dir = get_backup_dir(machine_id, machine_name, date_str, device_type)
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
) -> Path:
    """Salva um arquivo ZIP no diretório correspondente e retorna seu caminho."""
    target = _resolve_zip_target(machine_id, machine_name, date_str, device_type, filename)
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
) -> tuple[Path, int]:
    """Grava o ZIP em streaming (chunks) a partir de um file-like, sem carregar tudo em memória.

    Escreve em arquivo temporário e só substitui o destino ao concluir; se passar de
    `max_bytes` levanta UploadTooLargeError e remove o temporário.
    Retorna (caminho_final, tamanho_em_bytes).
    """
    target = _resolve_zip_target(machine_id, machine_name, date_str, device_type, filename)
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


def get_zip_path(machine_id: UUID, machine_name: str, zip_filename: str, date_str: str = None) -> Path | None:
    """Encontra o arquivo ZIP armazenado para uma dada máquina.

    Procura primeiramente na pasta específica da data (se fornecida).
    Depois, procura recursivamente dentro da pasta da máquina, com compatibilidade para estruturas legadas.
    """
    # Nome vindo de fora: rejeita separadores e metacaracteres de glob (path traversal)
    if not _is_safe_lookup_name(zip_filename):
        return None

    storage_base = Path(settings.BACKUP_STORAGE_PATH)
    clean_name = _sanitize_name(machine_name)

    candidate_dirs = [
        storage_base / _get_machine_dir_name(machine_id, machine_name),
        storage_base / f"{clean_name}_{machine_id}",
        storage_base / f"{machine_name}_{machine_id}",
        storage_base / str(machine_id),
    ]

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

    # 2. Fallback: procura recursivamente (pode retornar backup de outra data se nomes colidirem)
    for base in candidate_dirs:
        if base.exists() and base.is_dir() and base not in checked:
            checked.add(base)
            found = _find_by_name(base)
            if found:
                return found

    # 3. Fallback final: procura em qualquer pasta que contenha o UUID da máquina
    if storage_base.exists():
        for d in storage_base.iterdir():
            if d.is_dir() and str(machine_id) in d.name and d not in checked:
                checked.add(d)
                found = _find_by_name(d)
                if found:
                    return found

    return None


def delete_old_backups(machine_id: UUID, machine_name: str, keep_days: int) -> int:
    """Deleta os diretórios de data mais antigos que keep_days para a máquina.

    Apaga a pasta da data inteira (removendo NVR, OLT, ONU, PABX de uma só vez).
    Retorna a quantidade de pastas apagadas.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    storage_base = Path(settings.BACKUP_STORAGE_PATH)
    clean_name = _sanitize_name(machine_name)

    candidate_dirs = [
        storage_base / _get_machine_dir_name(machine_id, machine_name),
        storage_base / f"{clean_name}_{machine_id}",
        storage_base / f"{machine_name}_{machine_id}",
        storage_base / str(machine_id),
    ]

    deleted = 0
    checked = set()

    for base in candidate_dirs:
        if base.exists() and base.is_dir() and base not in checked:
            checked.add(base)
            for file_zip in base.glob("backup_*.zip"):
                try:
                    date_str = file_zip.name.replace("backup_", "").replace(".zip", "")
                    dt = datetime.strptime(date_str, "%d-%m-%Y").replace(tzinfo=timezone.utc)
                    if dt < cutoff:
                        file_zip.unlink()
                        deleted += 1
                except ValueError:
                    pass
    return deleted


def move_machine_to_trash(machine_id: UUID, machine_name: str) -> bool:
    """Move a pasta de backups da máquina para a lixeira."""
    storage_base = Path(settings.BACKUP_STORAGE_PATH)
    machine_dir = storage_base / _get_machine_dir_name(machine_id, machine_name)
    
    if machine_dir.exists() and machine_dir.is_dir():
        trash_base = storage_base / "lixeira"
        trash_base.mkdir(parents=True, exist_ok=True)
        
        target_dir = trash_base / machine_dir.name
        
        if target_dir.exists():
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            target_dir = trash_base / f"{machine_dir.name}_{timestamp}"
            
        shutil.move(str(machine_dir), str(target_dir))
        return True
    return False