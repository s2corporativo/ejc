#!/usr/bin/env python3
# Probe: por que busca-avancada retorna 0? Verificar teses QA ativas no banco.
import asyncio
from app.core.database import AsyncSessionLocal
from app.models.tese import Tese, TeseStatus
from sqlalchemy import select

async def probe():
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Tese).where(Tese.deleted_at.is_(None),
                               Tese.status == TeseStatus.ativa,
                               Tese.titulo.like("%EJC_QA M30%"))
        )).scalars().all()
        print(f"teses QA M30 ativas: {len(rows)}")
        for t in rows:
            print(f" - id={t.id[:12]} titulo={t.titulo[:50]} "
                  f"status={t.status} area={t.area_juridica} "
                  f"taxa={t.taxa_sucesso} tipo={t.tipo}")
        # busca exata replicando os filtros do endpoint
        q_all = (await db.execute(
            select(Tese).where(Tese.deleted_at.is_(None))
        )).scalars().all()
        print(f"todas teses não-deletadas: {len(q_all)}")
        for t in q_all[:15]:
            print(f" - {t.titulo[:50]} | status={t.status} taxa={t.taxa_sucesso}")

asyncio.get_event_loop().run_until_complete(probe())
