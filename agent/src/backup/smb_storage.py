"""
Módulo de integração SMB2/SMB3 para pastas compartilhadas remotas.
Permite acesso a shares Windows tanto a partir do Windows quanto de containers Linux/MikroTik.
"""
import hashlib
import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlsplit, unquote

from src.backup.file_manager.models import BackupStatus

try:
    import smbclient
    import smbprotocol.exceptions
    SMB_AVAILABLE = True
except ImportError:
    smbclient = None
    SMB_AVAILABLE = False


@dataclass
class SmbTarget:
    host: str
    share: str
    subpath: str
    unc_path: str
    username: Optional[str] = None
    password: Optional[str] = None
    port: int = 445


@dataclass
class SmbEntry:
    name: str
    unc_path: str
    is_dir: bool
    size: int = 0
    mtime: Optional[datetime] = None


def converter_para_unc(host: str, share: str, subpath: str = "") -> str:
    """Monta caminho UNC padrão \\host\\share\\subpath."""
    host_clean = host.strip().strip("\\/")
    share_clean = share.strip().strip("\\/")
    subpath_clean = subpath.replace("/", "\\").strip("\\")
    if subpath_clean:
        return f"\\\\{host_clean}\\{share_clean}\\{subpath_clean}"
    return f"\\\\{host_clean}\\{share_clean}"


def parse_smb_target(
    caminho: str,
    host: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    port: int = 445,
) -> SmbTarget:
    """
    Normaliza diferentes representações de caminhos de pasta para SmbTarget / UNC:
    - D:UNM2000/emsback, D:\\UNM2000\\emsback, D:/UNM2000/emsback (share D$)
    - host:D:UNM2000/emsback
    - \\\\host\\share\\subpath ou //host/share/subpath
    - smb://user:pass@host:port/share/subpath
    """
    c = (caminho or "").strip()
    if not c:
        raise ValueError("Caminho SMB vazio.")

    # 1. URI smb://
    if c.lower().startswith("smb://"):
        parsed = urlsplit(c)
        host_final = unquote(parsed.hostname) if parsed.hostname else host
        user_final = unquote(parsed.username) if parsed.username else user
        pass_final = unquote(parsed.password) if parsed.password else password
        port_final = parsed.port or port
        caminho_sem_barra = unquote(parsed.path).strip("/")
        if "/" in caminho_sem_barra:
            share, subpath = caminho_sem_barra.split("/", 1)
        else:
            share = caminho_sem_barra
            subpath = ""
        if not host_final:
            raise ValueError(f"Host não especificado na URI SMB: {c}")
        if not share:
            raise ValueError(f"Share não especificado na URI SMB: {c}")
        unc = converter_para_unc(host_final, share, subpath)
        return SmbTarget(
            host=host_final,
            share=share,
            subpath=subpath.replace("/", "\\"),
            unc_path=unc,
            username=user_final,
            password=pass_final,
            port=port_final,
        )

    # 2. Formato host:D:path ou host:D:\\path
    m_host_drive = re.match(r"^([^:]+):([a-zA-Z]):[\\/]*(.*)$", c)
    if m_host_drive:
        host_final = m_host_drive.group(1).strip()
        letra = m_host_drive.group(2).upper()
        share = f"{letra}$"
        subpath = m_host_drive.group(3).replace("/", "\\").strip("\\")
        unc = converter_para_unc(host_final, share, subpath)
        return SmbTarget(
            host=host_final,
            share=share,
            subpath=subpath,
            unc_path=unc,
            username=user,
            password=password,
            port=port,
        )

    # 3. Formato UNC padrão: \\\\host\\share\\subpath ou //host/share/subpath
    if c.startswith(("\\\\", "//")):
        c_norm = c.replace("/", "\\").lstrip("\\")
        partes = [p for p in c_norm.split("\\") if p]
        if len(partes) < 2:
            raise ValueError(f"Caminho UNC incompleto (esperado host e share): {c}")
        host_extraido = partes[0]
        share = partes[1]
        subpath = "\\".join(partes[2:]) if len(partes) > 2 else ""
        host_final = host or host_extraido
        unc = converter_para_unc(host_final, share, subpath)
        return SmbTarget(
            host=host_final,
            share=share,
            subpath=subpath,
            unc_path=unc,
            username=user,
            password=password,
            port=port,
        )

    # 4. Formato letra de drive simples: D:UNM2000/emsback, D:\\..., D:/...
    m_drive = re.match(r"^([a-zA-Z]):[\\/]*(.*)$", c)
    if m_drive:
        if not host:
            raise ValueError(f"Caminho '{c}' possui letra de unidade mas nenhum host/IP foi fornecido para conexão SMB.")
        letra = m_drive.group(1).upper()
        share = f"{letra}$"
        subpath = m_drive.group(2).replace("/", "\\").strip("\\")
        unc = converter_para_unc(host, share, subpath)
        return SmbTarget(
            host=host,
            share=share,
            subpath=subpath,
            unc_path=unc,
            username=user,
            password=password,
            port=port,
        )

    # 5. Outro formato relativo com host informado
    if host:
        partes = [p for p in c.replace("/", "\\").strip("\\").split("\\") if p]
        if partes:
            share = partes[0]
            subpath = "\\".join(partes[1:]) if len(partes) > 1 else ""
            unc = converter_para_unc(host, share, subpath)
            return SmbTarget(
                host=host,
                share=share,
                subpath=subpath,
                unc_path=unc,
                username=user,
                password=password,
                port=port,
            )

    raise ValueError(f"Não foi possível converter o caminho '{c}' em um destino SMB válido.")


