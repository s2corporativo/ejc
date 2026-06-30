"""DataJud CNJ public API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.services import datajud_service
from app.models.case import Case

router = APIRouter(prefix="/v1/datajud", tags=["datajud"])


@router.get("/process/{numero_cnj}")
async def lookup_process(
    numero_cnj: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Busca processo pelo número CNJ"""
    try:
        result = await datajud_service.consultar_processo(numero_cnj)
        if result is None:
            raise HTTPException(404, "Process not found in DataJud")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"DataJud error: {str(e)}")


@router.post("/cases/{case_id}/sync")
async def sync_case(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Sincroniza movimentações de um caso com o DataJud"""
    result = await db.execute(select(Case).where(Case.id == case_id, Case.deleted_at.is_(None)))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(404, "Case not found")
    if not case.numero_processo:
        raise HTTPException(400, "Case has no numero_processo")
    try:
        synced = await datajud_service.sincronizar_caso(db, case)
        return {"synced": synced, "numero_processo": case.numero_processo}
    except Exception as e:
        raise HTTPException(502, f"DataJud sync error: {str(e)}")
