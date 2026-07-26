"""Numeração interna canônica de casos (DPT-AAAA-NNNN).

Fonte única do alocador de número interno: usada pelo cadastro de casos
(routers/cases.py), pela conversão da Sala Jurídica e pela conversão do
Raio-X (services/raio_x_service.py) — evita formatos divergentes e números
duplicados entre superfícies.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def proximo_numero_interno(db: AsyncSession) -> str:
    """Numeração automática DPT-2026-0001 (sequencial por ano).

    Lock consultivo transacional (pg_advisory_xact_lock) serializa criações
    concorrentes no mesmo ano — evita numero_interno duplicado. Ordenação pelo
    sufixo NUMÉRICO (não lexicográfica: 'DPT-2026-10000' < 'DPT-2026-9999')."""
    ano = date.today().year
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:chave))"),
        {"chave": f"numero_interno_{ano}"},
    )
    result = await db.execute(text(r"""
        SELECT numero_interno FROM cases
        WHERE numero_interno LIKE :pref
        ORDER BY CAST(substring(numero_interno FROM '\d+$') AS INTEGER) DESC
        LIMIT 1
    """), {"pref": f"DPT-{ano}-%"})
    ultimo = result.scalar()
    seq = int(ultimo.split("-")[-1]) + 1 if ultimo else 1
    return f"DPT-{ano}-{seq:04d}"
