import base64
import binascii
import re
import smtplib
import logging
import time
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from typing import List, Optional
from sqlalchemy.orm import Session

from config import settings
from models import NVR, NVRCamera, Setting
from services.camera_offline import formatar_offline_ha, segundos_offline

logger = logging.getLogger(__name__)

LIMIT_ATTACH_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_OFFLINE_IMAGES = 10  # máx. de imagens de referência (câmeras offline) anexadas por e-mail


def _norm_status(r: dict) -> str:
    """Normaliza o status de um resultado de equipamento para OK / PARCIAL / ERRO.

    Aceita PARTIAL/ERROR (inglês) e PARCIAL/ERRO; demais valores (ex: SEM_ARQUIVOS)
    são mantidos em maiúsculas. Status ausente vira string vazia.
    """
    st = str(r.get("status") or "").strip().upper()
    if st == "PARTIAL":
        return "PARCIAL"
    if st == "ERROR":
        return "ERRO"
    return st


def _build_backup_section(nvr_results: List[dict], overall: str) -> str:
    """Seção 2 do e-mail — Backup dos equipamentos."""
    icon_map = {"OK": "✅", "PARCIAL": "⚠️", "PARTIAL": "⚠️", "ERRO": "❌", "ERROR": "❌", "SEM_ARQUIVOS": "ℹ️"}

    lines = "\n".join(
        f"  {icon_map.get(_norm_status(r), '❓')} {r.get('nome', '?')}: "
        f"{'OK' if _norm_status(r) == 'OK' else 'Gravações OK (Backup de config. não suportado)' if _norm_status(r) == 'SEM_ARQUIVOS' else 'FALHA — ' + (_norm_status(r) or 'DESCONHECIDO')}"
        for r in nvr_results
    )

    return (
        f"\n2. Backup de Equipamentos (NVR, PABX, Mikrotik...)\n"
        f"{'─' * 40}\n"
        f"Backup automático de configurações\n"
        f"Total de equipamentos: {len(nvr_results)}\n"
        f"Status geral: {overall}\n\n"
        f"Resultado por equipamento:\n{lines}\n"
    )


def _build_camera_section(nvr_results: List[dict]) -> str:
    """Seção 1 do e-mail — Verificação de Câmeras e Gravações."""
    total_nvrs = len(nvr_results)
    total_cameras = 0
    cameras_online = 0
    cameras_offline = 0
    cameras_online_sem_gravacao = 0
    problemas_por_nvr: dict[str, list[str]] = {}

    for r in nvr_results:
        cameras = r.get("cameras") or []
        nvr_nome = r.get("nome", "?")
        problemas: list[str] = []

        for cam in cameras:
            total_cameras += 1
            cam_nome = cam.get("nome", f"Canal {cam.get('canal', '?')}")

            # Novos status normalizados (Fallback para clientes antigos)
            status_comunicacao = cam.get("status_comunicacao")
            if not status_comunicacao:
                online = cam.get("online")
                status_comunicacao = "ONLINE" if online else "OFFLINE" if online is False else "DESCONHECIDO"
                
            status_gravacao = cam.get("status_gravacao")
            if not status_gravacao:
                total_dias = cam.get("total_dias", 0)
                mapa = cam.get("mapa", "")
                gravou_hoje = (mapa[-1] in ("█", "▒")) if mapa else (total_dias > 0)
                status_gravacao = "COM_GRAVACAO" if gravou_hoje else "SEM_GRAVACAO"

            if status_comunicacao == "ONLINE":
                cameras_online += 1
                if status_gravacao == "SEM_GRAVACAO":
                    cameras_online_sem_gravacao += 1
                    problemas.append(f"  ⚠️ {cam_nome}: Online, mas sem gravação")
                elif status_gravacao == "NAO_VERIFICADO":
                    problemas.append(f"  ⚠️ {cam_nome}: Online, mas falhou ao verificar histórico de gravação")
            else:
                cameras_offline += 1
                linha_offline = f"  ❌ {cam_nome}: Offline ({status_comunicacao})"
                if cam.get("offline_desde"):
                    seg, aprox = segundos_offline(cam, datetime.utcnow())
                    if seg is not None:
                        linha_offline += f" — offline {formatar_offline_ha(seg, aprox)}"
                problemas.append(linha_offline)

        if problemas:
            problemas_por_nvr[nvr_nome] = problemas

    section = (
        f"\n1. Verificação de Câmeras dos CFTVs\n"
        f"{'─' * 40}\n"
        f"Verificação das câmeras dos equipamentos compatíveis\n"
        f"Total de equipamentos verificados (com câmeras): {len(problemas_por_nvr) if problemas_por_nvr else (total_nvrs if total_cameras > 0 else 0)}\n"
        f"Total de câmeras: {total_cameras}\n"
        f"Câmeras online: {cameras_online}\n"
        f"Câmeras offline: {cameras_offline}\n"
        f"Câmeras online sem gravação: {cameras_online_sem_gravacao}\n"
    )

    if problemas_por_nvr:
        section += f"\nCâmeras com problemas:\n"
        for nvr_nome, probs in problemas_por_nvr.items():
            section += f"\n  {nvr_nome}:\n"
            section += "\n".join(probs) + "\n"
    elif total_cameras > 0:
        section += f"\n✅ Todas as câmeras estão online e gravando.\n"
    else:
        section += f"\nℹ️ Nenhum equipamento do tipo CFTV verificado neste ciclo.\n"

    return section


