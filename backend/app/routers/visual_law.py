# ── app/routers/visual_law.py ────────────────────────────────────────────────
# Visual Law — Calculadora de acordo (breakeven do litígio).
# POST /visual-law/breakeven: cálculo puro/determinístico (sem IA, sem banco).
# Contrato consumido por frontend/src/components/visual/CalculadoraAcordo.tsx
# (tipos em frontend/src/types/visualLaw.ts: BreakevenRequest/BreakevenResponse).
#
# Modelo financeiro:
#   valor_esperado    = valor_causa × prob_exito
#   custos_estimados  = valor_causa × custas% + valor_causa × sucumbência% × (1 − prob_exito)
#   líquido nominal   = valor_esperado − custos_estimados   (recebido ao fim do litígio)
#   vpl_litigio       = líquido nominal ÷ (1 + selic_anual)^tempo_anos
#   breakeven         = vpl_litigio  (acordo hoje equivalente ao litígio)
#   sugestao_acordo   = breakeven × (1 + MARGEM_NEGOCIACAO)  (margem de fechamento)
#   custo_do_tempo    = líquido nominal − vpl_litigio
#
# Selic: tenta a série SGS 432 do BCB (Meta Selic, % a.a.); em falha/timeout usa
# SELIC_FALLBACK_ANUAL. Se o cliente enviar `selic_anual`, esse valor prevalece
# (fonte reportada como "fallback", pois não veio do BCB nesta requisição).
#
# `case_id` (opcional no payload) é aceito e IGNORADO: o cálculo não lê nem
# expõe nenhum dado do caso, então não há superfície de acesso a validar.
from __future__ import annotations

import logging
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.models.user import User

logger = logging.getLogger("ejc.visual_law")

router = APIRouter(prefix="/visual-law", tags=["Visual Law"])

# Tempo médio de tramitação (anos) por tribunal — estimativas conservadoras
# (Justiça em Números/CNJ, ordem de grandeza). Usado só quando o cliente não
# informa tempo_anos.
TEMPO_MEDIO_ANOS = {
    "TJMG": 4.0,
    "TJSP": 4.5,
    "TRT3": 2.5,
    "TRF6": 5.0,
    "STJ": 3.0,
}
TEMPO_PADRAO_ANOS = 4.0
CUSTAS_PCT_PADRAO = 5.0                # % sobre o valor da causa
HONORARIOS_SUCUMBENCIA_PCT_PADRAO = 10.0  # % sobre o valor da causa (CPC art. 85 §2º, piso)
SELIC_FALLBACK_ANUAL = 0.15            # 15% a.a. quando o BCB está indisponível
MARGEM_NEGOCIACAO = 0.05               # sugestão de acordo = breakeven + 5%
_BCB_SELIC_META_URL = (
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
)


class BreakevenRequest(BaseModel):
    valor_causa: float = Field(gt=0)
    prob_exito: float = Field(ge=0, le=1, description="Probabilidade de êxito (0..1)")
    tempo_anos: Optional[float] = Field(default=None, gt=0, le=50)
    tribunal: Optional[str] = Field(default=None, max_length=40)
    custas_pct: Optional[float] = Field(default=None, ge=0, le=100)
    honorarios_sucumbencia_pct: Optional[float] = Field(default=None, ge=0, le=100)
    selic_anual: Optional[float] = Field(default=None, ge=0, le=1)
    case_id: Optional[str] = Field(default=None, max_length=64)  # aceito e ignorado


class BreakevenParametros(BaseModel):
    valor_causa: float
    prob_exito: float
    tempo_anos: float
    tribunal: Optional[str]
    selic_anual: float
    selic_fonte: Literal["bcb", "fallback"]
    custas_pct: float
    honorarios_sucumbencia_pct: float


class BreakevenComparativo(BaseModel):
    litigio_vpl: float
    acordo_imediato_equivalente: float
    custo_do_tempo: float


class BreakevenResponse(BaseModel):
    parametros: BreakevenParametros
    valor_esperado: float
    custos_estimados: float
    vpl_litigio: float
    sugestao_acordo: float
    breakeven: float
    comparativo: BreakevenComparativo
    memoria_calculo: list[str]


async def _obter_selic_anual() -> tuple[float, Literal["bcb", "fallback"]]:
    """Meta Selic anual via BCB/SGS (série 432). Falhou → fallback fixo."""
    try:
        async with httpx.AsyncClient(timeout=4) as c:
            r = await c.get(_BCB_SELIC_META_URL)
            r.raise_for_status()
            dados = r.json()
        taxa = float(str(dados[-1]["valor"]).replace(",", ".")) / 100.0
        if 0 < taxa < 1:
            return taxa, "bcb"
    except Exception as exc:  # rede/formato — nunca derruba o cálculo
        logger.warning("Selic BCB indisponível, usando fallback: %s", exc)
    return SELIC_FALLBACK_ANUAL, "fallback"


