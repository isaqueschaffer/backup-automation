import time
import hashlib
from base64 import b64encode
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

AES_KEY_HEX = bytes.fromhex("bf8a6df8640f38f3812c19d2aaca7743")  # Hikvision WebSDK key

def gerar_secretkey(senha: str | None) -> tuple[str, str]:
    senha_str = senha or ""
    timestamp = str(int(time.time() * 1000))
    iv_hex = hashlib.md5(timestamp.encode()).hexdigest()
    senha_esc = senha_str.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    texto = b64encode(senha_esc.encode())
    cipher = AES.new(AES_KEY_HEX, AES.MODE_CBC, bytes.fromhex(iv_hex))
    return cipher.encrypt(pad(texto, AES.block_size)).hex(), iv_hex
