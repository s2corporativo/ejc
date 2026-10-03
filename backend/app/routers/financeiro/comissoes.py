"""Rotas internas do módulo Financeiro. URLs públicas preservadas."""
from app.routers.financeiro.fechamento_comum import persistir_fechamento
from fastapi import Depends
from app.core.security import get_current_user
from app.core.database import get_db
import json
from app.services.fee_ledger import LEDGER_CTES
from fastapi import Query
from app.core.rate_limit import rate_limit
from uuid import uuid4

from .common import (
    APIRouter,
    AsyncSession,
    CommissionAdjustmentIn,
    CommissionBatchIn,
    CommissionCloseIn,
    CommissionRuleIn,
    CommissionRulePatch,
    date,
    datetime,
    Decimal,
    HTTPException,
    Optional,
    text,
    timezone,
    User,
    _commission_conference,
    _commission_statement,
    _exigir_financeiro,
    _exigir_gestor_regras,
    _GESTOR_FIN,
    _money,
    _month_bounds,
)

router = APIRouter(prefix="/financeiro", tags=["Financeiro"])
@router.get("/comissoes", dependencies=[Depends(rate_limit("fin-comissoes", 60))])
async def listar_comissoes(
    status: Optional[str] = None,
    search: Optional[str] = None,
    competencia: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    inicio = fim = None
    if competencia:
        ano, mes = (int(v) for v in competencia.split("-"))
        inicio = date(ano, mes, 1)
        fim = date(ano + (1 if mes == 12 else 0), 1 if mes == 12 else mes + 1, 1)

    rows = (
        await db.execute(
            text(
                """
                WITH ajustes AS (
                    SELECT
                        allocation_id,
                        COALESCE(SUM(valor_advogado), 0) AS valor_advogado,
                        COALESCE(SUM(valor_escritorio), 0) AS valor_escritorio,
                        COALESCE(SUM(valor_advogado - applied_value), 0) AS saldo_pendente,
                        COUNT(*) AS qtd
                    FROM commission_adjustments
                    GROUP BY allocation_id
                )
                SELECT
                    a.id,
                    a.case_id,
                    a.fee_payment_id,
                    a.advogado_responsavel_id AS advogado_id,
                    u.full_name AS advogado,
                    c.titulo AS caso,
                    c.numero_interno,
                    COALESCE(cl.nome, cl.razao_social, 'Cliente') AS cliente,
                    fp.data_pagamento,
                    a.bruto_recebido,
                    a.despesas_deduzidas,
                    a.base_liquida,
                    a.percentual_advogado,
                    a.valor_advogado,
                    a.valor_escritorio,
                    a.valor_advogado + COALESCE(aj.valor_advogado, 0) AS valor_advogado_efetivo,
                    a.valor_escritorio + COALESCE(aj.valor_escritorio, 0) AS valor_escritorio_efetivo,
                    COALESCE(aj.valor_advogado, 0) AS ajustes_advogado,
                    COALESCE(aj.valor_escritorio, 0) AS ajustes_escritorio,
                    COALESCE(aj.saldo_pendente, 0) AS saldo_ajuste_pendente,
                    COALESCE(aj.qtd, 0) AS ajustes_qtd,
                    cr.nome AS regra_nome,
                    cr.escopo AS regra_escopo,
                    a.withdrawal_id,
                    pw.status AS withdrawal_status,
                    pw.partner_share AS valor_ordem_pagamento,
                    pw.approved_at,
                    pw.paid_at,
                    pw.payment_method,
                    pw.payment_reference,
                    pw.comprovante_doc_id,
                    pw.payment_batch_id,
                    CASE
                        WHEN a.valor_advogado + COALESCE(aj.valor_advogado, 0) <= 0 THEN 'estornada'
                        WHEN a.withdrawal_id IS NULL THEN 'calculada'
                        WHEN pw.status = 'pendente' THEN 'a_aprovar'
                        WHEN pw.status = 'aprovado' THEN 'a_pagar'
                        WHEN pw.status = 'pago' THEN 'paga'
                        WHEN pw.status = 'rejeitado' THEN 'rejeitada'
                        WHEN pw.status = 'cancelado' THEN 'estornada'
                        ELSE COALESCE(pw.status, 'calculada')
                    END AS status
                FROM case_receipt_allocations a
                JOIN fee_payments fp ON fp.id = a.fee_payment_id
                JOIN fees f ON f.id = fp.fee_id
                JOIN cases c ON c.id = a.case_id
                LEFT JOIN clients cl ON cl.id = f.client_id AND cl.deleted_at IS NULL
                LEFT JOIN users u ON u.id = a.advogado_responsavel_id
                LEFT JOIN commission_rules cr ON cr.id = a.commission_rule_id
                LEFT JOIN partner_withdrawals pw ON pw.id = a.withdrawal_id AND pw.deleted_at IS NULL
                LEFT JOIN ajustes aj ON aj.allocation_id = a.id
                WHERE f.deleted_at IS NULL
                  AND a.valor_advogado > 0
                  AND (CAST(:inicio AS date) IS NULL OR fp.data_pagamento >= CAST(:inicio AS date))
                  AND (CAST(:fim AS date) IS NULL OR fp.data_pagamento < CAST(:fim AS date))
                ORDER BY fp.data_pagamento DESC, a.created_at DESC
                LIMIT 1000
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).mappings().all()

    all_rows = [dict(r) for r in rows]
    data = list(all_rows)
    termo = (search or "").strip().casefold()
    if termo:
        data = [
            r
            for r in data
            if termo
            in " ".join(
                str(r.get(k) or "")
                for k in (
                    "advogado",
                    "cliente",
                    "caso",
                    "numero_interno",
                    "bruto_recebido",
                    "valor_advogado_efetivo",
                )
            ).casefold()
        ]
    if status:
        data = [r for r in data if r.get("status") == status]

    def total_por(st: str) -> Decimal:
        return _money(
            sum(
                (
                    Decimal(str(r["valor_advogado_efetivo"] or 0))
                    for r in all_rows
                    if r["status"] == st
                ),
                Decimal("0"),
            )
        )

    pagamentos_reais = (
        await db.execute(
            text(
                """
                WITH pagos AS (
                    SELECT
                        i.partner_id,
                        SUM(i.valor_pago) AS valor
                    FROM commission_payment_batch_items i
                    JOIN commission_payment_batches b ON b.id=i.batch_id
                    WHERE (CAST(:inicio AS timestamptz) IS NULL OR b.paid_at >= CAST(:inicio AS timestamptz))
                      AND (CAST(:fim AS timestamptz) IS NULL OR b.paid_at < CAST(:fim AS timestamptz))
                    GROUP BY i.partner_id
                    UNION ALL
                    SELECT
                        pw.partner_id,
                        SUM(pw.partner_share) AS valor
                    FROM partner_withdrawals pw
                    WHERE pw.deleted_at IS NULL
                      AND pw.status='pago'
                      AND pw.payment_batch_id IS NULL
                      AND (CAST(:inicio AS timestamptz) IS NULL OR pw.paid_at >= CAST(:inicio AS timestamptz))
                      AND (CAST(:fim AS timestamptz) IS NULL OR pw.paid_at < CAST(:fim AS timestamptz))
                    GROUP BY pw.partner_id
                )
                SELECT partner_id,COALESCE(SUM(valor),0) AS valor
                FROM pagos
                GROUP BY partner_id
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).mappings().all()
    pago_por_advogado = {
        str(r["partner_id"]): _money(r["valor"]) for r in pagamentos_reais
    }
    pago_periodo = _money(
        sum(pago_por_advogado.values(), Decimal("0"))
    )
    escritorio = _money(
        sum(
            (Decimal(str(r["valor_escritorio_efetivo"] or 0)) for r in all_rows),
            Decimal("0"),
        )
    )
    ajustes_pendentes = _money(
        sum(
            (Decimal(str(r["saldo_ajuste_pendente"] or 0)) for r in all_rows),
            Decimal("0"),
        )
    )

    por_advogado_map: dict[str, dict] = {}
    for r in all_rows:
        aid = r.get("advogado_id")
        if not aid:
            continue
        item = por_advogado_map.setdefault(
            aid,
            {
                "advogado_id": aid,
                "advogado": r.get("advogado") or "Advogado",
                "recebido": Decimal("0"),
                "comissao_gerada": Decimal("0"),
                "comissao_paga": Decimal("0"),
                "saldo": Decimal("0"),
                "ajustes_pendentes": Decimal("0"),
            },
        )
        item["recebido"] += Decimal(str(r.get("bruto_recebido") or 0))
        efetiva = Decimal(str(r.get("valor_advogado_efetivo") or 0))
        item["comissao_gerada"] += efetiva
        item["ajustes_pendentes"] += Decimal(str(r.get("saldo_ajuste_pendente") or 0))

    por_advogado = []
    for item in sorted(por_advogado_map.values(), key=lambda x: x["advogado"].casefold()):
        pago = pago_por_advogado.get(str(item["advogado_id"]), Decimal("0"))
        saldo = max(
            item["comissao_gerada"] - pago,
            Decimal("0"),
        )
        por_advogado.append(
            {
                **item,
                "recebido": _money(item["recebido"]),
                "comissao_gerada": _money(item["comissao_gerada"]),
                "comissao_paga": _money(pago),
                "saldo": _money(saldo),
                "ajustes_pendentes": _money(item["ajustes_pendentes"]),
            }
        )

    return {
        "competencia": competencia,
        "data": data,
        "resumo": {
            "calculada": total_por("calculada"),
            "a_aprovar": total_por("a_aprovar"),
            "a_pagar": total_por("a_pagar"),
            "paga_periodo": pago_periodo,
            "escritorio_total": escritorio,
            "ajustes_pendentes": ajustes_pendentes,
        },
        "por_advogado": por_advogado,
    }


@router.post("/comissoes/{allocation_id}/enviar-aprovacao")
async def enviar_comissao_para_aprovacao(
    allocation_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    row = (
        await db.execute(
            text(
                """
                SELECT a.*, c.titulo, c.numero_interno
                FROM case_receipt_allocations a
                JOIN cases c ON c.id = a.case_id
                WHERE a.id=:id
                FOR UPDATE
                """
            ),
            {"id": allocation_id},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(404, "Comissão não encontrada")
    if row["withdrawal_id"]:
        return {"ok": True, "withdrawal_id": row["withdrawal_id"], "already_exists": True}
    if not row["advogado_responsavel_id"] or _money(row["valor_advogado"]) <= 0:
        raise HTTPException(422, "Comissão sem advogado ou valor disponível para aprovação")

    wid = str(uuid4())
    await db.execute(
        text(
            """
            INSERT INTO partner_withdrawals
                (id, partner_id, gross_value, case_expenses, net_value,
                 partner_share, description, period_reference, status,
                 created_at, updated_at)
            VALUES
                (:id, :partner_id, :gross, :expenses, :net, :share,
                 :description, :ref, 'pendente', now(), now())
            """
        ),
        {
            "id": wid,
            "partner_id": row["advogado_responsavel_id"],
            "gross": row["bruto_recebido"],
            "expenses": row["despesas_deduzidas"],
            "net": row["base_liquida"],
            "share": row["valor_advogado"],
            "description": f"Comissão — {row['numero_interno'] or row['titulo']}",
            "ref": f"commission:{str(row['fee_payment_id'])[:29]}",
        },
    )
    await db.execute(
        text(
            "UPDATE case_receipt_allocations SET withdrawal_id=:wid WHERE id=:id"
        ),
        {"wid": wid, "id": allocation_id},
    )
    from app.models.audit_log import criar_audit_log
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "SUBMIT",
        "case_receipt_allocations",
        allocation_id,
        detalhes="Comissão enviada à fila de aprovação.",
        dados_depois={"withdrawal_id": wid},
    )
    await db.commit()
    return {"ok": True, "withdrawal_id": wid}




@router.post("/comissoes/{allocation_id}/ajustes", status_code=201)
async def criar_ajuste_comissao(
    allocation_id: str,
    body: CommissionAdjustmentIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    from app.services.commission_service import registrar_ajuste_comissao
    from app.services.finance_governance import competencia_de_data, exigir_competencia_aberta

    await exigir_competencia_aberta(
        db,
        competencia_de_data(date.today()),
        "Registrar ajuste de comissão",
    )
    valor_escritorio = (
        body.valor_escritorio
        if body.valor_escritorio is not None
        else -body.valor_advogado
    )
    try:
        resultado = await registrar_ajuste_comissao(
            db,
            allocation_id=allocation_id,
            valor_advogado=body.valor_advogado,
            valor_escritorio=valor_escritorio,
            motivo=body.motivo,
            user=cu,
            source_type="ajuste",
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    await db.commit()
    return resultado


@router.get("/comissoes/previsao")
async def previsao_comissoes(
    competencia: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Estimativa separada do realizado; não deduz despesas futuras."""
    _exigir_financeiro(cu)
    inicio = fim = None
    if competencia:
        inicio, fim = _month_bounds(competencia)

    rows = (
        await db.execute(
            # SQL composto apenas por CTE constante e bind params; sem entrada estrutural do usuário.
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(
                f"""
                WITH {LEDGER_CTES},
                saldos AS (
                    SELECT
                        f.id,
                        f.case_id,
                        f.data_vencimento,
                        GREATEST(COALESCE(f.valor,0)-COALESCE(pe.total_pago,0),0) AS saldo
                    FROM fees f
                    LEFT JOIN pagamentos_efetivos pe ON pe.fee_id=f.id
                    WHERE f.deleted_at IS NULL
                      AND f.valor IS NOT NULL
                      AND CAST(f.status AS text) IN ('pendente','atrasado')
                )
                SELECT
                    s.id AS fee_id,
                    s.case_id,
                    s.data_vencimento,
                    s.saldo,
                    c.advogado_responsavel_id AS advogado_id,
                    u.full_name AS advogado,
                    c.titulo AS caso,
                    c.numero_interno,
                    COALESCE(cl.nome,cl.razao_social,'Cliente') AS cliente,
                    COALESCE(cr.percentual_advogado,50) AS percentual_advogado,
                    COALESCE(cr.nome,'Regra padrão 50/50') AS regra,
                    COALESCE(cr.escopo,'padrao') AS regra_escopo,
                    ROUND(s.saldo * COALESCE(cr.percentual_advogado,50) / 100, 2) AS comissao_prevista
                FROM saldos s
                JOIN cases c ON c.id=s.case_id AND c.deleted_at IS NULL
                LEFT JOIN users u ON u.id=c.advogado_responsavel_id
                LEFT JOIN clients cl ON cl.id=c.client_id AND cl.deleted_at IS NULL
                LEFT JOIN LATERAL (
                    SELECT r.percentual_advogado,r.nome,r.escopo
                    FROM commission_rules r
                    WHERE r.deleted_at IS NULL
                      AND r.ativo=TRUE
                      AND r.vigencia_inicio <= CURRENT_DATE
                      AND (r.vigencia_fim IS NULL OR r.vigencia_fim >= CURRENT_DATE)
                      AND (
                        (r.escopo='caso' AND r.case_id=c.id)
                        OR (r.escopo='advogado' AND r.advogado_id=c.advogado_responsavel_id)
                        OR (r.escopo='area' AND LOWER(r.area)=LOWER(CAST(c.area AS text)))
                        OR r.escopo='padrao'
                      )
                    ORDER BY
                      CASE r.escopo
                        WHEN 'caso' THEN 0
                        WHEN 'advogado' THEN 1
                        WHEN 'area' THEN 2
                        ELSE 3
                      END,
                      r.prioridade,
                      r.created_at DESC
                    LIMIT 1
                ) cr ON TRUE
                WHERE s.saldo > 0
                  AND c.advogado_responsavel_id IS NOT NULL
                  AND (CAST(:inicio AS date) IS NULL OR s.data_vencimento >= CAST(:inicio AS date))
                  AND (CAST(:fim AS date) IS NULL OR s.data_vencimento < CAST(:fim AS date))
                ORDER BY s.data_vencimento NULLS LAST,c.numero_interno
                LIMIT 1000
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).mappings().all()
    data = [dict(r) for r in rows]

    indeterminadas = (
        await db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM fees f
                JOIN cases c ON c.id=f.case_id AND c.deleted_at IS NULL
                WHERE f.deleted_at IS NULL
                  AND f.valor IS NULL
                  AND f.percentual_exito IS NOT NULL
                  AND CAST(f.status AS text) IN ('pendente','atrasado')
                  AND c.advogado_responsavel_id IS NOT NULL
                  AND (CAST(:inicio AS date) IS NULL OR f.data_vencimento >= CAST(:inicio AS date))
                  AND (CAST(:fim AS date) IS NULL OR f.data_vencimento < CAST(:fim AS date))
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).scalar() or 0

    grupos: dict[str, dict] = {}
    for row in data:
        aid = row["advogado_id"]
        g = grupos.setdefault(
            aid,
            {
                "advogado_id": aid,
                "advogado": row["advogado"] or "Advogado",
                "saldo_contratado": Decimal("0"),
                "comissao_prevista": Decimal("0"),
                "qtd": 0,
            },
        )
        g["saldo_contratado"] += Decimal(str(row["saldo"] or 0))
        g["comissao_prevista"] += Decimal(str(row["comissao_prevista"] or 0))
        g["qtd"] += 1

    por_advogado = [
        {
            **g,
            "saldo_contratado": _money(g["saldo_contratado"]),
            "comissao_prevista": _money(g["comissao_prevista"]),
        }
        for g in sorted(grupos.values(), key=lambda x: x["advogado"].casefold())
    ]
    return {
        "competencia": competencia,
        "total": _money(
            sum(
                (Decimal(str(r["comissao_prevista"] or 0)) for r in data),
                Decimal("0"),
            )
        ),
        "saldo_contratado": _money(
            sum((Decimal(str(r["saldo"] or 0)) for r in data), Decimal("0"))
        ),
        "indeterminadas": int(indeterminadas),
        "por_advogado": por_advogado,
        "data": data,
        "aviso": (
            "Previsão gerencial sobre saldos contratuais conhecidos. "
            "Despesas futuras não são deduzidas; êxito sem base monetária fica apenas na contagem."
        ),
    }


@router.get("/comissoes/conferencia")
async def conferencia_comissoes(
    competencia: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    return await _commission_conference(db, competencia)


@router.get("/comissoes/extrato-mensal")
async def extrato_mensal_comissoes(
    competencia: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    advogado_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    if advogado_id and cu.role.value not in _GESTOR_FIN and str(cu.id) != advogado_id:
        raise HTTPException(403, "Sem permissão para consultar outro advogado")
    extrato = await _commission_statement(db, competencia, advogado_id)
    fechamento = (
        await db.execute(
            text(
                """
                SELECT id,competencia,snapshot_json,closed_by,closed_at
                FROM commission_month_closings
                WHERE competencia=:competencia
                """
            ),
            {"competencia": competencia},
        )
    ).mappings().first()
    extrato["fechamento"] = dict(fechamento) if fechamento else None
    return extrato


@router.get("/comissoes/fechamentos/{competencia}")
async def obter_fechamento_comissoes(
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
                FROM commission_month_closings
                WHERE competencia=:competencia
                """
            ),
            {"competencia": competencia},
        )
    ).mappings().first()
    return dict(row) if row else {"competencia": competencia, "fechado": False}


@router.post("/comissoes/fechamentos", status_code=201)
async def fechar_competencia_comissoes(
    body: CommissionCloseIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_gestor_regras(cu)
    from app.services.finance_governance import exigir_lock_financeiro
    await exigir_lock_financeiro(db, "commission_close", body.competencia)
    existente = (
        await db.execute(
            text(
                "SELECT id FROM commission_month_closings WHERE competencia=:competencia"
            ),
            {"competencia": body.competencia},
        )
    ).scalar_one_or_none()
    if existente:
        raise HTTPException(409, "Competência de comissões já foi fechada")

    conferencia = await _commission_conference(db, body.competencia)
    if not conferencia["pronto"]:
        raise HTTPException(
            409,
            detail={
                "message": "Fechamento bloqueado por pendências de comissão",
                "conferencia": conferencia,
            },
        )

    snapshot = await _commission_statement(db, body.competencia)
    snapshot["conferencia"] = conferencia
    cid = str(uuid4())
    agora = datetime.now(timezone.utc)
    await persistir_fechamento(db, tipo="comissoes", cid=cid, competencia=body.competencia,
                              snapshot=snapshot, closed_by=cu.id, closed_at=agora)
    from app.models.audit_log import criar_audit_log
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "CLOSE",
        "commission_month_closings",
        cid,
        detalhes=f"Competência de comissões {body.competencia} fechada em snapshot.",
        dados_depois={"competencia": body.competencia},
    )
    await db.commit()
    return {
        "id": cid,
        "competencia": body.competencia,
        "closed_at": agora,
        "snapshot": snapshot,
    }


@router.post("/comissoes/lotes-pagamento", status_code=201)
async def pagar_comissoes_em_lote(
    body: CommissionBatchIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    ids = list(dict.fromkeys(body.withdrawal_ids))
    if body.comprovante_doc_id:
        doc = (
            await db.execute(
                text(
                    "SELECT id FROM documents WHERE id=:id AND deleted_at IS NULL"
                ),
                {"id": body.comprovante_doc_id},
            )
        ).scalar_one_or_none()
        if not doc:
            raise HTTPException(422, "Comprovante documental não encontrado")

    withdrawals = (
        await db.execute(
            text(
                """
                SELECT pw.*,u.full_name AS advogado
                FROM partner_withdrawals pw
                LEFT JOIN users u ON u.id=pw.partner_id
                WHERE pw.id = ANY(CAST(:ids AS varchar[]))
                  AND pw.deleted_at IS NULL
                FOR UPDATE OF pw
                """
            ),
            {"ids": ids},
        )
    ).mappings().all()
    if len(withdrawals) != len(ids):
        raise HTTPException(404, "Uma ou mais comissões selecionadas não existem")

    from app.services.finance_governance import (
        competencia_de_data,
        exigir_competencia_aberta,
        limite_dupla_aprovacao,
    )
    competencia_pagamento = competencia_de_data(body.paid_at)
    await exigir_competencia_aberta(
        db, competencia_pagamento, "Pagar comissões"
    )
    limite = await limite_dupla_aprovacao(db)
    total_nominal = _money(
        sum((Decimal(str(r["partner_share"] or 0)) for r in withdrawals), Decimal("0"))
    )
    if total_nominal >= limite and any(
        str(r.get("approved_by") or "") == str(cu.id) for r in withdrawals
    ):
        raise HTTPException(
            403,
            (
                f"Lote de {float(total_nominal):.2f} excede a alçada de "
                f"{float(limite):.2f}; quem aprovou a comissão não pode executar "
                "o pagamento. É necessária segunda pessoa autorizada."
            ),
        )

    por_partner: dict[str, list[dict]] = {}
    for raw in withdrawals:
        row = dict(raw)
        if row["status"] != "aprovado":
            raise HTTPException(
                409,
                f"Comissão {row['id']} precisa estar aprovada antes do pagamento",
            )
        if str(row["partner_id"]) == str(cu.id):
            raise HTTPException(
                403,
                "Pagamento da própria comissão não é permitido — segregação de funções",
            )
        por_partner.setdefault(str(row["partner_id"]), []).append(row)

    batch_id = str(uuid4())
    itens_batch: list[dict] = []
    total_batch = Decimal("0")

    for partner_id, items in por_partner.items():
        valor_retiradas = _money(
            sum((Decimal(str(i["partner_share"] or 0)) for i in items), Decimal("0"))
        )
        disponivel = valor_retiradas
        ajuste_total = Decimal("0")
        ajustes_aplicados: list[str] = []

        ajustes = (
            await db.execute(
                text(
                    """
                    SELECT ca.id,ca.valor_advogado,ca.applied_value
                    FROM commission_adjustments ca
                    JOIN case_receipt_allocations a ON a.id=ca.allocation_id
                    WHERE a.advogado_responsavel_id=:partner_id
                      AND ca.valor_advogado <> ca.applied_value
                    ORDER BY
                      CASE WHEN ca.valor_advogado-ca.applied_value > 0 THEN 0 ELSE 1 END,
                      ca.created_at,
                      ca.id
                    FOR UPDATE OF ca
                    """
                ),
                {"partner_id": partner_id},
            )
        ).mappings().all()

        for aj in ajustes:
            restante = _money(
                Decimal(str(aj["valor_advogado"]))
                - Decimal(str(aj["applied_value"] or 0))
            )
            if restante == 0:
                continue
            if restante > 0:
                delta = restante
            else:
                if disponivel <= 0:
                    continue
                delta = max(restante, -disponivel)
            if delta == 0:
                continue
            novo_aplicado = _money(Decimal(str(aj["applied_value"] or 0)) + delta)
            await db.execute(
                text(
                    "UPDATE commission_adjustments SET applied_value=:valor WHERE id=:id"
                ),
                {"valor": novo_aplicado, "id": aj["id"]},
            )
            disponivel = _money(disponivel + delta)
            ajuste_total = _money(ajuste_total + delta)
            ajustes_aplicados.append(aj["id"])

        valor_pago = max(disponivel, Decimal("0"))
        total_batch = _money(total_batch + valor_pago)
        itens_batch.append(
            {
                "partner_id": partner_id,
                "advogado": items[0].get("advogado") or "Advogado",
                "withdrawal_ids": [i["id"] for i in items],
                "adjustment_ids": ajustes_aplicados,
                "valor_retiradas": valor_retiradas,
                "valor_ajustes": ajuste_total,
                "valor_pago": valor_pago,
            }
        )

    competencia = competencia_pagamento
    await db.execute(
        text(
            """
            INSERT INTO commission_payment_batches
                (id,competencia,payment_method,payment_reference,
                 comprovante_doc_id,observacao,total_pago,paid_by,paid_at,created_at)
            VALUES
                (:id,:competencia,:method,:reference,:doc_id,:observacao,
                 :total,:paid_by,:paid_at,NOW())
            """
        ),
        {
            "id": batch_id,
            "competencia": competencia,
            "method": body.payment_method,
            "reference": body.payment_reference,
            "doc_id": body.comprovante_doc_id,
            "observacao": body.observacao,
            "total": total_batch,
            "paid_by": cu.id,
            "paid_at": body.paid_at,
        },
    )

    from app.models.audit_log import criar_audit_log
    for item in itens_batch:
        item_id = str(uuid4())
        await db.execute(
            text(
                """
                INSERT INTO commission_payment_batch_items
                    (id,batch_id,partner_id,withdrawal_ids,adjustment_ids,
                     valor_retiradas,valor_ajustes,valor_pago,created_at)
                VALUES
                    (:id,:batch_id,:partner_id,CAST(:withdrawals AS jsonb),
                     CAST(:adjustments AS jsonb),:retiradas,:ajustes,:pago,NOW())
                """
            ),
            {
                "id": item_id,
                "batch_id": batch_id,
                "partner_id": item["partner_id"],
                "withdrawals": json.dumps(item["withdrawal_ids"]),
                "adjustments": json.dumps(item["adjustment_ids"]),
                "retiradas": item["valor_retiradas"],
                "ajustes": item["valor_ajustes"],
                "pago": item["valor_pago"],
            },
        )
        await db.execute(
            text(
                """
                UPDATE partner_withdrawals
                SET status='pago',
                    paid_at=:paid_at,
                    paid_by=:paid_by,
                    payment_method=:method,
                    payment_reference=:reference,
                    comprovante_doc_id=:doc_id,
                    payment_batch_id=:batch_id,
                    updated_at=NOW()
                WHERE id = ANY(CAST(:ids AS varchar[]))
                """
            ),
            {
                "paid_at": body.paid_at,
                "paid_by": cu.id,
                "method": body.payment_method,
                "reference": body.payment_reference,
                "doc_id": body.comprovante_doc_id,
                "batch_id": batch_id,
                "ids": item["withdrawal_ids"],
            },
        )
        for withdrawal_id in item["withdrawal_ids"]:
            await criar_audit_log(
                db,
                cu.id,
                cu.role.value,
                "PAY_BATCH",
                "partner_withdrawals",
                withdrawal_id,
                detalhes=f"Comissão paga no lote {batch_id}.",
                dados_depois={
                    "batch_id": batch_id,
                    "payment_method": body.payment_method,
                    "payment_reference": body.payment_reference,
                    "comprovante_doc_id": body.comprovante_doc_id,
                },
            )

    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "CREATE",
        "commission_payment_batches",
        batch_id,
        detalhes=f"Lote de pagamento de comissões: {len(ids)} retirada(s).",
        dados_depois={
            "competencia": competencia,
            "total_pago": str(total_batch),
            "itens": len(itens_batch),
        },
    )
    await db.commit()
    return {
        "id": batch_id,
        "competencia": competencia,
        "total_pago": total_batch,
        "itens": itens_batch,
    }


@router.get("/comissoes/regras", dependencies=[Depends(rate_limit("fin-comissoes-regras", 60))])
async def listar_regras_comissao(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    rows = (
        await db.execute(
            text(
                """
                SELECT r.*, u.full_name AS advogado_nome,
                       c.titulo AS caso_titulo, c.numero_interno
                FROM commission_rules r
                LEFT JOIN users u ON u.id = r.advogado_id
                LEFT JOIN cases c ON c.id = r.case_id
                WHERE r.deleted_at IS NULL
                ORDER BY r.ativo DESC,
                    CASE r.escopo WHEN 'caso' THEN 1 WHEN 'advogado' THEN 2
                         WHEN 'area' THEN 3 ELSE 4 END,
                    r.prioridade, r.created_at DESC
                """
            )
        )
    ).mappings().all()
    return [dict(r) for r in rows]


@router.post("/comissoes/regras", status_code=201)
async def criar_regra_comissao(
    body: CommissionRuleIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_gestor_regras(cu)
    rid = str(uuid4())
    await db.execute(
        text(
            """
            INSERT INTO commission_rules
                (id,nome,escopo,area,advogado_id,case_id,percentual_advogado,
                 descontar_despesas,prioridade,ativo,vigencia_inicio,vigencia_fim,
                 created_by,created_at,updated_at)
            VALUES
                (:id,:nome,:escopo,:area,:advogado_id,:case_id,:pct,
                 :descontar,:prioridade,:ativo,:inicio,:fim,:created_by,now(),now())
            """
        ),
        {
            "id": rid, "nome": body.nome, "escopo": body.escopo,
            "area": body.area if body.escopo == "area" else None,
            "advogado_id": body.advogado_id if body.escopo == "advogado" else None,
            "case_id": body.case_id if body.escopo == "caso" else None,
            "pct": body.percentual_advogado, "descontar": body.descontar_despesas,
            "prioridade": body.prioridade, "ativo": body.ativo,
            "inicio": body.vigencia_inicio, "fim": body.vigencia_fim,
            "created_by": cu.id,
        },
    )
    from app.models.audit_log import criar_audit_log
    await criar_audit_log(
        db, cu.id, cu.role.value, "CREATE", "commission_rules", rid,
        detalhes="Regra de comissão criada.",
        dados_depois=body.model_dump(mode="json"),
    )
    await db.commit()
    return {"id": rid, "ok": True}


@router.patch("/comissoes/regras/{rule_id}")
async def atualizar_regra_comissao(
    rule_id: str,
    body: CommissionRulePatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_gestor_regras(cu)
    atual = (
        await db.execute(
            text("SELECT * FROM commission_rules WHERE id=:id AND deleted_at IS NULL"),
            {"id": rule_id},
        )
    ).mappings().first()
    if not atual:
        raise HTTPException(404, "Regra de comissão não encontrada")
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "Nenhuma alteração informada")
    campos = {
        "nome": "nome",
        "percentual_advogado": "percentual_advogado",
        "descontar_despesas": "descontar_despesas",
        "prioridade": "prioridade",
        "ativo": "ativo",
        "vigencia_fim": "vigencia_fim",
    }
    sets, params = [], {"id": rule_id}
    for key, value in changes.items():
        sets.append(f"{campos[key]}=:{key}")
        params[key] = value
    sets.append("updated_at=NOW()")
    await db.execute(
        # Nomes de coluna vêm exclusivamente do mapa campos; valores usam bind params.
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        text(f"UPDATE commission_rules SET {', '.join(sets)} WHERE id=:id AND deleted_at IS NULL"),
        params,
    )
    from app.models.audit_log import criar_audit_log
    await criar_audit_log(
        db, cu.id, cu.role.value, "UPDATE", "commission_rules", rule_id,
        dados_antes={k: atual.get(campos[k]) for k in changes},
        dados_depois=body.model_dump(exclude_unset=True, mode="json"),
    )
    await db.commit()
    return {"ok": True}


@router.delete("/comissoes/regras/{rule_id}")
async def remover_regra_comissao(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_gestor_regras(cu)
    if rule_id in {"commission-default-50", "commission-area-civil-0"}:
        raise HTTPException(409, "Regra estrutural: desative ou altere em vez de excluir")
    row = (
        await db.execute(
            text("SELECT id FROM commission_rules WHERE id=:id AND deleted_at IS NULL"),
            {"id": rule_id},
        )
    ).first()
    if not row:
        raise HTTPException(404, "Regra de comissão não encontrada")
    await db.execute(
        text("UPDATE commission_rules SET deleted_at=NOW(), ativo=FALSE, updated_at=NOW() WHERE id=:id"),
        {"id": rule_id},
    )
    from app.models.audit_log import criar_audit_log
    await criar_audit_log(
        db, cu.id, cu.role.value, "DELETE", "commission_rules", rule_id,
        detalhes="Regra de comissão removida por soft delete.",
    )
    await db.commit()
    return {"ok": True}


@router.get("/comissoes/opcoes")
async def opcoes_comissao(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    advogados = (
        await db.execute(
            text(
                """
                SELECT id, full_name, CAST(role AS text) AS role
                FROM users
                WHERE deleted_at IS NULL AND is_active=TRUE
                  AND CAST(role AS text) IN ('advogado','socio','admin','superadmin')
                ORDER BY full_name
                """
            )
        )
    ).mappings().all()
    casos = (
        await db.execute(
            text(
                """
                SELECT id, titulo, numero_interno, CAST(area AS text) AS area
                FROM cases
                WHERE deleted_at IS NULL AND CAST(status AS text) != 'arquivado'
                ORDER BY created_at DESC
                LIMIT 500
                """
            )
        )
    ).mappings().all()
    areas = (
        await db.execute(
            text(
                """
                SELECT DISTINCT CAST(area AS text) AS area
                FROM cases
                WHERE deleted_at IS NULL
                ORDER BY area
                """
            )
        )
    ).scalars().all()
    return {
        "advogados": [dict(r) for r in advogados],
        "casos": [dict(r) for r in casos],
        "areas": [a for a in areas if a],
    }


