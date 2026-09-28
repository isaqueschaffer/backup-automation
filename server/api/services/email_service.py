import smtplib
import logging
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import List, Optional
from sqlalchemy.orm import Session

from config import settings
from models import Setting

logger = logging.getLogger(__name__)

LIMIT_ATTACH_BYTES = 5 * 1024 * 1024  # 5 MB


def _build_backup_section(nvr_results: List[dict], overall: str) -> str:
    """Section 1 — Backup dos NVRs."""
    icon_map = {"OK": "✅", "PARCIAL": "⚠️", "PARTIAL": "⚠️", "ERRO": "❌", "ERROR": "❌", "SEM_ARQUIVOS": "ℹ️"}

    lines = "\n".join(
        f"  {icon_map.get(r['status'], '❓')} {r['nome']}: "
        f"{'OK' if r['status'] == 'OK' else 'Gravações OK (Backup de config. não suportado)' if r['status'] == 'SEM_ARQUIVOS' else 'FALHA — ' + r['status']}"
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
    """Section 2 — Verificação de Câmeras e Gravações."""
    total_nvrs = len(nvr_results)
    total_cameras = 0
    cameras_online = 0
    cameras_offline = 0
    cameras_online_sem_gravacao = 0
    problemas_por_nvr: dict[str, list[str]] = {}

    for r in nvr_results:
        cameras = r.get("cameras") or []
        nvr_nome = r["nome"]
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
                gravou_hoje = (mapa[-1] == "█") if mapa else (total_dias > 0)
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
                problemas.append(f"  ❌ {cam_nome}: Offline ({status_comunicacao})")

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
    """Section 3 — Resultado do Serviço."""
    has_cameras = any(r.get("cameras") for r in nvr_results)

    backup_ok = all(r["status"] in ("OK",) for r in nvr_results)
    has_unsupported_backup = any(r["status"] == "SEM_ARQUIVOS" for r in nvr_results)
    
    if backup_ok:
        backup_icon = "✅ Concluído"
    elif has_unsupported_backup and all(r["status"] in ("OK", "SEM_ARQUIVOS") for r in nvr_results):
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
                    gravou_hoje = (mapa[-1] == "█") if mapa else (cam.get("total_dias", 0) > 0)
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


def send_backup_report(
    client_name: str,
    date_str: str,
    nvr_results: List[dict],
    recipients: List[str],
    db: Session,
    zip_path: Optional[Path] = None,
    backup_id: Optional[str] = None,
    base_url: Optional[str] = None,
    public_url: Optional[str] = None,
) -> bool:
    """Send backup report email. Returns True on success."""
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
        logger.warning("SMTP not configured — skipping email.")
        return False

    if not recipients:
        logger.warning("No recipients configured — skipping email.")
        return False

    # ── Overall backup status ──
    overall = "✅ SUCESSO"
    if any(r["status"] in ("ERRO", "ERROR") for r in nvr_results):
        overall = "❌ COM ERROS"
    elif any(r["status"] in ("PARCIAL", "PARTIAL") for r in nvr_results):
        overall = "⚠️ PARCIAL"

    # ── Date/time formatting ──
    now = datetime.now()
    date_hora_str = now.strftime("%d/%m/%Y – %H:%M")

    # ── Build email ──
    msg = EmailMessage()
    msg["From"] = smtp_email
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = f"{client_name} POP - Verificação de câmeras e Backup dos equipamentos — {date_str}"

    # ── Header ──
    body = (
        f"{'═' * 50}\n"
        f"  {client_name} POP - Verificação de câmeras e Backup dos equipamentos\n"
        f"{'═' * 50}\n\n"
        f"Cliente: {client_name}\n"
        f"Data e hora: {date_hora_str}\n\n"
        f"Serviço executado:\n"
        f"Backup das configurações dos equipamentos de rede/CFTV e verificação de status operacional.\n\n"
    )

    # ── Section 1: Câmeras e Gravações ──
    body += _build_camera_section(nvr_results)

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
        if public_url:
            link_public = f"{public_url.rstrip('/')}/api/v1/backups/public-download/{backup_id}"
            body += f"  Acesso: {link_public}\n"
        if base_url:
            link_ddns = f"{base_url.rstrip('/')}/api/v1/backups/public-download/{backup_id}"
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

    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=60) as server:
            server.starttls()
            server.login(smtp_email, smtp_password or "")
            server.send_message(msg)
        logger.info(f"Email sent to {recipients}")
        return True
    except Exception as exc:
        logger.error(f"Failed to send email: {exc}")
        return False
