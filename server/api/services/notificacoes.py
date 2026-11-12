"""Notificações operacionais: as 3 automáticas (licença da UNM2000 vencendo, backup com falha, agente offline), as
opt-in por item (câmera offline, alarmes das centrais do DEFENSE) e as personalizadas (criadas pelo usuário). Geradas periodicamente (chamado por `main.py` a cada 10 min), aparecem no
painel (pop-up ao logar + aba Notificações) e, quando configurado, por e-mail."""
import html
import logging
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from typing import Optional

from sqlalchemy.orm import Session

from models import ConfiguracaoNotificacao, Conta, Machine, NotificacaoPersonalizada, NVR, Notificacao
from services.avisos_conta import destinatarios
from services.camera_offline import formatar_offline_ha, segundos_offline
from services.email_service import _smtp_config, _smtp_send
from services.galeria_vms import status_por_camera
from services.licenca_unm import licenca_da_config

logger = logging.getLogger("trilan.notificacoes")

TIPOS = ("LICENCA_UNM2000", "BACKUP_FALHOU", "AGENTE_OFFLINE")  # tipos com preferência geral por conta (ConfiguracaoNotificacao)
LIMIAR_LICENCA_DIAS = 10          # a partir de quantos dias antes do vencimento o alerta (e o e-mail diário) começam
LIMIAR_AGENTE_OFFLINE_MIN = 15    # máquina ativa sem contato por mais que isso = notificação (o status "ao vivo" usa 180s)
LIMIAR_CAMERA_OFFLINE_MIN = 15    # câmera marcada para notificar, offline por mais que isso = notificação
LIMIAR_ALARME_SEM_DADOS_MIN = 20  # status dos alarmes mais velho que isso (agente coleta a cada 5 min) não abre nem fecha alerta


def tipo_ativo(db: Session, conta_id, tipo: str) -> bool:
    """Preferência da conta para esse tipo (ausente no banco = ativo)."""
    cfg = db.query(ConfiguracaoNotificacao).filter_by(conta_id=conta_id, tipo=tipo).first()
    return cfg.ativo if cfg else True


def _notificacao_aberta(db: Session, conta_id, tipo: str, machine_id=None, nvr_id=None, definicao_id=None, camera_id=None,
                        referencia=None) -> Optional[Notificacao]:
    return db.query(Notificacao).filter(
        Notificacao.conta_id == conta_id, Notificacao.tipo == tipo, Notificacao.resolvido_em.is_(None),
        Notificacao.machine_id == machine_id, Notificacao.nvr_id == nvr_id, Notificacao.definicao_id == definicao_id,
        Notificacao.camera_id == camera_id, Notificacao.referencia == referencia,
    ).first()


def abrir_ou_atualizar(db: Session, conta_id, tipo: str, titulo: str, mensagem: str, machine_id=None, nvr_id=None, definicao_id=None,
                       camera_id=None, referencia=None) -> Notificacao:
    """Cria a notificação se não houver uma aberta igual; se já houver, só atualiza o texto (ex.: dias restantes)."""
    existente = _notificacao_aberta(db, conta_id, tipo, machine_id, nvr_id, definicao_id, camera_id, referencia)
    if existente:
        existente.titulo, existente.mensagem = titulo, mensagem
        existente.atualizado_em = datetime.utcnow()
        return existente
    nova = Notificacao(conta_id=conta_id, tipo=tipo, titulo=titulo, mensagem=mensagem, machine_id=machine_id,
                       nvr_id=nvr_id, definicao_id=definicao_id, camera_id=camera_id, referencia=referencia)
    db.add(nova)
    return nova


def resolver(db: Session, conta_id, tipo: str, machine_id=None, nvr_id=None, definicao_id=None, camera_id=None,
             referencia=None) -> None:
    """Fecha a notificação aberta (se houver) quando a condição deixou de valer."""
    existente = _notificacao_aberta(db, conta_id, tipo, machine_id, nvr_id, definicao_id, camera_id, referencia)
    if existente:
        existente.resolvido_em = datetime.utcnow()


