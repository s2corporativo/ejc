"""
honorarios_calc.py — Inteligência financeira DETERMINÍSTICA (#52, #53).

- Provisionamento de sucumbência (art. 85, §2º, CPC: 10%–20%).
- Teto ético: alerta se honorários totais estimados > 50% do proveito econômico.

SEM IA — cálculo puro sobre dados reais do caso/honorários. Resultado é
estimativa referencial (rascunho); o advogado define os valores finais.
Aditivo e isolado — não altera nenhum fluxo existente.
"""
from __future__ import annotations
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.case import Case
from app.models.fee import Fee, FeeTipo, FeeStatus

router = APIRouter(prefix="/honorarios-calc", tags=["Honorários — Cálculo"])

SUC_MIN = Decimal("0.10")      # art. 85 §2º CPC — piso
SUC_MAX = Decimal("0.20")      # art. 85 §2º CPC — teto
SUC_PROV = Decimal("0.15")     # provável (meio da faixa)
TETO_ETICO = Decimal("0.50")   # alerta se honorários > 50% do proveito
_CENT = Decimal("0.01")


def _f(x):
    return float(x) if x is not None else None


async def _get_case(db: AsyncSession, case_id: str) -> Case:
    c = (await db.execute(
        select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Caso não encontrado")
    return c


@router.get("/cases/{case_id}/provisionamento")
async def provisionamento(
    case_id: str,
    condenacao: float | None = Query(None, description="Base alternativa (condenação estimada)"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Provisão de sucumbência (art. 85 §2º CPC) sobre valor da causa ou condenação."""
    c = await _get_case(db, case_id)
    base = Decimal(str(condenacao)) if condenacao is not None else (c.valor_causa or Decimal("0"))
    if base <= 0:
        return {"ok": False, "aviso": "Caso sem valor da causa/condenação — informe ?condenacao=."}
    return {
        "ok": True,
        "base": _f(base),
        "sucumbencia_min": _f((base * SUC_MIN).quantize(_CENT)),
        "sucumbencia_provavel": _f((base * SUC_PROV).quantize(_CENT)),
        "sucumbencia_max": _f((base * SUC_MAX).quantize(_CENT)),
        "fundamento": "Art. 85, §2º, CPC — honorários de sucumbência fixados entre 10% e 20%.",
        "observacao": ("Estimativa determinística. Fazenda Pública segue as faixas do §3º "
                       "(verificar). Não inclui correção monetária/juros."),
    }


@router.get("/cases/{case_id}/teto-etico")
async def teto_etico(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Soma honorários contratuais + sucumbência estimada e alerta se > 50% do proveito."""
    c = await _get_case(db, case_id)
    proveito = c.valor_causa or Decimal("0")
    fees = (await db.execute(
        select(Fee).where(
            Fee.case_id == case_id, Fee.deleted_at.is_(None),
            Fee.status != FeeStatus.cancelado,
        )
    )).scalars().all()

    contratual = Decimal("0")
    for f in fees:
        if f.tipo == FeeTipo.custas_despesas:
            continue
        if f.valor:
            contratual += f.valor
        elif f.tipo in (FeeTipo.exito, FeeTipo.misto) and f.percentual_exito and proveito:
            contratual += (proveito * (f.percentual_exito / Decimal("100")))

    sucumbencia = (proveito * SUC_PROV) if proveito else Decimal("0")
    total = contratual + sucumbencia
    alerta = bool(proveito) and total > (proveito * TETO_ETICO)
    return {
        "proveito_economico": _f(proveito),
        "honorarios_contratuais": _f(contratual.quantize(_CENT)),
        "sucumbencia_estimada": _f(sucumbencia.quantize(_CENT)),
        "total_honorarios": _f(total.quantize(_CENT)),
        "percentual_sobre_proveito": _f((total / proveito * 100).quantize(Decimal("0.1"))) if proveito else None,
        "alerta_teto": alerta,
        "mensagem": ("⚠️ Honorários totais estimados superam 50% do proveito econômico — "
                     "revisar adequação ética (EOAB/quota litis)."
                     if alerta else "Dentro do parâmetro de referência (≤ 50% do proveito)."),
        "observacao": "Cálculo determinístico referencial. Proveito aproximado pelo valor da causa.",
    }
