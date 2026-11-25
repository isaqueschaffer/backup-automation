from datetime import datetime
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from auth import (
    Contexto,
    create_access_token,
    create_access_token_usuario,
    get_contexto_sem_bloqueio,
)
from config import settings
from database import get_db
from models import Setting, Usuario
from schemas import (
    ContaResumo,
    LoginRequest,
    MeResponse,
    Rotulos,
    TokenResponse,
    TrocarSenhaRequest,
    UsuarioMe,
)
from services import senhas
from services.contas import obter_conta_plataforma_id, resumo_da_conta, rotulos_da_conta
from services.dashboards.compartilhamento import LimitadorJanela, ip_do_cliente

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Senha do login legado (só senha, super admin da plataforma): bcrypt nesta chave da tabela settings; sem ela vale a
# variável de ambiente ADMIN_PASSWORD. Instalações antigas guardaram a senha em texto puro aqui (PUT /settings).
CHAVE_SENHA_ADMIN = "admin_password_hash"

limite_login = LimitadorJanela(maximo=10, janela_s=300)


def conferir_senha_admin(db: Session, senha: str) -> bool:
    """Confere a senha do login legado. Com hash bcrypt gravado, compara pelo bcrypt; com valor antigo em texto puro,
    compara em tempo constante e, se bater, regrava já como hash (migração no primeiro login). Sem nada gravado,
    compara com ADMIN_PASSWORD (variável de ambiente), que continua em texto puro no ambiente."""
    row = db.query(Setting).filter(Setting.key == CHAVE_SENHA_ADMIN).first()
    guardado = row.value if row else None
    if not guardado:
        return hmac.compare_digest((senha or "").encode(), (settings.ADMIN_PASSWORD or "").encode())
    if senhas.eh_hash_bcrypt(guardado):
        return senhas.conferir(senha, guardado)
    if not hmac.compare_digest((senha or "").encode(), guardado.encode()):
        return False
    if len(senha.encode()) <= senhas.SENHA_MAX_BYTES:  # acima disso o bcrypt cortaria a senha
        try:
            row.value = senhas.gerar_hash(senha)
            db.commit()
            logger.info("Senha do administrador da plataforma migrada de texto puro para bcrypt.")
        except Exception:
            db.rollback()
            logger.exception("Não foi possível regravar a senha do administrador como hash; o login segue valendo.")
    return True


def gravar_senha_admin(db: Session, senha: str) -> None:
    """Grava a nova senha do login legado como hash bcrypt (sem commit). ValueError se a senha não serve."""
    senhas.validar_senha_nova(senha)
    valor = senhas.gerar_hash(senha)
    row = db.query(Setting).filter(Setting.key == CHAVE_SENHA_ADMIN).first()
    if row:
        row.value = valor
    else:
        db.add(Setting(key=CHAVE_SENHA_ADMIN, value=valor))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = ip_do_cliente(request)
    if not limite_login.disponivel(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas. Tente novamente em alguns minutos.",
        )

    # Login legado: sem email (apenas senha)
    if not body.email or not body.email.strip():
        if not conferir_senha_admin(db, body.password):
            limite_login.registrar(ip)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong password")
        token = create_access_token({"sub": "admin"})
        return TokenResponse(access_token=token)

    # Login multi-contas: com email
    email_limpo = body.email.strip().lower()
    usuario = db.query(Usuario).filter(Usuario.email == email_limpo).first()

    senha_valida = senhas.conferir(body.password, usuario.senha_hash if usuario else None)
    if not senha_valida or not usuario or not usuario.ativo:
        limite_login.registrar(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos",
        )

    usuario.ultimo_login = datetime.utcnow()
    db.commit()

    token = create_access_token_usuario(usuario)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=MeResponse)
def get_me(
    ctx: Contexto = Depends(get_contexto_sem_bloqueio),
    db: Session = Depends(get_db),
):
    usuario_me = UsuarioMe(
        id=ctx.usuario_id,
        nome=ctx.nome,
        email=ctx.email,
        papel=ctx.papel,
    )

    conta_resumo = None
    if ctx.conta:
        plataforma_id = obter_conta_plataforma_id(db)
        conta_resumo = ContaResumo(**resumo_da_conta(ctx.conta, plataforma_id))

    rotulos = Rotulos(**rotulos_da_conta(ctx.conta))

    return MeResponse(
        usuario=usuario_me,
        conta=conta_resumo,
        somente_leitura=ctx.somente_leitura,
        pode_testar=ctx.pode_testar,
        rotulos=rotulos,
    )


@router.post("/renovar", response_model=TokenResponse)
def renovar(
    ctx: Contexto = Depends(get_contexto_sem_bloqueio),
    db: Session = Depends(get_db),
):
    """Troca um token ainda válido por um novo (mais ACCESS_TOKEN_EXPIRE_HOURS). O painel chama periodicamente para a
    tela de monitoramento não cair no login. Usuário desativado ou com senha trocada já falha em get_contexto (401).
    O login legado do admin (só senha) não renova: não há como revogar essa sessão sem trocar a SECRET_KEY."""
    if ctx.usuario_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O login só com senha não renova a sessão. Use um usuário com e-mail.",
        )
    usuario = db.query(Usuario).filter(Usuario.id == ctx.usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão expirada. Entre novamente.")
    return TokenResponse(access_token=create_access_token_usuario(usuario))


@router.post("/trocar-senha", response_model=TokenResponse)
def trocar_senha(
    body: TrocarSenhaRequest,
    ctx: Contexto = Depends(get_contexto_sem_bloqueio),
    db: Session = Depends(get_db),
):
    if ctx.usuario_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use Configurações para trocar a senha do administrador da plataforma.",
        )

    usuario = db.query(Usuario).filter(Usuario.id == ctx.usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    if not senhas.conferir(body.senha_atual, usuario.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Senha atual incorreta.",
        )

    usuario.senha_hash = senhas.gerar_hash(body.senha_nova)
    usuario.token_versao += 1
    db.commit()

    novo_token = create_access_token_usuario(usuario)
    return TokenResponse(access_token=novo_token)
