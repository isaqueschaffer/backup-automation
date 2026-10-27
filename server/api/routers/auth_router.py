from datetime import datetime
import secrets

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

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

limite_login = LimitadorJanela(maximo=10, janela_s=300)


def get_admin_password(db: Session) -> str:
    """Fetch admin password from DB settings or fall back to env var."""
    row = db.query(Setting).filter(Setting.key == "admin_password_hash").first()
    # If stored in settings table (plain for now — bcrypt optional upgrade)
    if row and row.value:
        return row.value
    return settings.ADMIN_PASSWORD


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
        admin_pw = get_admin_password(db)
        if not secrets.compare_digest(body.password.encode(), admin_pw.encode()):
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
        rotulos=rotulos,
    )


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
