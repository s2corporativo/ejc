"""Entidades de lixeira pertencentes a verticais legadas.

A lixeira Core pode consumir este registro sem importar models especializados.
"""
from __future__ import annotations

from app.models.environmental import EnvironmentalCase

LEGACY_TRASH_ENTITIES = {
    "environmental_cases": (
        EnvironmentalCase,
        lambda item: f"Auto {item.numero_auto}",
    ),
}
