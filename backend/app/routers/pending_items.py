"""Client pending items CRUD"""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from datetime import date
from app.core.database import get_db
from app.core.security import get_current_user

router = APIRouter(prefix="/v1/clients", tags=["pending-items"])


@router.get("/{client_id}/pending-items")
async def list_pending_items(
    client_id: str,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = "SELECT * FROM client_pending_items WHERE client_id=:cid AND deleted_at IS NULL"
    params = {"cid": client_id}
    if status:
        q += " AND status=:status"
        params["status"] = status
    q += " ORDER BY created_at DESC"
    result = await db.execute(text(q), params)
    return [dict(r) for r in result.mappings().all()]


@router.post("/{client_id}/pending-items")
async def create_pending_item(
    client_id: str,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not body.get('title'):
        raise HTTPException(422, 'Campo obrigatório: title')
    result = await db.execute(
        text("""INSERT INTO client_pending_items
            (client_id, case_id, type, title, description, status, due_date, created_by)
            VALUES (:cid,:case_id,:type,:title,:desc,:status,:due,:created_by)
            RETURNING *"""),
        {
            "cid": client_id,
            "case_id": body.get("case_id"),
            "type": body.get("type", "documento"),
            "title": body.get("title"),
            "desc": body.get("description"),
            "status": body.get("status", "pendente"),
            "due": body.get("due_date"),
            "created_by": str(current_user.id),
        }
    )
    await db.commit()
    return dict(result.mappings().first())


@router.patch("/{client_id}/pending-items/{item_id}")
async def update_pending_item(
    client_id: str,
    item_id: str,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(text("SELECT id FROM client_pending_items WHERE id=:id AND client_id=:cid AND deleted_at IS NULL"), {"id": item_id, "cid": client_id})
    if not result.fetchone():
        raise HTTPException(404, "Item not found")

    sets = []
    params = {"id": item_id}
    for field in ["title", "description", "type", "status", "due_date"]:
        if field in body:
            sets.append(f"{field}=:{field}")
            params[field] = body[field]
    if body.get("status") == "concluido":
        sets.append("completed_at=NOW()")
    sets.append("updated_at=NOW()")

    await db.execute(text(f"UPDATE client_pending_items SET {','.join(sets)} WHERE id=:id"), params)
    await db.commit()
    return {"ok": True}


@router.delete("/{client_id}/pending-items/{item_id}")
async def delete_pending_item(
    client_id: str,
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await db.execute(
        text("UPDATE client_pending_items SET deleted_at=NOW() WHERE id=:id AND client_id=:cid"),
        {"id": item_id, "cid": client_id}
    )
    await db.commit()
    return {"ok": True}
