"""Mensagens de WhatsApp com o mesmo conteúdo dos e-mails, em texto resumido + imagens das câmeras offline.

O WhatsApp não comporta o relatório completo do e-mail (seções longas, HTML), então cada mensagem traz:
status geral, contagens, só os equipamentos com falha, o link de download e, em seguida, as imagens de referência
das câmeras offline (as mesmas anexadas ao e-mail, no máximo MAX_OFFLINE_IMAGES).
Formatação do WhatsApp: *negrito*. Datas em BRT (UTC-3), a partir de UTC naive (REGRA-001).
"""
import logging
import threading
from datetime import datetime, timedelta
from typing import List, Optional, Sequence

from sqlalchemy.orm import Session

from database import SessionLocal
from models import AgentLog
from services.email_service import (
    MAX_OFFLINE_IMAGES,
    _OK_STATUSES,
    _cam_is_online,
    _collect_offline_images,
    _machine_summary_line,
    _norm_status,
    _overall_status,
    _tem_cameras,
    _tipo,
    _tipos_cadastrados,
    _titulo_relatorio,
    RUN_TRIGGER_LABELS,
)
from services.whatsapp_service import enviar_whatsapp

logger = logging.getLogger("trilan.whatsapp")

MAX_FALHAS_LISTADAS = 15
_ICONE = {"PARCIAL": "⚠️", "ERRO": "❌"}


def _contagem_cameras(nvr_results: List[dict]) -> Optional[str]:
    """'Câmeras: X online, Y offline' (None se nenhum equipamento trouxe câmeras)."""
    online = offline = 0
    for r in nvr_results:
        for cam in r.get("cameras") or []:
            if cam.get("status_comunicacao") == "NAO_VERIFICADO":
                continue
            if _cam_is_online(cam):
                online += 1
            else:
                offline += 1
    if not (online or offline):
        return None
    return f"📹 Câmeras: {online} online, {offline} offline"


def _linhas_falhas(nvr_results: List[dict], prefixo: str = "") -> List[str]:
    """Uma linha por equipamento que não terminou OK (a lista completa fica no e-mail e no painel)."""
    linhas = []
    for r in nvr_results:
        st = _norm_status(r)
        if st in _OK_STATUSES:
            continue
        linhas.append(f"  {_ICONE.get(st, '❌')} {prefixo}{r.get('nome', '?')}: {st or 'DESCONHECIDO'}")
    return linhas


def _limitar(linhas: List[str]) -> List[str]:
    if len(linhas) <= MAX_FALHAS_LISTADAS:
        return linhas
    return linhas[:MAX_FALHAS_LISTADAS] + [f"  … e mais {len(linhas) - MAX_FALHAS_LISTADAS} (veja o e-mail ou o painel)"]


def _nota_imagens(info: dict) -> str:
    total = len(info["attachments"])
    sem_imagem = info["without_image"]
    partes = []
    if total:
        enviadas = min(total, MAX_OFFLINE_IMAGES)
        partes.append(f"📷 Imagens das câmeras offline: {enviadas} a seguir" + (f" (de {total}; as demais vão no e-mail)." if total > enviadas else "."))
    if sem_imagem:
        partes.append(f"{sem_imagem} câmera(s) offline sem imagem de referência cadastrada.")
    return "\n".join(partes)


def _links(rota: str, identificador: str, public_url: Optional[str], base_url: Optional[str]) -> List[str]:
    """Link público de download (URL pública primeiro; o da requisição só se for diferente)."""
    links: List[str] = []
    for raiz in (public_url, base_url):
        if raiz:
            link = f"{raiz.rstrip('/')}/api/v1/backups/{rota}/{identificador}"
            if link not in links:
                links.append(link)
    return links


def enviar_relatorio_maquina(
    db: Session,
    machine_name: str,
    nvr_results: List[dict],
    numeros: Optional[Sequence[str]],
    machine_id=None,
    backup_id: Optional[str] = None,
    public_url: Optional[str] = None,
    base_url: Optional[str] = None,
) -> bool:
    """Relatório de uma máquina sem Cliente (equivale a `send_backup_report`). True se chegou a algum número."""
    if not numeros:
        return False
    try:
        tipos = {_tipo(r) for r in nvr_results} | _tipos_cadastrados(db, [machine_id])
        agora = datetime.utcnow() - timedelta(hours=3)
        ok = sum(1 for r in nvr_results if _norm_status(r) in _OK_STATUSES)

        linhas = [
            f"*{machine_name} POP - {_titulo_relatorio(tipos)}*",
            f"🕒 {agora.strftime('%d/%m/%Y – %H:%M')}",
            f"Status geral: {_overall_status(nvr_results)}",
            f"Equipamentos: {len(nvr_results)} ({ok} OK, {len(nvr_results) - ok} com falha)",
        ]
        cameras = _contagem_cameras(nvr_results) if any(_tem_cameras(r) for r in nvr_results) else None
        if cameras:
            linhas.append(cameras)
        falhas = _limitar(_linhas_falhas(nvr_results))
        if falhas:
            linhas += ["", "*Com falha:*"] + falhas

        imagens = _collect_offline_images(db, [(machine_id, nvr_results)])
        nota = _nota_imagens(imagens)
        if nota:
            linhas += ["", nota]

        if backup_id:
            links = _links("public-download", str(backup_id), public_url, base_url)
            if links:
                linhas += ["", "🔗 Baixar o backup:", links[0]]
        linhas += ["", "_Relatório automático — Trilan_"]

        return enviar_whatsapp(db, numeros, "\n".join(linhas), imagens["attachments"][:MAX_OFFLINE_IMAGES],
                               contexto=f"Relatório da máquina '{machine_name}'")
    except Exception:
        logger.exception("Falha ao montar o WhatsApp do relatório da máquina '%s'", machine_name)
        return False


