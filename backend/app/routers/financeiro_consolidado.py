"""Visão financeira consolidada — tela única.

GET /api/v1/financeiro/consolidado?competencia=YYYY-MM
GET /api/v1/financeiro/atencao
GET /api/v1/financeiro/demonstrativo?competencia=YYYY-MM

Princípio operacional: caixa usa pagamentos/baixas efetivas; competência usa
vencimento contratual dos honorários e a competência declarada das despesas.
O demonstrativo é GERENCIAL, não substitui escrituração ou DRE contábil.
"""
from datetime import date, timedelta
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
_GESTOR_FIN = {"superadmin", "admin", "socio", "financeiro"}


def _exigir_financeiro(cu: User) -> None:
    if cu.role.value not in _GESTOR_FIN:
        raise HTTPException(403, "Acesso restrito a gestão/financeiro")


def _competencia_atual(competencia: Optional[str]) -> str:
    if competencia:
        return competencia
    t = date.today()
    return f"{t.year}-{t.month:02d}"


@router.get("/consolidado")
async def consolidado(
    competencia: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    competencia = _competencia_atual(competencia)
    mes_ref = date.fromisoformat(f"{competencia}-01")

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


@router.get("/atencao")
async def pendencias_operacionais(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Fila curta do que exige decisão financeira.

    Retorna agregados sem PII de cliente/caso. A interface navega para a tela de
    origem, onde o RBAC existente continua sendo a autoridade para os detalhes.
    """
    _exigir_financeiro(cu)
    hoje = date.today()
    em_7_dias = hoje + timedelta(days=7)
    ha_30_dias = hoje - timedelta(days=30)

    hon = (
        await db.execute(
            text(
                """
                WITH pagos AS (
                    SELECT fee_id, COALESCE(SUM(valor), 0) AS total_pago
                    FROM fee_payments GROUP BY fee_id
                )
                SELECT COUNT(*) AS qtd,
                       COALESCE(SUM(GREATEST(f.valor - COALESCE(p.total_pago, 0), 0)), 0) AS total
                FROM fees f
                LEFT JOIN pagos p ON p.fee_id = f.id
                WHERE f.deleted_at IS NULL
                  AND f.valor IS NOT NULL
                  AND CAST(f.status AS text) IN ('pendente','atrasado')
                  AND f.data_vencimento < :hoje
                  AND GREATEST(f.valor - COALESCE(p.total_pago, 0), 0) > 0
                """
            ),
            {"hoje": hoje},
        )
    ).mappings().first()

    despesas = (
        await db.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (WHERE vencimento < :hoje) AS vencidas_qtd,
                    COALESCE(SUM(valor) FILTER (WHERE vencimento < :hoje), 0) AS vencidas_total,
                    COUNT(*) FILTER (
                        WHERE vencimento >= :hoje AND vencimento <= :limite
                    ) AS proximas_qtd,
                    COALESCE(SUM(valor) FILTER (
                        WHERE vencimento >= :hoje AND vencimento <= :limite
                    ), 0) AS proximas_total
                FROM office_expenses
                WHERE deleted_at IS NULL
                  AND status = 'pendente'
                  AND vencimento IS NOT NULL
                """
            ),
            {"hoje": hoje, "limite": em_7_dias},
        )
    ).mappings().first()

    sem_comprovante = (
        await db.execute(
            text(
                """
                SELECT COUNT(*) AS qtd, COALESCE(SUM(fp.valor), 0) AS total
                FROM fee_payments fp
                JOIN fees f ON f.id = fp.fee_id
                WHERE f.deleted_at IS NULL
                  AND fp.comprovante_doc_id IS NULL
                  AND fp.data_pagamento >= :inicio
                """
            ),
            {"inicio": ha_30_dias},
        )
    ).mappings().first()

    percentuais_sem_base = (
        await db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM fees
                WHERE deleted_at IS NULL
                  AND valor IS NULL
                  AND percentual_exito IS NOT NULL
                  AND CAST(status AS text) IN ('pendente','atrasado')
                """
            )
        )
    ).scalar() or 0

    contratos = (
        await db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM office_contracts
                WHERE deleted_at IS NULL
                  AND status = 'vigente'
                  AND end_date IS NOT NULL
                  AND end_date >= :hoje
                  AND end_date <= :limite
                """
            ),
            {"hoje": hoje, "limite": hoje + timedelta(days=30)},
        )
    ).scalar() or 0

    itens = []
    if int(hon["qtd"] or 0):
        itens.append({
            "codigo": "honorarios_vencidos",
            "prioridade": "alta",
            "titulo": "Honorários vencidos",
            "qtd": int(hon["qtd"] or 0),
            "valor": _money(hon["total"]),
            "acao": {"tab": "honorarios", "status": "atrasado"},
        })
    if int(despesas["vencidas_qtd"] or 0):
        itens.append({
            "codigo": "despesas_vencidas",
            "prioridade": "alta",
            "titulo": "Despesas vencidas",
            "qtd": int(despesas["vencidas_qtd"] or 0),
            "valor": _money(despesas["vencidas_total"]),
            "acao": {"tab": "despesas", "status": "pendente"},
        })
    if int(despesas["proximas_qtd"] or 0):
        itens.append({
            "codigo": "despesas_proximas",
            "prioridade": "media",
            "titulo": "Despesas vencem nos próximos 7 dias",
            "qtd": int(despesas["proximas_qtd"] or 0),
            "valor": _money(despesas["proximas_total"]),
            "acao": {"tab": "despesas", "status": "pendente"},
        })
    if int(sem_comprovante["qtd"] or 0):
        itens.append({
            "codigo": "pagamentos_sem_comprovante",
            "prioridade": "baixa",
            "titulo": "Pagamentos sem comprovante nos últimos 30 dias",
            "qtd": int(sem_comprovante["qtd"] or 0),
            "valor": _money(sem_comprovante["total"]),
            "acao": {"tab": "honorarios"},
        })
    if int(percentuais_sem_base):
        itens.append({
            "codigo": "percentuais_sem_base",
            "prioridade": "media",
            "titulo": "Honorários percentuais sem base monetária",
            "qtd": int(percentuais_sem_base),
            "valor": None,
            "acao": {"tab": "honorarios"},
        })
    if int(contratos):
        itens.append({
            "codigo": "contratos_vencendo",
            "prioridade": "media",
            "titulo": "Contratos vencem nos próximos 30 dias",
            "qtd": int(contratos),
            "valor": None,
            "acao": {"tab": "contratos"},
        })

    ordem = {"alta": 0, "media": 1, "baixa": 2}
    itens.sort(key=lambda item: ordem[item["prioridade"]])
    return {"gerado_em": hoje.isoformat(), "total": len(itens), "itens": itens}


