"""Kanban columns and case kanban management"""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

_TEAM = {"superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "estagiario"}


def _req_team(cu: User = Depends(get_current_user)) -> User:
    # Mover cartão sincroniza o STATUS do caso (até terminal): só equipe jurídica.
    if cu.role.value not in _TEAM:
        raise HTTPException(status_code=403, detail="Acesso restrito à equipe jurídica")
    return cu


router = APIRouter(prefix="/api/v1", tags=["kanban"])


def _status_da_coluna(nome: str) -> Optional[str]:
    """Mapeia o nome da coluna kanban para o status do caso (sincronização de fluxo).
    Retorna None se a coluna não corresponde a um estado terminal/conhecido."""
    if not nome:
        return None
    n = nome.lower()
    if "arquiv" in n:
        return "arquivado"
    if "sem acordo" in n:
        return "encerrado"
    if "acordo" in n:
        return "acordo"
    if "encerrad" in n or "entregue" in n:
        return "encerrado"
    if "aguardando prazo" in n or "suspens" in n:
        return "suspenso"
    return None


@router.get("/kanban-columns")
async def list_kanban_columns(
    legal_area: Optional[str] = "default",
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        text("SELECT id, name, legal_area, position, color, icon FROM kanban_columns WHERE is_active=true AND legal_area=:area ORDER BY position"),
        {"area": legal_area}
    )
    rows = result.mappings().all()
    return [dict(r) for r in rows]


@router.patch("/cases/{case_id}/kanban")
async def update_case_kanban(
    case_id: str,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_req_team),
):
    kanban_column = body.get("kanban_column")
    kanban_position = body.get("kanban_position", 0)
    row = (await db.execute(
        text("SELECT status FROM cases WHERE id=:id AND deleted_at IS NULL"), {"id": case_id}
    )).mappings().first()
    if not row:
        raise HTTPException(404, "Case not found")

    novo_status = _status_da_coluna(kanban_column or "")
    if novo_status and novo_status != row["status"]:
        await db.execute(
            text("UPDATE cases SET kanban_column=:col, kanban_position=:pos, status=:st, updated_at=NOW() WHERE id=:id"),
            {"col": kanban_column, "pos": kanban_position, "st": novo_status, "id": case_id}
        )
    else:
        await db.execute(
            text("UPDATE cases SET kanban_column=:col, kanban_position=:pos, updated_at=NOW() WHERE id=:id"),
            {"col": kanban_column, "pos": kanban_position, "id": case_id}
        )
    await db.commit()
    return {"ok": True, "status_sincronizado": novo_status}
