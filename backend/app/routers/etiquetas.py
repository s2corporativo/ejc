# ── app/routers/etiquetas.py ──────────────────────────────────────────────────
# Etiquetas reutilizáveis (área/responsável/fase/livre) aplicáveis a casos.
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.audit_log import criar_audit_log

router = APIRouter(tags=["Etiquetas"])


class EtiquetaIn(BaseModel):
    nome: str = Field(min_length=1, max_length=60)
    cor: str = "#AA8660"
    tipo: Optional[str] = "livre"


class AtribuirIn(BaseModel):
    etiqueta_id: str


@router.get("/etiquetas")
async def listar(db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    r = await db.execute(text("SELECT id, nome, cor, tipo FROM etiquetas ORDER BY nome"))
    return [dict(x) for x in r.mappings().all()]


@router.post("/etiquetas", status_code=201)
async def criar(body: EtiquetaIn, db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    r = await db.execute(
        text("INSERT INTO etiquetas (nome, cor, tipo, created_by) "
             "VALUES (:n, :c, :t, :u) RETURNING id"),
        {"n": body.nome, "c": body.cor, "t": body.tipo, "u": cu.id},
    )
    row = r.mappings().first()
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "etiquetas", row["id"])
    await db.commit()
    return {"id": row["id"], "nome": body.nome, "cor": body.cor, "tipo": body.tipo}


@router.delete("/etiquetas/{etiqueta_id}", status_code=204)
async def remover(etiqueta_id: str, db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    await db.execute(text("DELETE FROM etiquetas WHERE id = :id"), {"id": etiqueta_id})
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "etiquetas", etiqueta_id)
    await db.commit()


@router.get("/cases/{case_id}/etiquetas")
async def do_caso(case_id: str, db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    r = await db.execute(
        text("""SELECT e.id, e.nome, e.cor, e.tipo
                FROM case_etiquetas ce JOIN etiquetas e ON e.id = ce.etiqueta_id
                WHERE ce.case_id = :cid ORDER BY e.nome"""),
        {"cid": case_id},
    )
    return [dict(x) for x in r.mappings().all()]


@router.post("/cases/{case_id}/etiquetas", status_code=201)
async def atribuir(case_id: str, body: AtribuirIn, db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    try:
        await db.execute(
            text("INSERT INTO case_etiquetas (case_id, etiqueta_id) VALUES (:c, :e) "
                 "ON CONFLICT (case_id, etiqueta_id) DO NOTHING"),
            {"c": case_id, "e": body.etiqueta_id},
        )
        await criar_audit_log(db, cu.id, cu.role.value, "TAG", "case_etiquetas", case_id)
        await db.commit()
    except Exception as e:
        raise HTTPException(400, f"Falha ao atribuir: {str(e)[:120]}")
    return {"ok": True}


@router.delete("/cases/{case_id}/etiquetas/{etiqueta_id}", status_code=204)
async def desatribuir(case_id: str, etiqueta_id: str, db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    await db.execute(
        text("DELETE FROM case_etiquetas WHERE case_id = :c AND etiqueta_id = :e"),
        {"c": case_id, "e": etiqueta_id},
    )
    await db.commit()
