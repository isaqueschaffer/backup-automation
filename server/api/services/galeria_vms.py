"""
Pareamento das câmeras de equipamentos DIGIFORT/DEFENSE.

O agente numera as câmeras pela ordem do export local e a Galeria pela ordem da importação, então o
canal não identifica a mesma câmera nos dois lados: o pareamento é por nome e por IP.
"""
import re
from typing import List, Optional, Tuple


def canal_int(valor) -> Optional[int]:
    # Motorola (agentes < 1.1.4) reportava o canal como GUID "{0000000N-0000-...}"
    try:
        return int(valor)
    except (ValueError, TypeError):
        try:
            return int(str(valor).strip("{}").split("-")[0], 16)
        except ValueError:
            return None


def _norm(texto) -> str:
    return re.sub(r"[^a-z0-9]", "", (texto or "").lower())


def _palavras(texto) -> list:
    return re.findall(r"[a-z0-9]+", (texto or "").lower())


def _parecidos(a, b) -> bool:
    """Um nome contém o outro por palavras inteiras ('1 ANDAR' em '1 ANDAR- ACESSO'; 'Camera 1' não está em 'Camera 10')."""
    pa, pb = _palavras(a), _palavras(b)
    if not pa or not pb:
        return False
    curto, longo = (pa, pb) if len(pa) <= len(pb) else (pb, pa)
    return any(longo[i:i + len(curto)] == curto for i in range(len(longo) - len(curto) + 1))


def ip_valido(ip) -> str:
    """IP reportado utilizável ('' para vazio ou 'N/A')."""
    ip = (ip or "").strip()
    return ip if ip and ip != "N/A" and "." in ip else ""


def parear_cameras(cameras_db: list, relatorio: list) -> List[Tuple[Optional[int], Optional[dict], Optional[object], int]]:
    """Pareia as câmeras do relatório do agente com as da Galeria.

    Ordem de preferência: nome igual (sem pontuação/maiúsculas), mesmo IP e nome parecido (um contém o
    outro por palavras inteiras, só com um único candidato e sem IPs diferentes). Nunca por canal. A câmera do relatório sem par vira linha sem
    registro, num canal livre depois dos já usados na Galeria.

    Retorna (índice no relatório | None, entrada do relatório | None, câmera da Galeria | None, canal)."""
    entradas = [(i, st) for i, st in enumerate(relatorio or []) if isinstance(st, dict)]
    par = {}
    usadas = set()

    def passada(casa):
        for i, st in entradas:
            if i in par:
                continue
            for c in cameras_db:
                if c.id not in usadas and casa(st, c):
                    par[i] = c
                    usadas.add(c.id)
                    break

    passada(lambda st, c: bool(_norm(st.get("nome"))) and _norm(c.nome) == _norm(st.get("nome")))
    passada(lambda st, c: bool(ip_valido(st.get("ip"))) and (c.ip or "").strip() == ip_valido(st.get("ip")))

    for i, st in entradas:
        if i in par or not _palavras(st.get("nome")):
            continue
        ip_st = ip_valido(st.get("ip"))
        candidatas = [c for c in cameras_db
                      if c.id not in usadas and _parecidos(st.get("nome"), c.nome)
                      and not (ip_st and (c.ip or "").strip() and (c.ip or "").strip() != ip_st)]
        if len(candidatas) == 1:
            par[i] = candidatas[0]
            usadas.add(candidatas[0].id)

    ocupados = {c.canal for c in cameras_db}
    resultado = []
    for i, st in entradas:
        c = par.get(i)
        if c is not None:
            resultado.append((i, st, c, c.canal))
            continue
        canal = canal_int(st.get("canal")) or (i + 1)
        while canal in ocupados:
            canal += 1
        ocupados.add(canal)
        resultado.append((i, st, None, canal))

    for c in cameras_db:
        if c.id not in usadas:
            resultado.append((None, None, c, c.canal))
    return resultado