def _enviar_email(db: Session, conta: Conta, assunto: str, texto_puro: str, corpo_html: str, contexto: str) -> bool:
    cfg = _smtp_config(db)
    if cfg is None:
        return False
    para = destinatarios(db, conta)
    if not para:
        logger.warning("%s (conta %s) sem destinatários para o e-mail.", contexto, conta.id)
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = assunto, cfg["email"], ", ".join(para)
    msg.set_content(texto_puro)
    msg.add_alternative(corpo_html, subtype="html")
    return _smtp_send(msg, cfg, para)


def _enviar_email_licenca(db: Session, conta: Conta, nvr: NVR, dias_restantes: int) -> bool:
    nome_escapado = html.escape(nvr.name)
    if dias_restantes < 0:
        assunto = f"Licença da UNM2000 '{nvr.name}' vencida"
        texto_puro = f"A licença da UNM2000 '{nvr.name}' venceu há {-dias_restantes} dia(s). Renove para não perder o monitoramento."
        corpo_html = f"<p>A licença da UNM2000 <strong>{nome_escapado}</strong> venceu há {-dias_restantes} dia(s). Renove para não perder o monitoramento.</p>"
    else:
        assunto = f"Licença da UNM2000 '{nvr.name}' vence em {dias_restantes} dia(s)"
        texto_puro = f"A licença da UNM2000 '{nvr.name}' vence em {dias_restantes} dia(s). Renove para não perder o monitoramento."
        corpo_html = f"<p>A licença da UNM2000 <strong>{nome_escapado}</strong> vence em {dias_restantes} dia(s). Renove para não perder o monitoramento.</p>"
    return _enviar_email(db, conta, assunto, texto_puro, corpo_html, f"Licença da UNM2000 '{nvr.name}'")


def _enviar_email_camera_offline(db: Session, conta: Conta, nvr: NVR, camera_nome: str, tempo_texto: str) -> bool:
    nome_eq, nome_cam = html.escape(nvr.name), html.escape(camera_nome)
    assunto = f"Câmera '{camera_nome}' offline em '{nvr.name}'"
    texto_puro = f"A câmera '{camera_nome}' do equipamento '{nvr.name}' está offline {tempo_texto}."
    corpo_html = f"<p>A câmera <strong>{nome_cam}</strong> do equipamento <strong>{nome_eq}</strong> está offline {tempo_texto}.</p>"
    return _enviar_email(db, conta, assunto, texto_puro, corpo_html, f"Câmera offline '{camera_nome}' em '{nvr.name}'")


def _enviar_email_alarme(db: Session, conta: Conta, titulo: str, mensagem: str) -> bool:
    return _enviar_email(db, conta, titulo, mensagem, f"<p>{html.escape(mensagem)}</p>", f"Alarme '{titulo}'")


def _enviar_email_personalizada(db: Session, conta: Conta, definicao: NotificacaoPersonalizada, titulo: str, mensagem: str) -> bool:
    texto_puro = f"{mensagem}\n\n(Notificação personalizada criada no painel: '{definicao.titulo}'.)"
    corpo_html = f"<p>{html.escape(mensagem)}</p><p style='color:#888;font-size:12px'>Notificação personalizada criada no painel: '{html.escape(definicao.titulo)}'.</p>"
    return _enviar_email(db, conta, titulo, texto_puro, corpo_html, f"Notificação personalizada '{definicao.titulo}'")


