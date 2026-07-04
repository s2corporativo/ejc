# ── app/schemas/visual_law.py ────────────────────────────────────────────────
# Schemas do módulo Visual Law (calculadora de breakeven/VPL de acordo).
# Contrato espelhado em frontend/src/types/visualLaw.ts.
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class BreakevenIn(BaseModel):
    """Entrada da calculadora de ponto de equilíbrio (breakeven) de acordo.

    `valor_causa` e `tribunal` podem ser omitidos quando `case_id` é enviado —
    nesse caso os valores cadastrados no caso são usados como default.
    Percentuais aceitos em fração (0.10) ou escala 0–100 (10 → 10%)."""
    valor_causa: Optional[float] = Field(
        None, gt=0, description="Valor da causa em R$ (default: valor do caso)")
    prob_exito: float = Field(
        ..., ge=0.0, le=1.0, description="Probabilidade de êxito (0..1)")
    tempo_anos: Optional[float] = Field(
        None, gt=0, le=50,
        description="Tempo estimado de tramitação em anos (default: média do tribunal)")
    tribunal: Optional[str] = Field(
        None, max_length=20, description="Sigla do tribunal (ex.: TJMG)")
    custas_pct: float = Field(
        0.10, ge=0.0, le=100.0, description="Custas processuais (fração ou %)")
    honorarios_sucumbencia_pct: float = Field(
        0.10, ge=0.0, le=100.0,
        description="Honorários de sucumbência (fração ou %)")
    selic_anual: Optional[float] = Field(
        None, ge=0.0, le=2.0,
        description="Selic anual em fração (default: BCB série 4390 anualizada)")
    case_id: Optional[str] = Field(
        None, max_length=36, description="Caso para defaults de valor/tribunal")
