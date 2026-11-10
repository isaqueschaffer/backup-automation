"""Rotas administrativas de Contas (inquilinos), Planos e Super Admins (só SUPER_ADMIN)."""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import Contexto, exigir_super_admin
from database import get_db
from models import Conta, Customer, Plano, Usuario
from schemas import (
    ContaCreate,
    ContaDetalheResponse,
    ContaResponse,
    ContaUpdate,
    MoverContaRequest,
    PlanoCreate,
    PlanoResponse,
    PlanoUpdate,
    RenovarRequest,
    SuperAdminCreate,
    SuperAdminUpdate,
    UsuarioResponse,
)
from routers.conta import montar_conta_detalhe as _montar_conta_detalhe
from services import senhas
from services.contas import (
    ajustar_validade,
    contagens_por_conta,
    obter_conta_plataforma_id,
    renovar_conta,
    resumo_da_conta,
)

router = APIRouter(prefix="/api/v1/admin", tags=["Contas"])


# ─── Planos ───────────────────────────────────────────────────────────────────

@router.get("/planos", response_model=List[PlanoResponse])
def listar_planos(
    ctx: Contexto = Depends(exigir_super_admin),
    db: Session = Depends(get_db),
):
    return db.query(Plano).order_by(Plano.duracao_dias.asc()).all()


@router.post("/planos", status_code=status.HTTP_201_CREATED, response_model=PlanoResponse)
def criar_plano(
    body: PlanoCreate,
    ctx: Contexto = Depends(exigir_super_admin),
    db: Session = Depends(get_db),
):
    ja_existe = db.query(Plano).filter(func.lower(Plano.nome) == body.nome.lower()).first()
    if ja_existe:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um plano com esse nome.",
        )
    plano = Plano(nome=body.nome, duracao_dias=body.duracao_dias)
    db.add(plano)
    db.commit()
    db.refresh(plano)
    return plano


@router.put("/planos/{id}", response_model=PlanoResponse)
def atualizar_plano(
    id: UUID,
    body: PlanoUpdate,
    ctx: Contexto = Depends(exigir_super_admin),
    db: Session = Depends(get_db),
):
    plano = db.query(Plano).filter(Plano.id == id).first()
    if not plano:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plano não encontrado.")

    if body.nome is not None:
        conflito = (
            db.query(Plano)
            .filter(Plano.id != id, func.lower(Plano.nome) == body.nome.lower())
            .first()
        )
        if conflito:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe um plano com esse nome.",
            )

    if "nome" in body.model_fields_set and body.nome is not None:
        plano.nome = body.nome
    if "duracao_dias" in body.model_fields_set and body.duracao_dias is not None:
        plano.duracao_dias = body.duracao_dias
    if "ativo" in body.model_fields_set and body.ativo is not None:
        plano.ativo = body.ativo

    db.commit()
    db.refresh(plano)
    return plano


# ─── Contas ───────────────────────────────────────────────────────────────────

@router.get("/contas", response_model=List[ContaResponse])
def listar_contas(
    ctx: Contexto = Depends(exigir_super_admin),
    db: Session = Depends(get_db),
):
    plataforma_id = obter_conta_plataforma_id(db)
    contagens = contagens_por_conta(db)
    contas = db.query(Conta).order_by(Conta.nome.asc()).all()
    resultado = []
    for c in contas:
        resumo = resumo_da_conta(c, plataforma_id)
        cli, mac, usr = contagens.get(c.id, (0, 0, 0))
        resultado.append(
            ContaResponse(
                **resumo,
                documento=c.documento,
                email_contato=c.email_contato,
                telefone=c.telefone,
                observacoes=c.observacoes,
                plano_id=c.plano_id,
                ativo=c.ativo,
                criado_em=c.criado_em,
                total_clientes=cli,
                total_maquinas=mac,
                total_usuarios=usr,
            )
        )
    return resultado