def verificar_licencas_unm2000(db: Session, hoje: Optional[date] = None) -> int:
    """Abre/atualiza/resolve a notificação de cada OLT com `licenca_fim` cadastrada; envia o e-mail diário
    enquanto faltar <= LIMIAR_LICENCA_DIAS. Retorna quantos e-mails foram enviados nesta chamada."""
    hoje = hoje or date.today()
    enviados = 0
    nvrs = db.query(NVR).join(Machine, NVR.machine_id == Machine.id).filter(
        NVR.tipo == "OLT", NVR.active == True, Machine.active == True
    ).all()
    for nvr in nvrs:
        try:
            licenca = licenca_da_config(nvr.config_extra)
            conta_id = nvr.machine.conta_id
            if not licenca or not tipo_ativo(db, conta_id, "LICENCA_UNM2000"):
                resolver(db, conta_id, "LICENCA_UNM2000", nvr_id=nvr.id)
                continue
            dias = licenca["dias_restantes"]
            if dias > LIMIAR_LICENCA_DIAS:
                resolver(db, conta_id, "LICENCA_UNM2000", nvr_id=nvr.id)
                continue

            if dias < 0:
                titulo = f"Licença da UNM2000 '{nvr.name}' vencida"
                mensagem = f"A licença venceu há {-dias} dia(s) (validade {licenca['fim']})."
            else:
                titulo = f"Licença da UNM2000 '{nvr.name}' vence em {dias} dia(s)"
                mensagem = f"A licença vence em {dias} dia(s) ({licenca['fim']})."
            notif = abrir_ou_atualizar(db, conta_id, "LICENCA_UNM2000", titulo, mensagem, nvr_id=nvr.id)

            if notif.ultimo_email_em != hoje:
                conta = nvr.machine.conta
                if conta and _enviar_email_licenca(db, conta, nvr, dias):
                    notif.ultimo_email_em = hoje
                    enviados += 1
        except Exception:
            logger.exception("Falha ao verificar a licença da UNM2000 '%s' (nvr %s)", getattr(nvr, "name", ""), getattr(nvr, "id", None))
    return enviados


def verificar_backups_falhos(db: Session) -> None:
    """Abre/resolve a notificação de backup com falha pelo último status conhecido da Máquina."""
    maquinas = db.query(Machine).filter(Machine.active == True).all()
    for m in maquinas:
        try:
            if not tipo_ativo(db, m.conta_id, "BACKUP_FALHOU"):
                resolver(db, m.conta_id, "BACKUP_FALHOU", machine_id=m.id)
                continue
            if m.last_backup_status == "ERROR":
                abrir_ou_atualizar(
                    db, m.conta_id, "BACKUP_FALHOU",
                    f"Backup com falha em '{m.name}'",
                    f"O último backup de '{m.name}' terminou com erro.",
                    machine_id=m.id,
                )
            else:
                resolver(db, m.conta_id, "BACKUP_FALHOU", machine_id=m.id)
        except Exception:
            logger.exception("Falha ao verificar o backup da máquina '%s' (%s)", getattr(m, "name", ""), getattr(m, "id", None))


def verificar_agentes_offline(db: Session, agora: Optional[datetime] = None) -> None:
    """Abre/resolve a notificação de agente offline (sem contato há mais de LIMIAR_AGENTE_OFFLINE_MIN minutos).
    Máquina que nunca chegou a conectar (`last_seen` nulo) não entra: ainda não é uma queda, é uma instalação pendente."""
    agora = agora or datetime.utcnow()
    limite = agora - timedelta(minutes=LIMIAR_AGENTE_OFFLINE_MIN)
    maquinas = db.query(Machine).filter(Machine.active == True, Machine.last_seen.isnot(None)).all()
    for m in maquinas:
        try:
            if not tipo_ativo(db, m.conta_id, "AGENTE_OFFLINE"):
                resolver(db, m.conta_id, "AGENTE_OFFLINE", machine_id=m.id)
                continue
            if m.last_seen < limite:
                abrir_ou_atualizar(
                    db, m.conta_id, "AGENTE_OFFLINE",
                    f"Agente offline em '{m.name}'",
                    f"'{m.name}' está sem contato desde {m.last_seen.strftime('%d/%m/%Y %H:%M')}.",
                    machine_id=m.id,
                )
            else:
                resolver(db, m.conta_id, "AGENTE_OFFLINE", machine_id=m.id)
        except Exception:
            logger.exception("Falha ao verificar o contato da máquina '%s' (%s)", getattr(m, "name", ""), getattr(m, "id", None))


