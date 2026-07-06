# ── app/utils/datas.py ───────────────────────────────────────────────────────
# Utilidades de data seguras — fonte única reusada pelos cálculos jurídicos
# (trabalhista, prescrição, ambiental). Motivo: construir date(ano, mês, dia)
# com dia fixo estoura ValueError quando o dia não existe no mês/ano destino
# (ex.: aniversário 29/02 projetado para ano não bissexto, ou dia 31 num mês de
# 30). Aqui o dia é "clampado" ao último dia real do mês.
from __future__ import annotations

import calendar
from datetime import date


def ultimo_dia_do_mes(ano: int, mes: int) -> int:
    return calendar.monthrange(ano, mes)[1]


def data_segura(ano: int, mes: int, dia: int) -> date:
    """date(ano, mes, dia) com o dia limitado ao último dia real do mês.

    data_segura(2025, 2, 29) -> date(2025, 2, 28)  (2025 não é bissexto)
    data_segura(2024, 4, 31) -> date(2024, 4, 30)
    """
    return date(ano, mes, min(dia, ultimo_dia_do_mes(ano, mes)))


def adicionar_anos(d: date, anos: int) -> date:
    """d + N anos, tratando 29/02 com segurança (vira 28/02 em ano não bissexto)."""
    return data_segura(d.year + anos, d.month, d.day)
