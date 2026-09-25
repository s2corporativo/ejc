"""Compatibilidade LGPD para dados sensíveis mantidos em verticais legadas.

Este módulo concentra operações necessárias à anonimização enquanto os models
especializados ainda existirem no EJC. Não deve receber novas regras de produto.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case
from app.models.especializado import TrabalhistaCase


async def anonymize_legacy_health_data(
    db: AsyncSession,
    client_id: str,
    *,
    is_natural_person: bool,
) -> int:
    """Apaga CID do próprio cliente PF quando ele figura como reclamante.

    Preserva a regra vigente de segurança/LGPD:
    - considera inclusive casos soft-deleted, pois podem ser restaurados;
    - não apaga CID em cenários de cliente PJ/reclamado, onde o dado pode
      pertencer a terceiro;
    - retorna a quantidade de registros efetivamente anonimizados.
    """
    if not is_natural_person:
        return 0

    case_ids = select(Case.id).where(Case.client_id == client_id)
    rows = (
        await db.execute(
            select(TrabalhistaCase).where(
                TrabalhistaCase.case_id.in_(case_ids),
                TrabalhistaCase.deleted_at.is_(None),
                TrabalhistaCase.polo == "reclamante",
            )
        )
    ).scalars().all()

    anonymized = 0
    for row in rows:
        if row.cid is not None:
            row.cid = None
            anonymized += 1
    return anonymized