def verificar_cameras_offline(db: Session, agora: Optional[datetime] = None) -> int:
    """Abre/atualiza/resolve a notificação de câmera offline (CAMERA_OFFLINE) para cada câmera marcada com
    `NVRCamera.notificar_offline=True` que estiver offline há mais que LIMIAR_CAMERA_OFFLINE_MIN minutos,
    segundo o `last_recording_status` do equipamento. Vale para NVR, DIGIFORT e DEFENSE — o pareamento de
    cada câmera com o relatório do agente usa a mesma regra de cada tipo (`services.galeria_vms.status_por_camera`:
    nome/pasta para DIGIFORT/DEFENSE, canal físico para NVR). Retorna quantos e-mails foram enviados nesta chamada."""
    agora = agora or datetime.utcnow()
    limite_s = LIMIAR_CAMERA_OFFLINE_MIN * 60
    enviados = 0
    nvrs = db.query(NVR).join(Machine, NVR.machine_id == Machine.id).filter(
        NVR.tipo.in_(("NVR", "DIGIFORT", "DEFENSE")), NVR.active == True, Machine.active == True
    ).all()
    for nvr in nvrs:
        try:
            cameras = list(nvr.cameras_status)
            if not any(c.notificar_offline for c in cameras):
                continue
            conta_id = nvr.machine.conta_id
            status_por_camera_id = status_por_camera(cameras, nvr.tipo, nvr.last_recording_status or [])
            for camera in cameras:
                if not camera.notificar_offline:
                    resolver(db, conta_id, "CAMERA_OFFLINE", nvr_id=nvr.id, camera_id=camera.id)
                    continue
                st = status_por_camera_id.get(camera.id)
                segundos, aprox = segundos_offline(st, agora) if st else (None, False)
                if segundos is None or segundos < limite_s:
                    resolver(db, conta_id, "CAMERA_OFFLINE", nvr_id=nvr.id, camera_id=camera.id)
                    continue
                tempo_texto = formatar_offline_ha(segundos, aprox)
                titulo = f"Câmera '{camera.nome}' offline em '{nvr.name}'"
                mensagem = f"A câmera '{camera.nome}' do equipamento '{nvr.name}' está offline {tempo_texto}."
                notif = abrir_ou_atualizar(db, conta_id, "CAMERA_OFFLINE", titulo, mensagem, nvr_id=nvr.id, camera_id=camera.id)
                if notif.ultimo_email_em != agora.date():
                    conta = nvr.machine.conta
                    if conta and _enviar_email_camera_offline(db, conta, nvr, camera.nome, tempo_texto):
                        notif.ultimo_email_em = agora.date()
                        enviados += 1
        except Exception:
            logger.exception("Falha ao verificar câmeras offline de '%s' (%s)", getattr(nvr, "name", ""), getattr(nvr, "id", None))
    return enviados


def _id_texto(valor, reserva) -> str:
    texto = str(valor).strip() if valor is not None else ""
    return texto or str(reserva or "").strip()


def id_central(central: dict) -> str:
    """Chave da central de alarme em `NVR.alarmes_notificar`: o id do painel (texto) ou, sem id, o nome."""
    return _id_texto(central.get("id"), central.get("nome"))


def situacoes_alarme(nvr: NVR) -> Optional[dict]:
    """{referencia: (titulo, mensagem)} do que está errado agora nas centrais marcadas (`NVR.alarmes_notificar`)
    de um DEFENSE, pelo último `last_alarm_status`. None quando a consulta falhou: aí só a referência "FALHA" vale,
    e o estado das centrais fica como estava (não dá para saber se o disparo já passou)."""
    marcadas = {str(c) for c in (nvr.alarmes_notificar or [])}
    status = nvr.last_alarm_status or {}
    if not marcadas:
        return {}
    if status.get("erro"):
        return None
    saida = {}
    for central in status.get("alarmes") or []:
        if not isinstance(central, dict):
            continue
        cid = id_central(central)
        if cid not in marcadas:
            continue
        nome_c = central.get("nome") or "Central sem nome"
        if central.get("status") != 1:
            saida[f"{cid}:DESCONECTADA"] = (
                f"Central de alarme '{nome_c}' desconectada",
                f"A central de alarme '{nome_c}' do equipamento '{nvr.name}' está desconectada.",
            )
        for particao in central.get("particoes") or []:
            if not isinstance(particao, dict):
                continue
            pid = _id_texto(particao.get("id"), particao.get("nome"))
            nome_p = particao.get("nome") or "Partição"
            if particao.get("disparada"):
                saida[f"{cid}:{pid}:DISPARO"] = (
                    f"Alarme disparado: '{nome_c}' / '{nome_p}'",
                    f"A partição '{nome_p}' da central '{nome_c}' ({nvr.name}) está em disparo.",
                )
            if not particao.get("armada"):
                saida[f"{cid}:{pid}:DESARMADA"] = (
                    f"Partição desarmada: '{nome_c}' / '{nome_p}'",
                    f"A partição '{nome_p}' da central '{nome_c}' ({nvr.name}) está desarmada.",
                )
    return saida


