"""Baixa a foto cadastrada de cada pessoa de uma facial Intelbras (linha SS/ASI, API CGI) e salva como "<Nome>.jpg".

Uso:  python baixar_fotos_facial.py http://192.168.75.11 admin SENHA PASTA_DESTINO
A senha tambem pode vir da variavel de ambiente FACIAL_SENHA (omita o argumento). So le da facial; nada e alterado nela.
Nomes repetidos ou vazios recebem o UserID no fim ("Nome (012736).jpg"). As fotos sao dados pessoais: guarde fora do repositorio.
"""
import base64
import os
import re
import sys
import time
from pathlib import Path

import requests
from requests.auth import HTTPDigestAuth

TIMEOUT_S = 15
LOTE = 1  # a facial corta a conexao quando a resposta junta varias fotos em base64
TENTATIVAS = 3


def _pares(texto: str) -> dict:
    """Linhas 'chave=valor' da resposta CGI."""
    saida = {}
    for linha in texto.replace("\r", "").split("\n"):
        if "=" in linha:
            chave, valor = linha.split("=", 1)
            saida[chave.strip()] = valor.strip()
    return saida


def listar_pessoas(sessao, base: str) -> dict:
    """{UserID: nome} das pessoas cadastradas (AccessControlCard)."""
    r = sessao.get(f"{base}/cgi-bin/recordFinder.cgi", params={"action": "find", "name": "AccessControlCard", "count": 5000}, timeout=TIMEOUT_S)
    r.raise_for_status()
    campos = _pares(r.text)
    pessoas = {}
    for chave, valor in campos.items():
        m = re.fullmatch(r"records\[(\d+)\]\.UserID", chave)
        if m and valor:
            pessoas[valor] = campos.get(f"records[{m.group(1)}].CardName", "")
    return pessoas


def fotos_das_pessoas(sessao, base: str, user_ids: list) -> dict:
    """{UserID: bytes do JPEG} da primeira foto cadastrada de cada pessoa que tiver."""
    params = {"action": "list"}
    params.update({f"UserIDList[{i}]": uid for i, uid in enumerate(user_ids)})
    for tentativa in range(TENTATIVAS):
        try:
            r = sessao.get(f"{base}/cgi-bin/AccessFace.cgi", params=params, timeout=TIMEOUT_S)
            if r.status_code == 400:  # a facial responde 400 para quem nao tem rosto cadastrado
                return {}
            r.raise_for_status()
            break
        except requests.exceptions.RequestException:
            if tentativa == TENTATIVAS - 1:
                raise
            time.sleep(1)
    campos = _pares(r.text)
    fotos = {}
    for chave, valor in campos.items():
        m = re.fullmatch(r"FaceDataList\[(\d+)\]\.PhotoData\[0\]", chave)
        if m and valor:
            uid = campos.get(f"FaceDataList[{m.group(1)}].UserID")
            if uid:
                fotos[uid] = base64.b64decode(valor)
    return fotos


def nome_de_arquivo(nome: str, uid: str, usados: set) -> str:
    limpo = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (nome or "").strip()).strip(". ")[:120]
    final = limpo or f"sem nome ({uid})"
    if final.lower() in usados:
        final = f"{final} ({uid})"
    usados.add(final.lower())
    return f"{final}.jpg"


def baixar(base: str, usuario: str, senha: str, destino: Path, progresso=None, cancelar=None) -> dict:
    """`progresso(feitas, total, nome)` e `cancelar()` (True para parar) sao opcionais, para uso por uma tela."""
    base = base.rstrip("/")
    if "://" not in base:
        base = "http://" + base
    sessao = requests.Session()
    sessao.auth = HTTPDigestAuth(usuario, senha)
    pessoas = listar_pessoas(sessao, base)
    destino.mkdir(parents=True, exist_ok=True)
    usados, salvas, sem_foto = set(), 0, []
    ids = list(pessoas)
    for i in range(0, len(ids), LOTE):
        if cancelar and cancelar():
            break
        lote = ids[i:i + LOTE]
        if progresso:
            progresso(i, len(ids), pessoas[lote[0]] or lote[0])
        fotos = fotos_das_pessoas(sessao, base, lote)
        for uid in lote:
            if uid not in fotos:
                sem_foto.append(pessoas[uid] or uid)
                continue
            (destino / nome_de_arquivo(pessoas[uid], uid, usados)).write_bytes(fotos[uid])
            salvas += 1
    if progresso:
        progresso(len(ids), len(ids), "")
    return {"pessoas": len(pessoas), "salvas": salvas, "sem_foto": sem_foto}


if __name__ == "__main__":
    args = sys.argv[1:]
    senha_env = os.environ.get("FACIAL_SENHA")
    if len(args) == 3 and senha_env:
        args.insert(2, senha_env)
    if len(args) != 4:
        sys.exit(__doc__)
    resultado = baixar(args[0], args[1], args[2], Path(args[3]))
    print(f"{resultado['salvas']} foto(s) salva(s) de {resultado['pessoas']} pessoa(s).")
    if resultado["sem_foto"]:
        print("Sem foto cadastrada:", ", ".join(resultado["sem_foto"]))