def _build_result_section(nvr_results: List[dict]) -> str:
    """Seção 3 do e-mail — Resultado do Serviço."""
    has_cameras = any(r.get("cameras") for r in nvr_results)

    backup_ok = all(_norm_status(r) == "OK" for r in nvr_results)
    has_unsupported_backup = any(_norm_status(r) == "SEM_ARQUIVOS" for r in nvr_results)
    
    if backup_ok:
        backup_icon = "✅ Concluído"
    elif has_unsupported_backup and all(_norm_status(r) in ("OK", "SEM_ARQUIVOS") for r in nvr_results):
        backup_icon = "ℹ️ Concluído (alguns equipamentos não suportam backup de arquivo)"
    else:
        backup_icon = "⚠️ Concluído com ressalvas"

    if has_cameras:
        all_cameras = [cam for r in nvr_results for cam in (r.get("cameras") or [])]
        any_offline = False
        any_no_rec = False
        
        for cam in all_cameras:
            status_comunicacao = cam.get("status_comunicacao")
            if not status_comunicacao:
                status_comunicacao = "ONLINE" if cam.get("online") else "OFFLINE"
                
            if status_comunicacao != "ONLINE":
                any_offline = True
            
            if status_comunicacao == "ONLINE":
                status_gravacao = cam.get("status_gravacao")
                if not status_gravacao:
                    mapa = cam.get("mapa", "")
                    gravou_hoje = (mapa[-1] in ("█", "▒")) if mapa else (cam.get("total_dias", 0) > 0)
                    status_gravacao = "COM_GRAVACAO" if gravou_hoje else "SEM_GRAVACAO"
                    
                if status_gravacao in ("SEM_GRAVACAO", "NAO_VERIFICADO"):
                    any_no_rec = True

        cam_icon = "⚠️ Concluída com problemas" if any_offline else "✅ Concluída"
        rec_icon = "⚠️ Concluída com problemas" if (any_offline or any_no_rec) else "✅ Concluída"
    else:
        cam_icon = "ℹ️ Sem dados de câmeras"
        rec_icon = "ℹ️ Sem dados de gravações"

    return (
        f"\n3. Resultado do Serviço\n"
        f"{'─' * 40}\n"
        f"Backup das configurações: {backup_icon}\n"
        f"Monitoramento (Câmeras): {cam_icon}\n"
        f"Monitoramento (Gravações): {rec_icon}\n"
    )


def _cam_is_online(cam: dict) -> bool:
    """Mesmo critério da seção de câmeras: só ONLINE conta como online."""
    status_comunicacao = cam.get("status_comunicacao")
    if not status_comunicacao:
        status_comunicacao = "ONLINE" if cam.get("online") else "OFFLINE"
    return status_comunicacao == "ONLINE"


