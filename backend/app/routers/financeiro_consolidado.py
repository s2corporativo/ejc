"""Visão financeira consolidada — tela única.

GET /api/v1/financeiro/consolidado?competencia=YYYY-MM
Receitas classificadas + despesas por competência + caixa do período.

Princípio contábil operacional deste endpoint: entrada de caixa vem de
`fee_payments`; `fees.valor` representa o valor contratado/original e só serve
para apurar o saldo ainda a receber. Isso evita reconhecer integralmente um fee
no mês da quitação quando parcelas foram recebidas em meses anteriores.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.fee import FeeTipo
from app.models.user import User

router = APIRouter(prefix="/financeiro", tags=["Financeiro Consolidado"])

_Q2 = Decimal("0.01")
_Q1 = Decimal("0.1")


def _money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(_Q2, ROUND_HALF_UP)


_suc = getattr(FeeTipo, "sucumbencia", None)
_SUCUMB = _suc.value if _suc is not None else "sucumbencia"

# Least-privilege: caixa/receitas do escritório só p/ gestão/financeiro.
_GESTOR_FIN = {"superadmin", "admin", "socio", "financeiro"}


@router.get("/consolidado")
async def consolidado(
    competencia: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if cu.role.value not in _GESTOR_FIN:
        raise HTTPException(403, "Acesso restrito a gestão/financeiro")
    if not competencia:
        t = date.today()
        competencia = f"{t.year}-{t.month:02d}"
    mes_ref = date.fromisoformat(f"{competencia}-01")

    # ── Receitas / saldos de honorários ──────────────────────────────
    # Duas bases independentes:
    # 1) `pagamentos_mes`: fluxo de caixa efetivamente recebido no período;
    # 2) `saldos`: valor original menos todos os pagamentos já registrados.
    #
    # Percentuais sem valor monetário realizado não são transformados em reais
    # por suposição: o contador separado torna essa lacuna visível ao operador.
    fees = (
        await db.execute(
            text(
                f"""
                WITH pagamentos_totais AS (
                    SELECT fee_id, COALESCE(SUM(valor), 0) AS total_pago
                    FROM fee_payments
                    GROUP BY fee_id
                ),
                saldos AS (
                    SELECT
                        f.id,
                        CAST(f.tipo AS text) AS tipo,
                        f.descricao,
                        CAST(f.status AS text) AS status,
                        GREATEST(
                            COALESCE(f.valor, 0) - COALESCE(pt.total_pago, 0),
                            0
                        ) AS saldo
                    FROM fees f
                    LEFT JOIN pagamentos_totais pt ON pt.fee_id = f.id
                    WHERE f.deleted_at IS NULL
                ),
                pagamentos_mes AS (
                    SELECT
                        fp.valor,
                        CAST(f.tipo AS text) AS tipo,
                        f.descricao
                    FROM fee_payments fp
                    JOIN fees f ON f.id = fp.fee_id
                    WHERE f.deleted_at IS NULL
                      AND date_trunc('month', fp.data_pagamento)
                          = date_trunc('month', CAST(:mes AS date))
                )
                SELECT
                    (SELECT COALESCE(SUM(valor), 0) FROM pagamentos_mes)
                        AS recebido_mes,
                    COALESCE(SUM(saldo) FILTER (WHERE status='pendente'), 0)
                        AS a_receber,
                    COALESCE(SUM(saldo) FILTER (WHERE status='atrasado'), 0)
                        AS atrasado,
                    (SELECT COALESCE(SUM(valor), 0) FROM pagamentos_mes
                        WHERE tipo IN ('fixo','misto','por_hora')
                          AND descricao NOT ILIKE '%sucumb%') AS rec_contratual,
                    (SELECT COALESCE(SUM(valor), 0) FROM pagamentos_mes
                        WHERE tipo='exito'
                          AND descricao NOT ILIKE '%sucumb%') AS rec_exito,
                    (SELECT COALESCE(SUM(valor), 0) FROM pagamentos_mes
                        WHERE tipo = '{_SUCUMB}' OR descricao ILIKE '%sucumb%')
                        AS rec_sucumbencia,
                    (SELECT COALESCE(SUM(valor), 0) FROM pagamentos_mes
                        WHERE tipo='custas_despesas') AS rec_custas,
                    COALESCE(SUM(saldo) FILTER (
                        WHERE status IN ('pendente','atrasado')
                          AND tipo IN ('fixo','misto','por_hora')
                          AND descricao NOT ILIKE '%sucumb%'
                    ), 0) AS prev_contratual,
                    COALESCE(SUM(saldo) FILTER (
                        WHERE status IN ('pendente','atrasado')
                          AND tipo='exito'
                          AND descricao NOT ILIKE '%sucumb%'
                    ), 0) AS prev_exito,
                    COALESCE(SUM(saldo) FILTER (
                        WHERE status IN ('pendente','atrasado')
                          AND (tipo = '{_SUCUMB}' OR descricao ILIKE '%sucumb%')
                    ), 0) AS prev_sucumbencia,
                    COALESCE(SUM(saldo) FILTER (
                        WHERE status IN ('pendente','atrasado')
                          AND tipo='custas_despesas'
                    ), 0) AS prev_custas,
                    (
                        SELECT COUNT(*)
                        FROM fees f2
                        WHERE f2.deleted_at IS NULL
                          AND f2.valor IS NULL
                          AND f2.percentual_exito IS NOT NULL
                          AND CAST(f2.status AS text) IN ('pendente','atrasado')
                    ) AS percentuais_sem_valor
                FROM saldos
                """
            ),
            {"mes": mes_ref},
        )
    ).mappings().first()
    bruto = dict(fees)
    percentuais_sem_valor = int(bruto.pop("percentuais_sem_valor") or 0)
    fees = {k: _money(v) for k, v in bruto.items()}

    # ── Despesas (office_expenses) ───────────────────────────────────
    desp = (
        await db.execute(
            text(
                """
                SELECT
                  COALESCE(SUM(valor) FILTER (WHERE status='pago'), 0) AS pago,
                  COALESCE(SUM(valor) FILTER (WHERE status='pendente'), 0) AS a_pagar,
                  COALESCE(SUM(valor) FILTER (
                      WHERE tipo='fixo' AND status!='cancelado'
                  ), 0) AS fixo,
                  COALESCE(SUM(valor) FILTER (
                      WHERE tipo='variavel' AND status!='cancelado'
                  ), 0) AS variavel
                FROM office_expenses
                WHERE deleted_at IS NULL AND competencia = :comp
                """
            ),
            {"comp": competencia},
        )
    ).mappings().first()
    desp = {k: _money(v) for k, v in dict(desp).items()}

    por_cat = (
        await db.execute(
            text(
                """
                SELECT categoria, COALESCE(SUM(valor),0) AS total, COUNT(*) AS qtd
                FROM office_expenses
                WHERE deleted_at IS NULL
                  AND status != 'cancelado'
                  AND competencia = :comp
                GROUP BY categoria ORDER BY total DESC
                """
            ),
            {"comp": competencia},
        )
    ).mappings().all()
    por_categoria = [
        {
            "categoria": r["categoria"],
            "total": _money(r["total"]),
            "qtd": int(r["qtd"]),
        }
        for r in por_cat
    ]

    recebido = fees["recebido_mes"]
    despesas_pagas = desp["pago"]
    caixa = _money(recebido - despesas_pagas)
    margem = (
        (caixa / recebido * 100).quantize(_Q1, ROUND_HALF_UP)
        if recebido
        else Decimal("0")
    )

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
            "percentuais_sem_valor": percentuais_sem_valor,
            "previsto": {
                "contratual": fees["prev_contratual"],
                "exito": fees["prev_exito"],
                "sucumbencia": fees["prev_sucumbencia"],
                "custas": fees["prev_custas"],
                "total": _money(
                    fees["prev_contratual"]
                    + fees["prev_exito"]
                    + fees["prev_sucumbencia"]
                    + fees["prev_custas"]
                ),
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
