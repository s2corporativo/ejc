import csv
import io
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

_FIN = {"superadmin", "admin", "socio", "financeiro"}


def _req_fin(cu: User = Depends(get_current_user)) -> User:
    # Despesas do escritório = dado financeiro: só gestão/financeiro.
    # Conjunto explícito (cliente_externo já barrado no AuthMiddleware).
    if cu.role.value not in _FIN:
        raise HTTPException(status_code=403, detail="Acesso restrito a gestão/financeiro")
    return cu


router = APIRouter(prefix="/v1/despesas", tags=["despesas"], dependencies=[Depends(_req_fin)])


@router.get("/resumo")
async def get_resumo(
    competencia: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    comp_filter = "AND competencia = :competencia" if competencia else ""
    result = await db.execute(text(f"""
        SELECT
            COALESCE(SUM(CASE WHEN tipo = 'fixo' AND deleted_at IS NULL THEN valor END), 0) AS total_fixo,
            COALESCE(SUM(CASE WHEN tipo = 'variavel' AND deleted_at IS NULL THEN valor END), 0) AS total_variavel,
            COALESCE(SUM(CASE WHEN status = 'pago' AND deleted_at IS NULL {comp_filter} THEN valor END), 0) AS total_pago_mes,
            COALESCE(SUM(CASE WHEN status = 'pendente' AND deleted_at IS NULL {comp_filter} THEN valor END), 0) AS total_pendente_mes
        FROM office_expenses
        WHERE deleted_at IS NULL
    """), {"competencia": competencia} if competencia else {})
    row = result.mappings().first()

    por_cat = await db.execute(text("""
        SELECT categoria, SUM(valor) AS total, COUNT(*) AS qtd
        FROM office_expenses
        WHERE deleted_at IS NULL
        GROUP BY categoria
        ORDER BY total DESC
    """))
    categorias = [dict(r) for r in por_cat.mappings().all()]

    return {
        "total_fixo": float(row["total_fixo"]),
        "total_variavel": float(row["total_variavel"]),
        "total_pago_mes": float(row["total_pago_mes"]),
        "total_pendente_mes": float(row["total_pendente_mes"]),
        "por_categoria": categorias
    }


@router.get("")
async def list_despesas(
    categoria: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    competencia: Optional[str] = Query(None),
    recorrente: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
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
    result = await db.execute(text(f"""
        SELECT id, categoria, subcategoria, tipo, descricao, valor,
               vencimento, pago_em, recorrente, recorrencia, status,
               competencia, created_by, created_at, updated_at
        FROM office_expenses
        WHERE {where}
        ORDER BY categoria, descricao
    """), params)
    rows = result.mappings().all()
    return [dict(r) for r in rows]


@router.get("/export/csv")
async def export_despesas_csv(
    competencia: Optional[str] = Query(None),
    categoria: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Exporta as despesas do escritório em CSV (pt-BR: separador ';', BOM UTF-8,
    vírgula decimal). Endpoint que faltava (consumido por FinanceiroDashboard)."""
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
    result = await db.execute(text(f"""
        SELECT competencia, categoria, subcategoria, tipo, descricao, valor,
               vencimento, pago_em, recorrente, recorrencia, status
        FROM office_expenses
        WHERE {where}
        ORDER BY competencia DESC, categoria, descricao
    """), params)
    rows = result.mappings().all()

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([
        "Competência", "Categoria", "Subcategoria", "Tipo", "Descrição",
        "Valor", "Vencimento", "Pago em", "Recorrente", "Recorrência", "Status",
    ])
    for r in rows:
        w.writerow([
            r["competencia"] or "", r["categoria"] or "", r["subcategoria"] or "",
            r["tipo"] or "", r["descricao"] or "",
            f'{float(r["valor"] or 0):.2f}'.replace(".", ","),
            r["vencimento"] or "", r["pago_em"] or "",
            "Sim" if r["recorrente"] else "Não", r["recorrencia"] or "",
            r["status"] or "",
        ])
    nome = f"despesas_{competencia or 'todas'}.csv"
    # BOM (﻿) para o Excel abrir UTF-8 corretamente.
    return Response(
        content="﻿" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.post("")
async def create_despesa(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    for field in ["categoria", "descricao", "valor"]:
        if field not in body:
            raise HTTPException(status_code=422, detail=f"Campo obrigatório: {field}")

    result = await db.execute(text("""
        INSERT INTO office_expenses
            (categoria, subcategoria, tipo, descricao, valor, vencimento, pago_em,
             recorrente, recorrencia, status, competencia, created_by)
        VALUES
            (:categoria, :subcategoria, :tipo, :descricao, :valor, :vencimento, :pago_em,
             :recorrente, :recorrencia, :status, :competencia, :created_by)
        RETURNING id, categoria, subcategoria, tipo, descricao, valor,
                  vencimento, pago_em, recorrente, recorrencia, status,
                  competencia, created_at
    """), {
        "categoria": body.get("categoria"),
        "subcategoria": body.get("subcategoria"),
        "tipo": body.get("tipo", "fixo"),
        "descricao": body.get("descricao"),
        "valor": body.get("valor", 0),
        "vencimento": body.get("vencimento"),
        "pago_em": body.get("pago_em"),
        "recorrente": body.get("recorrente", False),
        "recorrencia": body.get("recorrencia"),
        "status": body.get("status", "pendente"),
        "competencia": body.get("competencia"),
        "created_by": current_user.id,
    })
    await db.commit()
    row = result.mappings().first()
    return dict(row)


@router.patch("/{despesa_id}")
async def update_despesa(
    despesa_id: str,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    check = await db.execute(text(
        "SELECT id FROM office_expenses WHERE id = :id AND deleted_at IS NULL"
    ), {"id": despesa_id})
    if not check.first():
        raise HTTPException(status_code=404, detail="Despesa não encontrada")

    allowed = ["categoria", "subcategoria", "tipo", "descricao", "valor",
               "vencimento", "pago_em", "recorrente", "recorrencia", "status", "competencia"]
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=422, detail="Nenhum campo válido para atualizar")

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["id"] = despesa_id
    updates["updated_at"] = "NOW()"

    result = await db.execute(text(f"""
        UPDATE office_expenses
        SET {set_clause}, updated_at = NOW()
        WHERE id = :id AND deleted_at IS NULL
        RETURNING id, categoria, subcategoria, tipo, descricao, valor,
                  vencimento, pago_em, recorrente, recorrencia, status,
                  competencia, updated_at
    """), updates)
    await db.commit()
    row = result.mappings().first()
    return dict(row)


@router.delete("/{despesa_id}")
async def delete_despesa(
    despesa_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    check = await db.execute(text(
        "SELECT id FROM office_expenses WHERE id = :id AND deleted_at IS NULL"
    ), {"id": despesa_id})
    if not check.first():
        raise HTTPException(status_code=404, detail="Despesa não encontrada")

    await db.execute(text(
        "UPDATE office_expenses SET deleted_at = NOW() WHERE id = :id"
    ), {"id": despesa_id})
    await db.commit()
    return {"ok": True, "id": despesa_id}
