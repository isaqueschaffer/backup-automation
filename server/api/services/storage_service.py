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


def _get_client_dir_name(client_id: UUID, client_name: str) -> str:
    """Retorna o nome padronizado da pasta do cliente: NOME_CLIENTE_UUID."""
    return f"{_sanitize_name(client_name)}_{client_id}"


def get_backup_dir(client_id: UUID, client_name: str, date_str: str, device_type: str) -> Path:
    """Retorna (e cria) o diretório de armazenamento para o backup do cliente.

    Estrutura: BACKUP_STORAGE_PATH / NOME_CLIENTE_UUID / backup_DD-MM-YYYY / DEVICE_TYPE
    """
    clean_device_type = device_type.strip().upper()
    path = (
        Path(settings.BACKUP_STORAGE_PATH)
        / _get_client_dir_name(client_id, client_name)
        / f"backup_{date_str}"
        / clean_device_type
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_zip(
    client_id: UUID,
    client_name: str,
    date_str: str,
    device_type: str,
    filename: str,
    data: bytes,
) -> Path:
    """Salva um arquivo ZIP no diretório correspondente e retorna seu caminho."""
    target_dir = get_backup_dir(client_id, client_name, date_str, device_type)
    target = target_dir / filename
    target.write_bytes(data)
    return target


def get_zip_path(client_id: UUID, client_name: str, zip_filename: str, date_str: str = None) -> Path | None:
    """Encontra o arquivo ZIP armazenado para um dado cliente.

    Procura primeiramente na pasta específica da data (se fornecida).
    Depois, procura recursivamente dentro da pasta do cliente, com compatibilidade para estruturas legadas.
    """
    storage_base = Path(settings.BACKUP_STORAGE_PATH)
    clean_name = _sanitize_name(client_name)

    candidate_dirs = [
        storage_base / _get_client_dir_name(client_id, client_name),
        storage_base / f"{clean_name}_{client_id}",
        storage_base / f"{client_name}_{client_id}",
        storage_base / str(client_id),
    ]

    checked = set()
    
    # 1. Se tivermos a data, tentamos buscar diretamente na pasta da data
    if date_str:
        for base in candidate_dirs:
            if base.exists() and base.is_dir():
                date_dir = base / f"backup_{date_str}"
                if date_dir.exists() and date_dir.is_dir():
                    for candidate in date_dir.rglob(zip_filename):
                        if candidate.is_file():
                            return candidate

    # 2. Fallback: procura recursivamente (pode retornar backup de outra data se nomes colidirem)
    for base in candidate_dirs:
        if base.exists() and base.is_dir() and base not in checked:
            checked.add(base)
            for candidate in base.rglob(zip_filename):
                if candidate.is_file():
                    return candidate

    # 3. Fallback final: procura em qualquer pasta que contenha o UUID do cliente
    if storage_base.exists():
        for d in storage_base.iterdir():
            if d.is_dir() and str(client_id) in d.name and d not in checked:
                checked.add(d)
                for candidate in d.rglob(zip_filename):
                    if candidate.is_file():
                        return candidate

    return None


def delete_old_backups(client_id: UUID, client_name: str, keep_days: int) -> int:
    """Deleta os diretórios de data mais antigos que keep_days para o cliente.

    Apaga a pasta da data inteira (removendo NVR, OLT, ONU, PABX de uma só vez).
    Retorna a quantidade de pastas apagadas.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    storage_base = Path(settings.BACKUP_STORAGE_PATH)
    clean_name = _sanitize_name(client_name)

    candidate_dirs = [
        storage_base / _get_client_dir_name(client_id, client_name),
        storage_base / f"{clean_name}_{client_id}",
        storage_base / f"{client_name}_{client_id}",
        storage_base / str(client_id),
    ]

    deleted = 0
    checked = set()

    for base in candidate_dirs:
        if base.exists() and base.is_dir() and base not in checked:
            checked.add(base)
            for date_dir in base.iterdir():
                if date_dir.is_dir():
                    try:
                        # Converte a pasta da data (ex: "backup_17-09-2026") para comparação
                        date_str = date_dir.name.replace("backup_", "")
                        dt = datetime.strptime(date_str, "%d-%m-%Y").replace(
                            tzinfo=timezone.utc
                        )
                        if dt < cutoff:
                            shutil.rmtree(date_dir)  # Apaga a pasta da data inteira
                            deleted += 1
                    except ValueError:
                        pass
    return deleted