def calcular_breakeven(
    *,
    valor_causa: float,
    prob_exito: float,
    tempo_anos: float,
    tribunal: Optional[str],
    selic_anual: float,
    selic_fonte: Literal["bcb", "fallback"],
    custas_pct: float,
    honorarios_sucumbencia_pct: float,
) -> BreakevenResponse:
    """Cálculo puro e determinístico do ponto de equilíbrio do acordo."""
    valor_esperado = valor_causa * prob_exito
    custas = valor_causa * custas_pct / 100.0
    sucumbencia_esperada = (
        valor_causa * honorarios_sucumbencia_pct / 100.0 * (1.0 - prob_exito)
    )
    custos_estimados = custas + sucumbencia_esperada
    liquido_nominal = valor_esperado - custos_estimados

    fator_desconto = (1.0 + selic_anual) ** tempo_anos
    vpl_litigio = liquido_nominal / fator_desconto
    breakeven = max(0.0, vpl_litigio)
    sugestao_acordo = breakeven * (1.0 + MARGEM_NEGOCIACAO)
    custo_do_tempo = max(0.0, liquido_nominal - vpl_litigio)

    r2 = lambda x: round(x, 2)  # noqa: E731 — moeda com 2 casas
    memoria = [
        f"Valor esperado = {valor_causa:.2f} × {prob_exito:.2%} = R$ {valor_esperado:.2f}",
        f"Custas processuais = {valor_causa:.2f} × {custas_pct:.1f}% = R$ {custas:.2f}",
        (
            f"Sucumbência esperada = {valor_causa:.2f} × {honorarios_sucumbencia_pct:.1f}% "
            f"× (1 − {prob_exito:.2%}) = R$ {sucumbencia_esperada:.2f}"
        ),
        f"Custos estimados = {custas:.2f} + {sucumbencia_esperada:.2f} = R$ {custos_estimados:.2f}",
        f"Líquido nominal ao fim do litígio = {valor_esperado:.2f} − {custos_estimados:.2f} = R$ {liquido_nominal:.2f}",
        (
            f"Fator de desconto = (1 + {selic_anual:.4f})^{tempo_anos:g} = {fator_desconto:.6f} "
            f"(Selic {selic_anual:.2%} a.a., fonte {'BCB' if selic_fonte == 'bcb' else 'estimada'})"
        ),
        f"VPL do litígio = {liquido_nominal:.2f} ÷ {fator_desconto:.6f} = R$ {vpl_litigio:.2f}",
        f"Breakeven (acordo hoje equivalente ao litígio) = R$ {breakeven:.2f}",
        f"Sugestão de acordo = breakeven × (1 + {MARGEM_NEGOCIACAO:.0%}) = R$ {sugestao_acordo:.2f}",
        f"Custo do tempo = {liquido_nominal:.2f} − {vpl_litigio:.2f} = R$ {custo_do_tempo:.2f}",
    ]

    return BreakevenResponse(
        parametros=BreakevenParametros(
            valor_causa=r2(valor_causa),
            prob_exito=prob_exito,
            tempo_anos=tempo_anos,
            tribunal=tribunal,
            selic_anual=selic_anual,
            selic_fonte=selic_fonte,
            custas_pct=custas_pct,
            honorarios_sucumbencia_pct=honorarios_sucumbencia_pct,
        ),
        valor_esperado=r2(valor_esperado),
        custos_estimados=r2(custos_estimados),
        vpl_litigio=r2(vpl_litigio),
        sugestao_acordo=r2(sugestao_acordo),
        breakeven=r2(breakeven),
        comparativo=BreakevenComparativo(
            litigio_vpl=r2(vpl_litigio),
            acordo_imediato_equivalente=r2(breakeven),
            custo_do_tempo=r2(custo_do_tempo),
        ),
        memoria_calculo=memoria,
    )


@router.post("/breakeven", response_model=BreakevenResponse)
async def breakeven(
    payload: BreakevenRequest,
    cu: User = Depends(get_current_user),
) -> BreakevenResponse:
    """Compara VPL do litígio × acordo imediato e sugere o ponto de equilíbrio."""
    if payload.selic_anual is not None:
        selic_anual: float = payload.selic_anual
        selic_fonte: Literal["bcb", "fallback"] = "fallback"
    else:
        selic_anual, selic_fonte = await _obter_selic_anual()

    tribunal = payload.tribunal.strip().upper() if payload.tribunal else None
    tempo_anos = payload.tempo_anos or TEMPO_MEDIO_ANOS.get(
        tribunal or "", TEMPO_PADRAO_ANOS
    )
    custas_pct = (
        payload.custas_pct if payload.custas_pct is not None else CUSTAS_PCT_PADRAO
    )
    honorarios_pct = (
        payload.honorarios_sucumbencia_pct
        if payload.honorarios_sucumbencia_pct is not None
        else HONORARIOS_SUCUMBENCIA_PCT_PADRAO
    )

    return calcular_breakeven(
        valor_causa=payload.valor_causa,
        prob_exito=payload.prob_exito,
        tempo_anos=tempo_anos,
        tribunal=tribunal,
        selic_anual=selic_anual,
        selic_fonte=selic_fonte,
        custas_pct=custas_pct,
        honorarios_sucumbencia_pct=honorarios_pct,
    )
