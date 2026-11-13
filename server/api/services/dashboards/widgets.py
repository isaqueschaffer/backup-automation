from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session, selectinload

from models import Backup, Customer, Machine, NVR
from routers.machines import check_machine_online
from schemas import TIPOS_EQUIPAMENTO
from services.camera_offline import segundos_offline
from .registro import TipoWidget, registrar


@dataclass
class ContextoDados:
    db: Session
    customer: Customer
    maquinas: List[Machine]      # só as máquinas ATIVAS do cliente, com equipamentos já carregados
    periodo: str                 # filtro global: "24h" | "7d" | "30d"
    agora: datetime              # utcnow naive
    publico: bool = False        # True quando os dados vão para o link público (esconde o que expõe o local)


def carregar_contexto(db: Session, customer: Customer, periodo: str, publico: bool = False) -> ContextoDados:
    maquinas = (
        db.query(Machine)
        .options(selectinload(Machine.equipamentos))
        .filter(Machine.customer_id == customer.id, Machine.active == True)
        .order_by(Machine.queue_order, Machine.name)
        .all()
    )
    return ContextoDados(
        db=db,
        customer=customer,
        maquinas=maquinas,
        periodo=periodo,
        agora=datetime.utcnow(),
        publico=publico,
    )


PERIODO_HORAS = {"24h": 24, "7d": 168, "30d": 720}


def filtrar_maquinas(ctx: ContextoDados, ids: List[UUID]) -> List[Machine]:
    if not ids:
        return ctx.maquinas
    id_set = set(ids)
    return [m for m in ctx.maquinas if m.id in id_set]


def equipamentos_ativos(maquina: Machine) -> List[NVR]:
    return [e for e in maquina.equipamentos if e.active]


def contar_cameras(equipamento: NVR) -> Dict[str, int]:
    raw = equipamento.last_recording_status
    if not isinstance(raw, list):
        return {"total": 0, "online": 0, "offline": 0, "sem_gravacao": 0}

    total = 0
    online = 0
    offline = 0
    sem_gravacao = 0

    for cam in raw:
        if not isinstance(cam, dict):
            continue
        total += 1
        comunicacao = cam.get("status_comunicacao") or ("ONLINE" if cam.get("online") else "OFFLINE")
        gravacao = cam.get("status_gravacao")
        if comunicacao == "ONLINE":
            online += 1
            if gravacao == "SEM_GRAVACAO":
                sem_gravacao += 1
        else:
            offline += 1

    return {"total": total, "online": online, "offline": offline, "sem_gravacao": sem_gravacao}


def contar_status_cameras(equipamento: NVR) -> Dict[str, int]:
    raw = equipamento.last_recording_status
    if not isinstance(raw, list):
        return {"total": 0, "gravando": 0, "sem_gravacao": 0, "nao_verificado": 0, "offline": 0}

    total = 0
    gravando = 0
    sem_gravacao = 0
    nao_verificado = 0
    offline = 0

    for cam in raw:
        if not isinstance(cam, dict):
            continue
        total += 1
        comunicacao = cam.get("status_comunicacao") or ("ONLINE" if cam.get("online") else "OFFLINE")
        gravacao = cam.get("status_gravacao")
        if comunicacao != "ONLINE":
            offline += 1
        elif gravacao == "COM_GRAVACAO":
            gravando += 1
        elif gravacao == "SEM_GRAVACAO":
            sem_gravacao += 1
        else:
            nao_verificado += 1

    return {
        "total": total,
        "gravando": gravando,
        "sem_gravacao": sem_gravacao,
        "nao_verificado": nao_verificado,
        "offline": offline,
    }


