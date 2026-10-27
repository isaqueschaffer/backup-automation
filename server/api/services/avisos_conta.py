"""Avisos de vencimento das Contas por e-mail (7, 3 e 1 dia antes e no dia do vencimento)."""
import html
import logging
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import List, Optional

from sqlalchemy.orm import Session

from models import Conta, Usuario
from services.contas import status_da_conta
from services.email_service import _clean_recipients, _smtp_config, _smtp_send

logger = logging.getLogger("trilan.avisos_conta")

# Dias antes do vencimento em que sai e-mail; 0 = venceu (conta bloqueada)
MARCOS_EMAIL = (7, 3, 1, 0)


def marco_devido(dias: Optional[int], enviados: Optional[List[int]] = None) -> Optional[int]:
    """Marco mais urgente já alcançado e ainda não enviado (None = nada a enviar).
    Ex.: conta criada a 2 dias do fim manda só o de 3; vencida (dias <= 0) manda o 0 uma vez."""
    if dias is None:
        return None
    alcancados = [m for m in MARCOS_EMAIL if dias <= m]
    if not alcancados:
        return None
    marco = min(alcancados)
    return None if marco in (enviados or []) else marco


def destinatarios(db: Session, conta: Conta) -> List[str]:
    """E-mail de contato da conta + administradores ativos dela (sem repetição)."""
    emails = [conta.email_contato] if conta.email_contato else []
    emails += [u.email for u in db.query(Usuario).filter(
        Usuario.conta_id == conta.id, Usuario.papel == "ADMIN", Usuario.ativo == True
    ).all()]
    return _clean_recipients(emails)


def enviar_aviso(db: Session, conta: Conta, marco: int, dias: int, para: List[str]) -> bool:
    """Envia o e-mail de aviso de vencimento ou conta vencida. Retorna True em caso de sucesso."""
    cfg = _smtp_config(db)
    if cfg is None:
        return False

    data_formatada = (conta.expira_em - timedelta(hours=3)).strftime("%d/%m/%Y às %H:%M") + " (horário de Brasília)"

    if marco == 0:
        assunto = f"Conta {conta.nome} vencida: backups suspensos"
        texto_puro = (
            f"O plano da conta {conta.nome} venceu em {data_formatada}.\n\n"
            "O painel está em modo somente leitura e os backups automáticos estão suspensos até a renovação. "
            "Nenhum dado foi apagado. Fale com a Trilan para renovar."
        )
        nome_escapado = html.escape(conta.nome)
        html_corpo = (
            f"<p>O plano da conta <strong>{nome_escapado}</strong> venceu em {data_formatada}.</p>"
            "<p>O painel está em modo somente leitura e os backups automáticos estão suspensos até a renovação. "
            "Nenhum dado foi apagado. Fale com a Trilan para renovar.</p>"
        )
    else:
        assunto = f"Conta {conta.nome}: o plano vence em {dias} dia(s)"
        texto_puro = (
            f"O plano da conta {conta.nome} vence em {dias} dia(s), em {data_formatada}.\n\n"
            "Para não interromper os backups automáticos, fale com a Trilan e renove o plano."
        )
        nome_escapado = html.escape(conta.nome)
        html_corpo = (
            f"<p>O plano da conta <strong>{nome_escapado}</strong> vence em {dias} dia(s), em {data_formatada}.</p>"
            "<p>Para não interromper os backups automáticos, fale com a Trilan e renove o plano.</p>"
        )

    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = cfg["email"]
    msg["To"] = ", ".join(para)
    msg.set_content(texto_puro)
    msg.add_alternative(html_corpo, subtype="html")

    return _smtp_send(msg, cfg, para)


def verificar_vencimentos(db: Session, agora: Optional[datetime] = None) -> int:
    """Verifica todas as contas ativas com expira_em e envia avisos devidos. Retorna o total de e-mails enviados."""
    contas = db.query(Conta).filter(Conta.ativo == True, Conta.expira_em.isnot(None)).all()
    total_enviados = 0

    for conta in contas:
        try:
            status, dias = status_da_conta(conta, agora)
            marco = marco_devido(dias, conta.avisos_enviados)
            if marco is None:
                continue

            para = destinatarios(db, conta)
            if not para:
                logger.warning("Conta %s (%s) sem destinatários para aviso de vencimento (marco %s).", conta.id, conta.nome, marco)
                conta.avisos_enviados = list(conta.avisos_enviados or []) + [marco]
                db.commit()
                continue

            # dias pode ser 0 ou negativo quando vencida
            dias_val = dias if dias is not None else 0
            enviado = enviar_aviso(db, conta, marco, dias_val, para)
            if enviado:
                total_enviados += 1
                conta.avisos_enviados = list(conta.avisos_enviados or []) + [marco]
                db.commit()
        except Exception:
            logger.exception("Falha ao processar avisos de vencimento da conta %s (%s)", getattr(conta, 'id', None), getattr(conta, 'nome', ''))
            db.rollback()

    return total_enviados
