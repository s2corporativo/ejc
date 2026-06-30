# ── app/routers/trash.py ─────────────────────────────────────────────────────
# Lixeira: lista e restaura registros soft-deleted. Admin/sócio apenas.
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles
from app.models.user import User
from app.models.audit_log import criar_audit_log

# Whitelist: entidade → (Model, campo_rótulo)
from app.models.client import Client
from app.models.case import Case
from app.models.deadline import Deadline
from app.models.document import Document
from app.models.legal_doc import LegalDoc
from app.models.fee import Fee
from app.models.procuracao import Procuracao
from app.models.environmental import EnvironmentalCase
from app.models.task import Task

ENTIDADES = {
    "clients":             (Client, lambda x: x.nome or x.razao_social),
    "cases":               (Case, lambda x: f"{x.numero_interno} {x.titulo}"),
    "deadlines":           (Deadline, lambda x: x.titulo),
    "documents":           (Document, lambda x: x.titulo),
    "legal_docs":          (LegalDoc, lambda x: x.titulo),
    "fees":                (Fee, lambda x: x.descricao),
    "procuracoes":         (Procuracao, lambda x: f"Procuração {x.id[:8]}"),
    "environmental_cases": (EnvironmentalCase, lambda x: f"Auto {x.numero_auto}"),
    "tasks":               (Task, lambda x: x.titulo),
}

router = APIRouter(prefix="/trash", tags=["Lixeira"])


@router.get("/")
async def listar(
    entidade: str = Query(...),
    page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    if entidade not in ENTIDADES:
        raise HTTPException(status_code=422,
                            detail=f"Entidade inválida. Use: {list(ENTIDADES)}")
    Model, rotulo = ENTIDADES[entidade]
    rows = (await db.execute(
        select(Model).where(Model.deleted_at.isnot(None))
        .order_by(Model.deleted_at.desc())
        .offset((page-1)*page_size).limit(page_size)
    )).scalars().all()
    return {"data": [
        {"id": r.id, "rotulo": rotulo(r),
         "excluido_em": r.deleted_at}
        for r in rows
    ]}


@router.post("/{entidade}/{registro_id}/restaurar")
async def restaurar(
    entidade: str, registro_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    if entidade not in ENTIDADES:
        raise HTTPException(status_code=422, detail="Entidade inválida")
    Model, _ = ENTIDADES[entidade]
    r = (await db.execute(select(Model).where(
        Model.id == registro_id, Model.deleted_at.isnot(None)
    ))).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Registro não está na lixeira")
    r.deleted_at = None
    await criar_audit_log(db, cu.id, cu.role.value, "RESTORE", entidade, registro_id)
    await db.commit()
    return {"detail": "Registro restaurado"}
