# ── app/routers/mensagens.py ──────────────────────────────────────────────────
# Chat cliente↔escritório por caso (Portal Corporativo, FASE 8).
# Mesmo endpoint para os dois lados: o papel do usuário define autor_tipo e o
# isolamento (cliente_externo só acessa os próprios casos).
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, UserRole
from app.models.audit_log import criar_audit_log

router = APIRouter(prefix="/cases/{case_id}/mensagens", tags=["Mensagens do Caso"])


class MsgIn(BaseModel):
    mensagem: str = Field(min_length=1, max_length=4000)


async def _verificar_acesso(case_id: str, cu: User, db: AsyncSession):
    """cliente_externo só acessa caso do próprio client_id; staff acessa qualquer um."""
    if cu.role == UserRole.cliente_externo:
        if not cu.client_id:
            raise HTTPException(403, "Cliente sem vínculo")
        r = await db.execute(
            text("SELECT 1 FROM cases WHERE id = :cid AND client_id = :clid AND deleted_at IS NULL"),
            {"cid": case_id, "clid": cu.client_id},
        )
        if not r.first():
            raise HTTPException(403, "Acesso negado a este caso")


def _meu_tipo(cu: User) -> str:
    return "cliente" if cu.role == UserRole.cliente_externo else "escritorio"


@router.get("")
async def listar_mensagens(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    await _verificar_acesso(case_id, cu, db)
    res = await db.execute(
        text("""
            SELECT id, autor_tipo, autor_id, autor_nome, mensagem, lida, created_at
            FROM portal_mensagens WHERE case_id = :cid ORDER BY created_at ASC
        """),
        {"cid": case_id},
    )
    msgs = [dict(r) for r in res.mappings().all()]
    # marca como lidas as mensagens do outro lado
    await db.execute(
        text("UPDATE portal_mensagens SET lida = true "
             "WHERE case_id = :cid AND autor_tipo <> :t AND lida = false"),
        {"cid": case_id, "t": _meu_tipo(cu)},
    )
    await db.commit()
    return msgs


@router.post("", status_code=201)
async def enviar_mensagem(
    case_id: str,
    body: MsgIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    await _verificar_acesso(case_id, cu, db)
    nome = getattr(cu, "nome", None) or getattr(cu, "nome_completo", None) or cu.email
    res = await db.execute(
        text("""
            INSERT INTO portal_mensagens (case_id, autor_tipo, autor_id, autor_nome, mensagem)
            VALUES (:cid, :tipo, :aid, :nome, :msg)
            RETURNING id, created_at
        """),
        {"cid": case_id, "tipo": _meu_tipo(cu), "aid": cu.id, "nome": nome, "msg": body.mensagem},
    )
    row = res.mappings().first()
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "portal_mensagens", row["id"])
    await db.commit()
    return {"id": row["id"], "created_at": row["created_at"]}
