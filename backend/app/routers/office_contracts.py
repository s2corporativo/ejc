"""Contratos administrativos do próprio escritório.

Leitura: gestão/financeiro. Mutação de termos contratuais: gestão (sócio+).
Este módulo organiza obrigações; não substitui o documento contratual assinado.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.audit_log import criar_audit_log
from app.models.user import User

_FIN = {"superadmin", "admin", "socio", "financeiro"}


def _req_fin(cu: User = Depends(get_current_user)) -> User:
    if cu.role.value not in _FIN:
        raise HTTPException(status_code=403, detail="Acesso restrito a gestão/financeiro")
    return cu


def _req_gestao(cu: User = Depends(get_current_user)) -> User:
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        raise HTTPException(
            status_code=403,
            detail="Alterações contratuais são restritas a sócios/administradores",
        )
    return cu


router = APIRouter(prefix="/office-contracts", tags=["office-contracts"])


class ContractBase(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    counterparty: str = Field(min_length=2, max_length=255)
    contract_type: str = Field(default="prestacao_servico", max_length=80)
    status: Literal["vigente", "encerrado", "suspenso", "rascunho"] = "vigente"
    start_date: date
    end_date: date | None = None
    value: Decimal | None = Field(default=None, ge=Decimal("0"), max_digits=14, decimal_places=2)
    description: str | None = Field(default=None, max_length=5000)
    file_url: str | None = Field(default=None, max_length=1000)
    alert_days_before: int = Field(default=30, ge=1, le=3650)

    @model_validator(mode="after")
    def _datas(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date não pode ser anterior a start_date")
        return self


class ContractCreate(ContractBase):
    pass


class ContractUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    counterparty: str | None = Field(default=None, min_length=2, max_length=255)
    contract_type: str | None = Field(default=None, max_length=80)
    status: Literal["vigente", "encerrado", "suspenso", "rascunho"] | None = None
    start_date: date | None = None
    end_date: date | None = None
    value: Decimal | None = Field(default=None, ge=Decimal("0"), max_digits=14, decimal_places=2)
    description: str | None = Field(default=None, max_length=5000)
    file_url: str | None = Field(default=None, max_length=1000)
    alert_days_before: int | None = Field(default=None, ge=1, le=3650)


async def _get(db: AsyncSession, contract_id: str) -> dict | None:
    row = (
        await db.execute(
            text(
                "SELECT * FROM office_contracts "
                "WHERE id=:id AND deleted_at IS NULL"
            ),
            {"id": contract_id},
        )
    ).mappings().first()
    return dict(row) if row else None


@router.get("")
async def list_contracts(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_req_fin),
):
    q = "SELECT * FROM office_contracts WHERE deleted_at IS NULL"
    params: dict = {}
    if status:
        q += " AND status=:status"
        params["status"] = status
    count_result = await db.execute(text(q.replace("SELECT *", "SELECT COUNT(*)")), params)
    total = int(count_result.scalar() or 0)
    q += " ORDER BY COALESCE(end_date, DATE '9999-12-31'), created_at DESC LIMIT :limit OFFSET :offset"
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    result = await db.execute(text(q), params)
    return {
        "data": [dict(r) for r in result.mappings().all()],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/expiring")
async def list_expiring(
    days: int | None = Query(default=None, ge=1, le=3650),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_req_fin),
):
    """Contratos dentro do alerta.

    Sem `days`, cada contrato usa sua própria `alert_days_before`. Com `days`,
    o parâmetro funciona como janela adicional de consulta manual.
    """
    if days is None:
        sql = """
            SELECT *, (end_date - CURRENT_DATE) AS days_remaining
            FROM office_contracts
            WHERE deleted_at IS NULL AND status='vigente' AND end_date IS NOT NULL
              AND end_date BETWEEN CURRENT_DATE
                  AND CURRENT_DATE + (alert_days_before * INTERVAL '1 day')
            ORDER BY end_date
        """
        params = {}
    else:
        sql = """
            SELECT *, (end_date - CURRENT_DATE) AS days_remaining
            FROM office_contracts
            WHERE deleted_at IS NULL AND status='vigente' AND end_date IS NOT NULL
              AND end_date BETWEEN CURRENT_DATE
                  AND CURRENT_DATE + (:days * INTERVAL '1 day')
            ORDER BY end_date
        """
        params = {"days": days}
    result = await db.execute(text(sql), params)
    return [dict(r) for r in result.mappings().all()]


@router.post("", status_code=201)
async def create_contract(
    body: ContractCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_req_gestao),
):
    dados = body.model_dump(mode="python")
    result = await db.execute(
        text(
            """
            INSERT INTO office_contracts
                (title,counterparty,contract_type,status,start_date,end_date,value,
                 description,file_url,alert_days_before,created_by)
            VALUES
                (:title,:counterparty,:contract_type,:status,:start_date,:end_date,:value,
                 :description,:file_url,:alert_days_before,:created_by)
            RETURNING *
            """
        ),
        {**dados, "created_by": str(current_user.id)},
    )
    row = dict(result.mappings().first())
    await criar_audit_log(
        db,
        current_user.id,
        current_user.role.value,
        "CREATE",
        "office_contracts",
        str(row["id"]),
        dados_depois={
            "title": row.get("title"),
            "counterparty": row.get("counterparty"),
            "status": row.get("status"),
            "start_date": str(row.get("start_date")),
            "end_date": str(row.get("end_date")) if row.get("end_date") else None,
            "value": str(row.get("value")) if row.get("value") is not None else None,
        },
    )
    await db.commit()
    return row


@router.get("/{contract_id}")
async def get_contract(
    contract_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_req_fin),
):
    row = await _get(db, contract_id)
    if not row:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    return row


@router.patch("/{contract_id}")
async def update_contract(
    contract_id: str,
    body: ContractUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_req_gestao),
):
    antes = await _get(db, contract_id)
    if not antes:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    updates = body.model_dump(exclude_unset=True, mode="python")
    if not updates:
        raise HTTPException(status_code=422, detail="Nenhuma alteração informada")

    start = updates.get("start_date", antes.get("start_date"))
    end = updates.get("end_date", antes.get("end_date"))
    if start and end and end < start:
        raise HTTPException(status_code=422, detail="end_date não pode ser anterior a start_date")

    sets = [f"{field}=:{field}" for field in updates]
    sets.append("updated_at=NOW()")
    result = await db.execute(
        text(
            f"UPDATE office_contracts SET {','.join(sets)} "
            "WHERE id=:id AND deleted_at IS NULL RETURNING *"
        ),
        {**updates, "id": contract_id},
    )
    depois = dict(result.mappings().first())
    await criar_audit_log(
        db,
        current_user.id,
        current_user.role.value,
        "UPDATE",
        "office_contracts",
        contract_id,
        dados_antes={k: str(antes.get(k)) for k in updates},
        dados_depois={k: str(depois.get(k)) for k in updates},
    )
    await db.commit()
    return depois


@router.delete("/{contract_id}")
async def delete_contract(
    contract_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_req_gestao),
):
    antes = await _get(db, contract_id)
    if not antes:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    await db.execute(
        text(
            "UPDATE office_contracts SET deleted_at=NOW(), updated_at=NOW() "
            "WHERE id=:id AND deleted_at IS NULL"
        ),
        {"id": contract_id},
    )
    await criar_audit_log(
        db,
        current_user.id,
        current_user.role.value,
        "DELETE",
        "office_contracts",
        contract_id,
        dados_antes={
            "title": antes.get("title"),
            "counterparty": antes.get("counterparty"),
            "status": antes.get("status"),
            "end_date": str(antes.get("end_date")) if antes.get("end_date") else None,
        },
    )
    await db.commit()
    return {"ok": True}
