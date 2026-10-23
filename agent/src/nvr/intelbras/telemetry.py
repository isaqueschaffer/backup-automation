import asyncio
import logging

from pysnmp.hlapi.asyncio import (
    SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
    ObjectType, ObjectIdentity, get_cmd, walk_cmd,
)

TIMEOUT = 2.0
COMMUNITY_PADRAO = "Public"

# MIB proprietaria Intelbras: nao expoe utilizacao de CPU, so RAM e discos.
_OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"        # RFC1213-MIB / SNMPv2-MIB: sysUpTime (TimeTicks em centésimos de segundo)
_OID_RAM_TOTAL_MB = "1.3.6.1.4.1.1004849.2.1.9.1.0"
_OID_RAM_USO_PCT = "1.3.6.1.4.1.1004849.2.1.9.2.0"
_OID_TABELA_HDD = "1.3.6.1.4.1.1004849.2.4.1.1"  # .4={device} .5={status} .6={total_gb} .7={free_gb}
_OID_IF_TABLE = "1.3.6.1.2.1.2.2.1"     # IF-MIB: .2=name, .5=speed, .6=mac, .8=operStatus, .10=in, .16=out
_OID_IFX_TABLE = "1.3.6.1.2.1.31.1.1.1" # IF-MIB XTable: .6=inHC, .10=outHC, .15=highSpeed

# Status de HD do MIB Intelbras traduzidos para o StatusBadge do dashboard
_STATUS_DISCO = {
    "normal": "OK",
    "ok": "OK",
    "running": "OK",
    "idle": "OK",
    "sleep": "OK",
    "error": "ERRO",
    "abnormal": "ERRO",
    "lost": "ERRO",
    "notexist": "DESCONHECIDO",
}


def _status_disco(status_bruto):
    chave = (status_bruto or "").strip().lower()
    return _STATUS_DISCO.get(chave, (status_bruto or "DESCONHECIDO").upper())