def _canal_int(valor) -> Optional[int]:
    # Motorola (agentes < 1.1.4) reportava o canal como GUID "{0000000N-0000-...}"
    try:
        return int(valor)
    except (ValueError, TypeError):
        try:
            return int(str(valor).strip("{}").split("-")[0], 16)
        except ValueError:
            return None


def _image_filename(cam_nome: str, used: set) -> str:
    """Nome do arquivo = nome da câmera (sem caracteres inválidos); repetidos ganham sufixo."""
    base = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", cam_nome).strip(" .") or "camera"
    name = f"{base}.jpg"
    n = 2
    while name.lower() in used:
        name = f"{base} ({n}).jpg"
        n += 1
    used.add(name.lower())
    return name


def _collect_offline_images(db: Session, groups: List[tuple]) -> dict:
    """Imagem de referência (perfeita) das câmeras offline.

    `groups`: lista de (machine_id, nvr_results). O NVR é achado por máquina + nome,
    como no recebimento do relatório (routers/agent.py). Retorna `attachments`
    (no máx. MAX_OFFLINE_IMAGES, como (filename, bytes)), `with_image` (offline com
    imagem cadastrada) e `without_image` (offline sem imagem).
    """
    attachments: List[tuple] = []
    used: set = set()
    with_image = 0
    without_image = 0

    for machine_id, nvr_results in groups:
        for r in nvr_results or []:
            offline = [c for c in (r.get("cameras") or []) if not _cam_is_online(c)]
            if not offline:
                continue
            nvr = None
            if machine_id is not None:
                nvr = db.query(NVR).filter(NVR.machine_id == machine_id, NVR.name == r.get("nome")).first()
            imgs = {}
            if nvr is not None:
                imgs = {
                    c.canal: c.perfect_image_base64
                    for c in db.query(NVRCamera).filter(NVRCamera.nvr_id == nvr.id).all()
                    if c.perfect_image_base64
                }
            for cam in offline:
                b64 = imgs.get(_canal_int(cam.get("canal")))
                if not b64:
                    without_image += 1
                    continue
                with_image += 1
                try:
                    data = base64.b64decode(b64.split(",", 1)[-1], validate=False)
                except (binascii.Error, ValueError):
                    logger.warning(f"Imagem de referência inválida: {r.get('nome')} / canal {cam.get('canal')}")
                    with_image -= 1
                    without_image += 1
                    continue
                cam_nome = cam.get("nome") or f"Canal {cam.get('canal', '?')}"
                attachments.append((_image_filename(cam_nome, used), data))

    return {"attachments": attachments, "with_image": with_image, "without_image": without_image}


def _offline_images_note(info: dict) -> str:
    """Texto do corpo sobre as imagens anexadas (vazio se não houver câmera offline)."""
    total = info["with_image"] + info["without_image"]
    if total == 0:
        return ""
    total_anexos = len(info["attachments"])
    if total_anexos <= MAX_OFFLINE_IMAGES:
        note = f"\n📷 Imagens de referência das câmeras offline: {total_anexos} em anexo.\n"
    else:
        restantes = total_anexos - MAX_OFFLINE_IMAGES
        note = (
            f"\n📷 Imagens de referência das câmeras offline: {MAX_OFFLINE_IMAGES} de {total_anexos} em anexo "
            f"(as demais {restantes} imagem(ns) foram enviadas em resposta a este e-mail).\n"
        )
    if info["without_image"]:
        note += f"  {info['without_image']} câmera(s) offline sem imagem de referência cadastrada.\n"
    return note


def _attach_offline_images(msg: EmailMessage, info_or_list) -> None:
    attachments = info_or_list["attachments"] if isinstance(info_or_list, dict) else info_or_list
    for filename, data in attachments:
        msg.add_attachment(data, maintype="image", subtype="jpeg", filename=filename)


