"""Taxonomia única de áreas do direito — fonte canônica (resolve as 3 taxonomias desalinhadas)."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/areas", tags=["Áreas do Direito"])


@router.get("")
async def listar(db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    rows = (await db.execute(text(
        "SELECT slug, nome, ordem FROM areas WHERE ativo = true ORDER BY ordem"
    ))).mappings().all()
    return {"areas": [dict(r) for r in rows]}
