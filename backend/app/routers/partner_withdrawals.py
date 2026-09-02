"""Saques de sócios com segregação de funções e trilha de auditoria."""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.user import User

router = APIRouter(prefix="/partner-withdrawals", tags=["partner-withdrawals"])

# Gestão precisa enxergar a fila compartilhada para que um segundo responsável
# aprove/rejeite. Apenas sócio (ou superadmin agindo administrativamente) pode
# originar retirada; admin pode gerir, mas não cria saque em nome próprio.
_GESTAO = {"superadmin", "admin", "socio"}
_SOLICITANTES = {"superadmin", "socio"}
_Q2 = Decimal("0.01")


def _money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(_Q2, ROUND_HALF_UP)


def _role(user: User) -> str:
    return getattr(user.role, "value", str(user.role))


def _require_gestao(user: User) -> None:
    if _role(user) not in _GESTAO:
        raise HTTPException(403, "Acesso restrito à gestão societária")


def _require_solicitante(user: User) -> None:
    if _role(user) not in _SOLICITANTES:
        raise HTTPException(403, "Apenas sócios podem solicitar retirada")


class WithdrawalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    partner_id: Optional[str] = None
    gross_value: Decimal = Field(gt=0)
    case_expenses: Decimal = Field(default=Decimal("0"), ge=0)
    description: Optional[str] = Field(None, max_length=1000)
    period_reference: Optional[str] = Field(None, max_length=20)


async def _buscar(db: AsyncSession, withdrawal_id: str):
    result = await db.execute(
        text("SELECT * FROM partner_withdrawals WHERE id=:id AND deleted_at IS NULL"),
        {"id": withdrawal_id},
    )
    return result.mappings().first()


async def _exigir_socio_ativo(db: AsyncSession, partner_id: str) -> None:
    """A retirada só pode ser atribuída a usuário que integra o cap table ativo."""
    socio = await db.execute(
        text(
            """
            SELECT id
            FROM socios
            WHERE user_id=:user_id AND ativo=TRUE
            LIMIT 1
            """
        ),
        {"user_id": partner_id},
    )
    if socio.scalar_one_or_none() is None:
        raise HTTPException(422, "Sócio ativo não encontrado para a retirada informada")


