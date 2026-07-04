# ── app/routers/visual_law.py ────────────────────────────────────────────────
# Calculadora de acordo (breakeven do litígio) — backend do componente
# frontend/src/components/visual/CalculadoraAcordo.tsx (POST /visual-law/breakeven).
#
# Compara o valor presente do litígio (VPL) com um acordo imediato:
#   valor_esperado = valor_causa × prob_exito
#   custos = custas + honorários de sucumbência ponderados pela chance de perda
#   VPL = (valor_esperado − custos) / (1 + selic_anual)^tempo_anos
#
# Selic: tenta a série mensal 4390 do BCB (últimos 12 meses, composta para
# taxa anual); indisponível → fallback documentado. Nenhum número é inventado:
# toda premissa aparece em `memoria_calculo`.
from __future__ import annotations

import logging
from datetime import date, timedelta
from math import pow as _pow
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

logger = logging.getLogger("ejc.visual_law")

router = APIRouter(prefix="/visual-law", tags=["Visual Law"])

# Fallback quando o BCB está fora do ar (taxa anual, documentada na memória).
SELIC_ANUAL_FALLBACK = 0.1075

# Tempo médio de tramitação usado quando o advogado não informa (estimativa
# conservadora de conhecimento geral; sempre explicitada na memória de cálculo).
TEMPO_ANOS_PADRAO = 3.0


class BreakevenRequest(BaseModel):
    valor_causa: float = Field(gt=0, le=1e12)
    prob_exito: float = Field(ge=0, le=1)
    tempo_anos: Optional[float] = Field(default=None, gt=0, le=50)
    tribunal: Optional[str] = Field(default=None, max_length=120)
    custas_pct: float = Field(default=0.0, ge=0, le=100)
    honorarios_sucumbencia_pct: float = Field(default=0.0, ge=0, le=100)
    selic_anual: Optional[float] = Field(default=None, gt=0, le=1)
    case_id: Optional[str] = None


async def _selic_anual_bcb() -> Optional[float]:
    """Taxa Selic anualizada a partir da série mensal 4390 (últimos 12 meses).
    Retorna None se o BCB estiver indisponível — o caller aplica o fallback."""
    try:
        from app.services.bcb_service import _buscar_serie, SERIES

        fim = date.today()
        ini = fim - timedelta(days=370)
        serie = await _buscar_serie(SERIES["selic"]["codigo"], ini, fim)
        meses = serie[-12:]
        if not meses:
            return None
        fator = 1.0
        for item in meses:
            fator *= 1.0 + float(item["valor"].replace(",", ".")) / 100.0
        # Anualiza pela média geométrica quando vieram menos de 12 meses.
        if len(meses) < 12:
            fator = _pow(fator, 12.0 / len(meses))
        return round(fator - 1.0, 6)
    except Exception as e:  # rede/formatação — nunca derruba o cálculo
        logger.warning(f"[visual-law] Selic BCB indisponível ({str(e)[:120]})")
        return None


@router.post("/breakeven")
async def breakeven(
    req: BreakevenRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if req.case_id:
        from app.core.ownership import verificar_acesso_caso

        await verificar_acesso_caso(db, cu, req.case_id)

    memoria: list[str] = []

    # ── Selic (parâmetro explícito > BCB > fallback) ─────────────────────────
    if req.selic_anual is not None:
        selic, selic_fonte = req.selic_anual, "usuario"
        memoria.append(f"Selic anual informada pelo usuário: {selic:.2%}.")
    else:
        selic_bcb = await _selic_anual_bcb()
        if selic_bcb is not None:
            selic, selic_fonte = selic_bcb, "bcb"
            memoria.append(
                f"Selic anualizada da série 4390 do BCB (últimos 12 meses): {selic:.2%}."
            )
        else:
            selic, selic_fonte = SELIC_ANUAL_FALLBACK, "fallback"
            memoria.append(
                f"BCB indisponível — usando Selic de referência {selic:.2%} "
                "(confira a taxa vigente antes de decidir)."
            )

    tempo = req.tempo_anos if req.tempo_anos is not None else TEMPO_ANOS_PADRAO
    if req.tempo_anos is None:
        memoria.append(
            f"Tempo de tramitação não informado — usando estimativa padrão de "
            f"{TEMPO_ANOS_PADRAO:.1f} anos (ajuste conforme a vara/tribunal)."
        )

    # ── Cálculo ──────────────────────────────────────────────────────────────
    valor_esperado = req.valor_causa * req.prob_exito
    memoria.append(
        f"Valor esperado = R$ {req.valor_causa:,.2f} × {req.prob_exito:.0%} "
        f"= R$ {valor_esperado:,.2f}."
    )

    custas = req.valor_causa * req.custas_pct / 100.0
    sucumbencia = req.valor_causa * req.honorarios_sucumbencia_pct / 100.0 * (1.0 - req.prob_exito)
    custos = custas + sucumbencia
    memoria.append(
        f"Custos estimados = custas R$ {custas:,.2f} "
        f"({req.custas_pct:.1f}%) + sucumbência ponderada pela chance de perda "
        f"R$ {sucumbencia:,.2f} ({req.honorarios_sucumbencia_pct:.1f}% × "
        f"{1.0 - req.prob_exito:.0%}) = R$ {custos:,.2f}."
    )

    liquido_esperado = valor_esperado - custos
    fator_desconto = _pow(1.0 + selic, tempo)
    vpl = liquido_esperado / fator_desconto
    memoria.append(
        f"VPL do litígio = R$ {liquido_esperado:,.2f} / (1 + {selic:.2%})^"
        f"{tempo:.1f} = R$ {vpl:,.2f}."
    )

    custo_do_tempo = liquido_esperado - vpl
    memoria.append(
        f"Custo do tempo (o que a espera consome do valor líquido esperado): "
        f"R$ {custo_do_tempo:,.2f}."
    )
    memoria.append(
        "Breakeven: um acordo imediato igual ou superior ao VPL equivale "
        "financeiramente a litigar até o fim — acima disso, o acordo tende a "
        "ser vantajoso. Premissas devem ser validadas pelo advogado (HITL)."
    )

    return {
        "parametros": {
            "valor_causa": req.valor_causa,
            "prob_exito": req.prob_exito,
            "tempo_anos": tempo,
            "tribunal": req.tribunal,
            "selic_anual": selic,
            "selic_fonte": selic_fonte,
            "custas_pct": req.custas_pct,
            "honorarios_sucumbencia_pct": req.honorarios_sucumbencia_pct,
        },
        "valor_esperado": round(valor_esperado, 2),
        "custos_estimados": round(custos, 2),
        "vpl_litigio": round(vpl, 2),
        "sugestao_acordo": round(vpl, 2),
        "breakeven": round(vpl, 2),
        "comparativo": {
            "litigio_vpl": round(vpl, 2),
            "acordo_imediato_equivalente": round(vpl, 2),
            "custo_do_tempo": round(custo_do_tempo, 2),
        },
        "memoria_calculo": memoria,
    }
