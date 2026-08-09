from __future__ import annotations

import csv
import io
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.user import User
from app.schemas.despesa import DespesaCreate, DespesaUpdate, GerarRecorrentesRequest
from app.services import despesa_service

_FIN = {"superadmin", "admin", "socio", "financeiro"}


def _req_fin(cu: User = Depends(get_current_user)) -> User:
    if cu.role.value not in _FIN:
        raise HTTPException(
            status_code=403, detail="Acesso restrito a gestão/financeiro"
        )
    return cu


router = APIRouter(
    prefix="/despesas", tags=["despesas"], dependencies=[Depends(_req_fin)]
)


def _money_csv(value) -> str:
    return format(Decimal(str(value or 0)).quantize(Decimal("0.01")), "f").replace(
        ".", ","
    )


@router.get("/resumo")
async def get_resumo(
    competencia: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # A competência, quando informada, recorta TODAS as métricas e categorias.
    # Antes apenas pago/pendente respeitavam o filtro, misturando períodos.
    comp_filter = "AND competencia = :competencia" if competencia else ""
    params = {"competencia": competencia} if competencia else {}
    result = await db.execute(
        text(
            f"""
            SELECT
                COALESCE(SUM(CASE WHEN tipo = 'fixo' AND deleted_at IS NULL
                    {comp_filter} THEN valor END), 0) AS total_fixo,
                COALESCE(SUM(CASE WHEN tipo = 'variavel' AND deleted_at IS NULL
                    {comp_filter} THEN valor END), 0) AS total_variavel,
                COALESCE(SUM(CASE WHEN status = 'pago' AND deleted_at IS NULL
                    {comp_filter} THEN valor END), 0) AS total_pago_mes,
                COALESCE(SUM(CASE WHEN status = 'pendente' AND deleted_at IS NULL
                    {comp_filter} THEN valor END), 0) AS total_pendente_mes
            FROM office_expenses
            WHERE deleted_at IS NULL
            """
        ),
        params,
    )
    row = result.mappings().first()

    por_cat = await db.execute(
        text(
            f"""
            SELECT categoria, SUM(valor) AS total, COUNT(*) AS qtd
            FROM office_expenses
            WHERE deleted_at IS NULL {comp_filter}
            GROUP BY categoria
            ORDER BY total DESC
            """
        ),
        params,
    )
    categorias = [dict(r) for r in por_cat.mappings().all()]

    def _dec(v):
        return Decimal(str(v)) if v is not None else Decimal("0")

    return {
        "total_fixo": _dec(row["total_fixo"]),
        "total_variavel": _dec(row["total_variavel"]),
        "total_pago_mes": _dec(row["total_pago_mes"]),
        "total_pendente_mes": _dec(row["total_pendente_mes"]),
        "por_categoria": categorias,
    }


@router.get("")
async def list_despesas(
    categoria: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    competencia: Optional[str] = Query(None),
    recorrente: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conditions = ["deleted_at IS NULL"]
    params = {}
    if categoria:
        conditions.append("categoria = :categoria")
        params["categoria"] = categoria
    if tipo:
        conditions.append("tipo = :tipo")
        params["tipo"] = tipo
    if status:
        conditions.append("status = :status")
        params["status"] = status
    if competencia:
        conditions.append("competencia = :competencia")
        params["competencia"] = competencia
    if recorrente is not None:
        conditions.append("recorrente = :recorrente")
        params["recorrente"] = recorrente

    where = " AND ".join(conditions)
    result = await db.execute(
        text(
            f"""
            SELECT id, categoria, subcategoria, tipo, descricao, valor,
                   vencimento, pago_em, recorrente, recorrencia, status,
                   competencia, recorrencia_origem_id, created_by,
                   created_at, updated_at
            FROM office_expenses
            WHERE {where}
            ORDER BY categoria, descricao
            """
        ),
        params,
    )
    return [dict(r) for r in result.mappings().all()]


@router.get("/export/csv")
async def export_despesas_csv(
    competencia: Optional[str] = Query(None),
    categoria: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conditions = ["deleted_at IS NULL"]
    params: dict = {}
    if competencia:
        conditions.append("competencia = :competencia")
        params["competencia"] = competencia
    if categoria:
        conditions.append("categoria = :categoria")
        params["categoria"] = categoria
    if tipo:
        conditions.append("tipo = :tipo")
        params["tipo"] = tipo
    if status:
        conditions.append("status = :status")
        params["status"] = status
    where = " AND ".join(conditions)
    result = await db.execute(
        text(
            f"""
            SELECT competencia, categoria, subcategoria, tipo, descricao, valor,
                   vencimento, pago_em, recorrente, recorrencia, status,
                   recorrencia_origem_id
            FROM office_expenses
            WHERE {where}
            ORDER BY competencia DESC, categoria, descricao
            """
        ),
        params,
    )
    rows = result.mappings().all()

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(
        [
            "Competência",
            "Categoria",
            "Subcategoria",
            "Tipo",
            "Descrição",
            "Valor",
            "Vencimento",
            "Pago em",
            "Modelo recorrente",
            "Recorrência",
            "Status",
            "Origem recorrente",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["competencia"] or "",
                row["categoria"] or "",
                row["subcategoria"] or "",
                row["tipo"] or "",
                row["descricao"] or "",
                _money_csv(row["valor"]),
                row["vencimento"] or "",
                row["pago_em"] or "",
                "Sim" if row["recorrente"] else "Não",
                row["recorrencia"] or "",
                row["status"] or "",
                row["recorrencia_origem_id"] or "",
            ]
        )
    nome = f"despesas_{competencia or 'todas'}.csv"
    return Response(
        content="﻿" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.post("", status_code=201)
async def create_despesa(
    body: DespesaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await despesa_service.criar_despesa(db, body, user_id=current_user.id)
    await criar_audit_log(
        db,
        current_user.id,
        current_user.role.value,
        "CREATE",
        "office_expenses",
        row["id"],
        dados_depois={
            "categoria": row.get("categoria"),
            "tipo": row.get("tipo"),
            "valor": str(row.get("valor") or "0"),
            "competencia": row.get("competencia"),
            "recorrente": row.get("recorrente"),
        },
    )
    await db.commit()
    return row


@router.post("/recorrentes/gerar")
async def gerar_recorrentes(
    body: GerarRecorrentesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resumo = await despesa_service.gerar_recorrentes(
        db, body.competencia, user_id=current_user.id
    )
    await criar_audit_log(
        db,
        current_user.id,
        current_user.role.value,
        "GENERATE",
        "office_expenses",
        body.competencia,
        dados_depois={
            "competencia": body.competencia,
            "modelos": resumo["modelos"],
            "gerados": resumo["gerados"],
            "ja_existentes": resumo["ja_existentes"],
        },
        detalhes="Geração idempotente de despesas recorrentes por competência.",
    )
    await db.commit()
    return resumo


@router.patch("/{despesa_id}")
async def update_despesa(
    despesa_id: str,
    body: DespesaUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        antes, depois = await despesa_service.atualizar_despesa(db, despesa_id, body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await criar_audit_log(
        db,
        current_user.id,
        current_user.role.value,
        "UPDATE",
        "office_expenses",
        despesa_id,
        dados_antes={
            "categoria": antes.get("categoria"),
            "tipo": antes.get("tipo"),
            "valor": str(antes.get("valor") or "0"),
            "status": antes.get("status"),
            "competencia": antes.get("competencia"),
            "recorrente": antes.get("recorrente"),
        },
        dados_depois={
            "categoria": depois.get("categoria"),
            "tipo": depois.get("tipo"),
            "valor": str(depois.get("valor") or "0"),
            "status": depois.get("status"),
            "competencia": depois.get("competencia"),
            "recorrente": depois.get("recorrente"),
        },
    )
    await db.commit()
    return depois


@router.delete("/{despesa_id}")
async def delete_despesa(
    despesa_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        antes = await despesa_service.excluir_despesa(db, despesa_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await criar_audit_log(
        db,
        current_user.id,
        current_user.role.value,
        "DELETE",
        "office_expenses",
        despesa_id,
        dados_antes={
            "categoria": antes.get("categoria"),
            "valor": str(antes.get("valor") or "0"),
            "status": antes.get("status"),
            "competencia": antes.get("competencia"),
            "recorrente": antes.get("recorrente"),
        },
    )
    await db.commit()
    return {"ok": True, "id": despesa_id}