@router.post("/contas", status_code=status.HTTP_201_CREATED, response_model=ContaDetalheResponse)
def criar_conta(
    body: ContaCreate,
    ctx: Contexto = Depends(exigir_super_admin),
    db: Session = Depends(get_db),
):
    plano = db.query(Plano).filter(Plano.id == body.plano_id, Plano.ativo == True).first()
    if not plano:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Plano inválido.",
        )

    email_admin = body.admin.email.strip().lower()
    if db.query(Usuario.id).filter(Usuario.email == email_admin).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="E-mail já cadastrado.",
        )

    conta = Conta(
        nome=body.nome,
        tipo=body.tipo,
        documento=body.documento,
        email_contato=body.email_contato,
        telefone=body.telefone,
        observacoes=body.observacoes,
        plano_id=body.plano_id,
        expira_em=None,
        avisos_enviados=[],
    )
    db.add(conta)
    db.flush()

    renovar_conta(db, conta, plano, feito_por=ctx.feito_por)

    usuario = Usuario(
        nome=body.admin.nome,
        email=email_admin,
        senha_hash=senhas.gerar_hash(body.admin.senha),
        papel="ADMIN",
        conta_id=conta.id,
        ativo=True,
    )
    db.add(usuario)
    db.commit()
    db.refresh(conta)

    plataforma_id = obter_conta_plataforma_id(db)
    return _montar_conta_detalhe(conta, db, plataforma_id)


@router.get("/contas/{id}", response_model=ContaDetalheResponse)
def obter_conta(
    id: UUID,
    ctx: Contexto = Depends(exigir_super_admin),
    db: Session = Depends(get_db),
):
    conta = db.query(Conta).filter(Conta.id == id).first()
    if not conta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta não encontrada.",
        )
    plataforma_id = obter_conta_plataforma_id(db)
    return _montar_conta_detalhe(conta, db, plataforma_id)


@router.put("/contas/{id}", response_model=ContaDetalheResponse)
def atualizar_conta(
    id: UUID,
    body: ContaUpdate,
    ctx: Contexto = Depends(exigir_super_admin),
    db: Session = Depends(get_db),
):
    conta = db.query(Conta).filter(Conta.id == id).first()
    if not conta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta não encontrada.",
        )

    plataforma_id = obter_conta_plataforma_id(db)

    if "expira_em" in body.model_fields_set:
        if conta.id == plataforma_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A conta da plataforma não tem validade.",
            )
        if body.expira_em is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Informe a data de validade.",
            )
        ajustar_validade(db, conta, body.expira_em, feito_por=ctx.feito_por)

    if "nome" in body.model_fields_set and body.nome is not None:
        conta.nome = body.nome
    if "tipo" in body.model_fields_set and body.tipo is not None:
        conta.tipo = body.tipo
    if "documento" in body.model_fields_set:
        conta.documento = body.documento
    if "email_contato" in body.model_fields_set:
        conta.email_contato = body.email_contato
    if "telefone" in body.model_fields_set:
        conta.telefone = body.telefone
    if "observacoes" in body.model_fields_set:
        conta.observacoes = body.observacoes

    db.commit()
    db.refresh(conta)
    return _montar_conta_detalhe(conta, db, plataforma_id)


@router.post("/contas/{id}/renovar", response_model=ContaDetalheResponse)
def renovar_plano_conta(
    id: UUID,
    body: RenovarRequest,
    ctx: Contexto = Depends(exigir_super_admin),
    db: Session = Depends(get_db),
):
    conta = db.query(Conta).filter(Conta.id == id).first()
    if not conta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta não encontrada.",
        )

    plataforma_id = obter_conta_plataforma_id(db)
    if conta.id == plataforma_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A conta da plataforma não tem validade.",
        )

    plano = db.query(Plano).filter(Plano.id == body.plano_id, Plano.ativo == True).first()
    if not plano:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Plano inválido.",
        )

    renovar_conta(db, conta, plano, feito_por=ctx.feito_por)
    db.commit()
    db.refresh(conta)
    return _montar_conta_detalhe(conta, db, plataforma_id)


