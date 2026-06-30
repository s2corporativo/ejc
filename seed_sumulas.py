import asyncio, sys
sys.path.insert(0, '/app')
from app.core.database import AsyncSessionLocal
from app.services.sumulas_ingestion import ingerir_sumulas_seed

async def run():
    async with AsyncSessionLocal() as db:
        result = await ingerir_sumulas_seed(db)
        print('Resultado:', result)

asyncio.run(run())