from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text


def competencia_de_data(value: date | datetime | None) -> str:
    d = value.date() if isinstance(value, datetime) else value
    d = d or date.today()
    return f"{d.year}-{d.month:02d}"


async def competencia_fechada(db, competencia: str) -> bool:
    row = (
        await db.execute(
            text("SELECT id FROM finance_month_closings WHERE competencia=:c"),
            {"c": competencia},
        )
    ).scalar_one_or_none()
    return bool(row)


async def exigir_competencia_aberta(db, competencia: str, acao: str) -> None:
    if await competencia_fechada(db, competencia):
        raise HTTPException(
            409,
            (
                f"Competência {competencia} já está fechada. "
                f"{acao} não pode reescrever um mês fechado; registre a correção "
                "como novo ajuste/estorno na competência atual."
            ),
        )


async def limite_dupla_aprovacao(db) -> Decimal:
    valor = (
        await db.execute(
            text(
                """
                SELECT double_approval_threshold
                FROM finance_policy_settings
                WHERE id='default'
                """
            )
        )
    ).scalar_one_or_none()
    return Decimal(str(valor if valor is not None else 10000))


async def solicitar_ou_consumir_aprovacao(
    db,
    *,
    entity_type: str,
    entity_id: str,
    amount,
    user,
    reason: str,
) -> dict:
    valor = Decimal(str(amount or 0))
    limite = await limite_dupla_aprovacao(db)
    if valor < limite:
        return {"required": False, "threshold": limite}

    aprovado = (
        await db.execute(
            text(
                """
                SELECT id, requested_by, approved_by
                FROM finance_payment_approvals
                WHERE entity_type=:t AND entity_id=:id AND status='aprovado'
                ORDER BY approved_at DESC
                LIMIT 1
                FOR UPDATE
                """
            ),
            {"t": entity_type, "id": entity_id},
        )
    ).mappings().first()
    if aprovado:
        await db.execute(
            text(
                """
                UPDATE finance_payment_approvals
                SET status='consumido'
                WHERE id=:id
                """
            ),
            {"id": aprovado["id"]},
        )
        return {
            "required": False,
            "consumed_approval_id": aprovado["id"],
            "threshold": limite,
        }

    pendente = (
        await db.execute(
            text(
                """
                SELECT id
                FROM finance_payment_approvals
                WHERE entity_type=:t AND entity_id=:id AND status='pendente'
                ORDER BY requested_at DESC
                LIMIT 1
                """
            ),
            {"t": entity_type, "id": entity_id},
        )
    ).scalar_one_or_none()
    if pendente:
        return {
            "required": True,
            "approval_id": pendente,
            "threshold": limite,
        }

    aid = str(uuid4())
    await db.execute(
        text(
            """
            INSERT INTO finance_payment_approvals
                (id,entity_type,entity_id,amount,status,requested_by,
                 requested_at,reason,metadata_json)
            VALUES
                (:id,:t,:entity_id,:amount,'pendente',:requested_by,
                 NOW(),:reason,CAST(:metadata AS jsonb))
            """
        ),
        {
            "id": aid,
            "t": entity_type,
            "entity_id": entity_id,
            "amount": valor,
            "requested_by": getattr(user, "id", None),
            "reason": reason,
            "metadata": "{}",
        },
    )
    return {
        "required": True,
        "approval_id": aid,
        "threshold": limite,
    }


