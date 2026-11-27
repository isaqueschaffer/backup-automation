import logging
import pyzipper
from datetime import datetime
from pathlib import Path

def data_hoje() -> str:
    return datetime.now().strftime("%d-%m-%Y")

def criar_zip(pasta: Path, nome_ou_cliente, senha: str) -> Path | None:
    if isinstance(nome_ou_cliente, Path):
        zip_path = nome_ou_cliente
    elif isinstance(nome_ou_cliente, str) and nome_ou_cliente.endswith(".zip"):
        zip_path = pasta / nome_ou_cliente
    else:
        zip_path = pasta / f"BACKUP_{str(nome_ou_cliente).upper().replace(' ','_')}_{data_hoje()}.zip"
    try:
        if senha:
            with pyzipper.AESZipFile(zip_path, "w", compression=pyzipper.ZIP_DEFLATED,
                                      encryption=pyzipper.WZ_AES) as zf:
                zf.setpassword(senha.encode())
                for arq in pasta.rglob("*"):
                    if arq.is_file() and arq.name != zip_path.name:
                        zf.write(arq, arq.relative_to(pasta))
            with pyzipper.AESZipFile(zip_path, "r") as zf:
                zf.setpassword(senha.encode())
                if zf.testzip() is not None:
                    raise ValueError("ZIP corrompido.")
        else:
            import zipfile
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for arq in pasta.rglob("*"):
                    if arq.is_file() and arq.name != zip_path.name:
                        zf.write(arq, arq.relative_to(pasta))
            with zipfile.ZipFile(zip_path, "r") as zf:
                if zf.testzip() is not None:
                    raise ValueError("ZIP corrompido.")

        logging.info(f"  ZIP criado: {zip_path.name}")
        return zip_path
    except Exception as e:
        logging.error(f"  Erro ao criar ZIP: {e}")
        return None
