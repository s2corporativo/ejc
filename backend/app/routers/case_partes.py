# ── app/routers/case_partes.py ────────────────────────────────────────────────
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import verificar_acesso_caso
from app.models.user import User
from app.models.audit_log import criar_audit_log

router = APIRouter(prefix="/cases/{case_id}/partes", tags=["Partes Processuais"])


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


@router.get("")
async def listar_partes(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    # Mesmo gate de ownership de POST/DELETE — partes carregam PII (CPF/CNPJ,
    # e-mail, telefone) e a leitura não pode vazar para fora da equipe do caso.
    await verificar_acesso_caso(db, cu, case_id)
    result = await db.execute(
        text("""
            SELECT id, tipo, papel_processual, nome, cpf_cnpj,
                   qualificacao, email, telefone, representante_legal,
                   oab, client_id, ativo, observacoes, created_at
            FROM case_partes
            WHERE case_id = :case_id AND ativo = true
            ORDER BY tipo, nome
        """),
        {"case_id": case_id},
    )
    return [dict(r) for r in result.mappings().all()]


@router.post("", status_code=201)
async def criar_parte(
    case_id: str,
    body: ParteCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    await verificar_acesso_caso(db, cu, case_id)
    result = await db.execute(
        text("""
            INSERT INTO case_partes
                (case_id, tipo, papel_processual, nome, cpf_cnpj,
                 qualificacao, email, telefone, representante_legal,
                 oab, client_id, observacoes, created_by)
            VALUES
                (:cid, :tipo, :papel, :nome, :cpf, :qual,
                 :email, :tel, :rep, :oab, :cli, :obs, :user)
            RETURNING id
        """),
        {
            "cid": case_id, "tipo": body.tipo, "papel": body.papel_processual,
            "nome": body.nome, "cpf": body.cpf_cnpj, "qual": body.qualificacao,
            "email": body.email, "tel": body.telefone, "rep": body.representante_legal,
            "oab": body.oab, "cli": body.client_id, "obs": body.observacoes,
            "user": cu.id,
        },
    )
    row = result.mappings().first()
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "case_partes", row["id"])
    await db.commit()
    return {"id": row["id"], "message": "Parte criada"}


@router.delete("/{parte_id}", status_code=204)
async def remover_parte(
    case_id: str,
    parte_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    await verificar_acesso_caso(db, cu, case_id)
    await db.execute(
        text("UPDATE case_partes SET ativo = false WHERE id = :id AND case_id = :cid"),
        {"id": parte_id, "cid": case_id},
    )
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "case_partes", parte_id)
    await db.commit()
