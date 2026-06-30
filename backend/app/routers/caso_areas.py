"""Multi-área por caso — área principal + áreas relacionadas (N:N).
   Um mesmo caso pode tocar vários ramos (ex.: multa ambiental = ambiental + administrativo + tributário).
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import verificar_acesso_caso
from app.models.user import User

router = APIRouter(prefix="/cases/{case_id}/areas", tags=["Áreas do Caso"])


@router.get("")
async def listar_areas(case_id: str, db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    rows = (await db.execute(text("""
        SELECT area, principal FROM caso_areas WHERE case_id = :cid ORDER BY principal DESC, area
    """), {"cid": case_id})).mappings().all()
    return {"areas": [dict(r) for r in rows]}


@router.post("")
async def adicionar_area(case_id: str, body: dict = Body(...),
                         db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    area = (body.get("area") or "").strip()
    if not area:
        raise HTTPException(422, "Campo obrigatório: area")
    principal = bool(body.get("principal", False))
    existe = (await db.execute(text("SELECT id FROM cases WHERE id = :cid AND deleted_at IS NULL"), {"cid": case_id})).scalar()
    if not existe:
        raise HTTPException(404, "Caso não encontrado")
    await verificar_acesso_caso(db, cu, case_id)
    if principal:
        await db.execute(text("UPDATE caso_areas SET principal = false WHERE case_id = :cid"), {"cid": case_id})
    await db.execute(text("""
        INSERT INTO caso_areas (case_id, area, principal) VALUES (:cid, :a, :p)
        ON CONFLICT (case_id, area) DO UPDATE SET principal = EXCLUDED.principal
    """), {"cid": case_id, "a": area, "p": principal})
    await db.commit()
    return {"ok": True}


@router.delete("/{area}")
async def remover_area(case_id: str, area: str,
                       db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    await verificar_acesso_caso(db, cu, case_id)
    await db.execute(text("""
        DELETE FROM caso_areas WHERE case_id = :cid AND area = :a AND principal = false
    """), {"cid": case_id, "a": area})
    await db.commit()
    return {"ok": True}