async def aprovar_solicitacao(db, approval_id: str, user) -> dict:
    row = (
        await db.execute(
            text(
                """
                SELECT id,status,requested_by,amount,entity_type,entity_id
                FROM finance_payment_approvals
                WHERE id=:id
                FOR UPDATE
                """
            ),
            {"id": approval_id},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(404, "Solicitação de aprovação não encontrada")
    if row["status"] != "pendente":
        raise HTTPException(409, f"Solicitação já está {row['status']}")
    if str(row["requested_by"]) == str(getattr(user, "id", "")):
        raise HTTPException(
            403,
            "A segunda aprovação deve ser realizada por outro usuário autorizado.",
        )
    await db.execute(
        text(
            """
            UPDATE finance_payment_approvals
            SET status='aprovado',approved_by=:uid,approved_at=:now
            WHERE id=:id
            """
        ),
        {
            "uid": getattr(user, "id", None),
            "now": datetime.now(timezone.utc),
            "id": approval_id,
        },
    )
    return dict(row) | {
        "status": "aprovado",
        "approved_by": getattr(user, "id", None),
    }


async def resultado_escritorio_competencia(db, competencia: str) -> Decimal:
    ano, mes = (int(v) for v in competencia.split("-"))
    inicio = date(ano, mes, 1)
    fim = date(ano + (1 if mes == 12 else 0), 1 if mes == 12 else mes + 1, 1)
    row = (
        await db.execute(
            text(
                """
                WITH eventos_caixa AS (
                    SELECT f.case_id, fp.valor AS valor
                    FROM fee_payments fp
                    JOIN fees f ON f.id=fp.fee_id
                    WHERE f.deleted_at IS NULL
                      AND f.case_id IS NOT NULL
                      AND fp.data_pagamento >= :inicio AND fp.data_pagamento < :fim
                    UNION ALL
                    SELECT f.case_id, -fe.valor AS valor
                    FROM fee_estornos fe
                    JOIN fees f ON f.id=fe.fee_id
                    WHERE f.deleted_at IS NULL
                      AND f.case_id IS NOT NULL
                      AND fe.data_estorno >= :inicio AND fe.data_estorno < :fim
                ),
                despesas AS (
                    SELECT case_id, COALESCE(SUM(valor),0) AS valor
                    FROM centro_custos
                    WHERE deleted_at IS NULL
                      AND CAST(tipo AS text)='despesa'
                      AND pago=TRUE
                      AND COALESCE(data_pagamento,data_lancamento) >= :inicio
                      AND COALESCE(data_pagamento,data_lancamento) < :fim
                    GROUP BY case_id
                ),
                comissoes_base AS (
                    SELECT a.case_id, SUM(a.valor_advogado) AS valor
                    FROM case_receipt_allocations a
                    JOIN fee_payments fp ON fp.id=a.fee_payment_id
                    WHERE fp.data_pagamento >= :inicio AND fp.data_pagamento < :fim
                    GROUP BY a.case_id
                ),
                ajustes AS (
                    SELECT a.case_id, COALESCE(SUM(ca.valor_advogado),0) AS valor
                    FROM commission_adjustments ca
                    JOIN case_receipt_allocations a ON a.id=ca.allocation_id
                    WHERE ca.created_at >= :inicio AND ca.created_at < :fim
                    GROUP BY a.case_id
                ),
                receitas AS (
                    SELECT case_id, COALESCE(SUM(valor),0) AS valor
                    FROM eventos_caixa
                    GROUP BY case_id
                )
                , despesas_escritorio AS (
                    SELECT COALESCE(SUM(valor),0) AS valor
                    FROM office_expenses
                    WHERE deleted_at IS NULL
                      AND status='pago'
                      AND pago_em >= :inicio
                      AND pago_em < :fim
                )
                SELECT
                    COALESCE(SUM(r.valor),0)
                    - COALESCE((SELECT SUM(valor) FROM despesas),0)
                    - COALESCE((SELECT SUM(valor) FROM comissoes_base),0)
                    - COALESCE((SELECT SUM(valor) FROM ajustes),0)
                    - COALESCE((SELECT valor FROM despesas_escritorio),0) AS resultado
                FROM receitas r
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).scalar()
    return Decimal(str(row or 0)).quantize(Decimal("0.01"))


async def resultado_disponivel_distribuicao(db, competencia: str) -> dict:
    fechado = await competencia_fechada(db, competencia)
    resultado = await resultado_escritorio_competencia(db, competencia)
    distribuido = (
        await db.execute(
            text(
                """
                SELECT COALESCE(SUM(valor_total),0)
                FROM distribuicoes_lucro
                WHERE mes_referencia=:competencia
                  AND status IN ('calculado','aprovado','pago')
                """
            ),
            {"competencia": competencia},
        )
    ).scalar()
    distribuido = Decimal(str(distribuido or 0)).quantize(Decimal("0.01"))
    return {
        "competencia": competencia,
        "fechado": fechado,
        "resultado_escritorio": resultado,
        "ja_distribuido": distribuido,
        "disponivel": max(resultado - distribuido, Decimal("0.00")),
    }