@router.get("/demonstrativo")
async def demonstrativo_gerencial(
    competencia: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Separa competência operacional de fluxo de caixa.

    Não é DRE fiscal/contábil. Receita por competência usa o mês de vencimento
    do fee (único marcador econômico hoje existente); caixa usa a data efetiva
    do FeePayment. Despesa por competência usa ``office_expenses.competencia``;
    saída de caixa usa ``pago_em``. Percentuais sem base monetária ficam fora dos
    totais em reais e são explicitamente contados.
    """
    _exigir_financeiro(cu)
    competencia = _competencia_atual(competencia)
    mes_ref = date.fromisoformat(f"{competencia}-01")

    rec = (
        await db.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(valor) FILTER (
                        WHERE valor IS NOT NULL AND status != 'cancelado'
                    ), 0) AS receitas_competencia,
                    COUNT(*) FILTER (
                        WHERE valor IS NULL AND percentual_exito IS NOT NULL
                          AND status != 'cancelado'
                    ) AS percentuais_sem_base
                FROM fees
                WHERE deleted_at IS NULL
                  AND date_trunc('month', data_vencimento)
                      = date_trunc('month', CAST(:mes AS date))
                """
            ),
            {"mes": mes_ref},
        )
    ).mappings().first()

    despesas_comp = (
        await db.execute(
            text(
                """
                SELECT COALESCE(SUM(valor), 0)
                FROM office_expenses
                WHERE deleted_at IS NULL
                  AND status != 'cancelado'
                  AND competencia = :comp
                """
            ),
            {"comp": competencia},
        )
    ).scalar()

    entradas_caixa = (
        await db.execute(
            text(
                """
                SELECT COALESCE(SUM(fp.valor), 0)
                FROM fee_payments fp
                JOIN fees f ON f.id = fp.fee_id
                WHERE f.deleted_at IS NULL
                  AND date_trunc('month', fp.data_pagamento)
                      = date_trunc('month', CAST(:mes AS date))
                """
            ),
            {"mes": mes_ref},
        )
    ).scalar()

    saidas_caixa = (
        await db.execute(
            text(
                """
                SELECT COALESCE(SUM(valor), 0)
                FROM office_expenses
                WHERE deleted_at IS NULL
                  AND status = 'pago'
                  AND pago_em IS NOT NULL
                  AND date_trunc('month', pago_em)
                      = date_trunc('month', CAST(:mes AS date))
                """
            ),
            {"mes": mes_ref},
        )
    ).scalar()

    receitas_comp = _money(rec["receitas_competencia"])
    despesas_comp = _money(despesas_comp)
    entradas_caixa = _money(entradas_caixa)
    saidas_caixa = _money(saidas_caixa)

    return {
        "competencia": competencia,
        "natureza": "gerencial_nao_contabil",
        "criterios": {
            "receita_competencia": "mês de data_vencimento do honorário",
            "despesa_competencia": "office_expenses.competencia",
            "entrada_caixa": "fee_payments.data_pagamento",
            "saida_caixa": "office_expenses.pago_em",
        },
        "competencia_operacional": {
            "receitas": receitas_comp,
            "despesas": despesas_comp,
            "resultado": _money(receitas_comp - despesas_comp),
            "percentuais_sem_base_monetaria": int(rec["percentuais_sem_base"] or 0),
        },
        "fluxo_caixa": {
            "entradas": entradas_caixa,
            "saidas": saidas_caixa,
            "saldo_periodo": _money(entradas_caixa - saidas_caixa),
        },
        "aviso": (
            "Demonstrativo gerencial do EJC. Não substitui escrituração, DRE ou "
            "validação contábil/fiscal pelo profissional responsável."
        ),
    }
