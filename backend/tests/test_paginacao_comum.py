"""Paginação mantém filtros, total e ordenação sobre um banco isolado."""
import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.pagination import executar_pagina


@pytest.mark.parametrize("contar_sem_ordem", [False, True])
async def test_total_filtrado_e_segunda_pagina_ordenada(contar_sem_ordem):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    metadata = MetaData()
    itens = Table("itens", metadata, Column("id", Integer, primary_key=True), Column("dono", String))
    try:
        async with engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
            await connection.execute(itens.insert(), [
                {"id": i, "dono": "equipe" if i <= 5 else "alheio"} for i in range(1, 9)
            ])
        async with AsyncSession(engine) as db:
            query = select(itens.c.id).where(itens.c.dono == "equipe").order_by(itens.c.id.desc())
            total, pagina = await executar_pagina(db, query, 2, 2, contar_sem_ordem=contar_sem_ordem)
            assert total == 5
            assert pagina == [3, 2]
            total, pagina = await executar_pagina(db, query, 4, 2, contar_sem_ordem=contar_sem_ordem)
            assert total == 5
            assert pagina == []
    finally:
        await engine.dispose()
