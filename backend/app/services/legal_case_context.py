"""Contratos neutros de contexto jurídico do caso.

O EJC Core consome este contrato sem conhecer models ORM especializados por ramo.
Adapters verticais podem preencher os campos enquanto durar a compatibilidade.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class SpecializedCaseContext:
    """Contexto opcional fornecido por uma vertical/adapter legado."""

    label: str
    fields: tuple[tuple[str, str], ...]
    source: str = "legacy_vertical"


def format_context_value(value) -> str:
    """Formatação estável usada no dossiê de contexto jurídico."""
    if value is None:
        return "—"
    if hasattr(value, "value") and not isinstance(value, (int, float, bool)):
        return str(value.value).replace("_", " ")
    if isinstance(value, Decimal):
        from app.utils.format import formatar_brl
        return formatar_brl(value)
    if isinstance(value, (date, datetime)):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, bool):
        return "Sim" if value else "Não"
    return str(value)
