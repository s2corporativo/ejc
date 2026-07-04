# ── app/routers/visual_law.py ────────────────────────────────────────────────
# Visual Law — ferramentas visuais determinísticas de apoio à decisão.
#
#   POST /visual-law/breakeven → calculadora de acordo (ponto de equilíbrio
#   entre acordo imediato e prosseguir com a ação). Consumida por
#   frontend/src/components/visual/CalculadoraAcordo.tsx.
#
# 100% determinístico (sem IA): a única dependência externa é a Selic vigente
# via API pública do BCB, com fallback fixo quando indisponível.
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import require_roles
from app.models.user import User
from app.services import bcb_service
from app.services.calc.breakeven_acordo import (
    SELIC_ANUAL_FALLBACK,
    calcular_breakeven,
)

router = APIRouter(prefix="/visual-law", tags=["visual-law"])

# Equipe interna (mesma regra das calculadoras — cliente externo não acessa)
_EQUIPE = ["superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "estagiario"]


class BreakevenIn(BaseModel):
    """Contrato do frontend (types/visualLaw.ts → BreakevenRequest)."""
    valor_causa: float = Field(..., gt=0, le=1_000_000_000)
    prob_exito: float = Field(..., ge=0, le=1, description="0..1")
    tempo_anos: Optional[float] = Field(None, gt=0, le=30)
    tribunal: Optional[str] = Field(None, max_length=20)
    custas_pct: Optional[float] = Field(None, ge=0, le=100)
    honorarios_sucumbencia_pct: Optional[float] = Field(None, ge=0, le=100)
    selic_anual: Optional[float] = Field(
        None, gt=0, lt=1,
        description="Fração a.a. (ex.: 0.15). Se omitido, busca no BCB.")
    case_id: Optional[str] = Field(None, max_length=64)


@router.post("/breakeven", summary="Calculadora de acordo (breakeven do litígio)")
async def breakeven(body: BreakevenIn, cu: User = Depends(require_roles(_EQUIPE))):
    """Compara o VPL de prosseguir com a ação × acordo imediato.

    Determinístico e auditável (memória de cálculo passo a passo) — nenhuma
    chamada de IA. Selic: informada no body > API do BCB > fallback fixo.
    """
    if body.selic_anual is not None:
        selic, fonte = body.selic_anual, "fallback"   # informada pelo usuário
    else:
        selic, fonte = await bcb_service.selic_anual_atual(SELIC_ANUAL_FALLBACK)
    return calcular_breakeven(
        valor_causa=body.valor_causa,
        prob_exito=body.prob_exito,
        tempo_anos=body.tempo_anos,
        tribunal=body.tribunal,
        custas_pct=body.custas_pct,
        honorarios_sucumbencia_pct=body.honorarios_sucumbencia_pct,
        selic_anual=selic,
        selic_fonte=fonte,
    )