@router.post("/contas/{id}/suspender", response_model=ContaDetalheResponse)
def suspender_conta(
    id: UUID,
    ctx: Contexto = Depends(exigir_super_admin),
    db: Session = Depends(get_db),
):
    conta = db.query(Conta).filter(Conta.id == id).first()
    if not conta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta não encontrada.",
        )

    plataforma_id = obter_conta_plataforma_id(db)
    if conta.id == plataforma_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A conta da plataforma não pode ser suspensa.",
        )

    conta.ativo = False
    db.commit()
    db.refresh(conta)
    return _montar_conta_detalhe(conta, db, plataforma_id)


@router.post("/contas/{id}/reativar", response_model=ContaDetalheResponse)
def reativar_conta(
    id: UUID,
    ctx: Contexto = Depends(exigir_super_admin),
    db: Session = Depends(get_db),
):
    conta = db.query(Conta).filter(Conta.id == id).first()
    if not conta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta não encontrada.",
        )

    plataforma_id = obter_conta_plataforma_id(db)
    if conta.id == plataforma_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A conta da plataforma não pode ser suspensa.",
        )

    conta.ativo = True
    db.commit()
    db.refresh(conta)
    return _montar_conta_detalhe(conta, db, plataforma_id)


# ─── Clientes ─────────────────────────────────────────────────────────────────

@router.post("/clientes/{customer_id}/mover-conta")
def mover_cliente_de_conta(
    customer_id: UUID,
    body: MoverContaRequest,
    ctx: Contexto = Depends(exigir_super_admin),
    db: Session = Depends(get_db),
):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente não encontrado.",
        )

    conta_destino = db.query(Conta).filter(Conta.id == body.conta_id).first()
    if not conta_destino:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta não encontrada",
        )

    if customer.queue_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Aguarde a fila de backup do Cliente terminar.",
        )

    customer.conta_id = conta_destino.id
    for machine in customer.machines:
        machine.conta_id = conta_destino.id

    db.commit()
    return {"status": "ok", "maquinas_movidas": len(customer.machines)}


# ─── Super Admins ─────────────────────────────────────────────────────────────

@router.get("/super-admins", response_model=List[UsuarioResponse])
def listar_super_admins(
    ctx: Contexto = Depends(exigir_super_admin),
    db: Session = Depends(get_db),
):
    return db.query(Usuario).filter(Usuario.papel == "SUPER_ADMIN").order_by(Usuario.nome.asc()).all()


@router.post("/super-admins", status_code=status.HTTP_201_CREATED, response_model=UsuarioResponse)
def criar_super_admin(
    body: SuperAdminCreate,
    ctx: Contexto = Depends(exigir_super_admin),
    db: Session = Depends(get_db),
):
    email = body.email.strip().lower()
    if db.query(Usuario.id).filter(Usuario.email == email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="E-mail já cadastrado.",
        )

    usuario = Usuario(
        nome=body.nome,
        email=email,
        senha_hash=senhas.gerar_hash(body.senha),
        papel="SUPER_ADMIN",
        conta_id=None,
        ativo=True,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


@router.put("/super-admins/{id}", response_model=UsuarioResponse)
def atualizar_super_admin(
    id: UUID,
    body: SuperAdminUpdate,
    ctx: Contexto = Depends(exigir_super_admin),
    db: Session = Depends(get_db),
):
    usuario = db.query(Usuario).filter(Usuario.id == id, Usuario.papel == "SUPER_ADMIN").first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado.",
        )

    if body.ativo is False and usuario.id == ctx.usuario_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Você não pode desativar o próprio usuário.",
        )

    if body.senha:
        usuario.senha_hash = senhas.gerar_hash(body.senha)
        usuario.token_versao += 1

    if body.ativo is not None and body.ativo != usuario.ativo:
        usuario.ativo = body.ativo
        usuario.token_versao += 1

    if "nome" in body.model_fields_set and body.nome is not None:
        usuario.nome = body.nome

    db.commit()
    db.refresh(usuario)
    return usuario