def iso(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat() + "Z"


def segundos_desde(agora: datetime, dt: Optional[datetime]) -> Optional[int]:
    if dt is None:
        return None
    if agora.tzinfo is not None:
        agora = agora.astimezone(timezone.utc).replace(tzinfo=None)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    diff = int((agora - dt).total_seconds())
    return max(0, diff)


def telemetria_publica(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    out: Dict[str, Any] = {}

    chaves_escalares = (
        "cpu_percent", "ram_percent", "ram_used_gb", "ram_total_gb",
        "disk_percent", "disk_free_gb", "disk_total_gb",
        "gpu_percent", "gpu_memory_used", "gpu_memory_total",
    )
    for k in chaves_escalares:
        v = raw.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = v

    if isinstance(raw.get("gpu_name"), str):
        out["gpu_name"] = str(raw["gpu_name"])[:120]

    disks_raw = raw.get("disks")
    if isinstance(disks_raw, list):
        disks_out = []
        for d in disks_raw[:16]:
            if isinstance(d, dict):
                item_d: Dict[str, Any] = {}
                dev = d.get("device") or d.get("mountpoint")
                if dev:
                    item_d["device"] = str(dev)[:40]
                if isinstance(d.get("fstype"), str):
                    item_d["fstype"] = str(d["fstype"])[:20]
                for nk in ("percent", "total_gb", "used_gb", "free_gb"):
                    nv = d.get(nk)
                    if isinstance(nv, (int, float)) and not isinstance(nv, bool):
                        item_d[nk] = nv
                disks_out.append(item_d)
        out["disks"] = disks_out

    nets_raw = raw.get("networks")
    if isinstance(nets_raw, list):
        nets_out = []
        for n in nets_raw[:16]:
            if isinstance(n, dict):
                item_n: Dict[str, Any] = {}
                nm = n.get("name")
                if nm:
                    item_n["name"] = str(nm)[:80]
                for nk in ("mbps_sent", "mbps_recv"):
                    nv = n.get(nk)
                    if isinstance(nv, (int, float)) and not isinstance(nv, bool):
                        item_n[nk] = nv
                nets_out.append(item_n)
        out["networks"] = nets_out

    return out


STATUS_DISCO_OK = ("OK", "REPOUSO")
LIMITE_DISCO_CHEIO = 90


def disco_com_problema(d: Dict[str, Any]) -> bool:
    status = str(d.get("status") or "").upper()
    status_ruim = bool(status and status not in STATUS_DISCO_OK)
    pct = d.get("percent")
    pct_cheio = isinstance(pct, (int, float)) and not isinstance(pct, bool) and pct >= LIMITE_DISCO_CHEIO
    return status_ruim or pct_cheio


def telemetria_equipamento_publica(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None

    cpu_val = raw.get("cpu_percent")
    cpu_percent = cpu_val if isinstance(cpu_val, (int, float)) and not isinstance(cpu_val, bool) else None

    ram_val = raw.get("ram_percent")
    ram_percent = ram_val if isinstance(ram_val, (int, float)) and not isinstance(ram_val, bool) else None

    uptime_val = raw.get("uptime_seconds")
    uptime_seconds = uptime_val if isinstance(uptime_val, (int, float)) and not isinstance(uptime_val, bool) else None

    disks_raw = raw.get("disks")
    disks_out: List[Dict[str, Any]] = []
    if isinstance(disks_raw, list):
        for d in disks_raw[:32]:
            if not isinstance(d, dict):
                continue
            item_d: Dict[str, Any] = {}
            dev = d.get("device")
            if dev is not None:
                item_d["device"] = str(dev)[:40]
            st = d.get("status")
            item_d["status"] = str(st).upper()[:30] if st is not None else None
            for nk in ("percent", "total_gb", "free_gb", "power_on_days", "temperature_c"):
                nv = d.get(nk)
                item_d[nk] = nv if isinstance(nv, (int, float)) and not isinstance(nv, bool) else None
            disks_out.append(item_d)

    ram_total_val = raw.get("ram_total_gb")
    ram_total_gb = ram_total_val if isinstance(ram_total_val, (int, float)) and not isinstance(ram_total_val, bool) else None

    ram_used_val = raw.get("ram_used_gb")
    ram_used_gb = ram_used_val if isinstance(ram_used_val, (int, float)) and not isinstance(ram_used_val, bool) else None

    networks_raw = raw.get("networks")
    networks_out: List[Dict[str, Any]] = []
    if isinstance(networks_raw, list):
        for n in networks_raw[:8]:
            if not isinstance(n, dict):
                continue
            item_n: Dict[str, Any] = {}
            for k in ("name", "ip", "mac", "status"):
                if n.get(k) is not None:
                    item_n[k] = str(n[k])[:50]
            for k in ("speed_mbps", "recv_mbps", "sent_mbps"):
                v = n.get(k)
                item_n[k] = v if isinstance(v, (int, float)) and not isinstance(v, bool) else None
            networks_out.append(item_n)

    if (
        cpu_percent is None
        and ram_percent is None
        and uptime_seconds is None
        and not disks_out
        and not networks_out
    ):
        return None

    return {
        "cpu_percent": cpu_percent,
        "ram_percent": ram_percent,
        "ram_total_gb": ram_total_gb,
        "ram_used_gb": ram_used_gb,
        "uptime_seconds": uptime_seconds,
        "disks": disks_out,
        "networks": networks_out,
    }


def equipamento_tem_problema(t: Dict[str, Any]) -> bool:
    for d in t.get("disks") or []:
        if isinstance(d, dict) and disco_com_problema(d):
            return True
    for k in ("cpu_percent", "ram_percent"):
        v = t.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 90:
            return True
    return False


def ultimo_backup_por_maquina(ctx: ContextoDados) -> Dict[UUID, Backup]:
    if not ctx.maquinas:
        return {}
    maq_ids = [m.id for m in ctx.maquinas]
    limite = ctx.agora - timedelta(days=45)
    rows = (
        ctx.db.query(Backup)
        .filter(Backup.machine_id.in_(maq_ids), Backup.created_at >= limite)
        .order_by(Backup.created_at.desc())
        .all()
    )
    resultado: Dict[UUID, Backup] = {}
    for b in rows:
        if b.machine_id not in resultado:
            resultado[b.machine_id] = b
    return resultado


def status_equipamento(backup: Optional[Backup], nome: str) -> Optional[str]:
    if backup is None or not isinstance(backup.nvr_results, list):
        return None
    for item in backup.nvr_results:
        if isinstance(item, dict) and item.get("nome") == nome:
            return item.get("status")
    return None


# ─── Resumo ─────────────────────────────────────────────────────────────
class ConfigResumo(BaseModel):
    model_config = {"extra": "forbid"}


def construir_resumo(ctx: ContextoDados, config: ConfigResumo) -> Dict[str, Any]:
    maquinas_total = len(ctx.maquinas)
    maquinas_online = sum(1 for m in ctx.maquinas if check_machine_online(m))
    maquinas_offline = maquinas_total - maquinas_online
    backups_ok = sum(1 for m in ctx.maquinas if m.last_backup_status == "OK")
    backups_com_falha = sum(1 for m in ctx.maquinas if m.last_backup_status in ("PARTIAL", "ERROR"))
    sem_backup = sum(1 for m in ctx.maquinas if m.last_backup_status is None)

    equipamentos_total = 0
    cameras_total = 0
    cameras_online = 0
    cameras_offline = 0
    cameras_sem_gravacao = 0

    gravadores_com_telemetria = 0
    discos_total = 0
    discos_com_problema = 0
    antenas_total = 0
    antenas_online = 0

    for m in ctx.maquinas:
        for e in equipamentos_ativos(m):
            equipamentos_total += 1
            if (e.tipo or "").upper() == "ANTENA":
                ant = antena_publico(e.antena_status, ctx.agora)
                if ant:
                    antenas_total += ant["total"]
                    antenas_online += ant["online"]
            cnt = contar_cameras(e)
            cameras_total += cnt["total"]
            cameras_online += cnt["online"]
            cameras_offline += cnt["offline"]
            cameras_sem_gravacao += cnt["sem_gravacao"]

            t = telemetria_equipamento_publica(e.last_telemetry_status)
            if t is not None:
                gravadores_com_telemetria += 1
                disks = t.get("disks") or []
                discos_total += len(disks)
                for d in disks:
                    if disco_com_problema(d):
                        discos_com_problema += 1

    return {
        "maquinas_total": maquinas_total,
        "maquinas_online": maquinas_online,
        "maquinas_offline": maquinas_offline,
        "backups_ok": backups_ok,
        "backups_com_falha": backups_com_falha,
        "sem_backup": sem_backup,
        "equipamentos_total": equipamentos_total,
        "cameras_total": cameras_total,
        "cameras_online": cameras_online,
        "cameras_offline": cameras_offline,
        "cameras_sem_gravacao": cameras_sem_gravacao,
        "gravadores_com_telemetria": gravadores_com_telemetria,
        "discos_total": discos_total,
        "discos_com_problema": discos_com_problema,
        "antenas_total": antenas_total,
        "antenas_online": antenas_online,
    }


# ─── Saúde do Servidor ──────────────────────────────────────────────────
class ConfigSaudeServidor(BaseModel):
    model_config = {"extra": "forbid"}
    maquinas: List[UUID] = Field(default_factory=list, max_length=200)


def construir_saude_servidor(ctx: ContextoDados, config: ConfigSaudeServidor) -> Dict[str, Any]:
    maqs = filtrar_maquinas(ctx, config.maquinas)
    itens = [
        {
            "id": str(m.id),
            "nome": m.name,
            "online": check_machine_online(m),
            "ultimo_contato": iso(m.last_seen),
            "segundos_desde_contato": segundos_desde(ctx.agora, m.last_seen),
            "telemetria": telemetria_publica(m.telemetry),
        }
        for m in maqs
    ]
    return {"maquinas": itens}


# ─── Status dos Backups ─────────────────────────────────────────────────
class ConfigStatusBackups(BaseModel):
    model_config = {"extra": "forbid"}
    maquinas: List[UUID] = Field(default_factory=list, max_length=200)


def construir_status_backups(ctx: ContextoDados, config: ConfigStatusBackups) -> Dict[str, Any]:
    maqs = filtrar_maquinas(ctx, config.maquinas)
    ultimos = ultimo_backup_por_maquina(ctx)
    itens = []
    for m in maqs:
        ultimo = ultimos.get(m.id)
        eqs = [
            {
                "nome": e.name,
                "tipo": e.tipo or "NVR",
                "status": status_equipamento(ultimo, e.name),
            }
            for e in equipamentos_ativos(m)
        ]
        itens.append({
            "id": str(m.id),
            "nome": m.name,
            "status": m.last_backup_status,
            "ultimo_backup": iso(m.last_backup_at),
            "equipamentos": eqs,
        })
    return {"maquinas": itens}


# ─── Histórico de Backups ───────────────────────────────────────────────
class ConfigHistoricoBackups(BaseModel):
    model_config = {"extra": "forbid"}
    maquinas: List[UUID] = Field(default_factory=list, max_length=200)
    periodo: Optional[Literal["24h", "7d", "30d"]] = None
    visual: Literal["grafico", "tabela"] = "grafico"


def construir_historico_backups(ctx: ContextoDados, config: ConfigHistoricoBackups) -> Dict[str, Any]:
    periodo_efetivo = config.periodo or ctx.periodo
    horas = PERIODO_HORAS.get(periodo_efetivo, 168)
    limite = ctx.agora - timedelta(hours=horas)
    maqs = filtrar_maquinas(ctx, config.maquinas)
    maq_ids = [m.id for m in maqs]
    maq_nomes = {m.id: m.name for m in maqs}

    backups: List[Backup] = []
    if maq_ids:
        backups = (
            ctx.db.query(Backup)
            .filter(Backup.machine_id.in_(maq_ids), Backup.started_at >= limite)
            .order_by(Backup.started_at.desc())
            .all()
        )

    # Agrupamento diário no fuso de Brasília (UTC-3)
    inicio_brt = (limite - timedelta(hours=3)).date()
    fim_brt = (ctx.agora - timedelta(hours=3)).date()
    dias_dict: Dict[str, Dict[str, Any]] = {}
    cur = inicio_brt
    while cur <= fim_brt:
        chave_data = cur.strftime("%Y-%m-%d")
        dias_dict[chave_data] = {"data": chave_data, "ok": 0, "parcial": 0, "erro": 0}
        cur += timedelta(days=1)

    for b in backups:
        if not b.started_at:
            continue
        chave_data = (b.started_at - timedelta(hours=3)).date().strftime("%Y-%m-%d")
        if chave_data in dias_dict:
            if b.status == "OK":
                dias_dict[chave_data]["ok"] += 1
            elif b.status == "PARTIAL":
                dias_dict[chave_data]["parcial"] += 1
            else:
                dias_dict[chave_data]["erro"] += 1

    dias = list(dias_dict.values())

    recentes = []
    for b in backups[:20]:
        duracao_s = (
            int((b.finished_at - b.started_at).total_seconds())
            if (b.finished_at and b.started_at)
            else None
        )
        recentes.append({
            "maquina": maq_nomes.get(b.machine_id, "Desconhecida"),
            "inicio": iso(b.started_at),
            "fim": iso(b.finished_at),
            "status": b.status,
            "duracao_s": duracao_s,
        })

    return {"periodo": periodo_efetivo, "dias": dias, "recentes": recentes}


# ─── Câmeras e Gravação ─────────────────────────────────────────────────
class ConfigCameras(BaseModel):
    model_config = {"extra": "forbid"}
    equipamentos: List[UUID] = Field(default_factory=list, max_length=500)
    apenas_problemas: bool = False


def construir_cameras(ctx: ContextoDados, config: ConfigCameras) -> Dict[str, Any]:
    agora = datetime.utcnow()
    filtro_ids = set(config.equipamentos) if config.equipamentos else None
    itens = []

    for m in ctx.maquinas:
        for e in equipamentos_ativos(m):
            if filtro_ids is not None and e.id not in filtro_ids:
                continue
            raw_cams = e.last_recording_status
            if not isinstance(raw_cams, list) or not raw_cams:
                continue
            valid_cams = [c for c in raw_cams if isinstance(c, dict)]
            if not valid_cams:
                continue

            cnt = contar_cameras(e)
            cameras_lista = []
            tem_problema = False

            for cam in valid_cams[:300]:
                comunicacao = cam.get("status_comunicacao") or ("ONLINE" if cam.get("online") else "OFFLINE")
                gravacao = cam.get("status_gravacao")
                problema = (comunicacao != "ONLINE") or (gravacao == "SEM_GRAVACAO")
                if problema:
                    tem_problema = True
                if config.apenas_problemas and not problema:
                    continue
                seg, aprox = segundos_offline(cam, agora)
                cameras_lista.append({
                    "nome": cam.get("nome") or "Câmera",
                    "comunicacao": comunicacao,
                    "gravacao": gravacao,
                    "offline_segundos": seg,
                    "offline_aprox": aprox,
                })

            if config.apenas_problemas and not tem_problema:
                continue

            itens.append({
                "id": str(e.id),
                "nome": e.name,
                "tipo": e.tipo or "NVR",
                "maquina": m.name,
                "total": cnt["total"],
                "online": cnt["online"],
                "offline": cnt["offline"],
                "sem_gravacao": cnt["sem_gravacao"],
                "cameras": cameras_lista,
            })

    return {"equipamentos": itens}


# ─── Gravadores (CPU, RAM e discos) ────────────────────────────────────
METRICAS_TELEMETRIA = (
    "cpu", "ram", "uptime",
    "disco_uso", "disco_temperatura", "disco_saude", "disco_capacidade", "disco_idade",
)
MetricaTelemetria = Literal[
    "cpu", "ram", "uptime",
    "disco_uso", "disco_temperatura", "disco_saude", "disco_capacidade", "disco_idade",
]


class ConfigTelemetriaEquipamentos(BaseModel):
    model_config = {"extra": "forbid"}
    equipamentos: List[UUID] = Field(default_factory=list, max_length=500)
    apenas_problemas: bool = False
    metricas: List[MetricaTelemetria] = Field(default_factory=list, max_length=8)
    discos: Dict[UUID, List[str]] = Field(default_factory=dict)

    @field_validator("metricas")
    @classmethod
    def _validar_metricas(cls, metricas: List[MetricaTelemetria]) -> List[MetricaTelemetria]:
        vistas = set()
        resultado = []
        for m in metricas:
            if m not in vistas:
                vistas.add(m)
                resultado.append(m)
        return resultado

    @field_validator("discos")
    @classmethod
    def _validar_discos(cls, discos: Dict[UUID, List[str]]) -> Dict[UUID, List[str]]:
        if len(discos) > 500:
            raise ValueError("Número de gravadores em discos não pode exceder 500")
        limpo: Dict[UUID, List[str]] = {}
        for eq_id, nomes in discos.items():
            if len(nomes) > 32:
                raise ValueError(f"Gravador {eq_id} tem mais de 32 discos")
            nomes_unicos = []
            vistos = set()
            for nome in nomes:
                s = (str(nome) if nome is not None else "").strip()[:40]
                if s and s not in vistos:
                    vistos.add(s)
                    nomes_unicos.append(s)
            if nomes_unicos:
                limpo[eq_id] = nomes_unicos
        return limpo


def construir_telemetria_equipamentos(ctx: ContextoDados, config: ConfigTelemetriaEquipamentos) -> Dict[str, Any]:
    metricas = set(config.metricas) if config.metricas else set(METRICAS_TELEMETRIA)
    tem_metrica_disco = any(m.startswith("disco_") for m in metricas)
    filtro_ids = set(config.equipamentos) if config.equipamentos else None
    itens = []

    for m in ctx.maquinas:
        for e in equipamentos_ativos(m):
            if filtro_ids is not None and e.id not in filtro_ids:
                continue
            t = telemetria_equipamento_publica(e.last_telemetry_status)
            if t is None:
                continue
            problema = equipamento_tem_problema(t)
            if config.apenas_problemas and not problema:
                continue

            if not tem_metrica_disco:
                discos_projetados: List[Dict[str, Any]] = []
            else:
                escolhidos = config.discos.get(e.id)
                escolhidos_set = set(escolhidos) if escolhidos else None
                discos_filtrados = [
                    d for d in (t.get("disks") or [])
                    if not escolhidos_set or d.get("device") in escolhidos_set
                ]
                discos_projetados = []
                for d in discos_filtrados:
                    item_d: Dict[str, Any] = {"device": d.get("device")}
                    if "disco_uso" in metricas:
                        item_d["percent"] = d.get("percent")
                    if "disco_temperatura" in metricas:
                        item_d["temperature_c"] = d.get("temperature_c")
                    if "disco_saude" in metricas:
                        item_d["status"] = d.get("status")
                    if "disco_capacidade" in metricas:
                        item_d["total_gb"] = d.get("total_gb")
                        item_d["free_gb"] = d.get("free_gb")
                    if "disco_idade" in metricas:
                        item_d["power_on_days"] = d.get("power_on_days")
                    discos_projetados.append(item_d)

            cpu_val = t["cpu_percent"] if "cpu" in metricas else None
            ram_val = t["ram_percent"] if "ram" in metricas else None
            uptime_val = t["uptime_seconds"] if "uptime" in metricas else None

            itens.append({
                "id": str(e.id),
                "nome": e.name,
                "tipo": e.tipo or "NVR",
                "maquina": m.name,
                "atualizado_em": iso(e.updated_at),
                "cpu_percent": cpu_val,
                "ram_percent": ram_val,
                "uptime_seconds": uptime_val,
                "disks": discos_projetados,
                "tem_problema": problema,
            })

    itens.sort(key=lambda item: 0 if item["tem_problema"] else 1)
    return {
        "metricas": [m for m in METRICAS_TELEMETRIA if m in metricas],
        "equipamentos": itens,
    }


# ─── Equipamentos ───────────────────────────────────────────────────────
class ConfigEquipamentos(BaseModel):
    model_config = {"extra": "forbid"}
    tipos: List[str] = Field(default_factory=list, max_length=50)
    maquinas: List[UUID] = Field(default_factory=list, max_length=200)

    @field_validator("tipos")
    @classmethod
    def _validar_tipos(cls, tipos: List[str]) -> List[str]:
        normalizados = []
        for t in tipos:
            t_norm = (t or "").strip().upper()
            if t_norm not in TIPOS_EQUIPAMENTO:
                raise ValueError(f"Tipo de equipamento inválido: {t}")
            normalizados.append(t_norm)
        return normalizados


def construir_equipamentos(ctx: ContextoDados, config: ConfigEquipamentos) -> Dict[str, Any]:
    maqs = filtrar_maquinas(ctx, config.maquinas)
    ultimos = ultimo_backup_por_maquina(ctx)
    tipos_set = set(config.tipos) if config.tipos else None
    itens = []

    for m in maqs:
        ultimo = ultimos.get(m.id)
        for e in equipamentos_ativos(m):
            tipo_eq = (e.tipo or "NVR").upper()
            if tipos_set is not None and tipo_eq not in tipos_set:
                continue
            itens.append({
                "id": str(e.id),
                "nome": e.name,
                "tipo": tipo_eq,
                "maquina": m.name,
                "status": status_equipamento(ultimo, e.name),
            })

    return {"equipamentos": itens}


# ─── Texto ──────────────────────────────────────────────────────────────
class ConfigTexto(BaseModel):
    model_config = {"extra": "forbid"}
    texto: str = Field("", max_length=1000)


def construir_texto(ctx: ContextoDados, config: ConfigTexto) -> Dict[str, Any]:
    return {"texto": config.texto}


# ─── Status dos NVRs (pizza) ───────────────────────────────────────────
class ConfigStatusNvr(BaseModel):
    model_config = {"extra": "forbid"}
    equipamentos: List[UUID] = Field(default_factory=list, max_length=500)
    visual: Literal["por_equipamento", "agregado"] = "por_equipamento"


def construir_status_nvr(ctx: ContextoDados, config: ConfigStatusNvr) -> Dict[str, Any]:
    filtro_ids = set(config.equipamentos) if config.equipamentos else None
    itens = []

    for m in ctx.maquinas:
        for e in equipamentos_ativos(m):
            if filtro_ids is not None and e.id not in filtro_ids:
                continue
            c = contar_status_cameras(e)
            if c["total"] == 0:
                continue
            itens.append({
                "id": str(e.id),
                "nome": e.name,
                "tipo": e.tipo or "NVR",
                "maquina": m.name,
                **c,
            })

    total_geral = {
        "total": sum(i["total"] for i in itens),
        "gravando": sum(i["gravando"] for i in itens),
        "sem_gravacao": sum(i["sem_gravacao"] for i in itens),
        "nao_verificado": sum(i["nao_verificado"] for i in itens),
        "offline": sum(i["offline"] for i in itens),
    }

    return {
        "visual": config.visual,
        "total": total_geral,
        "equipamentos": itens,
    }


# ─── Auxiliares dos status periódicos (ANTENA, OLT, DEFENSE) ─────────────────
# Esses equipamentos guardam só o último status enviado pelo agente, numa coluna JSON. Cada função `*_publico`
# é a lista branca do que pode sair para o cliente (vale o link público): nada de IP, MAC, serial, texto de erro
# ou `config_extra`. O `nivel` de cada item ("critico" | "atencao" | "ok" | "neutro") define a cor no front.
FORMATO_STATUS = "%Y-%m-%dT%H:%M:%S"
ORDEM_NIVEL = {"critico": 0, "atencao": 1, "ok": 2, "neutro": 3}


def _num(v: Any) -> Optional[float]:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _inteiro(v: Any) -> int:
    n = _num(v)
    return int(n) if n is not None else 0


def _texto(v: Any, limite: int) -> Optional[str]:
    if v is None:
        return None
    t = " ".join(str(v).split())
    return t[:limite] or None


def _data_status(v: Any) -> Optional[datetime]:
    """Datas dos status são texto UTC naive ("2026-11-13T15:00:00"), REGRA-001."""
    if not v:
        return None
    try:
        return datetime.strptime(str(v)[:19], FORMATO_STATUS)
    except ValueError:
        return None


def _atualidade(ctx: ContextoDados, raw: Any, limite_min: int) -> Dict[str, Any]:
    dt = _data_status(raw.get("atualizado_em")) if isinstance(raw, dict) else None
    seg = segundos_desde(ctx.agora, dt)
    return {
        "atualizado_em": iso(dt),
        "segundos_desde_atualizacao": seg,
        "desatualizado": seg is None or seg > limite_min * 60,
    }


def _pior(niveis: List[str]) -> str:
    return min(niveis, key=lambda n: ORDEM_NIVEL.get(n, 9)) if niveis else "ok"


def equipamentos_do_tipo(ctx: ContextoDados, tipo: str, ids: List[UUID]) -> List[tuple]:
    """(máquina, equipamento) ativos do tipo, só das máquinas do cliente; ids de fora são ignorados."""
    filtro = set(ids) if ids else None
    saida = []
    for m in ctx.maquinas:
        for e in equipamentos_ativos(m):
            if (e.tipo or "").upper() != tipo:
                continue
            if filtro is not None and e.id not in filtro:
                continue
            saida.append((m, e))
    return saida


# ─── Antenas Wi-Fi (ANTENA) ─────────────────────────────────────────────
LIMIAR_ANTENA_CRITICA_S = 10 * 60   # igual a LIMIAR_ANTENA_OFFLINE_MIN da notificação
LIMITE_ANTENA_DADOS_MIN = 20        # igual a LIMIAR_ANTENA_SEM_DADOS_MIN (o agente envia a cada 3 min)
SITUACOES_ANTENA = ("ONLINE", "OFFLINE", "SEM_REGISTRO", "ERRO")


def antena_publico(raw: Any, agora: datetime) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    contagem = {"online": 0, "offline": 0, "sem_registro": 0, "erro": 0}
    antenas = []
    for a in (raw.get("antenas") or [])[:200]:
        if not isinstance(a, dict):
            continue
        status = str(a.get("status") or "").upper()
        if status not in SITUACOES_ANTENA:
            status = "ERRO"
        contagem[status.lower()] += 1
        fora_s = None
        if status != "ONLINE":
            fora_s = segundos_desde(agora, _data_status(a.get("offline_desde")))
        if status == "ONLINE":
            nivel = "ok"
        elif status in ("OFFLINE", "ERRO") and fora_s is not None and fora_s > LIMIAR_ANTENA_CRITICA_S:
            nivel = "critico"
        else:
            nivel = "atencao"
        antenas.append({
            "nome": _texto(a.get("nome"), 120) or "Antena",
            "marca": _texto(a.get("marca"), 40),
            "status": status,
            "nivel": nivel,
            "ping_ms": _num(a.get("ping_ms")),
            "fora_segundos": fora_s,
            "ultimo_online": iso(_data_status(a.get("ultimo_online"))),
        })
    antenas.sort(key=lambda x: (ORDEM_NIVEL[x["nivel"]], -(x["fora_segundos"] or 0), x["nome"].lower()))
    return {
        "falha_leitura": bool(raw.get("erro")),
        "total": len(antenas),
        **contagem,
        "antenas": antenas,
    }


class ConfigAntenas(BaseModel):
    model_config = {"extra": "forbid"}
    equipamentos: List[UUID] = Field(default_factory=list, max_length=200)
    mostrar_latencia: bool = True


def construir_antenas(ctx: ContextoDados, config: ConfigAntenas) -> Dict[str, Any]:
    total = {"total": 0, "online": 0, "offline": 0, "sem_registro": 0, "erro": 0}
    itens = []
    for m, e in equipamentos_do_tipo(ctx, "ANTENA", config.equipamentos):
        dados = antena_publico(e.antena_status, ctx.agora)
        atual = _atualidade(ctx, e.antena_status, LIMITE_ANTENA_DADOS_MIN)
        antenas = (dados or {}).get("antenas") or []
        if not config.mostrar_latencia:
            for a in antenas:
                a.pop("ping_ms", None)
        niveis = [a["nivel"] for a in antenas]
        if dados is None or dados["falha_leitura"] or atual["desatualizado"]:
            niveis.append("atencao")
        for k in total:
            total[k] += (dados or {}).get(k, 0)
        itens.append({
            "id": str(e.id),
            "nome": e.name,
            "maquina": m.name,
            **atual,
            "sem_status": dados is None,
            "falha_leitura": bool(dados and dados["falha_leitura"]),
            "total": (dados or {}).get("total", 0),
            "online": (dados or {}).get("online", 0),
            "nivel": _pior(niveis),
            "antenas": antenas,
        })
    itens.sort(key=lambda x: (ORDEM_NIVEL[x["nivel"]], x["nome"].lower()))
    return {"mostrar_latencia": config.mostrar_latencia, "total": total, "equipamentos": itens}


# ─── OLTs e ONUs (OLT) ──────────────────────────────────────────────────
LIMITE_OLT_DADOS_MIN = 15           # o agente envia a cada 5 min
LIMIAR_OLT_FORA_PCT = 5             # mais que isso de ONUs fora (offline + falha + sem energia) = vermelho
LIMIAR_LICENCA_ATENCAO_DIAS = 10    # igual a LIMIAR_LICENCA_DIAS da notificação
CHAVES_CONTAGEM_ONU = ("total", "online", "offline", "falha", "sem_energia", "sinal_ruim")


def _contagem_onus(raw: Any) -> Dict[str, int]:
    raw = raw if isinstance(raw, dict) else {}
    return {k: _inteiro(raw.get(k)) for k in CHAVES_CONTAGEM_ONU}


def olt_publico(raw: Any, nome_padrao: str) -> List[Dict[str, Any]]:
    """Uma entrada por OLT, só com contagens (sem ONU individual, serial, MAC, IP nem nome de assinante)."""
    if not isinstance(raw, dict):
        return []
    olts = []
    for o in (raw.get("olts") or [])[:32]:
        if not isinstance(o, dict):
            continue
        falha = bool(o.get("erro"))
        totais = _contagem_onus(o.get("totais"))
        fora = totais["offline"] + totais["falha"] + totais["sem_energia"]
        pct = round(fora * 100 / totais["total"], 1) if totais["total"] else 0.0
        pons = []
        for p in o.get("por_pon") or []:
            if not isinstance(p, dict):
                continue
            c = _contagem_onus(p)
            if c["offline"] + c["falha"] + c["sem_energia"] + c["sinal_ruim"] == 0:
                continue
            pons.append({"slot": _inteiro(p.get("slot")), "pon": _inteiro(p.get("pon")), **c})
        pons.sort(key=lambda p: (-(p["offline"] + p["falha"] + p["sem_energia"]), -p["sinal_ruim"], p["slot"], p["pon"]))
        if falha or pct > LIMIAR_OLT_FORA_PCT:
            nivel = "critico"
        elif fora or totais["sinal_ruim"]:
            nivel = "atencao"
        else:
            nivel = "ok"
        olts.append({
            "nome": _texto(o.get("nome"), 120) or nome_padrao,
            "fabricante": _texto(o.get("fabricante"), 30),
            "modelo": _texto(o.get("modelo"), 60),
            "falha_leitura": falha,
            "temperatura": _num(o.get("temperatura")),
            "totais": totais,
            "percentual_fora": pct,
            "pons": pons[:64],
            "pons_com_problema": len(pons),
            "nivel": nivel,
        })
    olts.sort(key=lambda x: (ORDEM_NIVEL[x["nivel"]], x["nome"].lower()))
    return olts


class ConfigStatusOlt(BaseModel):
    model_config = {"extra": "forbid"}
    equipamentos: List[UUID] = Field(default_factory=list, max_length=200)
    mostrar_pons: bool = True
    mostrar_licenca: bool = True


def construir_status_olt(ctx: ContextoDados, config: ConfigStatusOlt) -> Dict[str, Any]:
    from services.licenca_unm import licenca_da_config

    total = {k: 0 for k in CHAVES_CONTAGEM_ONU}
    itens = []
    for m, e in equipamentos_do_tipo(ctx, "OLT", config.equipamentos):
        olts = olt_publico(e.olt_status, e.name)
        if not config.mostrar_pons:
            for o in olts:
                o["pons"] = []
        atual = _atualidade(ctx, e.olt_status, LIMITE_OLT_DADOS_MIN)
        licenca = None
        if config.mostrar_licenca:
            lic = licenca_da_config(e.config_extra)
            if lic:
                dias = lic["dias_restantes"]
                licenca = {
                    "fim": lic["fim"],
                    "dias_restantes": dias,
                    "nivel": "critico" if dias < 0 else "atencao" if dias <= LIMIAR_LICENCA_ATENCAO_DIAS else "ok",
                }
        niveis = [o["nivel"] for o in olts]
        if licenca:
            niveis.append(licenca["nivel"])
        if not olts or atual["desatualizado"]:
            niveis.append("atencao")
        for o in olts:
            for k in total:
                total[k] += o["totais"][k]
        itens.append({
            "id": str(e.id),
            "nome": e.name,
            "maquina": m.name,
            **atual,
            "sem_status": not isinstance(e.olt_status, dict),
            "licenca": licenca,
            "nivel": _pior(niveis),
            "olts": olts,
        })
    itens.sort(key=lambda x: (ORDEM_NIVEL[x["nivel"]], x["nome"].lower()))
    return {"total": total, "equipamentos": itens}


# ─── Centrais de alarme (DEFENSE) ───────────────────────────────────────
LIMITE_ALARME_DADOS_MIN = 20        # igual a LIMIAR_ALARME_SEM_DADOS_MIN (o agente envia a cada 5 min)


def alarme_publico(raw: Any, publico: bool) -> Optional[Dict[str, Any]]:
    """Centrais e partições. No link público não sai se a partição está armada (diria quando o local está
    desprotegido): só disparo e desconexão."""
    if not isinstance(raw, dict):
        return None
    centrais = []
    totais = {"centrais": 0, "desconectadas": 0, "disparos": 0, "particoes": 0, "armadas": 0}
    for c in (raw.get("alarmes") or [])[:50]:
        if not isinstance(c, dict):
            continue
        conectada = c.get("status") == 1
        particoes = []
        disparos = 0
        for p in (c.get("particoes") or [])[:32]:
            if not isinstance(p, dict):
                continue
            disparada = bool(p.get("disparada"))
            armada = bool(p.get("armada"))
            disparos += disparada
            totais["particoes"] += 1
            totais["armadas"] += armada
            item = {"nome": _texto(p.get("nome"), 80) or "Partição", "disparada": disparada}
            if not publico:
                item["armada"] = armada
            particoes.append(item)
        particoes.sort(key=lambda p: (not p["disparada"], p["nome"].lower()))
        totais["centrais"] += 1
        totais["desconectadas"] += not conectada
        totais["disparos"] += disparos
        centrais.append({
            "nome": _texto(c.get("nome"), 120) or "Central de alarme",
            "modelo": _texto(c.get("modelo"), 40),
            "conectada": conectada,
            "disparos": disparos,
            "nivel": "critico" if disparos else "atencao" if not conectada else "ok",
            "particoes": particoes,
        })
    centrais.sort(key=lambda x: (ORDEM_NIVEL[x["nivel"]], x["nome"].lower()))
    incendio = [
        {"nome": _texto(i.get("nome"), 120) or "Central de incêndio", "modelo": _texto(i.get("modelo"), 40)}
        for i in (raw.get("incendio") or [])[:50]
        if isinstance(i, dict)
    ]
    if publico:
        totais.pop("armadas")
    return {"falha_leitura": bool(raw.get("erro")), "totais": totais, "centrais": centrais, "incendio": incendio}


class ConfigAlarmesDefense(BaseModel):
    model_config = {"extra": "forbid"}
    equipamentos: List[UUID] = Field(default_factory=list, max_length=200)
    mostrar_particoes: bool = True
    mostrar_incendio: bool = True


def construir_alarmes_defense(ctx: ContextoDados, config: ConfigAlarmesDefense) -> Dict[str, Any]:
    total = {"centrais": 0, "desconectadas": 0, "disparos": 0}
    itens = []
    for m, e in equipamentos_do_tipo(ctx, "DEFENSE", config.equipamentos):
        dados = alarme_publico(e.last_alarm_status, ctx.publico)
        atual = _atualidade(ctx, e.last_alarm_status, LIMITE_ALARME_DADOS_MIN)
        centrais = (dados or {}).get("centrais") or []
        if not config.mostrar_particoes:
            for c in centrais:
                c["particoes"] = []
        niveis = [c["nivel"] for c in centrais]
        if dados is None or dados["falha_leitura"] or atual["desatualizado"]:
            niveis.append("atencao")
        if dados:
            for k in total:
                total[k] += dados["totais"][k]
        itens.append({
            "id": str(e.id),
            "nome": e.name,
            "maquina": m.name,
            **atual,
            "sem_status": dados is None,
            "falha_leitura": bool(dados and dados["falha_leitura"]),
            "nivel": _pior(niveis),
            "centrais": centrais,
            "incendio": (dados or {}).get("incendio", []) if config.mostrar_incendio else [],
        })
    itens.sort(key=lambda x: (ORDEM_NIVEL[x["nivel"]], x["nome"].lower()))
    return {"mostra_armada": not ctx.publico, "total": total, "equipamentos": itens}


# ─── Registro dos tipos de widget ──────────────────────────────────────────
registrar(TipoWidget(
    tipo="resumo",
    rotulo="Resumo",
    descricao="Visão geral de máquinas, backups e câmeras do cliente",
    config_model=ConfigResumo,
    largura_padrao=12,
    altura_padrao=3,
    construir=construir_resumo,
))

registrar(TipoWidget(
    tipo="saude_servidor",
    rotulo="Saúde do servidor",
    descricao="Medidores de CPU, RAM, disco, rede e GPU das máquinas",
    config_model=ConfigSaudeServidor,
    largura_padrao=12,
    altura_padrao=9,
    construir=construir_saude_servidor,
))

registrar(TipoWidget(
    tipo="status_backups",
    rotulo="Status dos backups",
    descricao="Último status de backup por máquina e por equipamento",
    config_model=ConfigStatusBackups,
    largura_padrao=6,
    altura_padrao=6,
    construir=construir_status_backups,
))

registrar(TipoWidget(
    tipo="historico_backups",
    rotulo="Histórico de backups",
    descricao="Histórico de execuções com taxa de sucesso e duração",
    config_model=ConfigHistoricoBackups,
    largura_padrao=6,
    altura_padrao=6,
    construir=construir_historico_backups,
))

registrar(TipoWidget(
    tipo="cameras",
    rotulo="Câmeras e gravação",
    descricao="Status de comunicação e gravação das câmeras",
    config_model=ConfigCameras,
    largura_padrao=6,
    altura_padrao=6,
    construir=construir_cameras,
))

registrar(TipoWidget(
    tipo="telemetria_equipamentos",
    rotulo="Gravadores (CPU, RAM e discos)",
    descricao="Telemetria dos gravadores (NVR/DVR) personalizável: escolha CPU, memória, tempo ligado e, por disco, uso, temperatura, saúde, capacidade e idade",
    config_model=ConfigTelemetriaEquipamentos,
    largura_padrao=6,
    altura_padrao=6,
    construir=construir_telemetria_equipamentos,
))

registrar(TipoWidget(
    tipo="equipamentos",
    rotulo="Equipamentos",
    descricao="Lista de equipamentos cadastrados por tipo",
    config_model=ConfigEquipamentos,
    largura_padrao=6,
    altura_padrao=6,
    construir=construir_equipamentos,
))

registrar(TipoWidget(
    tipo="texto",
    rotulo="Texto",
    descricao="Bloco de texto livre ou aviso institucional",
    config_model=ConfigTexto,
    largura_padrao=4,
    altura_padrao=3,
    construir=construir_texto,
))

registrar(TipoWidget(
    tipo="status_nvr",
    rotulo="Status dos NVRs (pizza)",
    descricao="Gráfico de pizza com a situação das câmeras de cada NVR: gravando, sem gravação, offline e não verificado",
    config_model=ConfigStatusNvr,
    largura_padrao=6,
    altura_padrao=8,
    construir=construir_status_nvr,
))

registrar(TipoWidget(
    tipo="antenas",
    rotulo="Antenas Wi-Fi",
    descricao="Antenas online e fora do ar (com há quanto tempo), problemas primeiro",
    config_model=ConfigAntenas,
    largura_padrao=6,
    altura_padrao=6,
    construir=construir_antenas,
))

registrar(TipoWidget(
    tipo="status_olt",
    rotulo="OLTs e ONUs",
    descricao="ONUs online, fora do ar e com sinal ruim por OLT, PONs com problema e licença da UNM2000",
    config_model=ConfigStatusOlt,
    largura_padrao=6,
    altura_padrao=7,
    construir=construir_status_olt,
))

registrar(TipoWidget(
    tipo="alarmes_defense",
    rotulo="Centrais de alarme",
    descricao="Disparos, centrais desconectadas e partições das centrais de alarme do Defense",
    config_model=ConfigAlarmesDefense,
    largura_padrao=6,
    altura_padrao=6,
    construir=construir_alarmes_defense,
))
