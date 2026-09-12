"""Relógio operacional canônico do EJC.

Decisões jurídicas baseadas em data civil não podem depender do timezone do
container. O EJC agenda jobs e calendários no fuso America/Sao_Paulo; este
helper centraliza a mesma fronteira para regras que dependem de "hoje".
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

FUSO_OPERACIONAL = ZoneInfo("America/Sao_Paulo")


def hoje_operacional() -> date:
    """Data civil corrente no fuso operacional do escritório."""
    return datetime.now(FUSO_OPERACIONAL).date()
