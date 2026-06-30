import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os

DB = os.getenv("DATABASE_URL", "postgresql+asyncpg://ejc_user:ejc_pass@ejc_db:5432/ejc_db")

async def main():
    engine = create_async_engine(DB)
    async with engine.connect() as conn:
        # Tabelas novas
        r = await conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' "
            "AND table_name IN ('pricing_rules','inadimplencia_alerts','case_ambiental',"
            "'due_diligence_templates','document_access_log') ORDER BY table_name"
        ))
        tables = [row[0] for row in r.fetchall()]
        print("TABELAS:", tables)

        # Colunas do cofre em documents
        r2 = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='documents' "
            "AND column_name IN ('sensitivity_level','access_users','watermark','download_count','last_accessed_at') "
            "ORDER BY column_name"
        ))
        cols = [row[0] for row in r2.fetchall()]
        print("COFRE COLS:", cols)

        # Counts de seeds
        r3 = await conn.execute(text("SELECT COUNT(*) FROM pricing_rules"))
        print("pricing_rules seed:", r3.scalar())
        r4 = await conn.execute(text("SELECT COUNT(*) FROM due_diligence_templates"))
        print("due_diligence_templates seed:", r4.scalar())

        # Alembic head
        r5 = await conn.execute(text("SELECT version_num FROM alembic_version"))
        print("alembic head:", r5.scalar())

asyncio.run(main())
