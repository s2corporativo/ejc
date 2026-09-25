"""Gestão econômica do caso integrada ao ledger financeiro canônico."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, text

from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.fee import CaseReceiptAllocation, Fee, FeeEstorno, FeePayment, FeeStatus, FeeTipo
from app.models.socio import Socio

_Q2 = Decimal("0.01")

def _money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(_Q2, ROUND_HALF_UP)


def calcular_rateio_recebimento(area: str, valor, vara: str | None = None) -> dict:
    """Destinação de honorários efetivamente recebidos.

    Regra geral de produção: 50% responsável / 50% escritório.
    Carteira institucional cível/consumidor/JEC: 100% escritório.
    """
    bruto = _money(valor)
    area_norm = str(area or "").strip().casefold()
    vara_norm = str(vara or "").strip().casefold()
    integral_escritorio = (
        area_norm in {"civil", "consumidor"}
        or "juizado especial" in vara_norm
    )
    pct_adv = Decimal("0.00") if integral_escritorio else Decimal("50.00")
    valor_adv = _money(bruto * pct_adv / Decimal("100"))
    return {
        "percentual_advogado": pct_adv,
        "valor_advogado": valor_adv,
        "valor_escritorio": _money(bruto - valor_adv),
        "regra": "institucional_integral_escritorio" if integral_escritorio else "rateio_50_50",
    }

async def resumo_financeiro_caso(db, case: Case) -> dict:
    pagamentos = (await db.execute(
        select(func.coalesce(func.sum(FeePayment.valor), 0))
        .join(Fee, Fee.id == FeePayment.fee_id)
        .where(Fee.case_id == case.id, Fee.deleted_at.is_(None))
    )).scalar()
    estornos = (await db.execute(
        select(func.coalesce(func.sum(FeeEstorno.valor), 0))
        .join(Fee, Fee.id == FeeEstorno.fee_id)
        .where(Fee.case_id == case.id, Fee.deleted_at.is_(None))
    )).scalar()
    recebido = max(_money(pagamentos) - _money(estornos), Decimal("0.00"))

    rows = (await db.execute(
        select(
            CaseReceiptAllocation.percentual_advogado,
            FeePayment.valor,
            func.coalesce(func.sum(FeeEstorno.valor), 0).label("estornado"),
        )
        .join(FeePayment, FeePayment.id == CaseReceiptAllocation.fee_payment_id)
        .outerjoin(FeeEstorno, FeeEstorno.fee_payment_id == FeePayment.id)
        .where(CaseReceiptAllocation.case_id == case.id)
        .group_by(CaseReceiptAllocation.id, CaseReceiptAllocation.percentual_advogado, FeePayment.valor)
    )).all()
    adv = Decimal("0.00")
    esc = Decimal("0.00")
    for pct, bruto, estornado in rows:
        efetivo = max(_money(bruto) - _money(estornado), Decimal("0.00"))
        pct_dec = Decimal(str(pct or 0)) / Decimal("100")
        parte_adv = _money(efetivo * pct_dec)
        adv += parte_adv
        esc += _money(efetivo - parte_adv)

    return {
        "classificacao_financeira": case.classificacao_financeira or "normal",
        "valor_pleiteado": _money(case.valor_pleiteado) if case.valor_pleiteado is not None else None,
        "valor_recebido": _money(recebido),
        "credito_advogado": _money(adv),
        "parcela_escritorio": _money(esc),
        "pendente_sucumbencia": bool(case.pendente_sucumbencia),
        "pendente_exito": bool(case.pendente_exito),
        "regra_rateio": calcular_rateio_recebimento(
            getattr(case.area, "value", case.area), Decimal("1.00"), case.vara
        )["regra"],
    }

async def registrar_recebimento_caso(db, case: Case, valor, user) -> dict:
    valor = _money(valor)
    if valor <= 0:
        raise HTTPException(422, "O valor recebido deve ser maior que zero")

    area = getattr(case.area, "value", case.area)
    rateio = calcular_rateio_recebimento(area, valor, case.vara)
    if rateio["percentual_advogado"] > 0 and not case.advogado_responsavel_id:
        raise HTTPException(422, "Caso sem advogado responsável: defina o responsável antes do rateio 50/50")

    fid = str(uuid4())
    pid = str(uuid4())
    fee = Fee(
        id=fid, tipo=FeeTipo.misto, status=FeeStatus.pago,
        descricao="Honorários recebidos — lançamento pelo caso",
        valor=valor, data_pagamento=date.today(), client_id=case.client_id, case_id=case.id,
        observacoes="Recebimento lançado pela ficha do caso; rateio automático auditável.",
    )
    payment = FeePayment(
        id=pid, fee_id=fid, valor=valor, data_pagamento=date.today(), forma="outro"
    )
    db.add(fee)
    db.add(payment)
    # O rateio referencia fee_payments por FK. Sem flush explícito, o UoW
    # pode tentar inserir CaseReceiptAllocation antes do FeePayment porque não
    # há relacionamento ORM entre os objetos — falha observada em produção.
    await db.flush()

    pct_adv = rateio["percentual_advogado"]
    valor_adv = rateio["valor_advogado"]
    valor_esc = rateio["valor_escritorio"]
    alloc = CaseReceiptAllocation(
        id=str(uuid4()), case_id=case.id, fee_payment_id=pid,
        advogado_responsavel_id=case.advogado_responsavel_id,
        percentual_advogado=pct_adv, valor_advogado=valor_adv, valor_escritorio=valor_esc,
        regra=rateio["regra"],
    )
    db.add(alloc)

    # Crédito do responsável entra na fila societária quando ele é sócio ativo.
    # A retirada permanece pendente de aprovação, preservando segregação de funções.
    withdrawal_id = None
    if valor_adv > 0 and case.advogado_responsavel_id:
        socio_ativo = (await db.execute(
            select(Socio.id).where(
                Socio.user_id == case.advogado_responsavel_id,
                Socio.ativo.is_(True),
            )
        )).scalar_one_or_none()
        if socio_ativo:
            withdrawal_id = str(uuid4())
            await db.execute(text("""
                INSERT INTO partner_withdrawals
                    (id, partner_id, gross_value, case_expenses, net_value, partner_share,
                     description, period_reference, status, created_at, updated_at)
                VALUES
                    (:id, :partner_id, :gross, 0, :net, :share,
                     :description, :ref, 'pendente', now(), now())
            """), {
                "id": withdrawal_id,
                "partner_id": case.advogado_responsavel_id,
                "gross": valor,
                "net": valor,
                "share": valor_adv,
                "description": f"Rateio automático — {case.numero_interno or case.id}",
                "ref": f"case:{pid[:30]}",
            })

    await criar_audit_log(
        db, user.id, user.role.value, "CREATE", "case_receipt_allocations", alloc.id,
        detalhes="Recebimento do caso lançado no financeiro com rateio automático.",
        dados_depois={
            "case_id": case.id, "fee_id": fid, "fee_payment_id": pid,
            "valor": str(valor), "percentual_advogado": str(pct_adv),
            "valor_advogado": str(valor_adv), "valor_escritorio": str(valor_esc),
            "regra": alloc.regra, "withdrawal_id": withdrawal_id,
        },
    )
    return {
        "fee_id": fid, "fee_payment_id": pid, "valor": valor,
        "valor_advogado": valor_adv, "valor_escritorio": valor_esc,
        "percentual_advogado": pct_adv, "regra": alloc.regra,
        "withdrawal_id": withdrawal_id,
    }
