# ── app/routers/case_partes.py ────────────────────────────────────────────────
from __future__ import annotations

from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func as sqlfunc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.case_parte import CaseParte
from app.models.user import User
from app.services.pii_crypto import hash_documento, normalizar_documento
from app.services.validators_service import validar_cnpj, validar_cpf

TIPOS_PARTE = {"autor", "reu", "terceiro", "advogado", "procurador"}

router = APIRouter(prefix="/cases/{case_id}/partes", tags=["Partes Processuais"])


class ParteUpdate(BaseModel):
    """Partes carregam PII; campos omitidos não são alterados."""

    tipo: Optional[str] = None
    papel_processual: Optional[str] = None
    nome: Optional[str] = None
    cpf_cnpj: Optional[str] = None
    qualificacao: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    representante_legal: Optional[str] = None
    oab: Optional[str] = None
    client_id: Optional[str] = None
    observacoes: Optional[str] = None


class ParteCreate(BaseModel):
    tipo: str
    papel_processual: Optional[str] = None
    nome: str
    cpf_cnpj: Optional[str] = None
    qualificacao: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    representante_legal: Optional[str] = None
    oab: Optional[str] = None
    client_id: Optional[str] = None
    observacoes: Optional[str] = None


def _normalizar_validar_documento(valor: str | None) -> str | None:
    doc = normalizar_documento(valor)
    if not doc:
        return None
    if len(doc) == 11 and not validar_cpf(doc):
        raise HTTPException(status_code=422, detail="CPF inválido")
    if len(doc) == 14 and not validar_cnpj(doc):
        raise HTTPException(status_code=422, detail="CNPJ inválido")
    if len(doc) not in (11, 14):
        raise HTTPException(status_code=422, detail="CPF/CNPJ deve ter 11 ou 14 dígitos")
    return doc


def _legacy_doc_normalizado():
    """Expressão temporária para localizar legado plaintext durante a Fase A.

    Nunca é usada para nova gravação. A Fase B remove esta expressão junto da
    coluna antiga quando a prova operacional mostrar zero legado.
    """
    return sqlfunc.replace(
        sqlfunc.replace(
            sqlfunc.replace(
                sqlfunc.replace(CaseParte._cpf_cnpj_legacy, ".", ""),
                "-", "",
            ),
            "/", "",
        ),
        " ", "",
    )


def _filtro_documento_exato(doc_normalizado: str):
    try:
        blind = hash_documento(doc_normalizado)
    except RuntimeError as exc:
        # Em produção a chave é obrigatória no boot; se o runtime estiver
        # incoerente, falhar fechado é mais seguro do que gravar/buscar plaintext.
        raise HTTPException(status_code=503, detail="Índice protegido de PII indisponível") from exc
    return or_(
        CaseParte.cpf_cnpj_hash == blind,
        _legacy_doc_normalizado() == doc_normalizado,
    )


def _serializar(parte: CaseParte) -> dict:
    return {
        "id": parte.id,
        "tipo": parte.tipo,
        "papel_processual": parte.papel_processual,
        "nome": parte.nome,
        "cpf_cnpj": parte.cpf_cnpj,
        "qualificacao": parte.qualificacao,
        "email": parte.email,
        "telefone": parte.telefone,
        "representante_legal": parte.representante_legal,
        "oab": parte.oab,
        "client_id": parte.client_id,
        "ativo": parte.ativo,
        "observacoes": parte.observacoes,
        "created_at": parte.created_at,
    }


