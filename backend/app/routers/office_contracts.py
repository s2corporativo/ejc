"""Office contracts CRUD"""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

_FIN = {"superadmin", "admin", "socio", "financeiro"}


def _req_fin(cu: User = Depends(get_current_user)) -> User:
    # Contratos do escritório = societário/financeiro: só gestão/financeiro.
    if cu.role.value not in _FIN:
        raise HTTPException(status_code=403, detail="Acesso restrito a gestão/financeiro")
    return cu


router = APIRouter(prefix="/v1/office-contracts", tags=["office-contracts"], dependencies=[Depends(_req_fin)])


@router.get("")
async def list_contracts(
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = "SELECT * FROM office_contracts WHERE deleted_at IS NULL"
    params = {}
    if status:
        q += " AND status=:status"
        params["status"] = status
    count_result = await db.execute(text(q.replace("SELECT *", "SELECT COUNT(*)")), params)
    total = count_result.scalar()

    q += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    result = await db.execute(text(q), params)
    return {"data": [dict(r) for r in result.mappings().all()], "total": total, "page": page, "page_size": page_size}


@router.get("/expiring")
async def list_expiring(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        text("SELECT * FROM office_contracts WHERE deleted_at IS NULL AND status='vigente' AND end_date BETWEEN CURRENT_DATE AND CURRENT_DATE + make_interval(days => :days) ORDER BY end_date"),
        {"days": days}
    )
    return [dict(r) for r in result.mappings().all()]


@router.post("", status_code=201)
async def create_contract(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    faltando = [k for k in ("title","counterparty","start_date") if not body.get(k)]
    if faltando:
        raise HTTPException(422, "Campos obrigatórios: " + ", ".join(faltando))
    result = await db.execute(
        text("""INSERT INTO office_contracts (title,counterparty,contract_type,status,start_date,end_date,value,description,file_url,alert_days_before,created_by)
             VALUES (:title,:counterparty,:contract_type,:status,:start_date,:end_date,:value,:description,:file_url,:alert_days_before,:created_by)
             RETURNING *"""),
        {
            "title": body.get("title"),
            "counterparty": body.get("counterparty"),
            "contract_type": body.get("contract_type", "prestacao_servico"),
            "status": body.get("status", "vigente"),
            "start_date": body.get("start_date"),
            "end_date": body.get("end_date"),
            "value": body.get("value"),
            "description": body.get("description"),
            "file_url": body.get("file_url"),
            "alert_days_before": body.get("alert_days_before", 30),
            "created_by": str(current_user.id),
        }
    )
    await db.commit()
    return dict(result.mappings().first())


@router.get("/{contract_id}")
async def get_contract(
    contract_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(text("SELECT * FROM office_contracts WHERE id=:id AND deleted_at IS NULL"), {"id": contract_id})
    row = result.mappings().first()
    if not row:
        raise HTTPException(404, "Contract not found")
    return dict(row)


@router.patch("/{contract_id}")
async def update_contract(
    contract_id: str,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    sets = []
    params = {"id": contract_id}
    for field in ["title","counterparty","contract_type","status","start_date","end_date","value","description","file_url","alert_days_before"]:
        if field in body:
            sets.append(f"{field}=:{field}")
            params[field] = body[field]
    sets.append("updated_at=NOW()")
    await db.execute(text(f"UPDATE office_contracts SET {','.join(sets)} WHERE id=:id AND deleted_at IS NULL"), params)
    await db.commit()
    return {"ok": True}


@router.delete("/{contract_id}")
async def delete_contract(
    contract_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await db.execute(text("UPDATE office_contracts SET deleted_at=NOW() WHERE id=:id"), {"id": contract_id})
    await db.commit()
    return {"ok": True}
