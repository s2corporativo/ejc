"""Partner withdrawals with approval workflow"""
from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user

router = APIRouter(prefix="/v1/partner-withdrawals", tags=["partner-withdrawals"])

PRIVILEGED = {"superadmin", "socio"}

_Q2 = Decimal("0.01")


def _money(v) -> Decimal:
    """Coage numérico (Decimal de coluna Numeric, int, float, str, None) para
    Decimal com 2 casas (ROUND_HALF_UP). Dinheiro fica Decimal ponta a ponta."""
    return Decimal(str(v or 0)).quantize(_Q2, ROUND_HALF_UP)


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


@router.post("", status_code=201)
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
    gross = _money(body.get("gross_value"))
    expenses = _money(body.get("case_expenses"))
    net = _money(gross - expenses)
    result = await db.execute(
        text("""INSERT INTO partner_withdrawals (partner_id, gross_value, case_expenses, net_value, partner_share, description, period_reference, status)
             VALUES (:partner_id, :gross_value, :case_expenses, :net_value, :partner_share, :description, :period_reference, 'pendente')
             RETURNING id, partner_id, gross_value, case_expenses, net_value, partner_share, description, period_reference, status, created_at"""),
        {
            "partner_id": partner_id,
            "gross_value": gross,
            "case_expenses": expenses,
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

    result = await db.execute(text("SELECT partner_id, status FROM partner_withdrawals WHERE id=:id AND deleted_at IS NULL"), {"id": withdrawal_id})
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "Withdrawal not found")
    # [A6] Segregação de funções (SoD): quem cria não pode aprovar a PRÓPRIA
    # retirada — vale inclusive para superadmin (auto-dealing é do indivíduo,
    # não do papel). Sem exceção de role: em caso de dúvida, 403.
    if str(row[0]) == str(current_user.id):
        raise HTTPException(403, "Aprovação da própria retirada não é permitida — segregação de funções")
    if row[1] != "pendente":
        raise HTTPException(400, f"Cannot approve withdrawal in status '{row[1]}'")

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
        text("UPDATE partner_withdrawals SET status='rejeitado', approved_by=:uid, updated_at=NOW() WHERE id=:id"),
        {"uid": str(current_user.id), "id": withdrawal_id}
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

    result = await db.execute(text("SELECT partner_id, status FROM partner_withdrawals WHERE id=:id AND deleted_at IS NULL"), {"id": withdrawal_id})
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "Withdrawal not found")
    # [A6] Segregação de funções (SoD): ninguém paga a PRÓPRIA retirada, nem
    # superadmin — mantém o segundo par de olhos entre solicitação e pagamento.
    if str(row[0]) == str(current_user.id):
        raise HTTPException(403, "Pagamento da própria retirada não é permitido — segregação de funções")
    if row[1] != "aprovado":
        raise HTTPException(400, f"Withdrawal must be approved before marking as paid (current: '{row[1]}')")

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
