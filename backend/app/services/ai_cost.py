# ── app/services/ai_cost.py ──────────────────────────────────────────────────
# Estimativa de custo de chamadas de IA em R$.
# Ollama (local) = 0. Groq = tokens × preço por milhão (config via .env).
# Permite auditar o gasto com IA por chamada/caso (AILog.custo_estimado).
from __future__ import annotations
from decimal import Decimal

from app.core.config import get_settings

settings = get_settings()


def estimar_custo_brl(
    provedor: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> Decimal:
    """
    Retorna o custo estimado da chamada em R$ (Decimal).
    Ollama/local → 0. Groq → tokens × preço/milhão definido na config.
    Nunca levanta exceção; tokens ausentes contam como 0.
    """
    if provedor != "groq":
        return Decimal("0")
    ti = Decimal(int(input_tokens or 0))
    to = Decimal(int(output_tokens or 0))
    p_in = Decimal(str(settings.GROQ_PRECO_INPUT_BRL_POR_MILHAO))
    p_out = Decimal(str(settings.GROQ_PRECO_OUTPUT_BRL_POR_MILHAO))
    custo = (ti / Decimal(1_000_000)) * p_in + (to / Decimal(1_000_000)) * p_out
    return custo.quantize(Decimal("0.000001"))