def _send_offline_images_replies(
    cfg: dict,
    clean_recipients: List[str],
    original_subject: str,
    parent_msg_id: str,
    remaining_attachments: List[tuple],
    context_name: str,
    total_images: int,
) -> bool:
    """Envia e-mails de resposta encadeados (In-Reply-To/References) com os lotes restantes de imagens."""
    all_ok = True
    current_start = MAX_OFFLINE_IMAGES + 1
    re_subject = original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}"

    for i in range(0, len(remaining_attachments), MAX_OFFLINE_IMAGES):
        batch = remaining_attachments[i : i + MAX_OFFLINE_IMAGES]
        batch_end = current_start + len(batch) - 1

        reply_msg = EmailMessage()
        reply_msg["From"] = cfg["email"]
        reply_msg["To"] = ", ".join(clean_recipients)
        reply_msg["Subject"] = re_subject
        reply_msg["In-Reply-To"] = parent_msg_id
        reply_msg["References"] = parent_msg_id
        reply_msg["Message-ID"] = make_msgid()

        body = (
            f"{'═' * 50}\n"
            f"  {context_name} - Imagens de Câmeras Offline (Continuação)\n"
            f"{'═' * 50}\n\n"
            f"📷 Imagens de referência das câmeras offline: {current_start} a {batch_end} de {total_images} em anexo.\n\n"
            f"{'═' * 50}\n"
            f"  Relatório gerado automaticamente — Trilan CFTV\n"
            f"{'═' * 50}\n"
        )
        reply_msg.set_content(body)
        _attach_offline_images(reply_msg, batch)

        sent = _smtp_send(reply_msg, cfg, clean_recipients)
        if not sent:
            logger.error(f"[SMTP] Falha ao enviar resposta encadeada ({current_start}-{batch_end}) para {clean_recipients}")
            all_ok = False

        current_start += len(batch)

    return all_ok


def _smtp_config(db: Session) -> Optional[dict]:
    """Lê a configuração SMTP (tabela settings com fallback para variáveis de ambiente).

    Retorna None (com aviso no log) se servidor ou e-mail remetente não estiverem configurados.
    """
    smtp_server_setting = db.query(Setting).filter_by(key="smtp_server").first()
    smtp_email_setting = db.query(Setting).filter_by(key="smtp_email").first()
    smtp_port_setting = db.query(Setting).filter_by(key="smtp_port").first()
    smtp_password_setting = db.query(Setting).filter_by(key="smtp_password").first()

    smtp_server = smtp_server_setting.value if smtp_server_setting and smtp_server_setting.value else settings.SMTP_SERVER
    smtp_email = smtp_email_setting.value if smtp_email_setting and smtp_email_setting.value else settings.SMTP_EMAIL

    try:
        smtp_port = int(smtp_port_setting.value) if smtp_port_setting and smtp_port_setting.value else settings.SMTP_PORT
    except ValueError:
        smtp_port = settings.SMTP_PORT

    smtp_password = smtp_password_setting.value if smtp_password_setting and smtp_password_setting.value else settings.SMTP_PASSWORD

    if not smtp_server or not smtp_email:
        logger.warning(f"SMTP not configured (server='{smtp_server}', email='{smtp_email}') — skipping email.")
        return None

    return {"server": smtp_server, "port": smtp_port, "email": smtp_email, "password": smtp_password}


def _clean_recipients(recipients: Optional[List[str]]) -> List[str]:
    """Limpa e valida destinatários (aceita vários e-mails na mesma entrada, separados por , ou ;)."""
    clean_recipients: List[str] = []
    for r in (recipients or []):
        if not r:
            continue
        parts = str(r).replace(";", ",").split(",")
        for part in parts:
            item = part.strip()
            if item and "@" in item and "." in item:
                if item not in clean_recipients:
                    clean_recipients.append(item)
    return clean_recipients


def _overall_status(nvr_results: List[dict]) -> str:
    """Status geral do backup de uma máquina (texto usado na seção 2)."""
    if any(_norm_status(r) == "ERRO" for r in nvr_results):
        return "❌ COM ERROS"
    if any(_norm_status(r) == "PARCIAL" for r in nvr_results):
        return "⚠️ PARCIAL"
    return "✅ SUCESSO"


