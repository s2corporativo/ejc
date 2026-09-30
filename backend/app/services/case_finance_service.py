"""Gestão econômica do caso integrada ao ledger financeiro canônico."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import exists, func, select

from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.fee import CaseReceiptAllocation, Fee, FeeEstorno, FeePayment, FeeStatus, FeeTipo
from app.models.user import User
from app.services.commission_service import alocar_comissao_pagamento, resolver_regra_comissao

_Q2 = Decimal("0.01")


def _money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(_Q2, ROUND_HALF_UP)


def calcular_rateio_recebimento(area: str, valor, vara: str | None = None) -> dict:
    """Compatibilidade determinística para consumidores antigos/testes.

    Novos lançamentos usam commission_rules via commission_service.
    """
    bruto = _money(valor)
    area_norm = str(area or "").strip().casefold()
    integral_escritorio = area_norm == "civil"
    pct_adv = Decimal("0.00") if integral_escritorio else Decimal("50.00")
    valor_adv = _money(bruto * pct_adv / Decimal("100"))
    return {
        "percentual_advogado": pct_adv,
        "valor_advogado": valor_adv,
        "valor_escritorio": _money(bruto - valor_adv),
        "regra": "institucional_integral_escritorio" if integral_escritorio else "rateio_50_50",
    }


async def resumo_financeiro_caso(db, case: Case) -> dict:
    pagamentos = (
        await db.execute(
            select(func.coalesce(func.sum(FeePayment.valor), 0))
            .join(Fee, Fee.id == FeePayment.fee_id)
            .where(Fee.case_id == case.id, Fee.deleted_at.is_(None))
        )
    ).scalar()
    estornos = (
        await db.execute(
            select(func.coalesce(func.sum(FeeEstorno.valor), 0))
            .join(Fee, Fee.id == FeeEstorno.fee_id)
            .where(Fee.case_id == case.id, Fee.deleted_at.is_(None))
        )
    ).scalar()
    recebido = max(_money(pagamentos) - _money(estornos), Decimal("0.00"))

    rows = (
        await db.execute(
            select(
                CaseReceiptAllocation.valor_advogado,
                CaseReceiptAllocation.valor_escritorio,
                FeePayment.valor,
                func.coalesce(func.sum(FeeEstorno.valor), 0).label("estornado"),
            )
            .join(FeePayment, FeePayment.id == CaseReceiptAllocation.fee_payment_id)
            .outerjoin(FeeEstorno, FeeEstorno.fee_payment_id == FeePayment.id)
            .where(CaseReceiptAllocation.case_id == case.id)
            .group_by(
                CaseReceiptAllocation.id,
                CaseReceiptAllocation.valor_advogado,
                CaseReceiptAllocation.valor_escritorio,
                FeePayment.valor,
            )
        )
    ).all()
    adv = Decimal("0.00")
    esc = Decimal("0.00")
    for valor_adv, valor_esc, bruto, estornado in rows:
        bruto_dec = _money(bruto)
        efetivo = max(bruto_dec - _money(estornado), Decimal("0.00"))
        fator = (efetivo / bruto_dec) if bruto_dec > 0 else Decimal("0")
        adv += _money(_money(valor_adv) * fator)
        esc += _money(_money(valor_esc) * fator)

    pagamentos_sem_rateio = (
        await db.execute(
            select(FeePayment.id, FeePayment.valor)
            .join(Fee, Fee.id == FeePayment.fee_id)
            .outerjoin(
                CaseReceiptAllocation,
                CaseReceiptAllocation.fee_payment_id == FeePayment.id,
            )
            .where(
                Fee.case_id == case.id,
                Fee.deleted_at.is_(None),
                Fee.tipo != FeeTipo.custas_despesas,
                Fee.status != FeeStatus.cancelado,
                CaseReceiptAllocation.id.is_(None),
            )
        )
    ).all()
    ids_sem_rateio = [pid for pid, _valor in pagamentos_sem_rateio]
    estornos_sem_rateio: dict[str, Decimal] = {}
    if ids_sem_rateio:
        for payment_id, total in (
            await db.execute(
                select(
                    FeeEstorno.fee_payment_id,
                    func.coalesce(func.sum(FeeEstorno.valor), 0),
                )
                .where(FeeEstorno.fee_payment_id.in_(ids_sem_rateio))
                .group_by(FeeEstorno.fee_payment_id)
            )
        ).all():
            estornos_sem_rateio[payment_id] = _money(total)
    pendente_rateio_valor = sum(
        (
            max(
                _money(valor) - estornos_sem_rateio.get(payment_id, Decimal("0.00")),
                Decimal("0.00"),
            )
            for payment_id, valor in pagamentos_sem_rateio
        ),
        Decimal("0.00"),
    )

    responsavel_nome = None
    if case.advogado_responsavel_id:
        responsavel_nome = (
            await db.execute(
                select(User.full_name).where(User.id == case.advogado_responsavel_id)
            )
        ).scalar_one_or_none()

    regra_atual = await resolver_regra_comissao(
        db, case, case.advogado_responsavel_id, date.today()
    )

    return {
        "classificacao_financeira": case.classificacao_financeira or "normal",
        "valor_pleiteado": _money(case.valor_pleiteado) if case.valor_pleiteado is not None else None,
        "valor_recebido": _money(recebido),
        "credito_advogado": _money(adv),
        "parcela_escritorio": _money(esc),
        "pendente_sucumbencia": bool(case.pendente_sucumbencia),
        "pendente_exito": bool(case.pendente_exito),
        "regra_rateio": regra_atual.nome,
        "regra_rateio_escopo": regra_atual.escopo,
        "percentual_advogado_atual": _money(regra_atual.percentual_advogado),
        "descontar_despesas_comissao": bool(regra_atual.descontar_despesas),
        "advogado_responsavel_id": case.advogado_responsavel_id,
        "advogado_responsavel_nome": responsavel_nome,
        "rateio_pendente_quantidade": len(pagamentos_sem_rateio),
        "rateio_pendente_valor": _money(pendente_rateio_valor),
        "rateio_pendente_sem_responsavel": bool(
            _money(regra_atual.percentual_advogado) > 0
            and not case.advogado_responsavel_id
            and len(pagamentos_sem_rateio) > 0
        ),
    }


async def registrar_recebimento_caso(db, case: Case, valor, user) -> dict:
    valor = _money(valor)
    if valor <= 0:
        raise HTTPException(422, "O valor recebido deve ser maior que zero")

    fid = str(uuid4())
    pid = str(uuid4())
    fee = Fee(
        id=fid,
        tipo=FeeTipo.misto,
        status=FeeStatus.pago,
        descricao="Honorários recebidos — lançamento pelo caso",
        valor=valor,
        data_pagamento=date.today(),
        client_id=case.client_id,
        case_id=case.id,
        observacoes="Recebimento lançado pela ficha do caso; comissão automática auditável.",
    )
    payment = FeePayment(
        id=pid,
        fee_id=fid,
        valor=valor,
        data_pagamento=date.today(),
        forma="outro",
    )
    db.add(fee)
    await db.flush()
    db.add(payment)
    await db.flush()

    rateio = await alocar_comissao_pagamento(db, case, payment, user)
    return {
        "fee_id": fid,
        "fee_payment_id": pid,
        **rateio,
    }


async def reconciliar_rateios_pendentes(db, case: Case, user) -> dict:
    """Aplica a regra vigente apenas a pagamentos ainda sem alocação."""
    regra = await resolver_regra_comissao(
        db, case, case.advogado_responsavel_id, date.today()
    )
    if _money(regra.percentual_advogado) > 0 and not case.advogado_responsavel_id:
        raise HTTPException(
            422,
            "Defina o advogado responsável antes de reconciliar as comissões pendentes.",
        )

    pagamentos = (
        await db.execute(
            select(FeePayment)
            .join(Fee, Fee.id == FeePayment.fee_id)
            .where(
                Fee.case_id == case.id,
                Fee.deleted_at.is_(None),
                Fee.tipo != FeeTipo.custas_despesas,
                Fee.status != FeeStatus.cancelado,
                ~exists().where(
                    CaseReceiptAllocation.fee_payment_id == FeePayment.id
                ),
            )
            .order_by(FeePayment.created_at)
            .with_for_update()
        )
    ).scalars().all()

    total = Decimal("0.00")
    total_adv = Decimal("0.00")
    total_esc = Decimal("0.00")
    allocation_ids: list[str] = []
    withdrawal_ids: list[str] = []

    for payment in pagamentos:
        estornado = (
            await db.execute(
                select(func.coalesce(func.sum(FeeEstorno.valor), 0)).where(
                    FeeEstorno.fee_payment_id == payment.id
                )
            )
        ).scalar()
        efetivo = max(
            _money(payment.valor) - _money(estornado),
            Decimal("0.00"),
        )
        if efetivo <= 0:
            continue
        resultado = await alocar_comissao_pagamento(
            db,
            case,
            payment,
            user,
            valor_efetivo=efetivo,
        )
        if resultado.get("rateio_pendente"):
            continue
        if resultado.get("allocation_id"):
            allocation_ids.append(resultado["allocation_id"])
        if resultado.get("withdrawal_id"):
            withdrawal_ids.append(resultado["withdrawal_id"])
        total += efetivo
        total_adv += _money(resultado.get("valor_advogado"))
        total_esc += _money(resultado.get("valor_escritorio"))

    await criar_audit_log(
        db,
        user.id,
        user.role.value,
        "RECONCILIAR_COMISSOES",
        "cases",
        case.id,
        detalhes="Comissões pendentes reconciliadas após confirmação do responsável.",
        dados_depois={
            "allocation_ids": allocation_ids,
            "withdrawal_ids": withdrawal_ids,
            "advogado_responsavel_id": case.advogado_responsavel_id,
            "reconciliados": len(allocation_ids),
            "valor_total": str(_money(total)),
            "credito_advogado": str(_money(total_adv)),
            "parcela_escritorio": str(_money(total_esc)),
        },
    )
    return {
        "reconciliados": len(allocation_ids),
        "valor_total": _money(total),
        "credito_advogado": _money(total_adv),
        "parcela_escritorio": _money(total_esc),
        "allocation_ids": allocation_ids,
        "withdrawal_ids": withdrawal_ids,
    }
