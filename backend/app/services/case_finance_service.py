"""Gestão econômica do caso integrada ao ledger financeiro canônico."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import exists, func, select, text

from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.fee import CaseReceiptAllocation, Fee, FeeEstorno, FeePayment, FeeStatus, FeeTipo
from app.models.socio import Socio
from app.models.user import User

_Q2 = Decimal("0.01")

def _money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(_Q2, ROUND_HALF_UP)


def calcular_rateio_recebimento(area: str, valor, vara: str | None = None) -> dict:
    """Destinação de honorários efetivamente recebidos.

    Regra geral de produção: 50% responsável / 50% escritório.
    Exceção definida pelo escritório: área civil = 100% escritório.
    """
    bruto = _money(valor)
    area_norm = str(area or "").strip().casefold()
    # A regra é por área jurídica, não por rito/órgão julgador.
    # JEC e Consumidor só serão 100% escritório quando o caso estiver
    # efetivamente classificado na área canônica civil.
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
                Fee.descricao.ilike("Honorários recebidos%"),
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

    regra_atual = calcular_rateio_recebimento(
        getattr(case.area, "value", case.area), Decimal("1.00"), case.vara
    )["regra"]

    return {
        "classificacao_financeira": case.classificacao_financeira or "normal",
        "valor_pleiteado": _money(case.valor_pleiteado) if case.valor_pleiteado is not None else None,
        "valor_recebido": _money(recebido),
        "credito_advogado": _money(adv),
        "parcela_escritorio": _money(esc),
        "pendente_sucumbencia": bool(case.pendente_sucumbencia),
        "pendente_exito": bool(case.pendente_exito),
        "regra_rateio": regra_atual,
        "advogado_responsavel_id": case.advogado_responsavel_id,
        "advogado_responsavel_nome": responsavel_nome,
        "rateio_pendente_quantidade": len(pagamentos_sem_rateio),
        "rateio_pendente_valor": _money(pendente_rateio_valor),
        "rateio_pendente_sem_responsavel": bool(
            regra_atual == "rateio_50_50" and not case.advogado_responsavel_id
        ),
    }

async def registrar_recebimento_caso(db, case: Case, valor, user) -> dict:
    valor = _money(valor)
    if valor <= 0:
        raise HTTPException(422, "O valor recebido deve ser maior que zero")

    area = getattr(case.area, "value", case.area)
    rateio = calcular_rateio_recebimento(area, valor, case.vara)
    # O recebimento e fato financeiro e nao deve ser perdido por falta de
    # responsavel. Sem responsavel, a regra 50/50 fica pendente e nenhuma
    # parcela e atribuida ate revisao humana.
    rateio_pendente = bool(
        rateio["percentual_advogado"] > 0 and not case.advogado_responsavel_id
    )

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
    # Persistir explicitamente em ordem de dependência evita que o UoW tente
    # inserir a alocação antes do FeePayment em bancos PostgreSQL com FK ativa.
    db.add(fee)
    await db.flush()
    db.add(payment)
    await db.flush()

    pct_adv = rateio["percentual_advogado"]
    valor_adv = rateio["valor_advogado"]
    valor_esc = rateio["valor_escritorio"]
    alloc = None
    withdrawal_id = None

    if not rateio_pendente:
        alloc = CaseReceiptAllocation(
            id=str(uuid4()), case_id=case.id, fee_payment_id=pid,
            advogado_responsavel_id=case.advogado_responsavel_id,
            percentual_advogado=pct_adv, valor_advogado=valor_adv, valor_escritorio=valor_esc,
            regra=rateio["regra"],
        )
        db.add(alloc)

        # Credito do responsavel entra na fila societaria quando ele e socio ativo.
        # A retirada permanece pendente de aprovacao, preservando segregacao de funcoes.
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
                    "gross": valor_adv,
                    "net": valor_adv,
                    "share": valor_adv,
                    "description": f"Rateio automatico - {case.numero_interno or case.id}",
                    "ref": f"case:{pid[:30]}",
                })

        await criar_audit_log(
            db, user.id, user.role.value, "CREATE", "case_receipt_allocations", alloc.id,
            detalhes="Recebimento do caso lancado no financeiro com rateio automatico.",
            dados_depois={
                "case_id": case.id, "fee_id": fid, "fee_payment_id": pid,
                "valor": str(valor), "percentual_advogado": str(pct_adv),
                "valor_advogado": str(valor_adv), "valor_escritorio": str(valor_esc),
                "regra": alloc.regra, "withdrawal_id": withdrawal_id,
            },
        )
    else:
        await criar_audit_log(
            db, user.id, user.role.value, "CREATE", "fee_payments", pid,
            detalhes=(
                "Recebimento registrado sem rateio: caso ainda nao possui "
                "advogado responsavel. Rateio 50/50 pendente de revisao humana."
            ),
            dados_depois={
                "case_id": case.id,
                "fee_id": fid,
                "fee_payment_id": pid,
                "valor": str(valor),
                "regra_prevista": rateio["regra"],
                "rateio_pendente": True,
            },
        )

    return {
        "fee_id": fid,
        "fee_payment_id": pid,
        "valor": valor,
        "valor_advogado": None if rateio_pendente else valor_adv,
        "valor_escritorio": None if rateio_pendente else valor_esc,
        "percentual_advogado": None if rateio_pendente else pct_adv,
        "regra": rateio["regra"],
        "rateio_pendente": rateio_pendente,
        "allocation_id": alloc.id if alloc else None,
        "withdrawal_id": withdrawal_id,
    }


async def reconciliar_rateios_pendentes(db, case: Case, user) -> dict:
    """Aloca recebimentos antigos somente após o responsável estar definido.

    A ação é explícita e auditada. Nenhum advogado é inferido por nome,
    proximidade ou histórico. Em carteira civil (100% escritório), responsável
    não é necessário porque não existe crédito pessoal.
    """
    area = getattr(case.area, "value", case.area)
    regra_base = calcular_rateio_recebimento(area, Decimal("1.00"), case.vara)
    if regra_base["percentual_advogado"] > 0 and not case.advogado_responsavel_id:
        raise HTTPException(
            422,
            "Defina o advogado responsável antes de reconciliar o rateio 50/50.",
        )

    pagamentos = (
        await db.execute(
            select(FeePayment)
            .join(Fee, Fee.id == FeePayment.fee_id)
            .where(
                Fee.case_id == case.id,
                Fee.deleted_at.is_(None),
                Fee.descricao.ilike("Honorários recebidos%"),
                ~exists().where(
                    CaseReceiptAllocation.fee_payment_id == FeePayment.id
                ),
            )
            .order_by(FeePayment.created_at)
            .with_for_update()
        )
    ).scalars().all()

    if not pagamentos:
        return {
            "reconciliados": 0,
            "valor_total": Decimal("0.00"),
            "credito_advogado": Decimal("0.00"),
            "parcela_escritorio": Decimal("0.00"),
            "allocation_ids": [],
        }

    socio_ativo = None
    if case.advogado_responsavel_id:
        socio_ativo = (
            await db.execute(
                select(Socio.id).where(
                    Socio.user_id == case.advogado_responsavel_id,
                    Socio.ativo.is_(True),
                )
            )
        ).scalar_one_or_none()

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
        rateio = calcular_rateio_recebimento(area, efetivo, case.vara)
        allocation_id = str(uuid4())
        alloc = CaseReceiptAllocation(
            id=allocation_id,
            case_id=case.id,
            fee_payment_id=payment.id,
            advogado_responsavel_id=case.advogado_responsavel_id,
            percentual_advogado=rateio["percentual_advogado"],
            valor_advogado=rateio["valor_advogado"],
            valor_escritorio=rateio["valor_escritorio"],
            regra=rateio["regra"],
        )
        db.add(alloc)
        allocation_ids.append(allocation_id)
        total += efetivo
        total_adv += rateio["valor_advogado"]
        total_esc += rateio["valor_escritorio"]

        if (
            socio_ativo
            and rateio["valor_advogado"] > 0
            and case.advogado_responsavel_id
        ):
            withdrawal_id = str(uuid4())
            withdrawal_ids.append(withdrawal_id)
            await db.execute(
                text("""
                    INSERT INTO partner_withdrawals
                        (id, partner_id, gross_value, case_expenses, net_value,
                         partner_share, description, period_reference, status,
                         created_at, updated_at)
                    VALUES
                        (:id, :partner_id, :gross, 0, :net, :share,
                         :description, :ref, 'pendente', now(), now())
                """),
                {
                    "id": withdrawal_id,
                    "partner_id": case.advogado_responsavel_id,
                    "gross": rateio["valor_advogado"],
                    "net": rateio["valor_advogado"],
                    "share": rateio["valor_advogado"],
                    "description": (
                        f"Rateio reconciliado — {case.numero_interno or case.id}"
                    ),
                    "ref": f"case:{payment.id[:30]}",
                },
            )

    await criar_audit_log(
        db,
        user.id,
        user.role.value,
        "RECONCILIAR_RATEIO",
        "cases",
        case.id,
        detalhes="Rateios pendentes reconciliados após confirmação do responsável.",
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
    }