def _smtp_send(msg: EmailMessage, cfg: dict, clean_recipients: List[str]) -> bool:
    """Envio SMTP com retentativas e suporte a SSL/STARTTLS. Retorna True em caso de sucesso."""
    smtp_server, smtp_port = cfg["server"], cfg["port"]
    max_retries = 3
    last_error = None
    timeout_s = 30

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[SMTP] Tentativa {attempt}/{max_retries} para {clean_recipients} via {smtp_server}:{smtp_port}...")
            if smtp_port == 465:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=timeout_s)
            else:
                server = smtplib.SMTP(smtp_server, smtp_port, timeout=timeout_s)
                server.ehlo()
                if server.has_extn("STARTTLS"):
                    server.starttls()
                    server.ehlo()

            with server:
                if cfg["password"]:
                    server.login(cfg["email"], cfg["password"])
                server.send_message(msg)

            logger.info(f"[SMTP] E-mail enviado com sucesso para {clean_recipients} na tentativa {attempt}.")
            return True
        except Exception as exc:
            last_error = exc
            logger.warning(f"[SMTP] Tentativa {attempt}/{max_retries} falhou: {exc}")
            if attempt < max_retries:
                time.sleep(2 * attempt)

    logger.error(f"[SMTP] Falha definitiva no envio de e-mail para {clean_recipients} após {max_retries} tentativas: {last_error}")
    return False


def send_backup_report(
    machine_name: str,
    date_str: str,
    nvr_results: List[dict],
    recipients: List[str],
    db: Session,
    zip_path: Optional[Path] = None,
    backup_id: Optional[str] = None,
    base_url: Optional[str] = None,
    public_url: Optional[str] = None,
    machine_id=None,
) -> bool:
    """Send backup report email (máquina sem Cliente). Returns True on success.

    Com `machine_id`, anexa a imagem de referência das câmeras offline (máx. MAX_OFFLINE_IMAGES).
    """
    cfg = _smtp_config(db)
    if cfg is None:
        return False

    # ── Limpeza e validação de destinatários ──
    clean_recipients = _clean_recipients(recipients)
    if not clean_recipients:
        logger.warning(f"No valid recipients configured for '{machine_name}' (received: {recipients}) — skipping email.")
        return False

    # ── Overall backup status ──
    overall = _overall_status(nvr_results)

    # ── Date/time formatting (BRT = UTC-3, independente do fuso do container) ──
    now = datetime.utcnow() - timedelta(hours=3)
    date_hora_str = now.strftime("%d/%m/%Y – %H:%M")

    # ── Build email ──
    msg = EmailMessage()
    msg_id = make_msgid()
    msg["Message-ID"] = msg_id
    msg["From"] = cfg["email"]
    msg["To"] = ", ".join(clean_recipients)
    msg["Subject"] = f"{machine_name} POP - Verificação de câmeras e Backup dos equipamentos — {date_str}"

    # ── Header ──
    body = (
        f"{'═' * 50}\n"
        f"  {machine_name} POP - Verificação de câmeras e Backup dos equipamentos\n"
        f"{'═' * 50}\n\n"
        f"Máquina: {machine_name}\n"
        f"Data e hora: {date_hora_str}\n\n"
        f"Serviço executado:\n"
        f"Backup das configurações dos equipamentos de rede/CFTV e verificação de status operacional.\n\n"
    )

    # ── Section 1: Câmeras e Gravações ──
    body += _build_camera_section(nvr_results)
    offline_images = _collect_offline_images(db, [(machine_id, nvr_results)])
    body += _offline_images_note(offline_images)

    # ── Section 2: Backup ──
    body += _build_backup_section(nvr_results, overall)

    # ── Download links / attachment ──
    attach = False
    if zip_path and zip_path.exists():
        size = zip_path.stat().st_size
        if size <= LIMIT_ATTACH_BYTES:
            attach = True
            body += "\n📎 O arquivo ZIP protegido está em anexo.\n"
        else:
            body += f"\n⚠️ O ZIP excede o limite de anexo (5 MB) e não pôde ser anexado.\n"

    if backup_id:
        body += f"\n🔗 LINKS PARA BAIXAR O BACKUP DIRETAMENTE:\n"
        link_public = None
        if public_url:
            link_public = f"{public_url.rstrip('/')}/api/v1/backups/public-download/{backup_id}"
            body += f"  Acesso: {link_public}\n"
        if base_url:
            link_ddns = f"{base_url.rstrip('/')}/api/v1/backups/public-download/{backup_id}"
            # Evita repetir o mesmo link quando base_url coincide com a URL pública
            if link_ddns != link_public:
                body += f"  Acesso: {link_ddns}\n"
        body += f"\n  O link não requer senha do painel e pode ser acessado de qualquer navegador.\n"
    elif zip_path and not attach:
        body += f"\n  Arquivado no servidor: {zip_path.name}\n"

    # ── Section 3: Resultado do Serviço ──
    body += _build_result_section(nvr_results)

    # ── Footer ──
    body += (
        f"\n{'═' * 50}\n"
        f"  Relatório gerado automaticamente — Trilan CFTV\n"
        f"{'═' * 50}\n"
    )

    msg.set_content(body)

    if attach and zip_path:
        msg.add_attachment(
            zip_path.read_bytes(),
            maintype="application",
            subtype="zip",
            filename=zip_path.name,
        )
    all_attachments = offline_images.get("attachments") or []
    first_batch = all_attachments[:MAX_OFFLINE_IMAGES]
    remaining_batch = all_attachments[MAX_OFFLINE_IMAGES:]

    _attach_offline_images(msg, first_batch)

    sent = _smtp_send(msg, cfg, clean_recipients)
    if not sent:
        return False

    if remaining_batch:
        _send_offline_images_replies(
            cfg=cfg,
            clean_recipients=clean_recipients,
            original_subject=msg["Subject"],
            parent_msg_id=msg_id,
            remaining_attachments=remaining_batch,
            context_name=machine_name,
            total_images=len(all_attachments),
        )

    return True


