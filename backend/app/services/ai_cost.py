# ── app/services/ai_cost.py ──────────────────────────────────────────────────
# Estimativa de custo de chamadas de IA em R$ — FONTE ÚNICA de preço de IA do
# EJC (gateway, dossiê, skills). Ollama (local) = 0. Groq = tokens × preço/milhão
# (config via .env). Anthropic = tabela de preços por modelo (USD) × USD_BRL_RATE.
# Permite auditar o gasto com IA por chamada/caso (AILog.custo_estimado).
from __future__ import annotations
import os
from decimal import Decimal

from app.core.config import get_settings

settings = get_settings()

# Preços oficiais Anthropic (USD por 1M tokens) — manter em dia com a fatura.
_PRECOS_ANTHROPIC_USD_MM: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-haiku-4-5":          {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-6":         {"input": 3.00, "output": 15.00},
    "claude-sonnet-5":           {"input": 3.00, "output": 15.00},
    "claude-opus-4-7":           {"input": 5.00, "output": 25.00},
    "claude-opus-4-8":           {"input": 5.00, "output": 25.00},
}

# Preços Maritaca (BRL por 1M tokens) — empresa BRASILEIRA, fatura em R$ nativo
# (sem conversão USD). Por-modelo porque sabia-4 e sabiazinho-4 têm preços
# distintos; modelo fora da tabela cai nos defaults de config (.env).
_PRECOS_MARITACA_BRL_MM: dict[str, dict[str, float]] = {
    "sabia-4":       {"input": 5.00, "output": 10.00},
    "sabiazinho-4":  {"input": 1.00, "output": 4.00},
    "sabia-3":       {"input": 5.00, "output": 10.00},
    "sabia-3.1":     {"input": 5.00, "output": 10.00},
    "sabiazinho-3":  {"input": 1.00, "output": 3.00},
}


def estimar_custo_brl(
    provedor: str,
    input_tokens: int | None,
    output_tokens: int | None,
    modelo: str | None = None,
) -> Decimal:
    """
    Retorna o custo estimado da chamada em R$ (Decimal).
    Ollama/local → 0. Groq → tokens × preço/milhão definido na config.
    Anthropic → tabela de preços por `modelo` (USD/1M) × cotação USD_BRL_RATE.
    Modelo/provedor desconhecido → 0. Nunca levanta exceção; tokens ausentes
    contam como 0.
    """
    ti = Decimal(int(input_tokens or 0))
    to = Decimal(int(output_tokens or 0))
    if provedor == "groq":
        p_in = Decimal(str(settings.GROQ_PRECO_INPUT_BRL_POR_MILHAO))
        p_out = Decimal(str(settings.GROQ_PRECO_OUTPUT_BRL_POR_MILHAO))
        custo = (ti / Decimal(1_000_000)) * p_in + (to / Decimal(1_000_000)) * p_out
        return custo.quantize(Decimal("0.000001"))
    if provedor == "anthropic":
        p = _PRECOS_ANTHROPIC_USD_MM.get(modelo or "", {"input": 0.0, "output": 0.0})
        usd = (ti * Decimal(str(p["input"])) + to * Decimal(str(p["output"]))) / Decimal(1_000_000)
        cotacao = Decimal(str(os.getenv("USD_BRL_RATE", "5.70")))
        return (usd * cotacao).quantize(Decimal("0.000001"))
    if provedor == "maritaca":
        # BRL nativo: tabela por-modelo; modelo desconhecido → defaults de config.
        p = _PRECOS_MARITACA_BRL_MM.get(modelo or "")
        if p is None:
            p_in = Decimal(str(settings.MARITACA_PRECO_INPUT_BRL_POR_MILHAO))
            p_out = Decimal(str(settings.MARITACA_PRECO_OUTPUT_BRL_POR_MILHAO))
        else:
            p_in, p_out = Decimal(str(p["input"])), Decimal(str(p["output"]))
        custo = (ti / Decimal(1_000_000)) * p_in + (to / Decimal(1_000_000)) * p_out
        return custo.quantize(Decimal("0.000001"))
    return Decimal("0")
