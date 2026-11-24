"""Imagens nas respostas do MCP.

As rotas do painel devolvem fotos de câmera em base64 dentro do JSON (image_base64, perfect_image_base64,
night_image_base64). Como texto, uma foto Full HD passa de 300 mil caracteres e os apps de IA cortam a resposta.
Aqui elas saem do JSON (no lugar fica um aviso curto) e vão como conteúdo de imagem do MCP, que o Claude, o
ChatGPT e o Gemini mostram no chat. Resposta com muitas fotos (galeria inteira) não anexa todas: a IA pede a
foto de um canal com a ferramenta ver_imagem_camera.
"""
import base64
import binascii
import re
from typing import Any, List, Optional, Tuple

MAX_IMAGENS = 4
MAX_BYTES_TOTAL = 8 * 1024 * 1024
MIN_CHARS = 500  # string menor que isso não é foto

_DATA_URL = re.compile(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.*)$", re.S)

NOME_FERRAMENTA = "ver_imagem_camera"

FERRAMENTA = {
    "name": NOME_FERRAMENTA,
    "title": "Ver a imagem salva de uma câmera",
    "description": (
        "Mostra no chat a imagem salva de uma câmera de um equipamento (NVR/DVR/VMS): a imagem de referência "
        "(a 'perfeita', usada para comparar) ou a da noite (capturada da gravação da madrugada).\n"
        "Para achar os ids: list_customers / list_machines, depois list_equipamentos e get_nvr_cameras (que "
        "lista os canais sem as fotos). Para uma foto AO VIVO, use test_equipamento_rtsp."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "machine_id": {"type": "string", "description": "Id da máquina (computador com o agente)."},
            "equipamento_id": {"type": "string", "description": "Id do equipamento (NVR/DVR/VMS)."},
            "canal": {"type": "integer", "description": "Canal da câmera (como em get_nvr_cameras)."},
            "tipo": {
                "type": "string", "enum": ["noite", "referencia", "as_duas"], "default": "as_duas",
                "description": "Qual imagem: a da noite, a de referência ou as duas.",
            },
        },
        "required": ["machine_id", "equipamento_id", "canal"],
    },
    "annotations": {"title": "Ver a imagem salva de uma câmera", "readOnlyHint": True, "openWorldHint": False},
}


def _decodificar(valor: str) -> Optional[Tuple[str, str]]:
    """(mime, base64 limpo) se a string for uma imagem em base64; senão None."""
    m = _DATA_URL.match(valor)
    if m:
        mime, b64 = m.group(1), m.group(2)
    else:
        mime, b64 = None, valor
    b64 = re.sub(r"\s+", "", b64)
    try:
        cabeca = base64.b64decode(b64[:64] + "=" * (-len(b64[:64]) % 4), validate=False)
    except (binascii.Error, ValueError):
        return None
    if cabeca.startswith(b"\xff\xd8"):
        mime = "image/jpeg"
    elif cabeca.startswith(b"\x89PNG"):
        mime = "image/png"
    elif cabeca[:4] == b"RIFF" and cabeca[8:12] == b"WEBP":
        mime = "image/webp"
    elif cabeca[:3] == b"GIF":
        mime = "image/gif"
    if not mime:
        return None
    return mime, b64


def _rotulo(pai: dict, chave: str) -> str:
    tipo = {"perfect_image_base64": "referência", "night_image_base64": "noite"}.get(chave, "ao vivo")
    partes = [str(pai[c]) for c in ("nome",) if pai.get(c)]
    if pai.get("canal") is not None:
        partes.append(f"canal {pai['canal']}")
    return (" — ".join(partes) + f" ({tipo})") if partes else f"imagem ({tipo})"


def separar(dados: Any) -> Tuple[Any, List[dict]]:
    """Tira as imagens do JSON. Devolve (JSON com avisos no lugar, lista de {mime, b64, rotulo})."""
    achadas: List[dict] = []

    def visitar(no: Any, pai: Optional[dict] = None, chave: str = "") -> Any:
        if isinstance(no, dict):
            return {k: visitar(v, no, k) for k, v in no.items()}
        if isinstance(no, list):
            return [visitar(x, pai, chave) for x in no]
        if isinstance(no, str) and len(no) >= MIN_CHARS and ("image" in chave.lower() or no.startswith("data:image/")):
            dec = _decodificar(no)
            if dec:
                achadas.append({"mime": dec[0], "b64": dec[1], "rotulo": _rotulo(pai or {}, chave)})
                return f"[IMAGEM {len(achadas)}]"
        return no

    return visitar(dados), achadas


def anexar(achadas: List[dict]) -> Tuple[List[dict], str]:
    """Blocos de imagem do MCP (até o limite) e um texto explicando o que foi anexado ou omitido."""
    blocos: List[dict] = []
    linhas: List[str] = []
    total = 0
    for i, img in enumerate(achadas, 1):
        tamanho = len(img["b64"]) * 3 // 4
        if len(blocos) < MAX_IMAGENS and total + tamanho <= MAX_BYTES_TOTAL:
            total += tamanho
            blocos.append({"type": "image", "mimeType": img["mime"], "data": img["b64"]})
            linhas.append(f"[IMAGEM {i}] {img['rotulo']}: anexada abaixo ({tamanho // 1024} KB).")
        else:
            linhas.append(f"[IMAGEM {i}] {img['rotulo']}: não anexada (muitas imagens). Use {NOME_FERRAMENTA}.")
    return blocos, "\n".join(linhas)


def escolher_da_galeria(cameras: Any, canal: int, tipo: str) -> Tuple[List[dict], str]:
    """Para ver_imagem_camera: acha o canal na resposta de get_nvr_cameras e devolve (imagens, texto)."""
    if not isinstance(cameras, list):
        return [], "Resposta inesperada da galeria."
    cam = next((c for c in cameras if isinstance(c, dict) and str(c.get("canal")) == str(canal)), None)
    if not cam:
        canais = ", ".join(str(c.get("canal")) for c in cameras if isinstance(c, dict))
        return [], f"Canal {canal} não encontrado. Canais deste equipamento: {canais or 'nenhum'}."
    chaves = {"noite": ["night_image_base64"], "referencia": ["perfect_image_base64"]}.get(
        tipo, ["night_image_base64", "perfect_image_base64"])
    achadas = []
    for k in chaves:
        v = cam.get(k)
        dec = _decodificar(v) if isinstance(v, str) and v else None
        if dec:
            achadas.append({"mime": dec[0], "b64": dec[1], "rotulo": _rotulo(cam, k)})
    if not achadas:
        nome = cam.get("nome") or f"canal {canal}"
        return [], (f"A câmera {nome} não tem imagem salva desse tipo. Para uma foto ao vivo, use "
                    "test_equipamento_rtsp.")
    info = f"Câmera: {cam.get('nome') or '-'} (canal {canal})"
    if cam.get("night_image_date"):
        info += f"; imagem da noite de {cam['night_image_date']}"
    return achadas, info
