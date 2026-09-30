"""Cálculo e alocação de comissões sobre recebimentos reais.

A comissão nasce somente quando existe FeePayment. A regra usada e a base
financeira são fotografadas em case_receipt_allocations, preservando o
histórico mesmo quando regras futuras forem alteradas.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from sqlalchemy import and_, case as sql_case, func, or_, select, text

from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.fee import CaseReceiptAllocation, CommissionRule, FeePayment

_Q2 = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(_Q2, ROUND_HALF_UP)


def _role(user) -> str:
    return str(getattr(getattr(user, "role", ""), "value", getattr(user, "role", "")))


async def resolver_regra_comissao(
    db,
    case: Case,
    advogado_id: str | None = None,
    data_ref: date | None = None,
) -> CommissionRule:
    """Prioridade canônica: caso > advogado > área > padrão."""
    data_ref = data_ref or date.today()
    area = str(getattr(case.area, "value", case.area) or "").strip().casefold()
    advogado_id = advogado_id or case.advogado_responsavel_id

    aplicavel = or_(
        and_(CommissionRule.escopo == "caso", CommissionRule.case_id == case.id),
        and_(
            CommissionRule.escopo == "advogado",
            CommissionRule.advogado_id == advogado_id,
        ) if advogado_id else False,
        and_(CommissionRule.escopo == "area", func.lower(CommissionRule.area) == area),
        CommissionRule.escopo == "padrao",
    )
    rank = sql_case(
        (CommissionRule.escopo == "caso", 0),
        (CommissionRule.escopo == "advogado", 1),
        (CommissionRule.escopo == "area", 2),
        else_=3,
    )
    regra = (
        await db.execute(
            select(CommissionRule)
            .where(
                CommissionRule.deleted_at.is_(None),
                CommissionRule.ativo.is_(True),
                CommissionRule.vigencia_inicio <= data_ref,
                or_(
                    CommissionRule.vigencia_fim.is_(None),
                    CommissionRule.vigencia_fim >= data_ref,
                ),
                aplicavel,
            )
            .order_by(rank.asc(), CommissionRule.prioridade.asc(), CommissionRule.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if regra:
        return regra

    # Fail-safe para bases antigas durante transição. A migration 164 cria esta
    # regra, portanto este ramo não deve ser usado em produção normal.
    return CommissionRule(
        id="fallback-50",
        nome="Fallback 50/50",
        escopo="padrao",
        percentual_advogado=Decimal("50.00"),
        descontar_despesas=True,
        prioridade=999,
        ativo=True,
        vigencia_inicio=data_ref,
    )


async def despesas_dedutiveis_restantes(db, case_id: str) -> Decimal:
    """Custos efetivamente pagos do centro de custos ainda não abatidos."""
    total = (
        await db.execute(
            text(
                """
                SELECT COALESCE(SUM(valor), 0)
                FROM centro_custos
                WHERE case_id=:case_id
                  AND deleted_at IS NULL
                  AND CAST(tipo AS text)='despesa'
                  AND pago=TRUE
                """
            ),
            {"case_id": case_id},
        )
    ).scalar() or 0
    ja_deduzido = (
        await db.execute(
            select(func.coalesce(func.sum(CaseReceiptAllocation.despesas_deduzidas), 0))
            .where(CaseReceiptAllocation.case_id == case_id)
        )
    ).scalar() or 0
    return max(money(total) - money(ja_deduzido), Decimal("0.00"))


async def calcular_comissao(
    db,
    case: Case,
    bruto,
    advogado_id: str | None = None,
    data_ref: date | None = None,
) -> dict:
    bruto = money(bruto)
    regra = await resolver_regra_comissao(db, case, advogado_id, data_ref)
    despesas = Decimal("0.00")
    if regra.descontar_despesas and bruto > 0:
        restantes = await despesas_dedutiveis_restantes(db, case.id)
        despesas = min(bruto, restantes)
    base = money(max(bruto - despesas, Decimal("0.00")))
    pct = money(regra.percentual_advogado)
    valor_adv = money(base * pct / Decimal("100"))
    valor_esc = money(base - valor_adv)
    return {
        "regra": regra,
        "bruto": bruto,
        "despesas": despesas,
        "base_liquida": base,
        "percentual_advogado": pct,
        "valor_advogado": valor_adv,
        "valor_escritorio": valor_esc,
    }


async def alocar_comissao_pagamento(
    db,
    case: Case,
    payment: FeePayment,
    user,
    *,
    valor_efetivo=None,
) -> dict:
    """Cria no máximo uma alocação por pagamento e uma ordem de pagamento."""
    existente = (
        await db.execute(
            select(CaseReceiptAllocation).where(
                CaseReceiptAllocation.fee_payment_id == payment.id
            )
        )
    ).scalar_one_or_none()
    if existente:
        return {
            "allocation_id": existente.id,
            "withdrawal_id": existente.withdrawal_id,
            "valor_advogado": money(existente.valor_advogado),
            "valor_escritorio": money(existente.valor_escritorio),
            "percentual_advogado": money(existente.percentual_advogado),
            "base_liquida": money(existente.base_liquida),
            "despesas_deduzidas": money(existente.despesas_deduzidas),
            "rateio_pendente": False,
            "ja_existia": True,
        }

    bruto = money(valor_efetivo if valor_efetivo is not None else payment.valor)
    if bruto <= 0:
        return {
            "allocation_id": None,
            "withdrawal_id": None,
            "rateio_pendente": False,
            "ignorado": True,
        }

    calc = await calcular_comissao(
        db,
        case,
        bruto,
        case.advogado_responsavel_id,
        payment.data_pagamento,
    )
    regra = calc["regra"]
    pct = calc["percentual_advogado"]

    if pct > 0 and not case.advogado_responsavel_id:
        await criar_audit_log(
            db,
            getattr(user, "id", None),
            _role(user) or "system",
            "COMMISSION_PENDING",
            "fee_payments",
            payment.id,
            detalhes="Comissão pendente: caso sem advogado responsável.",
            dados_depois={
                "case_id": case.id,
                "fee_payment_id": payment.id,
                "commission_rule_id": regra.id,
                "percentual_previsto": str(pct),
            },
        )
        return {
            "allocation_id": None,
            "withdrawal_id": None,
            "rateio_pendente": True,
            "regra": regra.nome,
            "commission_rule_id": regra.id,
        }

    withdrawal_id = None
    if calc["valor_advogado"] > 0 and case.advogado_responsavel_id:
        withdrawal_id = str(uuid4())
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
                "id": withdrawal_id,
                "partner_id": case.advogado_responsavel_id,
                "gross": calc["bruto"],
                "expenses": calc["despesas"],
                "net": calc["base_liquida"],
                "share": calc["valor_advogado"],
                "description": f"Comissão — {case.numero_interno or case.titulo}",
                "ref": f"commission:{payment.id[:29]}",
            },
        )

    alloc = CaseReceiptAllocation(
        id=str(uuid4()),
        case_id=case.id,
        fee_payment_id=payment.id,
        advogado_responsavel_id=case.advogado_responsavel_id,
        percentual_advogado=pct,
        valor_advogado=calc["valor_advogado"],
        valor_escritorio=calc["valor_escritorio"],
        regra=f"rule:{regra.id}"[:50],
        commission_rule_id=None if regra.id == "fallback-50" else regra.id,
        bruto_recebido=calc["bruto"],
        despesas_deduzidas=calc["despesas"],
        base_liquida=calc["base_liquida"],
        withdrawal_id=withdrawal_id,
    )
    db.add(alloc)
    await db.flush()

    await criar_audit_log(
        db,
        getattr(user, "id", None),
        _role(user) or "system",
        "CREATE",
        "case_receipt_allocations",
        alloc.id,
        detalhes="Comissão calculada sobre recebimento efetivo com snapshot da regra.",
        dados_depois={
            "case_id": case.id,
            "fee_payment_id": payment.id,
            "commission_rule_id": alloc.commission_rule_id,
            "regra": regra.nome,
            "bruto": str(calc["bruto"]),
            "despesas_deduzidas": str(calc["despesas"]),
            "base_liquida": str(calc["base_liquida"]),
            "percentual_advogado": str(pct),
            "valor_advogado": str(calc["valor_advogado"]),
            "valor_escritorio": str(calc["valor_escritorio"]),
            "withdrawal_id": withdrawal_id,
        },
    )
    return {
        "allocation_id": alloc.id,
        "withdrawal_id": withdrawal_id,
        "valor": calc["bruto"],
        "valor_advogado": calc["valor_advogado"],
        "valor_escritorio": calc["valor_escritorio"],
        "percentual_advogado": pct,
        "despesas_deduzidas": calc["despesas"],
        "base_liquida": calc["base_liquida"],
        "regra": regra.nome,
        "commission_rule_id": alloc.commission_rule_id,
        "rateio_pendente": False,
    }


async def _aplicar_ajuste_em_retirada(
    db,
    *,
    allocation_id: str,
    advogado_id: str | None,
    withdrawal_id: str | None,
    case_id: str,
    delta_advogado: Decimal,
    adjustment_id: str,
) -> Decimal:
    """Aplica o ajuste na ordem ainda aberta quando possível.

    Retirada pendente/aprovada é corrigida no próprio valor operacional.
    Retirada paga nunca é reescrita: ajuste negativo vira crédito do escritório
    a compensar em lote futuro; ajuste positivo gera nova ordem pendente.
    """
    if delta_advogado == 0 or not advogado_id:
        return Decimal("0.00")

    row = None
    if withdrawal_id:
        row = (
            await db.execute(
                text(
                    """
                    SELECT id, status, partner_share
                    FROM partner_withdrawals
                    WHERE id=:id AND deleted_at IS NULL
                    FOR UPDATE
                    """
                ),
                {"id": withdrawal_id},
            )
        ).mappings().first()

    if row and row["status"] in {"pendente", "aprovado"}:
        atual = money(row["partner_share"])
        if delta_advogado < 0:
            aplicado = max(delta_advogado, -atual)
        else:
            aplicado = delta_advogado
        novo = money(atual + aplicado)
        novo_status = "cancelado" if novo == 0 else row["status"]
        await db.execute(
            text(
                """
                UPDATE partner_withdrawals
                SET partner_share=:share,
                    status=:status,
                    updated_at=NOW()
                WHERE id=:id
                """
            ),
            {"share": novo, "status": novo_status, "id": row["id"]},
        )
        return money(aplicado)

    # Se a ordem original já foi paga/cancelada (ou não existe), o ajuste
    # permanece como saldo pendente. Ele será compensado no próximo lote do
    # advogado, sem criar uma retirada paralela invisível na interface.

    return Decimal("0.00")


async def registrar_ajuste_comissao(
    db,
    *,
    allocation_id: str,
    valor_advogado,
    valor_escritorio,
    motivo: str,
    user,
    source_type: str = "ajuste",
    fee_estorno_id: str | None = None,
) -> dict:
    """Acrescenta ajuste imutável ao rateio, sem editar o snapshot original."""
    delta_adv = money(valor_advogado)
    delta_esc = money(valor_escritorio)
    if delta_adv == 0 and delta_esc == 0:
        return {"ajuste_id": None, "ignorado": True}
    if source_type not in {"ajuste", "estorno"}:
        raise ValueError("source_type inválido")

    allocation = (
        await db.execute(
            text(
                """
                SELECT id, case_id, advogado_responsavel_id, withdrawal_id
                FROM case_receipt_allocations
                WHERE id=:id
                FOR UPDATE
                """
            ),
            {"id": allocation_id},
        )
    ).mappings().first()
    if not allocation:
        raise ValueError("alocação de comissão não encontrada")

    if fee_estorno_id:
        existente = (
            await db.execute(
                text(
                    """
                    SELECT id
                    FROM commission_adjustments
                    WHERE fee_estorno_id=:id
                    LIMIT 1
                    """
                ),
                {"id": fee_estorno_id},
            )
        ).scalar_one_or_none()
        if existente:
            return {"ajuste_id": existente, "ja_existia": True}

    aid = str(uuid4())
    applied = await _aplicar_ajuste_em_retirada(
        db,
        allocation_id=allocation_id,
        advogado_id=allocation["advogado_responsavel_id"],
        withdrawal_id=allocation["withdrawal_id"],
        case_id=allocation["case_id"],
        delta_advogado=delta_adv,
        adjustment_id=aid,
    )

    await db.execute(
        text(
            """
            INSERT INTO commission_adjustments
                (id, allocation_id, fee_estorno_id, source_type,
                 valor_advogado, valor_escritorio, applied_value,
                 motivo, created_by, created_at)
            VALUES
                (:id, :allocation_id, :fee_estorno_id, :source_type,
                 :valor_advogado, :valor_escritorio, :applied_value,
                 :motivo, :created_by, NOW())
            """
        ),
        {
            "id": aid,
            "allocation_id": allocation_id,
            "fee_estorno_id": fee_estorno_id,
            "source_type": source_type,
            "valor_advogado": delta_adv,
            "valor_escritorio": delta_esc,
            "applied_value": applied,
            "motivo": motivo,
            "created_by": getattr(user, "id", None),
        },
    )

    await criar_audit_log(
        db,
        getattr(user, "id", None),
        _role(user) or "system",
        "COMMISSION_ADJUSTMENT",
        "case_receipt_allocations",
        allocation_id,
        detalhes=motivo[:500],
        dados_depois={
            "adjustment_id": aid,
            "source_type": source_type,
            "valor_advogado": str(delta_adv),
            "valor_escritorio": str(delta_esc),
            "applied_value": str(applied),
            "fee_estorno_id": fee_estorno_id,
        },
    )
    return {
        "ajuste_id": aid,
        "valor_advogado": delta_adv,
        "valor_escritorio": delta_esc,
        "aplicado_na_ordem": applied,
        "saldo_pendente": money(delta_adv - applied),
    }


async def registrar_reversao_comissao_estorno(
    db,
    *,
    fee_payment_id: str,
    fee_estorno_id: str,
    valor_estorno,
    motivo: str,
    user,
) -> dict | None:
    """Reverte proporcionalmente a comissão quando o recebimento é estornado."""
    alloc = (
        await db.execute(
            text(
                """
                SELECT id, bruto_recebido, valor_advogado, valor_escritorio
                FROM case_receipt_allocations
                WHERE fee_payment_id=:payment_id
                """
            ),
            {"payment_id": fee_payment_id},
        )
    ).mappings().first()
    if not alloc:
        return None

    bruto = money(alloc["bruto_recebido"])
    estorno = money(valor_estorno)
    if bruto <= 0 or estorno <= 0:
        return None
    proporcao = min(estorno / bruto, Decimal("1"))
    delta_adv = -money(money(alloc["valor_advogado"]) * proporcao)
    delta_esc = -money(money(alloc["valor_escritorio"]) * proporcao)

    return await registrar_ajuste_comissao(
        db,
        allocation_id=alloc["id"],
        valor_advogado=delta_adv,
        valor_escritorio=delta_esc,
        motivo=f"Estorno proporcional do recebimento: {motivo}",
        user=user,
        source_type="estorno",
        fee_estorno_id=fee_estorno_id,
    )
