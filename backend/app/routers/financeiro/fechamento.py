"""Rotas internas do módulo Financeiro. URLs públicas preservadas."""
from .common import *  # noqa: F401,F403

router = APIRouter(prefix="/financeiro", tags=["Financeiro"])
from .dashboard import demonstrativo_gerencial

@router.get("/fechamento-inteligente", dependencies=[Depends(rate_limit("fin-fechamento-inteligente", 10))])
async def fechamento_inteligente(
    competencia: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Pré-fechamento gerencial read-only da competência."""
    _exigir_financeiro(cu)
    competencia = _competencia_atual(competencia)
    mes_ref = date.fromisoformat(f"{competencia}-01")

    fee_integridade = (
        await db.execute(
            # SQL literal com bind params; a regra marca todo text(), sem olhar
            # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(
                f"""
                WITH {LEDGER_CTES}
                SELECT
                    COUNT(*) FILTER (
                        WHERE f.valor IS NOT NULL
                          AND COALESCE(pe.total_pago, 0) > f.valor
                    ) AS overpayment,
                    COUNT(*) FILTER (
                        WHERE CAST(f.status AS text) = 'pago'
                          AND f.valor IS NOT NULL
                          AND COALESCE(pe.total_pago, 0) < f.valor
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
                          AND GREATEST(f.valor - COALESCE(pe.total_pago, 0), 0) > 0
                    ) AS recebiveis_pendentes,
                    COALESCE(SUM(
                        GREATEST(f.valor - COALESCE(pe.total_pago, 0), 0)
                    ) FILTER (
                        WHERE CAST(f.status AS text) IN ('pendente','atrasado')
                          AND f.valor IS NOT NULL
                          AND f.data_vencimento <=
                              (date_trunc('month', CAST(:mes AS date))
                               + INTERVAL '1 month - 1 day')::date
                    ), 0) AS recebiveis_pendentes_valor,
                    COUNT(*) FILTER (
                        WHERE pe.legado_sem_subledger = TRUE
                          AND date_trunc('month', f.data_pagamento)
                              = date_trunc('month', CAST(:mes AS date))
                    ) AS legados_sem_subledger
                FROM fees f
                LEFT JOIN pagamentos_efetivos pe ON pe.fee_id = f.id
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
        acao={"tab": "honorarios"},
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
    adicionar(
        "legados_sem_subledger",
        "revisao",
        "Quitações históricas ainda não foram normalizadas no subledger",
        fee_integridade["legados_sem_subledger"],
        acao={"tab": "honorarios", "status": "pago"},
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
        "pode_fechar_persistente": len(bloqueios) == 0,
        "bloqueios": bloqueios,
        "revisoes": revisoes,
        "total_bloqueios": len(bloqueios),
        "total_revisoes": len(revisoes),
        "snapshot": snapshot,
        "dependencia_estrutural": None,
        "recomendacao": (
            "Corrija os bloqueios antes de fechar. Pendências de revisão podem "
            "permanecer abertas desde que sejam conscientemente conciliadas e "
            "documentadas no fechamento definitivo."
        ),
        "aviso": (
            "Pré-fechamento gerencial do EJC. Quando persistido pelo endpoint "
            "de fechamento, o mês fica bloqueado para mutações de caixa. "
            "Não substitui escrituração ou validação contábil."
        ),
    }
