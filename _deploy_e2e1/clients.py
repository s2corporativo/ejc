# ── app/routers/clients.py ───────────────────────────────────────────────────
# CRM de clientes + VERIFICAÇÃO DE CONFLITO DE INTERESSES (OAB obrigatório)
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.models.client import Client
from app.models.case import Case
from app.models.audit_log import criar_audit_log
from app.schemas.client import (
    ClientCreate, ClientUpdate, ClientResponse, ConflitoCheckRequest,
)
from app.schemas.common import MsgResponse

router = APIRouter(prefix="/clients", tags=["Clientes / CRM"])

# Gestão de clientes conforme a matriz de permissões (inclui secretaria; exclui
# estagiario/advogado_auxiliar/financeiro de escrita). Leitura segue autenticada.
_CLIENTES = {"superadmin", "admin", "socio", "advogado", "secretaria"}


def _req_clientes(cu: User = Depends(get_current_user)) -> User:
    if cu.role.value not in _CLIENTES:
        raise HTTPException(status_code=403, detail="Sem permissão para gerenciar clientes")
    return cu


@router.post("/verificar-conflito")
async def verificar_conflito(
    req: ConflitoCheckRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Verificação OBRIGATÓRIA antes de cadastrar cliente/caso (EOAB arts. 34-35).
    Busca: nome/CPF/CNPJ como cliente existente E como parte contrária.
    """
    # Lógica extraída para conflito_service (reutilizada no cadastro).
    from app.services.conflito_service import detectar_conflito

    resultado = await detectar_conflito(
        db, nome=req.nome, cpf=req.cpf, cnpj=req.cnpj,
        parte_contraria=req.parte_contraria,
    )
    achados = resultado["achados"]
    classificacao = resultado["classificacao"]
    conflito_grave = resultado["bloqueio"]

    # Audit obrigatório (proteção OAB)
    await criar_audit_log(
        db, cu.id, cu.role.value, "CONFLITO_CHECK", "clients",
        detalhes=f"{classificacao}: {len(achados)} achado(s)",
    )
    await db.commit()

    return {
        "classificacao": classificacao,
        "achados": achados,
        "bloqueio": conflito_grave,
        "orientacao": (
            "⛔ Conflito identificado — caso só pode prosseguir com aprovação de sócio"
            if conflito_grave else
            "⚠️ Verifique os achados antes de prosseguir"
            if achados else
            "✅ Nenhum conflito encontrado"
        ),
    }


@router.get("/")
async def listar(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None, status_f: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Client).where(Client.deleted_at.is_(None))
    if search:
        q = q.where(or_(
            Client.nome.ilike(f"%{search}%"),
            Client.razao_social.ilike(f"%{search}%"),
            Client.cpf.ilike(f"%{search}%"),
            Client.cnpj.ilike(f"%{search}%"),
        ))
    if status_f:
        q = q.where(Client.status == status_f)
    q = q.order_by(Client.created_at.desc())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar()
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {
        "data": [ClientResponse.model_validate(c) for c in rows],
        "total": total, "page": page, "page_size": page_size,
    }


@router.post("/", response_model=ClientResponse, status_code=201)
async def criar(
    payload: ClientCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_clientes),
):
    # Validação básica PF/PJ
    if payload.tipo == "PF" and not payload.nome:
        raise HTTPException(status_code=422, detail="PF requer nome")
    if payload.tipo == "PJ" and not payload.razao_social:
        raise HTTPException(status_code=422, detail="PJ requer razão social")

    # Validação matemática (dígito verificador) — evita cadastros com erro
    from app.services.validators_service import validar_cpf as _vcpf, validar_cnpj as _vcnpj
    if payload.cpf and not _vcpf(payload.cpf):
        raise HTTPException(status_code=422, detail="CPF inválido (dígito verificador)")
    if payload.cnpj and not _vcnpj(payload.cnpj):
        raise HTTPException(status_code=422, detail="CNPJ inválido (dígito verificador)")

    # Detecção de conflito (EOAB arts. 34-35) — NÃO bloqueia o cadastro
    # (resultado = alerta; decisão humana obrigatória), mas registra em
    # audit_logs para rastreabilidade ética.
    from app.services.conflito_service import detectar_conflito
    conflito = await detectar_conflito(
        db, nome=payload.nome or payload.razao_social,
        cpf=payload.cpf, cnpj=payload.cnpj,
    )

    c = Client(
        id=str(uuid4()), responsavel_id=cu.id,
        **payload.model_dump(),
    )
    db.add(c)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "clients", c.id)
    if conflito["classificacao"] != "SEM_CONFLITO":
        await criar_audit_log(
            db, cu.id, cu.role.value, "CONFLITO_CHECK", "clients", c.id,
            detalhes=(
                f"{conflito['classificacao']} no cadastro: "
                f"{len(conflito['achados'])} achado(s)"
            ),
        )
    await db.commit()
    await db.refresh(c)
    return c


@router.get("/{client_id}", response_model=ClientResponse)
async def detalhe(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    c = (await db.execute(
        select(Client).where(Client.id == client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return c


@router.patch("/{client_id}", response_model=ClientResponse)
async def atualizar(
    client_id: str, payload: ClientUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_clientes),
):
    c = (await db.execute(
        select(Client).where(Client.id == client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    await criar_audit_log(db, cu.id, cu.role.value, "UPDATE", "clients", client_id)
    await db.commit()
    await db.refresh(c)
    return c


@router.delete("/{client_id}", response_model=MsgResponse)
async def remover(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["admin", "socio"])),
):
    c = (await db.execute(
        select(Client).where(Client.id == client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    c.deleted_at = datetime.now(timezone.utc)
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "clients", client_id)
    await db.commit()
    return MsgResponse(detail="Cliente removido")


# ═══ Validação de documentos + Acesso ao Portal + Relatório LGPD ═══
from pydantic import BaseModel as _BM, EmailStr as _Email, Field as _Field
from app.services.validators_service import validar_cpf, validar_cnpj
from app.core.security import get_password_hash
from app.models.user import User as _User, UserRole as _Role
from fastapi.responses import Response as _Resp


class CriarAcessoReq(_BM):
    email: _Email
    senha_inicial: str = _Field(min_length=8)


@router.post("/{client_id}/criar-acesso", status_code=201)
async def criar_acesso_portal(
    client_id: str, payload: CriarAcessoReq,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio", "advogado"])),
):
    """Cria login do Portal do Cliente vinculado a este cliente."""
    c = (await db.execute(select(Client).where(
        Client.id == client_id, Client.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    existe = (await db.execute(select(_User).where(
        _User.email == payload.email.lower()
    ))).scalar_one_or_none()
    if existe:
        raise HTTPException(status_code=409, detail="E-mail já cadastrado no sistema")

    u = _User(
        id=str(uuid4()), email=payload.email.lower(),
        hashed_password=get_password_hash(payload.senha_inicial),
        full_name=c.nome or c.razao_social or "Cliente",
        role=_Role.cliente_externo,
        client_id=client_id,
        must_change_password=True,   # troca obrigatória no 1º acesso
        is_active=True,
    )
    db.add(u)
    await criar_audit_log(
        db, cu.id, cu.role.value, "CREATE", "users", u.id,
        detalhes=f"Acesso portal p/ cliente {client_id}",
    )
    await db.commit()
    return {
        "user_id": u.id,
        "detail": "Acesso criado. Cliente deve trocar a senha no 1º login.",
    }


@router.get("/{client_id}/relatorio-lgpd")
async def relatorio_lgpd(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    """
    Relatório do titular (LGPD art. 18, II) — PDF com todos os dados
    mantidos sobre o cliente. Para atender pedidos de acesso.
    """
    from app.models.case import Case as _Case
    from app.models.document import Document as _Doc
    from app.models.fee import Fee as _Fee
    from app.models.audit_log import AuditLog as _Audit
    from app.services.pdf_service import relatorio_lgpd_pdf_async

    c = (await db.execute(select(Client).where(
        Client.id == client_id, Client.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    casos = (await db.execute(select(_Case).where(
        _Case.client_id == client_id, _Case.deleted_at.is_(None)
    ))).scalars().all()
    docs = (await db.execute(select(_Doc).where(
        _Doc.client_id == client_id, _Doc.deleted_at.is_(None)
    ))).scalars().all()
    fees = (await db.execute(select(_Fee).where(
        _Fee.client_id == client_id, _Fee.deleted_at.is_(None)
    ))).scalars().all()
    acessos = (await db.execute(
        select(_Audit).where(_Audit.registro_id == client_id)
        .order_by(_Audit.created_at.desc()).limit(50)
    )).scalars().all()

    dados = {
        "cliente": {
            "nome": c.nome or c.razao_social, "tipo": c.tipo.value,
            "documento": c.cpf or c.cnpj or "—",
            "email": c.email, "telefone": c.telefone or c.whatsapp,
            "endereco": ", ".join(filter(None, [c.logradouro, c.numero,
                                  c.bairro, c.cidade, c.estado])) or "—",
            "origem": c.origem.value if c.origem else "—",
            "cadastrado_em": c.created_at.strftime("%d/%m/%Y"),
        },
        "casos": [{"numero": x.numero_interno, "titulo": x.titulo,
                   "status": str(x.status.value)} for x in casos],
        "documentos": [{"titulo": d.titulo,
                        "data": d.created_at.strftime("%d/%m/%Y")} for d in docs],
        "financeiro": [{"descricao": f.descricao,
                        "valor": float(f.valor or 0),
                        "status": str(f.status.value)} for f in fees],
        "acessos": [{"data": a.created_at.strftime("%d/%m/%Y %H:%M"),
                     "acao": a.acao, "perfil": a.user_role or "—"}
                    for a in acessos],
    }
    try:
        pdf = await relatorio_lgpd_pdf_async(dados)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    await criar_audit_log(db, cu.id, cu.role.value, "DOWNLOAD", "clients",
                          client_id, detalhes="Relatório LGPD art.18 emitido")
    await db.commit()
    return _Resp(content=pdf, media_type="application/pdf",
                 headers={"Content-Disposition":
                          f'attachment; filename="lgpd_{client_id[:8]}.pdf"'})


@router.get("/{client_id}/dados-lgpd.json")
async def dados_lgpd_json(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    """
    Portabilidade LGPD (art. 18, V) — dados do titular em JSON estruturado,
    machine-readable, para importação por outro sistema. Complementa o PDF (art. 18, II).
    """
    from app.models.case import Case as _Case
    from app.models.document import Document as _Doc
    from app.models.fee import Fee as _Fee

    c = (await db.execute(select(Client).where(
        Client.id == client_id, Client.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    casos = (await db.execute(select(_Case).where(
        _Case.client_id == client_id, _Case.deleted_at.is_(None)
    ))).scalars().all()
    docs = (await db.execute(select(_Doc).where(
        _Doc.client_id == client_id, _Doc.deleted_at.is_(None)
    ))).scalars().all()
    fees = (await db.execute(select(_Fee).where(
        _Fee.client_id == client_id, _Fee.deleted_at.is_(None)
    ))).scalars().all()

    payload = {
        "titular": {
            "nome": c.nome or c.razao_social, "tipo": c.tipo.value,
            "cpf": c.cpf, "cnpj": c.cnpj, "email": c.email,
            "telefone": c.telefone, "whatsapp": c.whatsapp,
            "cadastrado_em": c.created_at.isoformat() if c.created_at else None,
        },
        "casos": [{"numero_interno": x.numero_interno, "titulo": x.titulo,
                   "area": str(x.area.value), "status": str(x.status.value),
                   "numero_processo": x.numero_processo} for x in casos],
        "documentos": [{"titulo": d.titulo,
                        "data": d.created_at.isoformat() if d.created_at else None}
                       for d in docs],
        "financeiro": [{"descricao": f.descricao, "valor": float(f.valor or 0),
                        "status": str(f.status.value)} for f in fees],
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "base_legal": "LGPD (Lei 13.709/2018), art. 18, incisos II e V",
    }
    await criar_audit_log(db, cu.id, cu.role.value, "EXPORT_LGPD_JSON", "clients",
                          client_id, detalhes="Portabilidade LGPD art.18,V (JSON)")
    await db.commit()
    return payload
