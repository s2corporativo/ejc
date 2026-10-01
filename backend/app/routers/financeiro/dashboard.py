"""Rotas internas do módulo Financeiro. URLs públicas preservadas."""
from .common import *  # noqa: F401,F403

router = APIRouter(prefix="/financeiro", tags=["Financeiro"])
@router.get("/consolidado", dependencies=[Depends(rate_limit("fin-consolidado", 60))])
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
            # SQL literal com bind params; a regra marca todo text(), sem olhar
            # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(
                f"""
                WITH {LEDGER_CTES},
                saldos AS (
                    SELECT
                        f.id,
                        CAST(f.tipo AS text) AS tipo,
                        f.descricao,
                        CAST(f.status AS text) AS status,
                        GREATEST(
                            COALESCE(f.valor, 0) - COALESCE(pe.total_pago, 0),
                            0
                        ) AS saldo
                    FROM fees f
                    LEFT JOIN pagamentos_efetivos pe ON pe.fee_id = f.id
                    WHERE f.deleted_at IS NULL
                ),
                pagamentos_mes AS (
                    SELECT
                        re.valor,
                        CAST(f.tipo AS text) AS tipo,
                        f.descricao
                    FROM recebimentos_efetivos re
                    JOIN fees f ON f.id = re.fee_id
                    WHERE f.deleted_at IS NULL
                      AND date_trunc('month', re.data_pagamento)
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


@router.get("/atencao", dependencies=[Depends(rate_limit("fin-atencao", 60))])
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
            # SQL literal com bind params; a regra marca todo text(), sem olhar
            # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(
                f"""
                WITH {LEDGER_CTES}
                SELECT COUNT(*) AS qtd,
                       COALESCE(SUM(GREATEST(f.valor - COALESCE(pe.total_pago, 0), 0)), 0) AS total
                FROM fees f
                LEFT JOIN pagamentos_efetivos pe ON pe.fee_id = f.id
                WHERE f.deleted_at IS NULL
                  AND f.valor IS NOT NULL
                  AND CAST(f.status AS text) IN ('pendente','atrasado')
                  AND f.data_vencimento < :hoje
                  AND GREATEST(f.valor - COALESCE(pe.total_pago, 0), 0) > 0
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
                  AND end_date >= CURRENT_DATE
                  AND end_date <= CURRENT_DATE
                        + make_interval(days => COALESCE(alert_days_before, 30))
                """
            )
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
            # Sem filtro de status: o card conta pendentes vencidos E atrasados.
            "acao": {"tab": "honorarios"},
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
            "titulo": "Contratos dentro da janela individual de alerta",
            "qtd": int(contratos),
            "valor": None,
            "acao": {"tab": "contratos"},
        })

    ordem = {"alta": 0, "media": 1, "baixa": 2}
    itens.sort(key=lambda item: ordem[item["prioridade"]])
    return {"gerado_em": hoje.isoformat(), "total": len(itens), "itens": itens}


@router.get("/demonstrativo", dependencies=[Depends(rate_limit("fin-demonstrativo", 30))])
async def demonstrativo_gerencial(
    competencia: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Separa competência operacional de fluxo de caixa."""
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
            # SQL literal com bind params; a regra marca todo text(), sem olhar
            # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(
                f"""
                WITH {LEDGER_CTES}
                SELECT COALESCE(SUM(re.valor), 0)
                FROM recebimentos_efetivos re
                JOIN fees f ON f.id = re.fee_id
                WHERE f.deleted_at IS NULL
                  AND date_trunc('month', re.data_pagamento)
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
            "entrada_caixa": "fee_payments.data_pagamento (ledger canônico)",
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



@router.get("/operacional", dependencies=[Depends(rate_limit("fin-operacional", 60))])
async def painel_operacional(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    hoje = date.today()
    limite = hoje + timedelta(days=30)
    # SQL composto apenas por CTE constante e bind params; sem entrada estrutural do usuário.
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    recebiveis=(await db.execute(text(f"""
        WITH {LEDGER_CTES}
        SELECT f.id,f.descricao,f.data_vencimento,
          GREATEST(COALESCE(f.valor,0)-COALESCE(pe.total_pago,0),0) AS saldo,
          f.client_id,f.case_id,COALESCE(cl.nome,cl.razao_social,'Cliente') AS cliente,
          c.titulo AS caso
        FROM fees f
        LEFT JOIN pagamentos_efetivos pe ON pe.fee_id=f.id
        LEFT JOIN clients cl ON cl.id=f.client_id AND cl.deleted_at IS NULL
        LEFT JOIN cases c ON c.id=f.case_id AND c.deleted_at IS NULL
        WHERE f.deleted_at IS NULL
          AND CAST(f.status AS text) IN ('pendente','atrasado')
          AND f.valor IS NOT NULL
          AND f.data_vencimento BETWEEN :hoje AND :limite
          AND GREATEST(COALESCE(f.valor,0)-COALESCE(pe.total_pago,0),0)>0
        ORDER BY f.data_vencimento,f.id LIMIT 8
    """),{"hoje":hoje,"limite":limite})).mappings().all()
    pagamentos=(await db.execute(text("""
        SELECT id,descricao,valor,vencimento,categoria
        FROM office_expenses
        WHERE deleted_at IS NULL AND status='pendente'
          AND vencimento BETWEEN :hoje AND :limite
        ORDER BY vencimento,id LIMIT 8
    """),{"hoje":hoje,"limite":limite})).mappings().all()
    # SQL composto apenas por CTE constante e bind params; sem entrada estrutural do usuário.
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    inad=(await db.execute(text(f"""
        WITH {LEDGER_CTES}
        SELECT COUNT(DISTINCT f.client_id) AS clientes,COUNT(*) AS titulos,
          COALESCE(SUM(GREATEST(COALESCE(f.valor,0)-COALESCE(pe.total_pago,0),0)),0) AS valor
        FROM fees f LEFT JOIN pagamentos_efetivos pe ON pe.fee_id=f.id
        WHERE f.deleted_at IS NULL
          AND CAST(f.status AS text) IN ('pendente','atrasado')
          AND f.valor IS NOT NULL AND f.data_vencimento < :hoje
          AND GREATEST(COALESCE(f.valor,0)-COALESCE(pe.total_pago,0),0)>0
    """),{"hoje":hoje})).mappings().first()
    # SQL composto apenas por CTE constante e bind params; sem entrada estrutural do usuário.
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    totais=(await db.execute(text(f"""
        WITH {LEDGER_CTES},
        entradas AS (
          SELECT COALESCE(SUM(GREATEST(COALESCE(f.valor,0)-COALESCE(pe.total_pago,0),0)),0) total
          FROM fees f LEFT JOIN pagamentos_efetivos pe ON pe.fee_id=f.id
          WHERE f.deleted_at IS NULL AND CAST(f.status AS text) IN ('pendente','atrasado')
            AND f.valor IS NOT NULL AND f.data_vencimento BETWEEN :hoje AND :limite
        ),
        saidas AS (
          SELECT COALESCE(SUM(valor),0) total FROM office_expenses
          WHERE deleted_at IS NULL AND status='pendente' AND vencimento BETWEEN :hoje AND :limite
        )
        SELECT (SELECT total FROM entradas) entradas,(SELECT total FROM saidas) saidas
    """),{"hoje":hoje,"limite":limite})).mappings().first()
    # SQL composto apenas por CTE constante e bind params; sem entrada estrutural do usuário.
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    mov=(await db.execute(text(f"""
        WITH {LEDGER_CTES}, mov AS (
          SELECT 'entrada'::text natureza,re.data_pagamento data,f.descricao,re.valor,
                 f.id referencia_id,f.client_id,f.case_id,
                 COALESCE(cl.nome,cl.razao_social,'Cliente') cliente,c.titulo caso
          FROM recebimentos_efetivos re JOIN fees f ON f.id=re.fee_id
          LEFT JOIN clients cl ON cl.id=f.client_id AND cl.deleted_at IS NULL
          LEFT JOIN cases c ON c.id=f.case_id AND c.deleted_at IS NULL
          WHERE f.deleted_at IS NULL
          UNION ALL
          SELECT 'saida',oe.pago_em,oe.descricao,oe.valor,oe.id,NULL,NULL,NULL,NULL
          FROM office_expenses oe
          WHERE oe.deleted_at IS NULL AND oe.status='pago' AND oe.pago_em IS NOT NULL
        )
        SELECT * FROM mov WHERE data IS NOT NULL ORDER BY data DESC,referencia_id DESC LIMIT 12
    """))).mappings().all()
    e=_money(totais["entradas"]); sai=_money(totais["saidas"])
    return {
      "proximos_30_dias":{"entradas":e,"saidas":sai,"saldo":_money(e-sai)},
      "inadimplencia":{"clientes":int(inad["clientes"] or 0),"titulos":int(inad["titulos"] or 0),"valor":_money(inad["valor"])},
      "proximos_recebimentos":[{"id":r["id"],"descricao":r["descricao"],"vencimento":r["data_vencimento"],"valor":_money(r["saldo"]),"client_id":r["client_id"],"case_id":r["case_id"],"cliente":r["cliente"],"caso":r["caso"]} for r in recebiveis],
      "proximos_pagamentos":[{"id":r["id"],"descricao":r["descricao"],"vencimento":r["vencimento"],"valor":_money(r["valor"]),"categoria":r["categoria"]} for r in pagamentos],
      "movimentacoes_recentes":[{"natureza":r["natureza"],"data":r["data"],"descricao":r["descricao"],"valor":_money(r["valor"]),"referencia_id":r["referencia_id"],"client_id":r["client_id"],"case_id":r["case_id"],"cliente":r["cliente"],"caso":r["caso"]} for r in mov],
    }




