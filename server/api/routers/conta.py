"""Rotas do inquilino (minha conta e gestão de usuários da conta)."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import Contexto, exigir_admin_conta, get_contexto
from database import get_db
from models import Conta, Usuario
from schemas import (
    ContaDetalheResponse,
    RenovacaoResponse,
    UsuarioCreate,
    UsuarioResponse,
    UsuarioUpdate,
)
from services import senhas
from services.contas import contagens_por_conta, obter_conta_plataforma_id, resumo_da_conta

router = APIRouter(prefix="/api/v1/conta", tags=["Conta"])


def montar_conta_detalhe(conta: Conta, db: Session, plataforma_id: Optional[UUID]) -> ContaDetalheResponse:
    """Resposta completa da conta (também usada pelas rotas do super admin em contas_admin.py)."""
    resumo = resumo_da_conta(conta, plataforma_id)
    cli, mac, usr = contagens_por_conta(db).get(conta.id, (0, 0, 0))
    renovacoes = [RenovacaoResponse.model_validate(r) for r in conta.renovacoes]
    return ContaDetalheResponse(
        **resumo,
        documento=conta.documento,
        email_contato=conta.email_contato,
        telefone=conta.telefone,
        observacoes=conta.observacoes,
        plano_id=conta.plano_id,
        ativo=conta.ativo,
        criado_em=conta.criado_em,
        total_clientes=cli,
        total_maquinas=mac,
        total_usuarios=usr,
        renovacoes=renovacoes,
    )


@router.get("", response_model=ContaDetalheResponse)
def obter_minha_conta(
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    if not ctx.conta_id or not ctx.conta:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selecione uma conta.",
        )
    conta = db.query(Conta).filter(Conta.id == ctx.conta_id).first()
    if not conta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta não encontrada.",
        )
    plataforma_id = obter_conta_plataforma_id(db)
    return montar_conta_detalhe(conta, db, plataforma_id)


@router.get("/usuarios", response_model=List[UsuarioResponse])
def listar_usuarios(
    ctx: Contexto = Depends(exigir_admin_conta),
    db: Session = Depends(get_db),
):
    return db.query(Usuario).filter(Usuario.conta_id == ctx.conta_id).order_by(Usuario.nome.asc()).all()


@router.post("/usuarios", status_code=status.HTTP_201_CREATED, response_model=UsuarioResponse)
def criar_usuario(
    body: UsuarioCreate,
    ctx: Contexto = Depends(exigir_admin_conta),
    db: Session = Depends(get_db),
):
    if body.papel not in ("ADMIN", "LEITURA"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Papel inválido.")

    email = body.email.strip().lower()
    if db.query(Usuario.id).filter(Usuario.email == email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-mail já cadastrado.")

    usuario = Usuario(
        nome=body.nome,
        email=email,
        senha_hash=senhas.gerar_hash(body.senha),
        papel=body.papel,
        conta_id=ctx.conta_id,
        ativo=True,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


@router.put("/usuarios/{id}", response_model=UsuarioResponse)
def atualizar_usuario(
    id: UUID,
    body: UsuarioUpdate,
    ctx: Contexto = Depends(exigir_admin_conta),
    db: Session = Depends(get_db),
):
    usuario = db.query(Usuario).filter(Usuario.id == id, Usuario.conta_id == ctx.conta_id).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    novo_papel = body.papel if body.papel is not None else usuario.papel
    novo_ativo = body.ativo if body.ativo is not None else usuario.ativo

    # Se for mudar papel para LEITURA ou ativo para False, verifica se resta ao menos um ADMIN ativo
    if usuario.papel == "ADMIN" and usuario.ativo is True:
        if novo_papel != "ADMIN" or novo_ativo is not True:
            admin_ativos_restantes = db.query(Usuario).filter(
                Usuario.conta_id == ctx.conta_id,
                Usuario.papel == "ADMIN",
                Usuario.ativo == True,
                Usuario.id != usuario.id,
            ).count()
            if admin_ativos_restantes == 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A conta precisa de pelo menos um administrador ativo.",
                )

    mudou_seguranca = False
    if body.senha:
        usuario.senha_hash = senhas.gerar_hash(body.senha)
        mudou_seguranca = True

    if body.papel is not None and body.papel != usuario.papel:
        if body.papel not in ("ADMIN", "LEITURA"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Papel inválido.")
        usuario.papel = body.papel
        mudou_seguranca = True

    if body.ativo is not None and body.ativo != usuario.ativo:
        usuario.ativo = body.ativo
        mudou_seguranca = True

    if mudou_seguranca:
        usuario.token_versao += 1

    if "nome" in body.model_fields_set and body.nome is not None:
        usuario.nome = body.nome

    db.commit()
    db.refresh(usuario)
    return usuario
