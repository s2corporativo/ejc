import asyncio, sys
sys.path.insert(0, '/app')
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

async def run():
    async with AsyncSessionLocal() as db:
        # TOTP columns
        r = await db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name IN ('totp_secret', 'totp_enabled')"))
        cols = [row[0] for row in r.fetchall()]
        print('TOTP cols:', cols)
        
        # Sumulas count
        r2 = await db.execute(text("SELECT count(*) FROM teses WHERE tipo::text = 'jurisprudencia'"))
        print('Sumulas:', r2.scalar())
        
        # alembic head
        r3 = await db.execute(text("SELECT version_num FROM alembic_version"))
        print('Alembic:', r3.scalar())

asyncio.run(run())