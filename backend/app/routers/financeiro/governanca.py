"""Rotas internas do módulo Financeiro. URLs públicas preservadas."""
from fastapi import Depends
from app.core.security import get_current_user
from app.core.database import get_db
import json
from fastapi import Query
from uuid import uuid4

from .common import (
    APIRouter,
    AsyncSession,
    datetime,
    Decimal,
    FinanceCloseIn,
    FinancePolicyPatch,
    HTTPException,
    Optional,
    ReconcileConfirmIn,
    text,
    timezone,
    User,
    _exigir_financeiro,
    _exigir_gestor_regras,
    _money,
    _month_bounds,
)

router = APIRouter(prefix="/financeiro", tags=["Financeiro"])
from .fechamento import fechamento_inteligente

@router.get("/politica")
async def politica_financeira(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    row = (
        await db.execute(
            text(
                """
                SELECT id,double_approval_threshold,updated_by,created_at,updated_at
                FROM finance_policy_settings
                WHERE id='default'
                """
            )
        )
    ).mappings().first()
    return dict(row) if row else {"id": "default", "double_approval_threshold": 10000}


@router.patch("/politica")
async def atualizar_politica_financeira(
    body: FinancePolicyPatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_gestor_regras(cu)
    antes = (
        await db.execute(
            text(
                """
                SELECT double_approval_threshold
                FROM finance_policy_settings
                WHERE id='default'
                FOR UPDATE
                """
            )
        )
    ).scalar_one_or_none()
    await db.execute(
        text(
            """
            INSERT INTO finance_policy_settings
                (id,double_approval_threshold,updated_by,created_at,updated_at)
            VALUES
                ('default',:limite,:uid,NOW(),NOW())
            ON CONFLICT (id) DO UPDATE
            SET double_approval_threshold=EXCLUDED.double_approval_threshold,
                updated_by=EXCLUDED.updated_by,
                updated_at=NOW()
            """
        ),
        {"limite": body.double_approval_threshold, "uid": cu.id},
    )
    from app.models.audit_log import criar_audit_log
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "UPDATE",
        "finance_policy_settings",
        "default",
        detalhes="Alçada financeira atualizada.",
        dados_antes={"double_approval_threshold": str(antes or 0)},
        dados_depois={
            "double_approval_threshold": str(body.double_approval_threshold)
        },
    )
    await db.commit()
    return {
        "id": "default",
        "double_approval_threshold": body.double_approval_threshold,
    }


@router.get("/aprovacoes")
async def listar_aprovacoes_financeiras(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    rows = (
        await db.execute(
            text(
                """
                SELECT a.*, req.full_name AS solicitado_por_nome,
                       apr.full_name AS aprovado_por_nome
                FROM finance_payment_approvals a
                LEFT JOIN users req ON req.id=a.requested_by
                LEFT JOIN users apr ON apr.id=a.approved_by
                WHERE (CAST(:status AS text) IS NULL OR a.status=:status)
                ORDER BY a.requested_at DESC
                LIMIT 300
                """
            ),
            {"status": status},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


@router.post("/aprovacoes/{approval_id}/aprovar")
async def aprovar_pagamento_financeiro(
    approval_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_gestor_regras(cu)
    from app.models.audit_log import criar_audit_log
    from app.services.finance_governance import aprovar_solicitacao

    resultado = await aprovar_solicitacao(db, approval_id, cu)
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "APPROVE",
        "finance_payment_approvals",
        approval_id,
        detalhes="Segunda aprovação financeira concedida.",
        dados_depois={
            "entity_type": resultado["entity_type"],
            "entity_id": resultado["entity_id"],
            "amount": str(resultado["amount"]),
        },
    )
    await db.commit()
    return resultado


@router.get("/rentabilidade")
async def rentabilidade_financeira(
    competencia: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    inicio, fim = _month_bounds(competencia)
    rows = (
        await db.execute(
            text(
                """
                WITH caixa AS (
                    SELECT f.case_id, SUM(fp.valor) AS recebido
                    FROM fee_payments fp
                    JOIN fees f ON f.id=fp.fee_id
                    WHERE f.deleted_at IS NULL
                      AND f.case_id IS NOT NULL
                      AND fp.data_pagamento >= :inicio
                      AND fp.data_pagamento < :fim
                    GROUP BY f.case_id
                ),
                estornos AS (
                    SELECT f.case_id, SUM(fe.valor) AS valor
                    FROM fee_estornos fe
                    JOIN fees f ON f.id=fe.fee_id
                    WHERE f.deleted_at IS NULL
                      AND f.case_id IS NOT NULL
                      AND fe.data_estorno >= :inicio
                      AND fe.data_estorno < :fim
                    GROUP BY f.case_id
                ),
                despesas AS (
                    SELECT case_id, SUM(valor) AS valor
                    FROM (
                        SELECT case_id, valor
                        FROM centro_custos
                        WHERE deleted_at IS NULL
                          AND CAST(tipo AS text)='despesa'
                          AND pago=TRUE
                          AND COALESCE(data_pagamento,data_lancamento) >= :inicio
                          AND COALESCE(data_pagamento,data_lancamento) < :fim
                        UNION ALL
                        -- Despesa processual reembolsável (case_despesas) é saída de
                        -- caixa do escritório na data do adiantamento; o reembolso do
                        -- cliente entra como receita (fee custas_despesas). Sem esta
                        -- parcela o reembolso aparecia como lucro (plano ERP, E2).
                        SELECT case_id, valor
                        FROM case_despesas
                        WHERE deleted_at IS NULL
                          AND data >= :inicio AND data < :fim
                    ) d
                    GROUP BY case_id
                ),
                comissoes AS (
                    SELECT a.case_id, SUM(a.valor_advogado) AS valor
                    FROM case_receipt_allocations a
                    JOIN fee_payments fp ON fp.id=a.fee_payment_id
                    WHERE fp.data_pagamento >= :inicio
                      AND fp.data_pagamento < :fim
                    GROUP BY a.case_id
                ),
                ajustes AS (
                    SELECT a.case_id, SUM(ca.valor_advogado) AS valor
                    FROM commission_adjustments ca
                    JOIN case_receipt_allocations a ON a.id=ca.allocation_id
                    WHERE ca.created_at >= :inicio
                      AND ca.created_at < :fim
                    GROUP BY a.case_id
                )
                SELECT
                    c.id AS case_id,
                    c.client_id,
                    c.numero_interno,
                    c.titulo AS caso,
                    COALESCE(cl.nome,cl.razao_social,'Cliente') AS cliente,
                    COALESCE(cx.recebido,0)-COALESCE(es.valor,0) AS recebido,
                    COALESCE(dp.valor,0) AS despesas,
                    COALESCE(cm.valor,0)+COALESCE(aj.valor,0) AS comissoes,
                    COALESCE(cx.recebido,0)-COALESCE(es.valor,0)
                      -COALESCE(dp.valor,0)
                      -COALESCE(cm.valor,0)-COALESCE(aj.valor,0) AS resultado
                FROM cases c
                LEFT JOIN clients cl ON cl.id=c.client_id AND cl.deleted_at IS NULL
                LEFT JOIN caixa cx ON cx.case_id=c.id
                LEFT JOIN estornos es ON es.case_id=c.id
                LEFT JOIN despesas dp ON dp.case_id=c.id
                LEFT JOIN comissoes cm ON cm.case_id=c.id
                LEFT JOIN ajustes aj ON aj.case_id=c.id
                WHERE c.deleted_at IS NULL
                  AND (
                    COALESCE(cx.recebido,0)<>0
                    OR COALESCE(es.valor,0)<>0
                    OR COALESCE(dp.valor,0)<>0
                    OR COALESCE(cm.valor,0)<>0
                    OR COALESCE(aj.valor,0)<>0
                  )
                ORDER BY resultado DESC,c.numero_interno
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).mappings().all()
    casos = [dict(r) for r in rows]
    clientes: dict[str, dict] = {}
    for row in casos:
        key = row["client_id"] or "sem-cliente"
        item = clientes.setdefault(
            key,
            {
                "client_id": row["client_id"],
                "cliente": row["cliente"],
                "recebido": Decimal("0"),
                "despesas": Decimal("0"),
                "comissoes": Decimal("0"),
                "resultado": Decimal("0"),
                "casos": 0,
            },
        )
        for campo in ("recebido", "despesas", "comissoes", "resultado"):
            item[campo] += Decimal(str(row[campo] or 0))
        item["casos"] += 1
    clientes_out = [
        {
            **item,
            "recebido": _money(item["recebido"]),
            "despesas": _money(item["despesas"]),
            "comissoes": _money(item["comissoes"]),
            "resultado": _money(item["resultado"]),
        }
        for item in sorted(
            clientes.values(),
            key=lambda x: x["resultado"],
            reverse=True,
        )
    ]
    total_recebido = _money(
        sum((Decimal(str(r["recebido"] or 0)) for r in casos), Decimal("0"))
    )
    total_despesas = _money(
        sum((Decimal(str(r["despesas"] or 0)) for r in casos), Decimal("0"))
    )
    total_comissoes = _money(
        sum((Decimal(str(r["comissoes"] or 0)) for r in casos), Decimal("0"))
    )
    resultado_casos = _money(
        sum((Decimal(str(r["resultado"] or 0)) for r in casos), Decimal("0"))
    )
    despesas_escritorio = _money(
        (
            await db.execute(
                text(
                    """
                    SELECT COALESCE(SUM(valor),0)
                    FROM office_expenses
                    WHERE deleted_at IS NULL
                      AND status='pago'
                      AND pago_em >= :inicio
                      AND pago_em < :fim
                    """
                ),
                {"inicio": inicio, "fim": fim},
            )
        ).scalar()
    )
    total_resultado = _money(resultado_casos - despesas_escritorio)
    return {
        "competencia": competencia,
        "resumo": {
            "recebido": total_recebido,
            "despesas_casos": total_despesas,
            "comissoes": total_comissoes,
            "resultado_casos": resultado_casos,
            "despesas_escritorio": despesas_escritorio,
            "resultado_escritorio": total_resultado,
        },
        "casos": casos,
        "clientes": clientes_out,
    }


@router.get("/distribuicao-disponivel")
async def distribuicao_disponivel(
    competencia: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    from app.services.finance_governance import resultado_disponivel_distribuicao

    return await resultado_disponivel_distribuicao(db, competencia)


@router.get("/fechamentos/{competencia}")
async def obter_fechamento_financeiro(
    competencia: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    if not __import__("re").fullmatch(r"\d{4}-(0[1-9]|1[0-2])", competencia):
        raise HTTPException(422, "competencia inválida: use AAAA-MM")
    row = (
        await db.execute(
            text(
                """
                SELECT id,competencia,snapshot_json,closed_by,closed_at,created_at
                FROM finance_month_closings
                WHERE competencia=:competencia
                """
            ),
            {"competencia": competencia},
        )
    ).mappings().first()
    return dict(row) if row else {"competencia": competencia, "fechado": False}


@router.get("/baseline-referencia")
async def obter_baseline_referencia(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    row = (
        await db.execute(
            text(
                """
                SELECT id,competencia,snapshot_json,closed_by,closed_at,created_at
                FROM finance_month_closings
                WHERE COALESCE(
                    (snapshot_json->'reference_baseline'->>'is_baseline')::boolean,
                    FALSE
                ) = TRUE
                ORDER BY closed_at
                LIMIT 1
                """
            )
        )
    ).mappings().first()
    if not row:
        return {
            "disponivel": False,
            "motivo": "Nenhum fechamento íntegro sem revisões foi concluído ainda.",
        }
    return {"disponivel": True, **dict(row)}


@router.post("/fechamentos", status_code=201)
async def fechar_competencia_financeira(
    body: FinanceCloseIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_gestor_regras(cu)
    from app.services.finance_governance import (
        exigir_lock_financeiro,
        construir_snapshot_referencia,
    )
    await exigir_lock_financeiro(db, "finance_close", body.competencia)
    existente = (
        await db.execute(
            text(
                "SELECT id FROM finance_month_closings WHERE competencia=:c"
            ),
            {"c": body.competencia},
        )
    ).scalar_one_or_none()
    if existente:
        raise HTTPException(409, "Competência financeira já está fechada")

    pre = await fechamento_inteligente(body.competencia, db, cu)
    if pre.get("total_bloqueios", 0) > 0:
        raise HTTPException(
            409,
            detail={
                "message": "Fechamento bloqueado por inconsistências financeiras",
                "bloqueios": pre.get("bloqueios", []),
            },
        )
    rent = await rentabilidade_financeira(body.competencia, db, cu)
    reference_baseline = await construir_snapshot_referencia(
        db,
        body.competencia,
        pre_fechamento=pre,
        rentabilidade=rent,
    )
    snapshot = {
        "pre_fechamento": pre,
        "rentabilidade": rent,
        "demonstrativo": pre.get("snapshot"),
        "reference_baseline": reference_baseline,
    }
    cid = str(uuid4())
    agora = datetime.now(timezone.utc)
    await db.execute(
        text(
            """
            INSERT INTO finance_month_closings
                (id,competencia,snapshot_json,closed_by,closed_at,created_at)
            VALUES
                (:id,:competencia,CAST(:snapshot AS jsonb),:closed_by,:closed_at,NOW())
            """
        ),
        {
            "id": cid,
            "competencia": body.competencia,
            "snapshot": json.dumps(snapshot, default=str, ensure_ascii=False),
            "closed_by": cu.id,
            "closed_at": agora,
        },
    )
    from app.models.audit_log import criar_audit_log
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "CLOSE",
        "finance_month_closings",
        cid,
        detalhes=f"Competência financeira {body.competencia} fechada.",
        dados_depois={
            "competencia": body.competencia,
            "baseline_referencia": reference_baseline["is_baseline"],
            "baseline_sha256": reference_baseline["sha256"],
        },
    )
    await db.commit()
    return {
        "id": cid,
        "competencia": body.competencia,
        "closed_at": agora,
        "snapshot": snapshot,
    }


@router.get("/excecoes")
async def excecoes_financeiras(
    competencia: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    inicio, fim = _month_bounds(competencia)
    itens: list[dict] = []

    async def registros(sql: str, params: dict, *, tab: str, id_col: str = "id"):
        rows = (await db.execute(text(sql), params)).mappings().all()
        return [
            {
                "id": str(r[id_col]),
                "label": str(r.get("label") or r[id_col]),
                "value": r.get("value"),
                "action": {"tab": tab, "focus": str(r[id_col])},
            }
            for r in rows
        ]

    duplicados = (
        await db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT client_id,COALESCE(case_id,''),descricao,valor,data_vencimento
                    FROM fees
                    WHERE deleted_at IS NULL
                      AND CAST(status AS text) <> 'cancelado'
                    GROUP BY client_id,COALESCE(case_id,''),descricao,valor,data_vencimento
                    HAVING COUNT(*) > 1
                ) x
                """
            )
        )
    ).scalar() or 0
    if duplicados:
        itens.append(
            {
                "codigo": "possiveis_duplicidades",
                "titulo": "Possíveis honorários duplicados",
                "qtd": int(duplicados),
                "severidade": "revisao",
                "acao": {"tab": "honorarios"},
                "registros": await registros(
                    """
                    SELECT MIN(id) AS id, descricao AS label, COUNT(*) AS value
                    FROM fees
                    WHERE deleted_at IS NULL AND CAST(status AS text) <> 'cancelado'
                    GROUP BY client_id,COALESCE(case_id,''),descricao,valor,data_vencimento
                    HAVING COUNT(*) > 1
                    ORDER BY COUNT(*) DESC
                    LIMIT 20
                    """,
                    {},
                    tab="honorarios",
                ),
            }
        )

    sem_caso = (
        await db.execute(
            text(
                """
                SELECT COUNT(*),COALESCE(SUM(fp.valor),0)
                FROM fee_payments fp
                JOIN fees f ON f.id=fp.fee_id
                WHERE f.deleted_at IS NULL
                  AND f.case_id IS NULL
                  AND fp.data_pagamento >= :inicio
                  AND fp.data_pagamento < :fim
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).first()
    if sem_caso and int(sem_caso[0] or 0):
        itens.append(
            {
                "codigo": "recebimentos_sem_caso",
                "titulo": "Recebimentos sem caso vinculado",
                "qtd": int(sem_caso[0] or 0),
                "valor": _money(sem_caso[1]),
                "severidade": "revisao",
                "acao": {"tab": "honorarios"},
                "registros": await registros(
                    """
                    SELECT f.id, f.descricao AS label, fp.valor AS value
                    FROM fee_payments fp JOIN fees f ON f.id=fp.fee_id
                    WHERE f.deleted_at IS NULL AND f.case_id IS NULL
                      AND fp.data_pagamento >= :inicio AND fp.data_pagamento < :fim
                    ORDER BY fp.data_pagamento DESC LIMIT 20
                    """,
                    {"inicio": inicio, "fim": fim},
                    tab="honorarios",
                ),
            }
        )

    sem_comprovante = (
        await db.execute(
            text(
                """
                SELECT COUNT(*),COALESCE(SUM(partner_share),0)
                FROM partner_withdrawals
                WHERE deleted_at IS NULL
                  AND status='pago'
                  AND paid_at >= :inicio
                  AND paid_at < :fim
                  AND comprovante_doc_id IS NULL
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).first()
    if sem_comprovante and int(sem_comprovante[0] or 0):
        itens.append(
            {
                "codigo": "comissoes_sem_comprovante",
                "titulo": "Comissões pagas sem comprovante",
                "qtd": int(sem_comprovante[0] or 0),
                "valor": _money(sem_comprovante[1]),
                "severidade": "revisao",
                "acao": {"tab": "comissoes"},
                "registros": await registros(
                    """
                    SELECT id,
                           COALESCE(description,'Comissão/retirada') AS label,
                           partner_share AS value
                    FROM partner_withdrawals
                    WHERE deleted_at IS NULL AND status='pago'
                      AND paid_at >= :inicio AND paid_at < :fim
                      AND comprovante_doc_id IS NULL
                    ORDER BY paid_at DESC LIMIT 20
                    """,
                    {"inicio": inicio, "fim": fim},
                    tab="comissoes",
                ),
            }
        )

    sem_responsavel = (
        await db.execute(
            text(
                """
                SELECT COUNT(*),COALESCE(SUM(fp.valor),0)
                FROM fee_payments fp
                JOIN fees f ON f.id=fp.fee_id
                JOIN cases c ON c.id=f.case_id AND c.deleted_at IS NULL
                LEFT JOIN case_receipt_allocations a ON a.fee_payment_id=fp.id
                WHERE f.deleted_at IS NULL
                  AND c.advogado_responsavel_id IS NULL
                  AND a.id IS NULL
                  AND fp.data_pagamento >= :inicio
                  AND fp.data_pagamento < :fim
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).first()
    if sem_responsavel and int(sem_responsavel[0] or 0):
        itens.append(
            {
                "codigo": "comissoes_sem_responsavel",
                "titulo": "Recebimentos sem responsável para comissão",
                "qtd": int(sem_responsavel[0] or 0),
                "valor": _money(sem_responsavel[1]),
                "severidade": "bloqueio",
                "acao": {"tab": "honorarios"},
                "registros": await registros(
                    """
                    SELECT f.id, f.descricao AS label, fp.valor AS value
                    FROM fee_payments fp
                    JOIN fees f ON f.id=fp.fee_id
                    JOIN cases c ON c.id=f.case_id AND c.deleted_at IS NULL
                    LEFT JOIN case_receipt_allocations a ON a.fee_payment_id=fp.id
                    WHERE f.deleted_at IS NULL
                      AND c.advogado_responsavel_id IS NULL
                      AND a.id IS NULL
                      AND fp.data_pagamento >= :inicio AND fp.data_pagamento < :fim
                    ORDER BY fp.data_pagamento DESC LIMIT 20
                    """,
                    {"inicio": inicio, "fim": fim},
                    tab="honorarios",
                ),
            }
        )

    recon_pendente = (
        await db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM bank_transactions bt
                JOIN bank_analyses ba ON ba.id=bt.analysis_id
                WHERE ba.deleted_at IS NULL
                  AND bt.data >= :inicio
                  AND bt.data < :fim
                  AND NOT EXISTS (
                    SELECT 1 FROM finance_reconciliation_matches rm
                    WHERE rm.bank_transaction_id=bt.id
                      AND rm.status='confirmado'
                  )
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).scalar() or 0
    if recon_pendente:
        itens.append(
            {
                "codigo": "extrato_nao_conciliado",
                "titulo": "Movimentos bancários ainda não conciliados",
                "qtd": int(recon_pendente),
                "severidade": "revisao",
            }
        )

    rent = await rentabilidade_financeira(competencia, db, cu)
    if Decimal(str(rent["resumo"]["resultado_escritorio"])) < 0:
        itens.append(
            {
                "codigo": "resultado_negativo",
                "titulo": "Resultado líquido do escritório negativo",
                "qtd": 1,
                "valor": rent["resumo"]["resultado_escritorio"],
                "severidade": "alta",
            }
        )

    return {
        "competencia": competencia,
        "itens": itens,
        "total": len(itens),
        "bloqueios": sum(1 for i in itens if i["severidade"] == "bloqueio"),
    }


@router.get("/conciliacao/{analysis_id}")
async def sugestoes_conciliacao_bancaria(
    analysis_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    analise = (
        await db.execute(
            text(
                """
                SELECT id,arquivo_nome,banco,periodo_inicio,periodo_fim
                FROM bank_analyses
                WHERE id=:id AND deleted_at IS NULL
                """
            ),
            {"id": analysis_id},
        )
    ).mappings().first()
    if not analise:
        raise HTTPException(404, "Extrato bancário não encontrado")

    candidatos = (
        await db.execute(
            text(
                """
                WITH candidatos AS (
                    SELECT fp.id target_id,'fee_payment'::text target_type,
                           fp.data_pagamento AS data,fp.valor,
                           ('Recebimento · ' || f.descricao) AS label,
                           'credito'::text AS tipo
                    FROM fee_payments fp
                    JOIN fees f ON f.id=fp.fee_id
                    WHERE f.deleted_at IS NULL
                    UNION ALL
                    SELECT oe.id,'office_expense',oe.pago_em,oe.valor,
                           ('Despesa · ' || oe.descricao),'debito'
                    FROM office_expenses oe
                    WHERE oe.deleted_at IS NULL
                      AND oe.status='pago'
                      AND oe.pago_em IS NOT NULL
                    UNION ALL
                    SELECT b.id,'commission_batch',CAST(b.paid_at AS date),b.total_pago,
                           ('Comissões · ' || b.competencia),'debito'
                    FROM commission_payment_batches b
                )
                SELECT
                    bt.id AS bank_transaction_id,
                    bt.data AS bank_date,
                    bt.descricao AS bank_description,
                    bt.valor AS bank_value,
                    bt.tipo AS bank_type,
                    c.target_id,c.target_type,c.data AS target_date,
                    c.valor AS target_value,c.label,
                    CASE
                      WHEN bt.data=c.data THEN 1.0000
                      WHEN ABS(bt.data-c.data)=1 THEN 0.9500
                      ELSE 0.9000
                    END AS confidence
                FROM bank_transactions bt
                JOIN candidatos c
                  ON c.tipo=bt.tipo
                 AND ABS(c.valor-bt.valor) <= 0.01
                 AND c.data BETWEEN bt.data-3 AND bt.data+3
                WHERE bt.analysis_id=:analysis_id
                ORDER BY bt.data,confidence DESC,c.target_type
                """
            ),
            {"analysis_id": analysis_id},
        )
    ).mappings().all()

    for row in candidatos:
        await db.execute(
            text(
                """
                INSERT INTO finance_reconciliation_matches
                    (id,bank_transaction_id,target_type,target_id,confidence,
                     status,reason,created_by,created_at)
                VALUES
                    (:id,:bank_tx,:target_type,:target_id,:confidence,
                     'sugerido',:reason,:created_by,NOW())
                ON CONFLICT (bank_transaction_id,target_type,target_id)
                DO UPDATE SET
                    confidence=EXCLUDED.confidence,
                    reason=EXCLUDED.reason
                WHERE finance_reconciliation_matches.status='sugerido'
                """
            ),
            {
                "id": str(uuid4()),
                "bank_tx": row["bank_transaction_id"],
                "target_type": row["target_type"],
                "target_id": row["target_id"],
                "confidence": row["confidence"],
                "reason": "Mesmo valor e data em janela de até 3 dias.",
                "created_by": cu.id,
            },
        )
    await db.commit()

    rows = (
        await db.execute(
            text(
                """
                WITH candidatos AS (
                    SELECT fp.id target_id,'fee_payment'::text target_type,
                           fp.data_pagamento AS data,fp.valor,
                           ('Recebimento · ' || f.descricao) AS label
                    FROM fee_payments fp
                    JOIN fees f ON f.id=fp.fee_id
                    WHERE f.deleted_at IS NULL
                    UNION ALL
                    SELECT oe.id,'office_expense',oe.pago_em,oe.valor,
                           ('Despesa · ' || oe.descricao)
                    FROM office_expenses oe
                    WHERE oe.deleted_at IS NULL
                    UNION ALL
                    SELECT b.id,'commission_batch',CAST(b.paid_at AS date),b.total_pago,
                           ('Comissões · ' || b.competencia)
                    FROM commission_payment_batches b
                )
                SELECT rm.*,bt.data AS bank_date,bt.descricao AS bank_description,
                       bt.valor AS bank_value,bt.tipo AS bank_type,
                       c.data AS target_date,c.valor AS target_value,c.label
                FROM finance_reconciliation_matches rm
                JOIN bank_transactions bt ON bt.id=rm.bank_transaction_id
                JOIN candidatos c
                  ON c.target_id=rm.target_id AND c.target_type=rm.target_type
                WHERE bt.analysis_id=:analysis_id
                ORDER BY bt.data,rm.status='confirmado' DESC,rm.confidence DESC
                """
            ),
            {"analysis_id": analysis_id},
        )
    ).mappings().all()

    total_txs = (
        await db.execute(
            text(
                "SELECT COUNT(*) FROM bank_transactions WHERE analysis_id=:id"
            ),
            {"id": analysis_id},
        )
    ).scalar() or 0
    confirmados = len(
        {r["bank_transaction_id"] for r in rows if r["status"] == "confirmado"}
    )
    return {
        "analise": dict(analise),
        "total_transacoes": int(total_txs),
        "confirmados": confirmados,
        "pendentes": max(int(total_txs) - confirmados, 0),
        "sugestoes": [dict(r) for r in rows],
    }


@router.post("/conciliacao/confirmar")
async def confirmar_conciliacao_bancaria(
    body: ReconcileConfirmIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    row = (
        await db.execute(
            text(
                """
                SELECT id,status
                FROM finance_reconciliation_matches
                WHERE bank_transaction_id=:bank_tx
                  AND target_type=:target_type
                  AND target_id=:target_id
                FOR UPDATE
                """
            ),
            {
                "bank_tx": body.bank_transaction_id,
                "target_type": body.target_type,
                "target_id": body.target_id,
            },
        )
    ).mappings().first()
    if not row:
        raise HTTPException(404, "Sugestão de conciliação não encontrada")
    await db.execute(
        text(
            """
            UPDATE finance_reconciliation_matches
            SET status='rejeitado'
            WHERE bank_transaction_id=:bank_tx
              AND status='sugerido'
            """
        ),
        {"bank_tx": body.bank_transaction_id},
    )
    await db.execute(
        text(
            """
            UPDATE finance_reconciliation_matches
            SET status='confirmado',confirmed_by=:uid,confirmed_at=NOW()
            WHERE id=:id
            """
        ),
        {"uid": cu.id, "id": row["id"]},
    )
    from app.models.audit_log import criar_audit_log
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "RECONCILE",
        "finance_reconciliation_matches",
        row["id"],
        detalhes="Movimento bancário conciliado manualmente.",
        dados_depois=body.model_dump(),
    )
    await db.commit()
    return {"ok": True, "id": row["id"], "status": "confirmado"}