def is_smb_path(caminho: str, config_extra: Optional[dict] = None, ip: Optional[str] = None) -> bool:
    """
    Determina se um caminho deve ser acessado via SMB:
    - Se começa com \\\\, // ou smb://
    - Se tem prefixo host:D:...
    - Se config_extra define smb_host
    - Se rodando em Linux/MikroTik e caminho tem letra de drive (D:, C:...) ou IP não-local configurado
    """
    if not caminho:
        return False
    c = str(caminho).strip()
    if c.startswith(("\\\\", "//", "smb://")):
        return True

    # host:D:... (mais de 1 caractere antes dos dois pontos)
    if ":" in c:
        antes_dois_pontos = c.split(":", 1)[0]
        if len(antes_dois_pontos) > 1 and not (len(antes_dois_pontos) == 1 and antes_dois_pontos.isalpha()):
            return True

    cfg = config_extra or {}
    if cfg.get("smb_host"):
        return True

    # Se plataforma não for Windows e caminho usar letra de drive (D:\\ ou D:)
    if sys.platform != "win32":
        if re.match(r"^[a-zA-Z]:", c):
            return True
        if ip and ip not in ("127.0.0.1", "localhost", ""):
            return True

    return False


class SmbStorage:
    def __init__(self, connection_timeout: int = 15):
        self.connection_timeout = connection_timeout

    def register_session(self, target: SmbTarget) -> None:
        """Registra sessão SMB com smbclient."""
        if smbclient is None:
            raise RuntimeError("Biblioteca smbprotocol/smbclient não está instalada.")
        try:
            smbclient.register_session(
                server=target.host,
                username=target.username or "",
                password=target.password or "",
                port=target.port,
                connection_timeout=self.connection_timeout,
            )
        except Exception as e:
            err_msg = str(e)
            if target.password and target.password in err_msg:
                err_msg = err_msg.replace(target.password, "***")
            logging.debug(f"[SMB] register_session para {target.host}:{target.port}: {err_msg}")

    def scandir(self, target: SmbTarget) -> List[SmbEntry]:
        """Varre o diretório remoto no target UNC."""
        self.register_session(target)
        caminho_unc = target.unc_path
        entries: List[SmbEntry] = []
        try:
            for item in smbclient.scandir(caminho_unc):
                is_dir = item.is_dir()
                size = 0 if is_dir else item.stat().st_size
                mtime = None
                try:
                    mtime = datetime.fromtimestamp(item.stat().st_mtime)
                except Exception:
                    pass
                item_unc = f"{caminho_unc.rstrip('\\')}\\{item.name}"
                entries.append(SmbEntry(
                    name=item.name,
                    unc_path=item_unc,
                    is_dir=is_dir,
                    size=size,
                    mtime=mtime,
                ))
        except Exception as e:
            logging.error(f"[SMB] Erro ao listar diretório {caminho_unc}: {e}")
            raise
        return entries

    @staticmethod
    def get_file_size(remote_unc: str) -> int:
        """Retorna o tamanho do arquivo remoto em bytes via stat."""
        if smbclient is None:
            return 0
        try:
            st = smbclient.stat(remote_unc)
            return st.st_size
        except Exception:
            return 0

    def copy_file(self, remote_unc: str, local_dest: Path, check_hash: bool = True) -> Tuple[bool, BackupStatus]:
        """
        Copia arquivo do share SMB para local_dest de forma atômica e segura:
        1. Streaming de blocos de 1MB para local_dest.tmp calculando SHA256 em voo.
        2. Validação de tamanho com smbclient.stat(remote_unc).
        3. Validação de SHA256 do arquivo local contra o hash em voo (se check_hash=True).
        4. Renomeação atômica de local_dest.tmp para local_dest.
        """
        if smbclient is None:
            logging.error("[SMB] smbclient indisponível.")
            return False, BackupStatus.ERRO

        destino_tmp = local_dest.with_suffix(local_dest.suffix + ".tmp")
        sha256_remoto = hashlib.sha256()

        try:
            if destino_tmp.exists():
                destino_tmp.unlink()

            local_dest.parent.mkdir(parents=True, exist_ok=True)

            try:
                stat_remoto = smbclient.stat(remote_unc)
                tamanho_remoto = stat_remoto.st_size
            except Exception as e:
                logging.error(f"[SMB] Falha ao obter stat de {remote_unc}: {e}")
                return False, BackupStatus.NAO_ENCONTRADO

            logging.debug(f"[SMB] Baixando {remote_unc} ({tamanho_remoto / (1024*1024):.2f} MB) -> {destino_tmp.name}...")

            bytes_copiados = 0
            with smbclient.open_file(remote_unc, mode="rb") as fin:
                with open(destino_tmp, "wb") as fout:
                    while True:
                        bloco = fin.read(1048576)  # 1MB
                        if not bloco:
                            break
                        sha256_remoto.update(bloco)
                        fout.write(bloco)
                        bytes_copiados += len(bloco)

            # Valida tamanho
            if bytes_copiados != tamanho_remoto:
                logging.error(f"[SMB] Tamanho divergente após streaming ({bytes_copiados} vs {tamanho_remoto} bytes)")
                if destino_tmp.exists():
                    destino_tmp.unlink()
                return False, BackupStatus.CORROMPIDO

            # Valida SHA256 do arquivo salvo localmente
            if check_hash:
                hash_calculado = sha256_remoto.hexdigest()
                hash_local = hashlib.sha256()
                with open(destino_tmp, "rb") as f_check:
                    for chunk in iter(lambda: f_check.read(1048576), b""):
                        hash_local.update(chunk)
                if hash_local.hexdigest() != hash_calculado:
                    logging.error("[SMB] Divergência de hash SHA-256 no arquivo gravado localmente")
                    if destino_tmp.exists():
                        destino_tmp.unlink()
                    return False, BackupStatus.CORROMPIDO

            # Renomeação atômica
            if local_dest.exists():
                local_dest.unlink()
            destino_tmp.rename(local_dest)
            return True, BackupStatus.OK

        except Exception as e:
            logging.error(f"[SMB] Erro durante cópia de {remote_unc}: {e}")
            if destino_tmp.exists():
                try:
                    destino_tmp.unlink()
                except OSError:
                    pass
            return False, BackupStatus.ERRO

    def copy_directory(self, remote_unc: str, local_dest: Path) -> Tuple[bool, BackupStatus]:
        """
        Copia recursivamente um diretório remoto SMB para o caminho local local_dest:
        1. Copia recursivamente para local_dest.tmp
        2. Renomeia atômico de local_dest.tmp para local_dest
        """
        if smbclient is None:
            logging.error("[SMB] smbclient indisponível.")
            return False, BackupStatus.ERRO

        destino_tmp = local_dest.with_suffix(local_dest.suffix + ".tmp")
        try:
            if destino_tmp.exists():
                shutil.rmtree(destino_tmp, ignore_errors=True)

            destino_tmp.mkdir(parents=True, exist_ok=True)
            self._copy_dir_recursive(remote_unc, destino_tmp)

            if local_dest.exists():
                if local_dest.is_dir():
                    shutil.rmtree(local_dest, ignore_errors=True)
                else:
                    local_dest.unlink()

            destino_tmp.rename(local_dest)
            return True, BackupStatus.OK
        except Exception as e:
            logging.error(f"[SMB] Erro durante cópia recursiva do diretório {remote_unc}: {e}")
            if destino_tmp.exists():
                shutil.rmtree(destino_tmp, ignore_errors=True)
            return False, BackupStatus.ERRO

    def _copy_dir_recursive(self, remote_unc: str, local_dir: Path) -> None:
        """Helper recursivo para cópia de diretórios via SMB."""
        local_dir.mkdir(parents=True, exist_ok=True)
        for item in smbclient.scandir(remote_unc):
            sub_remote = f"{remote_unc.rstrip('\\')}\\{item.name}"
            sub_local = local_dir / item.name
            if item.is_dir():
                self._copy_dir_recursive(sub_remote, sub_local)
            else:
                with smbclient.open_file(sub_remote, mode="rb") as fin:
                    with open(sub_local, "wb") as fout:
                        while True:
                            bloco = fin.read(1048576)
                            if not bloco:
                                break
                            fout.write(bloco)

    def test_connection(self, target: SmbTarget) -> Tuple[bool, str, int]:
        """Testa conexão SMB com o target especificado."""
        if smbclient is None:
            return False, "Biblioteca smbprotocol/smbclient não instalada no agente", 0
        try:
            self.register_session(target)
            itens = smbclient.listdir(target.unc_path)
            qtd = len(itens)
            return True, f"Conexão SMB estabelecida ({qtd} itens em {target.unc_path})", qtd
        except Exception as e:
            err_msg = str(e)
            if target.password and target.password in err_msg:
                err_msg = err_msg.replace(target.password, "***")
            return False, f"Falha SMB ({err_msg})", 0