@router.get("")
async def list_withdrawals(
    partner_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_gestao(current_user)
    q = "SELECT * FROM partner_withdrawals WHERE deleted_at IS NULL"
    params = {}
    if partner_id:
        q += " AND partner_id=:pid"
        params["pid"] = partner_id
    if status:
        q += " AND status=:status"
        params["status"] = status
    count_result = await db.execute(text(q.replace("SELECT *", "SELECT COUNT(*)")), params)
    total = count_result.scalar() or 0

    q += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    result = await db.execute(text(q), params)
    return {
        "data": [dict(r) for r in result.mappings().all()],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", status_code=201)
async def create_withdrawal(
    body: WithdrawalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_solicitante(current_user)
    partner_id = body.partner_id or str(current_user.id)
    if partner_id != str(current_user.id) and _role(current_user) != "superadmin":
        raise HTTPException(403, "Não é permitido solicitar saque para outro sócio")
    await _exigir_socio_ativo(db, partner_id)

    gross = _money(body.gross_value)
    expenses = _money(body.case_expenses)
    net = _money(gross - expenses)
    if net < 0:
        raise HTTPException(
            422,
            "case_expenses não pode superar gross_value; o saque líquido ficaria negativo",
        )

    result = await db.execute(
        text(
            """
            INSERT INTO partner_withdrawals
                (partner_id, gross_value, case_expenses, net_value, partner_share,
                 description, period_reference, status)
            VALUES
                (:partner_id, :gross_value, :case_expenses, :net_value, :partner_share,
                 :description, :period_reference, 'pendente')
            RETURNING *
            """
        ),
        {
            "partner_id": partner_id,
            "gross_value": gross,
            "case_expenses": expenses,
            "net_value": net,
            "partner_share": net,
            "description": body.description,
            "period_reference": body.period_reference,
        },
    )
    row = dict(result.mappings().first())
    await criar_audit_log(
        db,
        current_user.id,
        _role(current_user),
        "CREATE",
        "partner_withdrawals",
        row["id"],
        detalhes="Solicitação de saque criada",
        dados_depois=jsonable_encoder(row),
    )
    await db.commit()
    return row


@router.patch("/{withdrawal_id}/approve")
async def approve_withdrawal(
    withdrawal_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_gestao(current_user)
    row = await _buscar(db, withdrawal_id)
    if not row:
        raise HTTPException(404, "Withdrawal not found")
    if str(row["partner_id"]) == str(current_user.id):
        raise HTTPException(403, "Aprovação da própria retirada não é permitida — segregação de funções")
    if row["status"] != "pendente":
        raise HTTPException(409, f"Cannot approve withdrawal in status '{row['status']}'")

    await db.execute(
        text(
            """
            UPDATE partner_withdrawals
            SET status='aprovado', approved_by=:uid, approved_at=NOW(), updated_at=NOW()
            WHERE id=:id AND deleted_at IS NULL
            """
        ),
        {"uid": str(current_user.id), "id": withdrawal_id},
    )
    await criar_audit_log(
        db,
        current_user.id,
        _role(current_user),
        "APPROVE",
        "partner_withdrawals",
        withdrawal_id,
        dados_antes={"status": row["status"]},
        dados_depois={"status": "aprovado"},
    )
    await db.commit()
    return {"ok": True, "status": "aprovado"}


@router.patch("/{withdrawal_id}/reject")
async def reject_withdrawal(
    withdrawal_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_gestao(current_user)
    row = await _buscar(db, withdrawal_id)
    if not row:
        raise HTTPException(404, "Withdrawal not found")
    if str(row["partner_id"]) == str(current_user.id):
        raise HTTPException(403, "Rejeição da própria retirada não é permitida — segregação de funções")
    if row["status"] != "pendente":
        raise HTTPException(409, f"Cannot reject withdrawal in status '{row['status']}'")

    await db.execute(
        text(
            """
            UPDATE partner_withdrawals
            SET status='rejeitado', approved_by=:uid, updated_at=NOW()
            WHERE id=:id AND deleted_at IS NULL
            """
        ),
        {"uid": str(current_user.id), "id": withdrawal_id},
    )
    await criar_audit_log(
        db,
        current_user.id,
        _role(current_user),
        "REJECT",
        "partner_withdrawals",
        withdrawal_id,
        dados_antes={"status": row["status"]},
        dados_depois={"status": "rejeitado"},
    )
    await db.commit()
    return {"ok": True, "status": "rejeitado"}


@router.patch("/{withdrawal_id}/pay")
async def pay_withdrawal(
    withdrawal_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_gestao(current_user)
    row = await _buscar(db, withdrawal_id)
    if not row:
        raise HTTPException(404, "Withdrawal not found")
    if str(row["partner_id"]) == str(current_user.id):
        raise HTTPException(403, "Pagamento da própria retirada não é permitido — segregação de funções")
    if row["status"] != "aprovado":
        raise HTTPException(409, f"Withdrawal must be approved before payment (current: '{row['status']}')")

    await db.execute(
        text(
            """
            UPDATE partner_withdrawals
            SET status='pago', paid_at=NOW(), updated_at=NOW()
            WHERE id=:id AND deleted_at IS NULL
            """
        ),
        {"id": withdrawal_id},
    )
    await criar_audit_log(
        db,
        current_user.id,
        _role(current_user),
        "PAY",
        "partner_withdrawals",
        withdrawal_id,
        dados_antes={"status": row["status"]},
        dados_depois={"status": "pago"},
    )
    await db.commit()
    return {"ok": True, "status": "pago"}


@router.delete("/{withdrawal_id}")
async def delete_withdrawal(
    withdrawal_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_gestao(current_user)
    row = await _buscar(db, withdrawal_id)
    if not row:
        raise HTTPException(404, "Withdrawal not found")
    if row["status"] in {"aprovado", "pago"}:
        raise HTTPException(
            409,
            "Retirada aprovada ou paga não pode ser excluída; preserve o histórico financeiro",
        )
    role = _role(current_user)
    if str(row["partner_id"]) != str(current_user.id) and role not in {"superadmin", "admin"}:
        raise HTTPException(403, "Não é permitido excluir solicitação de outro sócio")

    await db.execute(
        text("UPDATE partner_withdrawals SET deleted_at=NOW(), updated_at=NOW() WHERE id=:id"),
        {"id": withdrawal_id},
    )
    await criar_audit_log(
        db,
        current_user.id,
        role,
        "DELETE",
        "partner_withdrawals",
        withdrawal_id,
        detalhes="Solicitação de saque removida por soft delete",
        dados_antes=jsonable_encoder(dict(row)),
    )
    await db.commit()
    return {"ok": True}