def verificar_alarmes_equipamento(db: Session, nvr: NVR, agora: Optional[datetime] = None) -> int:
    """Abre/atualiza/resolve as notificações ALARME de um DEFENSE (uma por situação, separadas por `referencia`)
    e manda o e-mail diário de cada alerta aberto. Chamada ao receber o relatório do agente (o disparo aparece na
    hora) e no ciclo periódico (pega mudanças de opt-in). Relatório velho demais não muda nada: a queda do agente
    já tem a própria notificação. Retorna quantos e-mails foram enviados."""
    agora = agora or datetime.utcnow()
    conta_id = nvr.machine.conta_id
    abertas = db.query(Notificacao).filter(
        Notificacao.conta_id == conta_id, Notificacao.tipo == "ALARME", Notificacao.nvr_id == nvr.id,
        Notificacao.resolvido_em.is_(None),
    ).all()

    status = nvr.last_alarm_status or {}
    try:
        coletado = datetime.strptime(status.get("atualizado_em") or "", "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        coletado = None
    if nvr.alarmes_notificar and (coletado is None or agora - coletado > timedelta(minutes=LIMIAR_ALARME_SEM_DADOS_MIN)):
        return 0

    situacoes = situacoes_alarme(nvr)
    falhou = situacoes is None
    if falhou:
        situacoes = {"FALHA": (
            f"Falha ao consultar alarmes em '{nvr.name}'",
            f"O agente não conseguiu consultar o painel de alarmes de '{nvr.name}': {status.get('erro')}",
        )}

    for notif in abertas:
        manter = notif.referencia in situacoes or (falhou and notif.referencia != "FALHA")
        if not manter:
            notif.resolvido_em = agora

    enviados = 0
    for referencia, (titulo, mensagem) in situacoes.items():
        titulo = titulo[:255]
        notif = abrir_ou_atualizar(db, conta_id, "ALARME", titulo, mensagem, nvr_id=nvr.id, referencia=referencia[:120])
        if notif.ultimo_email_em != agora.date():
            conta = nvr.machine.conta
            if conta and _enviar_email_alarme(db, conta, titulo, mensagem):
                notif.ultimo_email_em = agora.date()
                enviados += 1
    return enviados


def verificar_alarmes(db: Session, agora: Optional[datetime] = None) -> int:
    """Roda `verificar_alarmes_equipamento` em todos os DEFENSE ativos. Retorna quantos e-mails saíram."""
    enviados = 0
    nvrs = db.query(NVR).join(Machine, NVR.machine_id == Machine.id).filter(
        NVR.tipo == "DEFENSE", NVR.active == True, Machine.active == True
    ).all()
    for nvr in nvrs:
        try:
            enviados += verificar_alarmes_equipamento(db, nvr, agora)
        except Exception:
            logger.exception("Falha ao verificar alarmes de '%s' (%s)", getattr(nvr, "name", ""), getattr(nvr, "id", None))
    return enviados


def verificar_personalizadas(db: Session, agora: Optional[datetime] = None, hoje: Optional[date] = None) -> int:
    """Verifica as definições personalizadas ativas de todas as contas. `mostrar_popup`/`enviar_email` não mudam
    o que é gravado aqui: a notificação sempre fica registrada e visível na aba Notificações; quem decide o que
    aparece no pop-up de login é o router (só os com `mostrar_popup=True`), e o e-mail só sai se `enviar_email=True`.
    - Modo DATA: comporta-se como a licença (1 notificação aberta, atualizada a cada ciclo) enquanto faltar
      <= dias_antes para data_alvo; depois que a data passa continua aberta avisando "venceu há N dias" até o
      usuário desativar ou apagar a definição (não se resolve sozinha). E-mail: 1 por dia corrido, se `enviar_email`.
    - Modo RECORRENTE: dispara a cada `intervalo_dias` (desde o último disparo, ou desde a criação se nunca
      disparou). Cada disparo fecha o alerta anterior (se houver) e cria um novo — fica um histórico. E-mail no
      momento do disparo, se `enviar_email` (sem dedup: o próprio intervalo evita repetição).
    Retorna quantos e-mails foram enviados nesta chamada."""
    agora = agora or datetime.utcnow()
    hoje = hoje or date.today()
    enviados = 0
    definicoes = db.query(NotificacaoPersonalizada).filter(NotificacaoPersonalizada.ativo == True).all()
    for defi in definicoes:
        try:
            conta_id = defi.conta_id
            if defi.modo == "DATA":
                if not defi.data_alvo:
                    continue
                dias = (defi.data_alvo - hoje).days
                limiar = defi.dias_antes if defi.dias_antes is not None else 0
                if dias > limiar:
                    resolver(db, conta_id, "PERSONALIZADA", definicao_id=defi.id)
                    continue
                if dias < 0:
                    titulo = f"{defi.titulo} (venceu há {-dias} dia(s))"
                else:
                    titulo = f"{defi.titulo} (faltam {dias} dia(s))"
                notif = abrir_ou_atualizar(db, conta_id, "PERSONALIZADA", titulo, defi.mensagem, definicao_id=defi.id)
                if defi.enviar_email and notif.ultimo_email_em != hoje:
                    conta = db.get(Conta, conta_id)
                    if conta and _enviar_email_personalizada(db, conta, defi, titulo, defi.mensagem):
                        notif.ultimo_email_em = hoje
                        enviados += 1
            elif defi.modo == "RECORRENTE":
                if not defi.intervalo_dias or defi.intervalo_dias < 1:
                    continue
                base = defi.ultimo_disparo_em or defi.criado_em
                if agora < base + timedelta(days=defi.intervalo_dias):
                    continue
                resolver(db, conta_id, "PERSONALIZADA", definicao_id=defi.id)  # fecha o disparo anterior (histórico)
                defi.ultimo_disparo_em = agora
                notif = Notificacao(
                    conta_id=conta_id, tipo="PERSONALIZADA", titulo=defi.titulo, mensagem=defi.mensagem,
                    definicao_id=defi.id,
                )
                db.add(notif)
                if defi.enviar_email:
                    conta = db.get(Conta, conta_id)
                    if conta and _enviar_email_personalizada(db, conta, defi, defi.titulo, defi.mensagem):
                        enviados += 1
        except Exception:
            logger.exception("Falha ao verificar a notificação personalizada '%s' (%s)", getattr(defi, "titulo", ""), getattr(defi, "id", None))
    return enviados


def verificar_notificacoes(db: Session) -> dict:
    """Roda as quatro verificações (cada uma isolada: uma falhar não impede as outras) e salva. Usada pela tarefa
    de fundo do main.py. Retorna um pequeno resumo para o log."""
    resumo = {"emails_licenca": 0, "emails_personalizadas": 0, "emails_camera_offline": 0, "emails_alarme": 0}
    try:
        resumo["emails_licenca"] = verificar_licencas_unm2000(db)
    except Exception:
        logger.exception("Falha geral ao verificar licenças da UNM2000")
    try:
        verificar_backups_falhos(db)
    except Exception:
        logger.exception("Falha geral ao verificar backups com falha")
    try:
        verificar_agentes_offline(db)
    except Exception:
        logger.exception("Falha geral ao verificar agentes offline")
    try:
        resumo["emails_camera_offline"] = verificar_cameras_offline(db)
    except Exception:
        logger.exception("Falha geral ao verificar câmeras offline")
    try:
        resumo["emails_alarme"] = verificar_alarmes(db)
    except Exception:
        logger.exception("Falha geral ao verificar alarmes")
    try:
        resumo["emails_personalizadas"] = verificar_personalizadas(db)
    except Exception:
        logger.exception("Falha geral ao verificar notificações personalizadas")
    db.commit()
    return resumo
