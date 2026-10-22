import asyncio
import logging

from pysnmp.hlapi.asyncio import (
    SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
    ObjectType, ObjectIdentity, get_cmd, walk_cmd,
)

TIMEOUT = 2.0
COMMUNITY_PADRAO = "Public"

# MIB proprietaria Intelbras: nao expoe utilizacao de CPU, so RAM e discos.
_OID_RAM_TOTAL_MB = "1.3.6.1.4.1.1004849.2.1.9.1.0"
_OID_RAM_USO_PCT = "1.3.6.1.4.1.1004849.2.1.9.2.0"
_OID_TABELA_HDD = "1.3.6.1.4.1.1004849.2.4.1.1"  # .4={device} .5={status} .6={total_gb} .7={free_gb}

# Status de HD do MIB Intelbras traduzidos para o StatusBadge do dashboard
_STATUS_DISCO = {
    "normal": "OK",
    "ok": "OK",
    "error": "ERRO",
    "abnormal": "ERRO",
    "lost": "ERRO",
    "notexist": "DESCONHECIDO",
}


def _status_disco(status_bruto):
    chave = (status_bruto or "").strip().lower()
    return _STATUS_DISCO.get(chave, (status_bruto or "DESCONHECIDO").upper())


async def _coletar_async(nvr_ip, community):
    target = await UdpTransportTarget.create((nvr_ip, 161), timeout=TIMEOUT, retries=1)
    engine = SnmpEngine()
    auth = CommunityData(community, mpModel=1)  # SNMPv2c
    ctx = ContextData()

    telemetria = {}
    teve_sucesso = False

    try:
        err_ind, err_status, _, var_binds = await get_cmd(
            engine, auth, target, ctx,
            ObjectType(ObjectIdentity(_OID_RAM_USO_PCT)),
            ObjectType(ObjectIdentity(_OID_RAM_TOTAL_MB)),
        )
        if not err_ind and not err_status and var_binds:
            try:
                telemetria["ram_percent"] = int(var_binds[0][1].prettyPrint())
                teve_sucesso = True
            except (ValueError, IndexError):
                pass
            try:
                if len(var_binds) > 1:
                    total_mb = int(var_binds[1][1].prettyPrint())
                    if total_mb > 0:
                        total_gb = round(total_mb / 1024, 1)
                        telemetria["ram_total_gb"] = total_gb
                        if "ram_percent" in telemetria:
                            telemetria["ram_used_gb"] = round(total_gb * (telemetria["ram_percent"] / 100), 1)
            except (ValueError, IndexError):
                pass
    except Exception:
        logging.warning(f"  Falha ao ler memoria SNMP do NVR {nvr_ip}.", exc_info=True)

    discos_map = {}
    try:
        async for err, st, _, var_binds in walk_cmd(
            engine, auth, target, ctx,
            ObjectType(ObjectIdentity(_OID_TABELA_HDD)),
            lexicographicMode=False,
        ):
            if err or st:
                break
            for vb in var_binds:
                partes = str(vb[0]).split(".")
                coluna = int(partes[-2])
                disco_id = int(partes[-1])
                disco = discos_map.setdefault(disco_id, {"id": disco_id})
                valor = vb[1].prettyPrint()
                if coluna == 4:
                    disco["dispositivo"] = valor
                elif coluna == 5:
                    disco["status"] = valor
                elif coluna == 6:
                    try:
                        disco["total_gb"] = int(valor)
                    except ValueError:
                        pass
                elif coluna == 7:
                    try:
                        disco["free_gb"] = int(valor)
                    except ValueError:
                        pass
        teve_sucesso = teve_sucesso or bool(discos_map)
    except Exception:
        logging.warning(f"  Falha ao ler discos SNMP do NVR {nvr_ip}.", exc_info=True)

    discos = []
    for d in discos_map.values():
        total_gb = d.get("total_gb")
        free_gb = d.get("free_gb")
        percent = None
        if isinstance(total_gb, int) and isinstance(free_gb, int) and total_gb > 0:
            percent = round((total_gb - free_gb) / total_gb * 100, 1)
        discos.append({
            "device": d.get("dispositivo") or f"HDD{d['id']}",
            "status": _status_disco(d.get("status")),
            "percent": percent,
            "total_gb": total_gb,
            "free_gb": free_gb,
        })
    telemetria["disks"] = discos

    return telemetria if teve_sucesso else None


def coletar_telemetria_intelbras(nvr_ip, community=COMMUNITY_PADRAO):
    """Coleta RAM e discos de um NVR Intelbras via SNMP (MIB proprietaria, porta 161).
    Sem CPU: a MIB Intelbras nao expoe utilizacao de processador.
    Retorna None se a consulta SNMP nao respondeu nada util (SNMP desligado, community errada etc.)."""
    try:
        return asyncio.run(_coletar_async(nvr_ip, community))
    except Exception:
        logging.warning(f"  Falha ao coletar telemetria SNMP do NVR {nvr_ip}.", exc_info=True)
        return None
