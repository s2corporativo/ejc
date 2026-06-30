"""Partner withdrawals with approval workflow"""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user

router = APIRouter(prefix="/api/v1/partner-withdrawals", tags=["partner-withdrawals"])

PRIVILEGED = {"superadmin", "socio"}


@router.get("")
async def list_withdrawals(
    partner_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = "SELECT * FROM partner_withdrawals WHERE deleted_at IS NULL"
    params = {}
    # Non-privileged users see only their own
    if current_user.role not in PRIVILEGED:
        q += " AND partner_id=:pid"
        params["pid"] = str(current_user.id)
    elif partner_id:
        q += " AND partner_id=:pid"
        params["pid"] = partner_id
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


@router.post("")
async def create_withdrawal(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.role not in PRIVILEGED:
        raise HTTPException(403, "Only partners can create withdrawal requests")

    # Default partner_id to current user if not superadmin setting for another
    partner_id = body.get("partner_id", str(current_user.id))
    if partner_id != str(current_user.id) and current_user.role != "superadmin":
        raise HTTPException(403, "Cannot create withdrawal for another partner")

    if body.get("gross_value") is None:
        raise HTTPException(422, "Campo obrigatório: gross_value")
    # Corrige bug: net_value/partner_share ficavam NULL e status sem default ->
    # retirada manual nascia inaprovavel. Retirada manual: o socio recebe o
    # liquido da propria retirada (gross - despesas do caso).
    gross = float(body.get("gross_value") or 0)
    expenses = float(body.get("case_expenses") or 0)
    net = round(gross - expenses, 2)
    result = await db.execute(
        text("""INSERT INTO partner_withdrawals (partner_id, gross_value, case_expenses, net_value, partner_share, description, period_reference, status)
             VALUES (:partner_id, :gross_value, :case_expenses, :net_value, :partner_share, :description, :period_reference, 'pendente')
             RETURNING id, partner_id, gross_value, case_expenses, net_value, partner_share, description, period_reference, status, created_at"""),
        {
            "partner_id": partner_id,
            "gross_value": body.get("gross_value"),
            "case_expenses": body.get("case_expenses", 0),
            "net_value": net,
            "partner_share": net,
            "description": body.get("description"),
            "period_reference": body.get("period_reference"),
        }
    )
    await db.commit()
    return dict(result.mappings().first())


@router.patch("/{withdrawal_id}/approve")
async def approve_withdrawal(
    withdrawal_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.role not in PRIVILEGED:
        raise HTTPException(403, "Only partners or admins can approve withdrawals")

    result = await db.execute(text("SELECT status FROM partner_withdrawals WHERE id=:id AND deleted_at IS NULL"), {"id": withdrawal_id})
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "Withdrawal not found")
    if row[0] != "pendente":
        raise HTTPException(400, f"Cannot approve withdrawal in status '{row[0]}'")

    await db.execute(
        text("UPDATE partner_withdrawals SET status='aprovado', approved_by=:uid, approved_at=NOW(), updated_at=NOW() WHERE id=:id"),
        {"uid": str(current_user.id), "id": withdrawal_id}
    )
    await db.commit()
    return {"ok": True, "status": "aprovado"}


@router.patch("/{withdrawal_id}/reject")
async def reject_withdrawal(
    withdrawal_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.role not in PRIVILEGED:
        raise HTTPException(403, "Only partners or admins can reject withdrawals")

    result = await db.execute(text("SELECT status FROM partner_withdrawals WHERE id=:id AND deleted_at IS NULL"), {"id": withdrawal_id})
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "Withdrawal not found")
    if row[0] != "pendente":
        raise HTTPException(400, f"Cannot reject withdrawal in status '{row[0]}'")

    await db.execute(
        text("UPDATE partner_withdrawals SET status='rejeitado', updated_at=NOW() WHERE id=:id"),
        {"id": withdrawal_id}
    )
    await db.commit()
    return {"ok": True, "status": "rejeitado"}


@router.patch("/{withdrawal_id}/pay")
async def pay_withdrawal(
    withdrawal_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.role not in PRIVILEGED:
        raise HTTPException(403, "Only partners or admins can mark withdrawals as paid")

    result = await db.execute(text("SELECT status FROM partner_withdrawals WHERE id=:id AND deleted_at IS NULL"), {"id": withdrawal_id})
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "Withdrawal not found")
    if row[0] != "aprovado":
        raise HTTPException(400, f"Withdrawal must be approved before marking as paid (current: '{row[0]}')")

    await db.execute(
        text("UPDATE partner_withdrawals SET status='pago', paid_at=NOW(), updated_at=NOW() WHERE id=:id"),
        {"id": withdrawal_id}
    )
    await db.commit()
    return {"ok": True, "status": "pago"}


@router.delete("/{withdrawal_id}")
async def delete_withdrawal(
    withdrawal_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.role not in PRIVILEGED:
        raise HTTPException(403, "Forbidden")
    await db.execute(text("UPDATE partner_withdrawals SET deleted_at=NOW() WHERE id=:id"), {"id": withdrawal_id})
    await db.commit()
    return {"ok": True}
