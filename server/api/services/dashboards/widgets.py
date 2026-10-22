from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session, selectinload

from models import Backup, Customer, Machine, NVR
from routers.machines import check_machine_online
from schemas import TIPOS_EQUIPAMENTO
from .registro import TipoWidget, registrar


@dataclass
class ContextoDados:
    db: Session
    customer: Customer
    maquinas: List[Machine]      # só as máquinas ATIVAS do cliente, com equipamentos já carregados
    periodo: str                 # filtro global: "24h" | "7d" | "30d"
    agora: datetime              # utcnow naive


def carregar_contexto(db: Session, customer: Customer, periodo: str) -> ContextoDados:
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
            for nk in ("percent", "total_gb", "free_gb"):
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

    if cpu_percent is None and ram_percent is None and not disks_out and not networks_out:
        return None

    return {
        "cpu_percent": cpu_percent,
        "ram_percent": ram_percent,
        "ram_total_gb": ram_total_gb,
        "ram_used_gb": ram_used_gb,
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

    for m in ctx.maquinas:
        for e in equipamentos_ativos(m):
            equipamentos_total += 1
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
                cameras_lista.append({
                    "nome": cam.get("nome") or "Câmera",
                    "comunicacao": comunicacao,
                    "gravacao": gravacao,
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
class ConfigTelemetriaEquipamentos(BaseModel):
    model_config = {"extra": "forbid"}
    equipamentos: List[UUID] = Field(default_factory=list, max_length=500)
    apenas_problemas: bool = False


def construir_telemetria_equipamentos(ctx: ContextoDados, config: ConfigTelemetriaEquipamentos) -> Dict[str, Any]:
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
            itens.append({
                "id": str(e.id),
                "nome": e.name,
                "tipo": e.tipo or "NVR",
                "maquina": m.name,
                "atualizado_em": iso(e.updated_at),
                "cpu_percent": t["cpu_percent"],
                "ram_percent": t["ram_percent"],
                "disks": t["disks"],
                "tem_problema": problema,
            })

    itens.sort(key=lambda item: 0 if item["tem_problema"] else 1)
    return {"equipamentos": itens}


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
    descricao="CPU, memória e discos dos gravadores (NVR/DVR) com alerta de disco com problema ou cheio",
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