# ─── E-mail único por rodada do Cliente ────────────────────────────────────

RUN_TRIGGER_LABELS = {
    "scheduled": "Agendado",
    "queue": "Fila (disparado pelo painel)",
    "manual_machine": "Avulso",
}

_OK_STATUSES = ("OK", "SEM_ARQUIVOS")


def _machine_summary_line(entry: dict) -> str:
    """Linha do resumo: nome, status e contagem de equipamentos OK / com erro (ou 'não executou')."""
    name = entry.get("name") or "?"
    status = entry.get("status")
    if not status:
        return f"  ❌ {name}: não executou (offline/sem retorno)"
    results = entry.get("nvr_results") or []
    ok = sum(1 for r in results if _norm_status(r) in _OK_STATUSES)
    err = len(results) - ok
    st = _norm_status({"status": status})  # PARTIAL/ERROR -> PARCIAL/ERRO
    icon = "✅" if st in _OK_STATUSES else "⚠️" if st == "PARCIAL" else "❌"
    return f"  {icon} {name}: {st} — {ok} equipamento(s) OK, {err} com erro"


def send_customer_report(
    customer_name: str,
    run_id: str,
    run_trigger: str,
    started_at: Optional[datetime],
    entries: List[dict],
    recipients: List[str],
    db: Session,
    has_zip: bool = False,
    public_url: Optional[str] = None,
    base_url: Optional[str] = None,
    manual_machine_name: Optional[str] = None,
) -> bool:
    """Envia o e-mail único da rodada do Cliente. Retorna True em caso de sucesso.

    `entries`: uma por máquina esperada (ordem da rodada), com chaves
    `name`, `status` (status do backup ou None se não executou), `nvr_results` e,
    opcionalmente, `machine_id`.
    O ZIP unificado da rodada fica disponível por link público (não vai anexo); anexos
    são só as imagens de referência das câmeras offline (máx. MAX_OFFLINE_IMAGES no e-mail).
    """
    cfg = _smtp_config(db)
    if cfg is None:
        return False

    clean_recipients = _clean_recipients(recipients)
    if not clean_recipients:
        logger.warning(f"No valid recipients configured for customer '{customer_name}' (received: {recipients}) — skipping email.")
        return False

    # Datas em BRT (UTC-3); started_at é UTC naive (REGRA-001)
    ref = (started_at or datetime.utcnow()) - timedelta(hours=3)
    date_str = ref.strftime("%d-%m-%Y")
    date_hora_str = ref.strftime("%d/%m/%Y – %H:%M")

    subject = f"{customer_name} - Verificação de câmeras e Backup dos equipamentos — {date_str}"
    tipo = RUN_TRIGGER_LABELS.get(run_trigger, run_trigger)
    if run_trigger == "manual_machine" and manual_machine_name:
        subject += f" (backup avulso: {manual_machine_name})"
        tipo = f"Avulso ({manual_machine_name})"

    msg = EmailMessage()
    msg_id = make_msgid()
    msg["Message-ID"] = msg_id
    msg["From"] = cfg["email"]
    msg["To"] = ", ".join(clean_recipients)
    msg["Subject"] = subject

    reported = [e for e in entries if e.get("status")]

    # ── Cabeçalho ──
    body = (
        f"{'═' * 50}\n"
        f"  {customer_name} - Verificação de câmeras e Backup dos equipamentos\n"
        f"{'═' * 50}\n\n"
        f"Cliente: {customer_name}\n"
        f"Data e hora: {date_hora_str}\n"
        f"Tipo da rodada: {tipo}\n\n"
        f"Serviço executado:\n"
        f"Backup das configurações dos equipamentos de rede/CFTV e verificação de status operacional.\n\n"
    )

    # ── Resumo por máquina ──
    body += (
        f"Resumo ({len(reported)}/{len(entries)} máquina(s) reportaram)\n"
        f"{'─' * 40}\n"
    )
    body += "\n".join(_machine_summary_line(e) for e in entries) + "\n"

    # ── Bloco por máquina que reportou ──
    for e in reported:
        nvr_results = e.get("nvr_results") or []
        body += (
            f"\n\n{'═' * 50}\n"
            f"  Máquina: {e.get('name') or '?'}\n"
            f"{'═' * 50}\n"
        )
        body += _build_camera_section(nvr_results)
        body += _build_backup_section(nvr_results, _overall_status(nvr_results))

    # ── Imagens de referência das câmeras offline (todas as máquinas) ──
    offline_images = _collect_offline_images(
        db, [(e.get("machine_id"), e.get("nvr_results") or []) for e in reported]
    )
    body += _offline_images_note(offline_images)

    # ── Link do ZIP unificado da rodada ──
    if has_zip:
        links = []
        if public_url:
            links.append(f"{public_url.rstrip('/')}/api/v1/backups/public-run-download/{run_id}")
        if base_url:
            link_base = f"{base_url.rstrip('/')}/api/v1/backups/public-run-download/{run_id}"
            if link_base not in links:
                links.append(link_base)
        if links:
            body += f"\n\n🔗 LINK PARA BAIXAR O ZIP DA RODADA (todas as máquinas):\n"
            for link in links:
                body += f"  Acesso: {link}\n"
            body += f"\n  O link não requer senha do painel e pode ser acessado de qualquer navegador.\n"
        else:
            body += "\n\n📦 ZIP disponível no painel.\n"

    # ── Rodapé ──
    body += (
        f"\n{'═' * 50}\n"
        f"  Relatório gerado automaticamente — Trilan CFTV\n"
        f"{'═' * 50}\n"
    )

    msg.set_content(body)

    all_attachments = offline_images.get("attachments") or []
    first_batch = all_attachments[:MAX_OFFLINE_IMAGES]
    remaining_batch = all_attachments[MAX_OFFLINE_IMAGES:]

    _attach_offline_images(msg, first_batch)

    sent = _smtp_send(msg, cfg, clean_recipients)
    if not sent:
        return False

    if remaining_batch:
        _send_offline_images_replies(
            cfg=cfg,
            clean_recipients=clean_recipients,
            original_subject=msg["Subject"],
            parent_msg_id=msg_id,
            remaining_attachments=remaining_batch,
            context_name=customer_name,
            total_images=len(all_attachments),
        )

    return True