@router.get("")
async def listar_partes(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    # Mesmo gate de ownership de POST/DELETE — a leitura decifra PII apenas
    # depois de confirmar acesso ao caso.
    await verificar_acesso_caso(db, cu, case_id)
    rows = (
        await db.execute(
            select(CaseParte)
            .where(CaseParte.case_id == case_id, CaseParte.ativo.is_(True))
            .order_by(CaseParte.tipo, CaseParte.nome)
        )
    ).scalars().all()
    return [_serializar(p) for p in rows]


@router.post("", status_code=201)
async def criar_parte(
    case_id: str,
    body: ParteCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    await verificar_acesso_caso(db, cu, case_id)
    if body.tipo not in TIPOS_PARTE:
        raise HTTPException(
            status_code=422,
            detail=f"Tipo de parte inválido: aceita {sorted(TIPOS_PARTE)}",
        )

    doc = _normalizar_validar_documento(body.cpf_cnpj)
    if doc:
        duplicado = (
            await db.execute(
                select(CaseParte.id).where(
                    CaseParte.case_id == case_id,
                    CaseParte.ativo.is_(True),
                    _filtro_documento_exato(doc),
                )
            )
        ).scalar_one_or_none()
        if duplicado:
            raise HTTPException(
                status_code=409,
                detail="Já existe parte ativa neste caso com este CPF/CNPJ",
            )

    parte = CaseParte(
        id=str(uuid4()),
        case_id=case_id,
        tipo=body.tipo,
        papel_processual=body.papel_processual,
        nome=body.nome,
        qualificacao=body.qualificacao,
        representante_legal=body.representante_legal,
        oab=body.oab,
        client_id=body.client_id,
        observacoes=body.observacoes,
        created_by=cu.id,
    )
    try:
        parte.cpf_cnpj = body.cpf_cnpj
        parte.email = body.email
        parte.telefone = body.telefone
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Criptografia de PII indisponível") from exc

    db.add(parte)
    try:
        await db.flush()
        await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "case_partes", parte.id)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Já existe parte ativa neste caso com este CPF/CNPJ",
        ) from exc
    return {"id": parte.id, "message": "Parte criada"}


@router.delete("/{parte_id}", status_code=204)
async def remover_parte(
    case_id: str,
    parte_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    await verificar_acesso_caso(db, cu, case_id)
    parte = (
        await db.execute(
            select(CaseParte)
            .where(
                CaseParte.id == parte_id,
                CaseParte.case_id == case_id,
                CaseParte.ativo.is_(True),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not parte:
        raise HTTPException(status_code=404, detail="Parte não encontrada")
    parte.ativo = False
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "case_partes", parte_id)
    await db.commit()


@router.patch("/{parte_id}")
async def atualizar_parte(
    case_id: str,
    parte_id: str,
    body: ParteUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Edição auditada; PII nova é sempre cifrada antes do flush."""
    await verificar_acesso_caso(db, cu, case_id)
    campos = body.model_dump(exclude_unset=True)
    if not campos:
        raise HTTPException(status_code=422, detail="Nada a atualizar")
    if "tipo" in campos and campos["tipo"] not in TIPOS_PARTE:
        raise HTTPException(
            status_code=422,
            detail=f"Tipo de parte inválido: aceita {sorted(TIPOS_PARTE)}",
        )

    parte = (
        await db.execute(
            select(CaseParte)
            .where(
                CaseParte.id == parte_id,
                CaseParte.case_id == case_id,
                CaseParte.ativo.is_(True),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not parte:
        raise HTTPException(status_code=404, detail="Parte não encontrada")

    if "cpf_cnpj" in campos:
        doc = _normalizar_validar_documento(campos["cpf_cnpj"])
        if doc:
            duplicado = (
                await db.execute(
                    select(CaseParte.id).where(
                        CaseParte.case_id == case_id,
                        CaseParte.ativo.is_(True),
                        CaseParte.id != parte_id,
                        _filtro_documento_exato(doc),
                    )
                )
            ).scalar_one_or_none()
            if duplicado:
                raise HTTPException(
                    status_code=409,
                    detail="Já existe parte ativa neste caso com este CPF/CNPJ",
                )
        # Preserva a forma de exibição informada; o setter calcula HMAC sobre
        # a forma normalizada e cifra o valor de apresentação.

    try:
        for campo, valor in campos.items():
            setattr(parte, campo, valor)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Criptografia de PII indisponível") from exc

    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "UPDATE",
        "case_partes",
        parte_id,
        detalhes=f"Campos atualizados: {sorted(campos)}",
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Já existe parte ativa neste caso com este CPF/CNPJ",
        ) from exc
    return {"id": parte_id, "message": "Parte atualizada"}
