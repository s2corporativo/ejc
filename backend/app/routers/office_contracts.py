"""Contratos operacionais do escritório — CRUD financeiro auditável."""
from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.sql_safe import construir_update
from app.models.audit_log import criar_audit_log
from app.models.user import User

_FIN = {"superadmin", "admin", "socio", "financeiro"}
_STATUS = Literal["vigente", "encerrado", "suspenso", "em_negociacao"]
_TIPO = Literal["prestacao_servico", "locacao", "fornecimento", "parceria", "nda", "outro"]


def _req_fin(cu: User = Depends(get_current_user)) -> User:
    if cu.role.value not in _FIN:
        raise HTTPException(status_code=403, detail="Acesso restrito a gestão/financeiro")
    return cu


router = APIRouter(
    prefix="/office-contracts",
    tags=["office-contracts"],
    dependencies=[Depends(_req_fin)],
)


class ContractBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(None, min_length=1, max_length=300)
    counterparty: Optional[str] = Field(None, min_length=1, max_length=300)
    contract_type: Optional[_TIPO] = None
    status: Optional[_STATUS] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    value: Optional[Decimal] = Field(None, ge=0)
    description: Optional[str] = Field(None, max_length=5000)
    file_url: Optional[str] = Field(None, max_length=1000)
    alert_days_before: Optional[int] = Field(None, ge=0, le=3650)

    @model_validator(mode="after")
    def _datas_coerentes(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date não pode ser anterior a start_date")
        return self


class ContractCreate(ContractBase):
    title: str = Field(..., min_length=1, max_length=300)
    counterparty: str = Field(..., min_length=1, max_length=300)
    contract_type: _TIPO = "prestacao_servico"
    status: _STATUS = "vigente"
    start_date: date
    alert_days_before: int = Field(30, ge=0, le=3650)


class ContractUpdate(ContractBase):
    pass


async def _buscar(db: AsyncSession, contract_id: str):
    result = await db.execute(
        text("SELECT * FROM office_contracts WHERE id=:id AND deleted_at IS NULL"),
        {"id": contract_id},
    )
    return result.mappings().first()


@router.get("")
async def list_contracts(
    status: Optional[_STATUS] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    params = {
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }
    if status:
        params["status"] = status
        count_result = await db.execute(
            text("""
                SELECT COUNT(*) FROM office_contracts
                WHERE deleted_at IS NULL AND status=:status
            """),
            {"status": status},
        )
        result = await db.execute(
            text("""
                SELECT * FROM office_contracts
                WHERE deleted_at IS NULL AND status=:status
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        )
    else:
        count_result = await db.execute(
            text("SELECT COUNT(*) FROM office_contracts WHERE deleted_at IS NULL")
        )
        result = await db.execute(
            text("""
                SELECT * FROM office_contracts
                WHERE deleted_at IS NULL
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        )
    total = count_result.scalar() or 0
    return {
        "data": [dict(r) for r in result.mappings().all()],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/expiring")
async def list_expiring(
    days: Optional[int] = Query(None, ge=0, le=3650),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Contratos cuja janela individual de alerta já foi atingida.

    `alert_days_before` é a regra do próprio contrato. O parâmetro opcional
    `days` funciona apenas como teto adicional para consultas administrativas;
    a chamada padrão da UI não o envia e, portanto, respeita integralmente a
    configuração individual.
    """
    if days is None:
        result = await db.execute(
            text("""
                SELECT *
                FROM office_contracts
                WHERE deleted_at IS NULL
                  AND status='vigente'
                  AND end_date IS NOT NULL
                  AND end_date >= CURRENT_DATE
                  AND end_date <= CURRENT_DATE
                        + make_interval(days => COALESCE(alert_days_before, 30))
                ORDER BY end_date
            """)
        )
    else:
        result = await db.execute(
            text("""
                SELECT *
                FROM office_contracts
                WHERE deleted_at IS NULL
                  AND status='vigente'
                  AND end_date IS NOT NULL
                  AND end_date >= CURRENT_DATE
                  AND end_date <= CURRENT_DATE
                        + make_interval(days => COALESCE(alert_days_before, 30))
                  AND end_date <= CURRENT_DATE + make_interval(days => :days)
                ORDER BY end_date
            """),
            {"days": days},
        )
    return [dict(r) for r in result.mappings().all()]


@router.post("", status_code=201)
async def create_contract(
    body: ContractCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dados = body.model_dump()
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
        row["id"],
        detalhes="Contrato do escritório criado",
        dados_depois=jsonable_encoder(row),
    )
    await db.commit()
    return row


@router.get("/{contract_id}")
async def get_contract(
    contract_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await _buscar(db, contract_id)
    if not row:
        raise HTTPException(404, "Contract not found")
    return dict(row)


@router.patch("/{contract_id}")
async def update_contract(
    contract_id: str,
    body: ContractUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    antes = await _buscar(db, contract_id)
    if not antes:
        raise HTTPException(404, "Contract not found")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(422, "Nenhum campo informado para atualizar")

    # Validação cruzada também quando apenas uma das datas é alterada.
    start = updates.get("start_date", antes["start_date"])
    end = updates.get("end_date", antes["end_date"])
    if start and end and end < start:
        raise HTTPException(422, "end_date não pode ser anterior a start_date")

    stmt, params = construir_update(
        updates,
        tabela="office_contracts",
        exigir_nao_excluido=True,
    )
    params["where_id"] = contract_id
    result = await db.execute(stmt, params)
    if result.rowcount == 0:
        raise HTTPException(404, "Contract not found")

    depois_row = await _buscar(db, contract_id)
    if not depois_row:
        raise HTTPException(404, "Contract not found")
    depois = dict(depois_row)
    await criar_audit_log(
        db,
        current_user.id,
        current_user.role.value,
        "UPDATE",
        "office_contracts",
        contract_id,
        detalhes=f"campos alterados: {sorted(updates)}",
        dados_antes=jsonable_encoder(dict(antes)),
        dados_depois=jsonable_encoder(depois),
    )
    await db.commit()
    return depois


@router.delete("/{contract_id}")
async def delete_contract(
    contract_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    antes = await _buscar(db, contract_id)
    if not antes:
        raise HTTPException(404, "Contract not found")
    await db.execute(
        text("UPDATE office_contracts SET deleted_at=NOW(), updated_at=NOW() WHERE id=:id"),
        {"id": contract_id},
    )
    await criar_audit_log(
        db,
        current_user.id,
        current_user.role.value,
        "DELETE",
        "office_contracts",
        contract_id,
        detalhes="Contrato do escritório removido por soft delete",
        dados_antes=jsonable_encoder(dict(antes)),
    )
    await db.commit()
    return {"ok": True}
