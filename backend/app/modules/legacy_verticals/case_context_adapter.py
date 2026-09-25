"""Adapter de compatibilidade para satélites jurídicos legados.

Isola o conhecimento de models especializados por ramo fora do EJC Core.
Não deve receber novas regras de negócio; existe apenas durante a migração #1843.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.environmental import EnvironmentalCase
from app.models.especializado import (
    AdminCase,
    BancarioCase,
    CivelCase,
    EmpresarialCase,
    PenalCase,
    TrabalhistaCase,
)
from app.services.legal_case_context import SpecializedCaseContext, format_context_value


_RAMO_MAP = {
    "ambiental": (EnvironmentalCase, "Ambiental"),
    "empresarial": (EmpresarialCase, "Empresarial"),
    "civil": (CivelCase, "Cível"),
    "consumidor": (CivelCase, "Cível/Consumidor"),
    "familia": (CivelCase, "Cível/Família"),
    "criminal": (PenalCase, "Penal"),
    "trabalhista": (TrabalhistaCase, "Trabalhista"),
    "tributario": (AdminCase, "Administrativo/Tributário"),
    "administrativo": (AdminCase, "Administrativo"),
    "bancario": (BancarioCase, "Bancário"),
    "imobiliario": (CivelCase, "Cível/Imobiliário"),
    "sucessoes": (CivelCase, "Cível/Sucessões"),
    "constitucional": (AdminCase, "Administrativo/Constitucional"),
    "digital_lgpd": (CivelCase, "Cível/Digital-LGPD"),
    "transito": (AdminCase, "Administrativo/Trânsito"),
}


def _filled_fields(obj) -> tuple[tuple[str, str], ...]:
    omitted = {"id", "case_id", "created_at", "updated_at", "deleted_at"}
    rows: list[tuple[str, str]] = []
    for col in obj.__table__.columns:
        if col.key in omitted:
            continue
        value = getattr(obj, col.key, None)
        if value is None or value == "" or value is False:
            continue
        label = col.key.replace("_", " ").capitalize()
        rows.append((label, format_context_value(value)))
    return tuple(rows)


async def load_specialized_case_context(
    db: AsyncSession,
    case_id: str,
    area: object,
) -> SpecializedCaseContext | None:
    """Carrega o satélite legado associado ao caso, sem expor ORM ao Core."""
    area_value = getattr(area, "value", area)
    area_key = str(area_value or "")
    model_info = _RAMO_MAP.get(area_key)

    if model_info:
        model, label = model_info
        obj = (
            await db.execute(
                select(model).where(
                    model.case_id == case_id,
                    model.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if obj is not None:
            return SpecializedCaseContext(label=label, fields=_filled_fields(obj))

    # Compatibilidade histórica: casos bancários antigos podiam existir sem
    # Case.area=bancario. Mantém o fallback enquanto houver dados legados.
    bank = (
        await db.execute(
            select(BancarioCase).where(
                BancarioCase.case_id == case_id,
                BancarioCase.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if bank is not None:
        return SpecializedCaseContext(
            label="Bancário/Financeiro",
            fields=_filled_fields(bank),
        )

    return None
