"""Visão financeira consolidada — tela única.
   GET /api/v1/financeiro/consolidado?competencia=YYYY-MM
   Receitas classificadas (contratual / êxito / sucumbência / custas) + despesas (fixo/variável/categoria) + caixa.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.fee import FeeTipo

router = APIRouter(prefix="/financeiro", tags=["Financeiro Consolidado"])

_Q2 = Decimal("0.01")
_Q1 = Decimal("0.1")


def _money(v) -> Decimal:
    """Coage qualquer numérico (Decimal de coluna Numeric, int, float, str, None)
    para Decimal com 2 casas (ROUND_HALF_UP). Mantém a matemática monetária exata
    ponta a ponta — a conversão para float fica só na fronteira de serialização
    (FastAPI/jsonable_encoder)."""
    return Decimal(str(v or 0)).quantize(_Q2, ROUND_HALF_UP)


# Sucumbência agora é label próprio do enum feetipo (adicionado pelo schema).
# Classificamos pelo enum via CAST(tipo AS text) = 'sucumbencia' — o cast para
# text evita o InvalidTextRepresentationError (500) caso a migration do label
# ainda não tenha sido aplicada, e casa exatamente as linhas do enum. Mantemos o
# fallback barato `descricao ILIKE '%sucumb%'` para linhas legadas (gravadas
# antes do enum existir). getattr mantém o módulo importável antes do landing.
_suc = getattr(FeeTipo, "sucumbencia", None)
_SUCUMB = _suc.value if _suc is not None else "sucumbencia"

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
    # Sucumbência classificada pelo enum feetipo (CAST(tipo AS text) = 'sucumbencia'),
    # com fallback barato por descrição para linhas legadas. Contratual/êxito já
    # excluem 'sucumbencia' por filtrarem seus próprios labels de tipo.
    fees = (await db.execute(text(f"""
        SELECT
          COALESCE(SUM(valor) FILTER (WHERE status='pago'
              AND date_trunc('month', data_pagamento) = date_trunc('month', CAST(:mes AS date))), 0) AS recebido_mes,
          COALESCE(SUM(valor) FILTER (WHERE status IN ('pendente')), 0) AS a_receber,
          COALESCE(SUM(valor) FILTER (WHERE status='atrasado'), 0) AS atrasado,
          COALESCE(SUM(valor) FILTER (WHERE status='pago'
              AND date_trunc('month', data_pagamento) = date_trunc('month', CAST(:mes AS date))
              AND tipo IN ('fixo','misto','por_hora')
              AND descricao NOT ILIKE '%sucumb%'), 0) AS rec_contratual,
          COALESCE(SUM(valor) FILTER (WHERE status='pago'
              AND date_trunc('month', data_pagamento) = date_trunc('month', CAST(:mes AS date))
              AND tipo='exito' AND descricao NOT ILIKE '%sucumb%'), 0) AS rec_exito,
          COALESCE(SUM(valor) FILTER (WHERE status='pago'
              AND date_trunc('month', data_pagamento) = date_trunc('month', CAST(:mes AS date))
              AND (CAST(tipo AS text) = '{_SUCUMB}' OR descricao ILIKE '%sucumb%')), 0) AS rec_sucumbencia,
          COALESCE(SUM(valor) FILTER (WHERE status='pago'
              AND date_trunc('month', data_pagamento) = date_trunc('month', CAST(:mes AS date))
              AND tipo='custas_despesas'), 0) AS rec_custas,
          -- PREVISTO (pendente + atrasado), independente de mes
          COALESCE(SUM(valor) FILTER (WHERE status IN ('pendente','atrasado')
              AND tipo IN ('fixo','misto','por_hora') AND descricao NOT ILIKE '%sucumb%'), 0) AS prev_contratual,
          COALESCE(SUM(valor) FILTER (WHERE status IN ('pendente','atrasado')
              AND tipo='exito' AND descricao NOT ILIKE '%sucumb%'), 0) AS prev_exito,
          COALESCE(SUM(valor) FILTER (WHERE status IN ('pendente','atrasado')
              AND (CAST(tipo AS text) = '{_SUCUMB}' OR descricao ILIKE '%sucumb%')), 0) AS prev_sucumbencia,
          COALESCE(SUM(valor) FILTER (WHERE status IN ('pendente','atrasado')
              AND tipo='custas_despesas'), 0) AS prev_custas
        FROM fees WHERE deleted_at IS NULL
    """), {"mes": mes_ref})).mappings().first()
    fees = {k: _money(v) for k, v in dict(fees).items()}

    # ── Despesas (office_expenses) ───────────────────────────────────
    desp = (await db.execute(text("""
        SELECT
          COALESCE(SUM(valor) FILTER (WHERE status='pago'), 0) AS pago,
          COALESCE(SUM(valor) FILTER (WHERE status!='pago'), 0) AS a_pagar,
          COALESCE(SUM(valor) FILTER (WHERE tipo='fixo'), 0) AS fixo,
          COALESCE(SUM(valor) FILTER (WHERE tipo='variavel'), 0) AS variavel
        FROM office_expenses WHERE deleted_at IS NULL AND competencia = :comp
    """), {"comp": competencia})).mappings().first()
    desp = {k: _money(v) for k, v in dict(desp).items()}

    por_cat = (await db.execute(text("""
        SELECT categoria, COALESCE(SUM(valor),0) AS total, COUNT(*) AS qtd
        FROM office_expenses WHERE deleted_at IS NULL AND competencia = :comp
        GROUP BY categoria ORDER BY total DESC
    """), {"comp": competencia})).mappings().all()
    por_categoria = [{"categoria": r["categoria"], "total": _money(r["total"]), "qtd": int(r["qtd"])} for r in por_cat]

    recebido = fees["recebido_mes"]
    despesas_pagas = desp["pago"]
    caixa = _money(recebido - despesas_pagas)
    margem = (caixa / recebido * 100).quantize(_Q1, ROUND_HALF_UP) if recebido else Decimal("0")

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
                "total": _money(fees["prev_contratual"]+fees["prev_exito"]+fees["prev_sucumbencia"]+fees["prev_custas"]),
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
