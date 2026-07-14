from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from pydantic import BaseModel
from app.core.database import get_db
from app.core.auth_middleware import get_current_user
from app.modules.auditoria.middleware import registrar_acao

router = APIRouter(prefix="/cases/{case_id}/partes", tags=["case-partes"])

TIPO_LABELS = {
    "autor": "Autor", "reu": "Réu", "terceiro_interessado": "Terceiro",
    "litisconsorte_ativo": "Litisconsorte Ativo", "litisconsorte_passivo": "Litisconsorte Passivo",
    "assistente": "Assistente", "amicus_curiae": "Amicus Curiae",
    "mp": "Ministério Público", "perito": "Perito",
}


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
    current_user=Depends(get_current_user),
):
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
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        text("""
            INSERT INTO case_partes
                (case_id, tipo, papel_processual, nome, cpf_cnpj,
                 qualificacao, email, telefone, representante_legal, oab,
                 client_id, observacoes, created_by)
            VALUES
                (:case_id, :tipo, :papel, :nome, :cpf,
                 :qual, :email, :tel, :rep, :oab, :cli, :obs, :user)
            RETURNING id
        """),
        {
            "case_id": case_id, "tipo": body.tipo, "papel": body.papel_processual,
            "nome": body.nome, "cpf": body.cpf_cnpj, "qual": body.qualificacao,
            "email": body.email, "tel": body.telefone, "rep": body.representante_legal,
            "oab": body.oab, "cli": body.client_id, "obs": body.observacoes,
            "user": str(current_user.get("id", "")),
        },
    )
    row = result.mappings().first()
    await db.commit()
    await registrar_acao(
        db=db, user_id=current_user.get("id"), acao="criar_parte",
        modulo="case_partes", registro_id=str(row["id"]),
        descricao=f"Parte '{body.nome}' ({body.tipo}) adicionada ao caso {case_id}", ip=None,
    )
    return {"id": row["id"], "message": "Parte criada"}


@router.delete("/{parte_id}")
async def remover_parte(
    case_id: str, parte_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await db.execute(
        text("UPDATE case_partes SET ativo = false WHERE id = :id AND case_id = :case_id"),
        {"id": parte_id, "case_id": case_id},
    )
    await db.commit()
    return {"message": "Removida"}
