# ── app/utils/format.py ──────────────────────────────────────────────────────
# Formatadores de exibição — fonte única. Antes o formatador de moeda BRL estava
# copiado verbatim em ~7 lugares, com tratamento de None inconsistente entre as
# cópias. Aqui há UMA implementação, robusta a None/str/float/Decimal.
from __future__ import annotations

from decimal import Decimal
from typing import Union

Numero = Union[int, float, Decimal, str, None]


def formatar_brl(valor: Numero) -> str:
    """Formata um valor monetário em Real (pt-BR): 1234.5 -> 'R$ 1.234,50'.

    None / '' / valor não numérico -> 'R$ 0,00' (nunca levanta exceção).
    """
    try:
        v = float(valor) if valor not in (None, "") else 0.0
    except (TypeError, ValueError):
        v = 0.0
    # US -> pt-BR: separador de milhar '.' e decimal ',' (troca via placeholder).
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
