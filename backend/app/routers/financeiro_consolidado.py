"""Visão financeira consolidada — tela única.

GET /api/v1/financeiro/consolidado?competencia=YYYY-MM
GET /api/v1/financeiro/atencao
GET /api/v1/financeiro/demonstrativo?competencia=YYYY-MM
GET /api/v1/financeiro/fechamento-inteligente?competencia=YYYY-MM

Princípio operacional: caixa usa pagamentos/baixas efetivas; competência usa
vencimento contratual dos honorários e a competência declarada das despesas.
O demonstrativo e o pré-fechamento são GERENCIAIS e não substituem escrituração,
DRE contábil ou validação fiscal pelo profissional responsável.
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


def _classificar_fechamento(itens: list[dict]) -> tuple[str, int]:
    """Classifica o pré-fechamento sem persistir decisão de negócio.

    O score é deliberadamente simples e explicável: cada categoria bloqueante
    presente reduz 25 pontos e cada categoria de revisão reduz 7. A quantidade
    de linhas aparece no detalhe, mas não multiplica a penalidade para evitar
    que uma competência volumosa pareça estruturalmente pior só por ter mais
    lançamentos.
    """
    bloqueios = sum(1 for item in itens if item.get("severidade") == "bloqueio")
    revisoes = sum(1 for item in itens if item.get("severidade") == "revisao")
    score = max(0, 100 - (bloqueios * 25) - (revisoes * 7))
    if bloqueios:
        return "bloqueado", score
    if revisoes:
        return "revisao", score
    return "pronto", score


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

    # Competência das despesas: visão de obrigações do mês, independente da data
    # em que a baixa financeira aconteceu.
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

    # Fluxo de caixa: saída pertence ao mês real de `pago_em`, não à competência
    # original. Isso mantém o card "Caixa do período" reconciliável com extrato.
    saidas_caixa_mes = _money(
        (
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
    )

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
    despesas_pagas_competencia = desp["pago"]
    caixa = _money(recebido - saidas_caixa_mes)
    margem = (
        (caixa / recebido * 100).quantize(_Q1, ROUND_HALF_UP)
        if recebido
        else Decimal("0")
    )

    return {
        "competencia": competencia,
        "caixa_periodo": caixa,
        "margem_pct": margem,
        "fluxo_caixa": {
            "entradas": recebido,
            "saidas": saidas_caixa_mes,
            "saldo_periodo": caixa,
        },
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
            "pagas": despesas_pagas_competencia,
            "saidas_caixa_mes": saidas_caixa_mes,
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
    """Fila curta do que exige decisão financeira sem expor PII no resumo."""
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
    do fee; caixa usa a data efetiva do FeePayment. Despesa por competência usa
    ``office_expenses.competencia`` e saída de caixa usa ``pago_em``.
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


@router.get("/fechamento-inteligente")
async def fechamento_inteligente(
    competencia: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Pré-fechamento gerencial read-only da competência.

    Não grava estado de fechamento e não torna o período imutável. Essa parte
    depende de schema próprio e deve entrar somente na próxima migration linear,
    após a revisão 156 hoje reservada por outra frente. Aqui o objetivo é dar
    ao gestor um gate explicável e reproduzível antes do fechamento definitivo.
    """
    _exigir_financeiro(cu)
    competencia = _competencia_atual(competencia)
    mes_ref = date.fromisoformat(f"{competencia}-01")

    fee_integridade = (
        await db.execute(
            text(
                """
                WITH pagos AS (
                    SELECT fee_id, COALESCE(SUM(valor), 0) AS total_pago
                    FROM fee_payments
                    GROUP BY fee_id
                )
                SELECT
                    COUNT(*) FILTER (
                        WHERE f.valor IS NOT NULL
                          AND COALESCE(p.total_pago, 0) > f.valor
                    ) AS overpayment,
                    COUNT(*) FILTER (
                        WHERE CAST(f.status AS text) = 'pago'
                          AND f.valor IS NOT NULL
                          AND COALESCE(p.total_pago, 0) < f.valor
                    ) AS pago_com_saldo,
                    COUNT(*) FILTER (
                        WHERE f.valor IS NULL
                          AND f.percentual_exito IS NOT NULL
                          AND CAST(f.status AS text) IN ('pendente','atrasado')
                          AND date_trunc('month', f.data_vencimento)
                              = date_trunc('month', CAST(:mes AS date))
                    ) AS percentuais_sem_base,
                    COUNT(*) FILTER (
                        WHERE CAST(f.status AS text) IN ('pendente','atrasado')
                          AND f.valor IS NOT NULL
                          AND f.data_vencimento <=
                              (date_trunc('month', CAST(:mes AS date))
                               + INTERVAL '1 month - 1 day')::date
                          AND GREATEST(f.valor - COALESCE(p.total_pago, 0), 0) > 0
                    ) AS recebiveis_pendentes,
                    COALESCE(SUM(
                        GREATEST(f.valor - COALESCE(p.total_pago, 0), 0)
                    ) FILTER (
                        WHERE CAST(f.status AS text) IN ('pendente','atrasado')
                          AND f.valor IS NOT NULL
                          AND f.data_vencimento <=
                              (date_trunc('month', CAST(:mes AS date))
                               + INTERVAL '1 month - 1 day')::date
                    ), 0) AS recebiveis_pendentes_valor
                FROM fees f
                LEFT JOIN pagos p ON p.fee_id = f.id
                WHERE f.deleted_at IS NULL
                  AND CAST(f.status AS text) != 'cancelado'
                """
            ),
            {"mes": mes_ref},
        )
    ).mappings().first()

    desp_integridade = (
        await db.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE status = 'pago' AND pago_em IS NULL
                    ) AS pagas_sem_data,
                    COUNT(*) FILTER (
                        WHERE status = 'pendente'
                          AND vencimento IS NOT NULL
                          AND vencimento <=
                              (date_trunc('month', CAST(:mes AS date))
                               + INTERVAL '1 month - 1 day')::date
                    ) AS despesas_pendentes,
                    COALESCE(SUM(valor) FILTER (
                        WHERE status = 'pendente'
                          AND vencimento IS NOT NULL
                          AND vencimento <=
                              (date_trunc('month', CAST(:mes AS date))
                               + INTERVAL '1 month - 1 day')::date
                    ), 0) AS despesas_pendentes_valor
                FROM office_expenses
                WHERE deleted_at IS NULL
                  AND competencia = :comp
                  AND status != 'cancelado'
                """
            ),
            {"mes": mes_ref, "comp": competencia},
        )
    ).mappings().first()

    comprovantes = (
        await db.execute(
            text(
                """
                SELECT COUNT(*) AS qtd, COALESCE(SUM(fp.valor), 0) AS total
                FROM fee_payments fp
                JOIN fees f ON f.id = fp.fee_id
                WHERE f.deleted_at IS NULL
                  AND fp.comprovante_doc_id IS NULL
                  AND date_trunc('month', fp.data_pagamento)
                      = date_trunc('month', CAST(:mes AS date))
                """
            ),
            {"mes": mes_ref},
        )
    ).mappings().first()

    itens: list[dict] = []

    def adicionar(codigo: str, severidade: str, titulo: str, qtd, *, valor=None, acao=None):
        quantidade = int(qtd or 0)
        if not quantidade:
            return
        itens.append({
            "codigo": codigo,
            "severidade": severidade,
            "titulo": titulo,
            "qtd": quantidade,
            "valor": _money(valor) if valor is not None else None,
            "acao": acao,
        })

    adicionar(
        "overpayment",
        "bloqueio",
        "Honorários com recebimento acima do valor contratado",
        fee_integridade["overpayment"],
        acao={"tab": "honorarios"},
    )
    adicionar(
        "pago_com_saldo",
        "bloqueio",
        "Honorários marcados como pagos ainda possuem saldo",
        fee_integridade["pago_com_saldo"],
        acao={"tab": "honorarios"},
    )
    adicionar(
        "despesa_paga_sem_data",
        "bloqueio",
        "Despesas pagas sem data efetiva de pagamento",
        desp_integridade["pagas_sem_data"],
        acao={"tab": "despesas"},
    )
    adicionar(
        "percentual_sem_base",
        "bloqueio",
        "Honorários percentuais da competência ainda sem base monetária",
        fee_integridade["percentuais_sem_base"],
        acao={"tab": "honorarios"},
    )
    adicionar(
        "recebiveis_pendentes",
        "revisao",
        "Contas a receber permanecem abertas até o fim da competência",
        fee_integridade["recebiveis_pendentes"],
        valor=fee_integridade["recebiveis_pendentes_valor"],
        acao={"tab": "honorarios", "status": "pendente"},
    )
    adicionar(
        "despesas_pendentes",
        "revisao",
        "Despesas da competência permanecem pendentes",
        desp_integridade["despesas_pendentes"],
        valor=desp_integridade["despesas_pendentes_valor"],
        acao={"tab": "despesas", "status": "pendente"},
    )
    adicionar(
        "pagamentos_sem_comprovante",
        "revisao",
        "Recebimentos do mês estão sem comprovante documental",
        comprovantes["qtd"],
        valor=comprovantes["total"],
        acao={"tab": "honorarios"},
    )

    status, score = _classificar_fechamento(itens)
    snapshot = await demonstrativo_gerencial(competencia, db, cu)
    bloqueios = [item for item in itens if item["severidade"] == "bloqueio"]
    revisoes = [item for item in itens if item["severidade"] == "revisao"]

    return {
        "competencia": competencia,
        "modo": "pre_fechamento_read_only",
        "status": status,
        "score_integridade": score,
        "pode_fechar_persistente": False,
        "bloqueios": bloqueios,
        "revisoes": revisoes,
        "total_bloqueios": len(bloqueios),
        "total_revisoes": len(revisoes),
        "snapshot": snapshot,
        "dependencia_estrutural": (
            "O fechamento imutável depende de migration própria após a revisão "
            "Alembic 156 atualmente reservada por outra frente."
        ),
        "recomendacao": (
            "Corrija os bloqueios antes de fechar. Pendências de revisão podem "
            "permanecer abertas desde que sejam conscientemente conciliadas e "
            "documentadas no fechamento definitivo."
        ),
        "aviso": (
            "Pré-fechamento gerencial do EJC. Não congela lançamentos e não "
            "substitui conciliação bancária, escrituração ou validação contábil."
        ),
    }
