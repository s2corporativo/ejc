"""Client pending items CRUD"""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import is_gestao
from app.models.user import User

# Prefixo SEM "/v1": o compat middleware (api_version_middleware.py) já expõe
# automaticamente todo /api/X também em /api/v1/X reescrevendo o path — não
# declarar "/v1" aqui. Causa raiz do bug (auditoria 2026-07-26): este router
# nascia com prefix="/v1/clients", então a ÚNICA rota registrada já era
# /api/v1/clients/.../pending-items. O middleware trata QUALQUER caminho que
# comece com /api/v1/ como "canônico" e o reescreve removendo o "/v1" antes de
# rotear — vira /api/clients/.../pending-items, que NUNCA existiu como rota
# (o app só tinha a versão com /v1 embutido), 404. Mesmo padrão de
# dossie_cliente.py/clients.py: declare o prefixo "real" sem /v1 e deixe o
# middleware sintetizar o alias canônico.
router = APIRouter(prefix="/clients", tags=["pending-items"])


async def _exigir_cliente_visivel(db: AsyncSession, cu: User, client_id: str) -> None:
    """Gate de visibilidade do cliente (ownership): gestão vê tudo; demais só
    clientes de que são responsáveis OU em cujos casos atuam. 404 (não 403) para
    não confirmar a existência de cliente alheio. Sem isso, qualquer usuário
    listava/alterava pendências de qualquer cliente (IDOR)."""
    if is_gestao(cu):
        return
    row = (await db.execute(text("""
        SELECT 1 FROM clients cl
        WHERE cl.id = :cid AND cl.deleted_at IS NULL
          AND (cl.responsavel_id = :uid
               OR EXISTS (SELECT 1 FROM cases c
                          WHERE c.client_id = cl.id AND c.deleted_at IS NULL
                            AND (c.advogado_responsavel_id = :uid
                                 OR c.advogado_auxiliar_id = :uid)))
        LIMIT 1
    """), {"cid": client_id, "uid": cu.id})).first()
    if row is None:
        raise HTTPException(404, "Cliente não encontrado")


@router.get("/{client_id}/pending-items")
async def list_pending_items(
    client_id: str,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _exigir_cliente_visivel(db, current_user, client_id)
    q = "SELECT * FROM client_pending_items WHERE client_id=:cid AND deleted_at IS NULL"
    params = {"cid": client_id}
    if status:
        q += " AND status=:status"
        params["status"] = status
    q += " ORDER BY created_at DESC"
    result = await db.execute(text(q), params)
    return [dict(r) for r in result.mappings().all()]


@router.post("/{client_id}/pending-items", status_code=201)
async def create_pending_item(
    client_id: str,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _exigir_cliente_visivel(db, current_user, client_id)
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
    await _exigir_cliente_visivel(db, current_user, client_id)
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
    await _exigir_cliente_visivel(db, current_user, client_id)
    await db.execute(
        text("UPDATE client_pending_items SET deleted_at=NOW() WHERE id=:id AND client_id=:cid"),
        {"id": item_id, "cid": client_id}
    )
    await db.commit()
    return {"ok": True}
