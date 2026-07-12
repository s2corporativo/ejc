"""Visão financeira consolidada — tela única.
   GET /api/v1/financeiro/consolidado?competencia=YYYY-MM
   Receitas classificadas (contratual / êxito / sucumbência / custas) + despesas (fixo/variável/categoria) + caixa.
"""
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/financeiro", tags=["Financeiro Consolidado"])

# Least-privilege: caixa/receitas do escritório só p/ gestão/financeiro.
# Conjunto explícito (NÃO require_roles, que pelo fallback hierárquico deixaria advogado passar).
_GESTOR_FIN = {"superadmin", "admin", "socio", "financeiro"}


@router.get("/consolidado")
async def consolidado(
    competencia: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if cu.role.value not in _GESTOR_FIN:
        raise HTTPException(403, "Acesso restrito a gestão/financeiro")
    if not competencia:
        t = date.today()
        competencia = f"{t.year}-{t.month:02d}"
    mes_ref = date.fromisoformat(f"{competencia}-01")

    # ── Receitas (fees) ──────────────────────────────────────────────
    # Sucumbência detectada por convenção de descrição (não há tipo próprio no enum).
    fees = (await db.execute(text("""
        SELECT
          COALESCE(SUM(valor) FILTER (WHERE status='pago'
              AND date_trunc('month', data_pagamento) = date_trunc('month', CAST(:mes AS date))), 0) AS recebido_mes,
          COALESCE(SUM(valor) FILTER (WHERE status IN ('pendente')), 0) AS a_receber,
          COALESCE(SUM(valor) FILTER (WHERE status='atrasado'), 0) AS atrasado,
          -- classificação por tipo (recebido no mês). Sucumbência NÃO é um label
          -- do enum feetipo (fixo/exito/misto/por_hora/custas_despesas) — é
          -- detectada por `descricao ILIKE '%sucumb%'`. Comparar o enum com o
          -- literal 'sucumbencia' estourava InvalidTextRepresentationError (500).
          COALESCE(SUM(valor) FILTER (WHERE status='pago'
              AND date_trunc('month', data_pagamento) = date_trunc('month', CAST(:mes AS date))
              AND tipo IN ('fixo','misto','por_hora')
              AND descricao NOT ILIKE '%sucumb%'), 0) AS rec_contratual,
          COALESCE(SUM(valor) FILTER (WHERE status='pago'
              AND date_trunc('month', data_pagamento) = date_trunc('month', CAST(:mes AS date))
              AND tipo='exito' AND descricao NOT ILIKE '%sucumb%'), 0) AS rec_exito,
          COALESCE(SUM(valor) FILTER (WHERE status='pago'
              AND date_trunc('month', data_pagamento) = date_trunc('month', CAST(:mes AS date))
              AND descricao ILIKE '%sucumb%'), 0) AS rec_sucumbencia,
          COALESCE(SUM(valor) FILTER (WHERE status='pago'
              AND date_trunc('month', data_pagamento) = date_trunc('month', CAST(:mes AS date))
              AND tipo='custas_despesas'), 0) AS rec_custas,
          -- PREVISTO (pendente + atrasado), independente de mes
          COALESCE(SUM(valor) FILTER (WHERE status IN ('pendente','atrasado')
              AND tipo IN ('fixo','misto','por_hora') AND descricao NOT ILIKE '%sucumb%'), 0) AS prev_contratual,
          COALESCE(SUM(valor) FILTER (WHERE status IN ('pendente','atrasado')
              AND tipo='exito' AND descricao NOT ILIKE '%sucumb%'), 0) AS prev_exito,
          COALESCE(SUM(valor) FILTER (WHERE status IN ('pendente','atrasado')
              AND descricao ILIKE '%sucumb%'), 0) AS prev_sucumbencia,
          COALESCE(SUM(valor) FILTER (WHERE status IN ('pendente','atrasado')
              AND tipo='custas_despesas'), 0) AS prev_custas
        FROM fees WHERE deleted_at IS NULL
    """), {"mes": mes_ref})).mappings().first()
    fees = {k: float(v or 0) for k, v in dict(fees).items()}

    # ── Despesas (office_expenses) ───────────────────────────────────
    desp = (await db.execute(text("""
        SELECT
          COALESCE(SUM(valor) FILTER (WHERE status='pago'), 0) AS pago,
          COALESCE(SUM(valor) FILTER (WHERE status!='pago'), 0) AS a_pagar,
          COALESCE(SUM(valor) FILTER (WHERE tipo='fixo'), 0) AS fixo,
          COALESCE(SUM(valor) FILTER (WHERE tipo='variavel'), 0) AS variavel
        FROM office_expenses WHERE deleted_at IS NULL AND competencia = :comp
    """), {"comp": competencia})).mappings().first()
    desp = {k: float(v or 0) for k, v in dict(desp).items()}

    por_cat = (await db.execute(text("""
        SELECT categoria, COALESCE(SUM(valor),0) AS total, COUNT(*) AS qtd
        FROM office_expenses WHERE deleted_at IS NULL AND competencia = :comp
        GROUP BY categoria ORDER BY total DESC
    """), {"comp": competencia})).mappings().all()
    por_categoria = [{"categoria": r["categoria"], "total": float(r["total"]), "qtd": int(r["qtd"])} for r in por_cat]

    recebido = fees["recebido_mes"]
    despesas_pagas = desp["pago"]
    caixa = round(recebido - despesas_pagas, 2)
    margem = round(caixa / recebido * 100, 1) if recebido else 0

    return {
        "competencia": competencia,
        "caixa_periodo": caixa,
        "margem_pct": margem,
        "receitas": {
            "recebido_mes": recebido,
            "a_receber": fees["a_receber"],
            "atrasado": fees["atrasado"],
            "contratual": fees["rec_contratual"],
            "exito": fees["rec_exito"],
            "sucumbencia": fees["rec_sucumbencia"],
            "custas": fees["rec_custas"],
            "previsto": {
                "contratual": fees["prev_contratual"],
                "exito": fees["prev_exito"],
                "sucumbencia": fees["prev_sucumbencia"],
                "custas": fees["prev_custas"],
                "total": round(fees["prev_contratual"]+fees["prev_exito"]+fees["prev_sucumbencia"]+fees["prev_custas"],2),
            },
        },
        "despesas": {
            "pagas": despesas_pagas,
            "a_pagar": desp["a_pagar"],
            "fixo": desp["fixo"],
            "variavel": desp["variavel"],
            "por_categoria": por_categoria,
        },
    }
