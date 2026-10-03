"""Execução comum da paginação offset, sem decidir filtros ou contrato de saída."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def executar_pagina(
    db: AsyncSession, stmt, page: int, page_size: int, *, contar_sem_ordem: bool = False,
):
    base = stmt.order_by(None) if contar_sem_ordem else stmt
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar()
    rows = (await db.execute(
        stmt.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return total, rows