def enviar_relatorio_cliente(
    db: Session,
    customer_name: str,
    run_id: str,
    run_trigger: str,
    started_at: Optional[datetime],
    entries: List[dict],
    numeros: Optional[Sequence[str]],
    has_zip: bool = False,
    public_url: Optional[str] = None,
    base_url: Optional[str] = None,
    manual_machine_name: Optional[str] = None,
) -> bool:
    """Relatório da rodada de um Cliente (equivale a `send_customer_report`). True se chegou a algum número."""
    if not numeros:
        return False
    try:
        reportaram = [e for e in entries if e.get("status")]
        tipos = {_tipo(r) for e in reportaram for r in (e.get("nvr_results") or [])}
        tipos |= _tipos_cadastrados(db, [e.get("machine_id") for e in entries])
        ref = (started_at or datetime.utcnow()) - timedelta(hours=3)

        tipo = RUN_TRIGGER_LABELS.get(run_trigger, run_trigger)
        if run_trigger == "manual_machine" and manual_machine_name:
            tipo = f"Avulso ({manual_machine_name})"

        linhas = [
            f"*{customer_name} - {_titulo_relatorio(tipos)}*",
            f"🕒 {ref.strftime('%d/%m/%Y – %H:%M')} · {tipo}",
            "",
            f"*Resumo ({len(reportaram)}/{len(entries)} máquina(s) reportaram)*",
        ]
        linhas += [_machine_summary_line(e).strip() for e in entries]

        todos = [r for e in reportaram for r in (e.get("nvr_results") or [])]
        cameras = _contagem_cameras(todos) if any(_tem_cameras(r) for r in todos) else None
        if cameras:
            linhas += ["", cameras]
        falhas = _limitar([
            linha
            for e in reportaram
            for linha in _linhas_falhas(e.get("nvr_results") or [], prefixo=f"{e.get('name') or '?'} › ")
        ])
        if falhas:
            linhas += ["", "*Com falha:*"] + falhas

        imagens = _collect_offline_images(
            db, [(e.get("machine_id"), e.get("nvr_results") or []) for e in reportaram]
        )
        nota = _nota_imagens(imagens)
        if nota:
            linhas += ["", nota]

        if has_zip:
            links = _links("public-run-download", str(run_id), public_url, base_url)
            if links:
                linhas += ["", "🔗 Baixar o ZIP da rodada:", links[0]]
        linhas += ["", "_Relatório automático — Trilan_"]

        return enviar_whatsapp(db, numeros, "\n".join(linhas), imagens["attachments"][:MAX_OFFLINE_IMAGES],
                               contexto=f"Relatório da rodada do cliente '{customer_name}'")
    except Exception:
        logger.exception("Falha ao montar o WhatsApp da rodada do cliente '%s'", customer_name)
        return False


def disparar_em_segundo_plano(funcao, descricao: str, log_machine_id=None, **kwargs) -> None:
    """Roda `funcao(db=..., **kwargs)` numa thread com sessão própria, para o WhatsApp (com pausas entre mensagens
    e imagens) não segurar a requisição do agente nem o fechamento da rodada. `kwargs` deve ter só dados simples
    (nada de objetos ligados à sessão da requisição). Com `log_machine_id`, grava o resultado no log da máquina."""
    def _tarefa():
        try:
            with SessionLocal() as db:
                enviado = bool(funcao(db=db, **kwargs))
                if log_machine_id is not None:
                    db.add(AgentLog(
                        machine_id=log_machine_id,
                        event_type="whatsapp_sent" if enviado else "whatsapp_error",
                        nivel="INFO" if enviado else "ERROR",
                        message=(f"WhatsApp enviado: {descricao}." if enviado
                                 else f"Falha no envio de WhatsApp: {descricao}. Confira se o número remetente está conectado (Configurações > WhatsApp) e os números de destino."),
                    ))
                    db.commit()
        except Exception:
            logger.exception("Falha na tarefa de WhatsApp (%s)", descricao)

    threading.Thread(target=_tarefa, name="whatsapp-envio", daemon=True).start()


def enviar_aviso_whatsapp(db: Session, numeros: Optional[Sequence[str]], titulo: str, mensagem: str, contexto: str = "") -> bool:
    """Notificação/aviso curto (licença, backup com falha, vencimento da conta...): título em negrito + texto."""
    if not numeros:
        return False
    return enviar_whatsapp(db, numeros, f"*{titulo}*\n\n{mensagem}\n\n_Trilan_", contexto=contexto or titulo)
