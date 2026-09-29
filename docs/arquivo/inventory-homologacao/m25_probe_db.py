"""Probe: súmulas vigentes na base + lexml crawler response."""
from __future__ import annotations
import asyncio
import sys
sys.path.insert(0, "/home/ubuntu/ejc_repo/backend")
from app.core.database import AsyncSessionLocal
from sqlalchemy import text

async def f():
    async with AsyncSessionLocal() as db:
        r = await db.execute(text(
            "SELECT chave_origem, titulo FROM knowledge_docs "
            "WHERE deleted_at IS NULL AND vigente "
            "AND (chave_origem LIKE 'sumula:%' OR categoria LIKE 'sumula%') "
            "ORDER BY 1"))
        rows = r.fetchall()
        print("total sumulas:", len(rows))
        for k, t in rows[:12]:
            print(k, "|", str(t)[:60])

asyncio.run(f())
