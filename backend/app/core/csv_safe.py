"""Neutralização canônica de Formula Injection em exportações CSV.

Campos textuais controlados por usuário/fonte externa que começam (mesmo após
whitespace de planilha) com =, +, - ou @ recebem apóstrofo. Valores realmente
numéricos permanecem tipados/inalterados para não degradar relatórios.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

_FORMULA_PREFIX = re.compile(r"^[\t\r\n ]*[=+\-@]")


def sanitize_csv_cell(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if _FORMULA_PREFIX.match(value):
        return "'" + value
    return value


def sanitize_csv_row(values: Iterable[Any]) -> list[Any]:
    return [sanitize_csv_cell(value) for value in values]