def _format_mac(raw):
    if not raw:
        return None
    s = str(raw).strip()
    if s.startswith("0x"):
        hex_str = s[2:]
        if len(hex_str) == 12:
            return ":".join(hex_str[i:i+2] for i in range(0, 12, 2))
    elif len(s) == 6:
        return ":".join(f"{b:02x}" for b in s.encode("latin-1"))
    return s if ":" in s else None


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
            ObjectType(ObjectIdentity(_OID_SYS_UPTIME)),
            ObjectType(ObjectIdentity(_OID_RAM_USO_PCT)),
            ObjectType(ObjectIdentity(_OID_RAM_TOTAL_MB)),
        )
        if not err_ind and not err_status and var_binds:
            # Uptime (centésimos de segundo -> segundos)
            try:
                timeticks = int(var_binds[0][1].prettyPrint())
                if timeticks >= 0:
                    telemetria["uptime_seconds"] = int(timeticks / 100)
                    teve_sucesso = True
            except (ValueError, IndexError):
                pass

            # RAM %
            try:
                if len(var_binds) > 1:
                    telemetria["ram_percent"] = int(var_binds[1][1].prettyPrint())
                    teve_sucesso = True
            except (ValueError, IndexError):
                pass

            # RAM Total e Usada
            try:
                if len(var_binds) > 2:
                    total_mb = int(var_binds[2][1].prettyPrint())
                    if total_mb > 0:
                        total_gb = round(total_mb / 1024, 1)
                        telemetria["ram_total_gb"] = total_gb
                        if "ram_percent" in telemetria:
                            telemetria["ram_used_gb"] = round(total_gb * (telemetria["ram_percent"] / 100), 1)
            except (ValueError, IndexError):
                pass
    except Exception:
        logging.warning(f"  Falha ao ler uptime e memoria SNMP do NVR {nvr_ip}.", exc_info=True)

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

    # 3. Informações de Rede (IF-MIB: 1.3.6.1.2.1.2.2.1 e 1.3.6.1.2.1.31.1.1.1)
    nics_map = {}
    try:
        async for err, st, _, var_binds in walk_cmd(
            engine, auth, target, ctx,
            ObjectType(ObjectIdentity(_OID_IF_TABLE)),
            lexicographicMode=False,
        ):
            if err or st:
                break
            for vb in var_binds:
                partes = str(vb[0]).split(".")
                coluna = int(partes[-2])
                nic_id = int(partes[-1])
                nic = nics_map.setdefault(nic_id, {"id": nic_id})
                valor = vb[1].prettyPrint()
                if coluna == 2:
                    nic["name"] = valor
                elif coluna == 5:
                    try:
                        nic["speed_bps"] = int(valor)
                    except ValueError:
                        pass
                elif coluna == 6:
                    nic["mac"] = _format_mac(valor)
                elif coluna == 8:
                    try:
                        nic["oper_status"] = int(valor)
                    except ValueError:
                        pass
                elif coluna == 10:
                    try:
                        nic["in_octets"] = int(valor)
                    except ValueError:
                        pass
                elif coluna == 16:
                    try:
                        nic["out_octets"] = int(valor)
                    except ValueError:
                        pass
    except Exception:
        logging.warning(f"  Falha ao ler interfaces SNMP do NVR {nvr_ip}.", exc_info=True)

    try:
        async for err, st, _, var_binds in walk_cmd(
            engine, auth, target, ctx,
            ObjectType(ObjectIdentity(_OID_IFX_TABLE)),
            lexicographicMode=False,
        ):
            if err or st:
                break
            for vb in var_binds:
                partes = str(vb[0]).split(".")
                coluna = int(partes[-2])
                nic_id = int(partes[-1])
                if nic_id in nics_map:
                    valor = vb[1].prettyPrint()
                    if coluna == 15:
                        try:
                            hs = int(valor)
                            if hs > 0:
                                nics_map[nic_id]["high_speed"] = hs
                        except ValueError:
                            pass
                    elif coluna == 6:
                        try:
                            nics_map[nic_id]["in_octets"] = int(valor)
                        except ValueError:
                            pass
                    elif coluna == 10:
                        try:
                            nics_map[nic_id]["out_octets"] = int(valor)
                        except ValueError:
                            pass
    except Exception:
        pass

    # Amostra de tráfego instantâneo para interfaces ativas
    ativas = [n for n in nics_map.values() if n.get("name") and not n["name"].startswith("lo") and n.get("oper_status") == 1]
    if ativas and any(n.get("in_octets") is not None for n in ativas):
        try:
            import time
            amostra1 = {n["id"]: (n.get("in_octets", 0), n.get("out_octets", 0)) for n in ativas}
            t1 = time.time()
            await asyncio.sleep(1.0)
            t2 = time.time()
            dt = t2 - t1

            oids_busca = []
            for n in ativas:
                oids_busca.append(ObjectType(ObjectIdentity(f"{_OID_IF_TABLE}.10.{n['id']}")))
                oids_busca.append(ObjectType(ObjectIdentity(f"{_OID_IF_TABLE}.16.{n['id']}")))

            err_ind, err_status, _, var_binds = await get_cmd(engine, auth, target, ctx, *oids_busca)
            if not err_ind and not err_status and var_binds:
                for i, n in enumerate(ativas):
                    try:
                        in2 = int(var_binds[i * 2][1].prettyPrint())
                        out2 = int(var_binds[i * 2 + 1][1].prettyPrint())
                        in1, out1 = amostra1[n["id"]]
                        d_in = in2 - in1
                        d_out = out2 - out1
                        if dt > 0 and d_in >= 0:
                            n["recv_mbps"] = round((d_in * 8) / (dt * 1_000_000), 1)
                        if dt > 0 and d_out >= 0:
                            n["sent_mbps"] = round((d_out * 8) / (dt * 1_000_000), 1)
                    except Exception:
                        pass
        except Exception:
            pass

    networks = []
    for n in nics_map.values():
        name = n.get("name") or ""
        if name.startswith("lo"):
            continue
        oper_st = n.get("oper_status")
        speed_mbps = n.get("high_speed")
        if not speed_mbps and n.get("speed_bps"):
            speed_mbps = int(round(n["speed_bps"] / 1_000_000))
        networks.append({
            "name": name or f"ETH{n['id']}",
            "mac": n.get("mac"),
            "status": "UP" if oper_st == 1 else "DOWN",
            "speed_mbps": speed_mbps if (speed_mbps and speed_mbps > 0) else None,
            "recv_mbps": n.get("recv_mbps"),
            "sent_mbps": n.get("sent_mbps"),
        })

    if networks:
        telemetria["networks"] = networks
        teve_sucesso = True

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
