import asyncio
from app.core.database import AsyncSessionLocal
from app.services.checklist_ia import gerar_checklist_ia
from sqlalchemy import text


async def main():
    async with AsyncSessionLocal() as db:
        caso = (await db.execute(text(
            "SELECT id, area FROM cases WHERE deleted_at IS NULL ORDER BY created_at LIMIT 1"
        ))).mappings().first()
        uid = (await db.execute(text(
            "SELECT id FROM users WHERE deleted_at IS NULL LIMIT 1"
        ))).scalar()
        res = await gerar_checklist_ia(db, caso["id"], "pre_processo", uid)
        print("gerado_id=", res and res["id"], "| total=", res and res["total_itens"], "| modelo=", res and res["modelo"])
        ck_id = res["id"] if res else None

    if ck_id:
        async with AsyncSessionLocal() as db2:
            row = (await db2.execute(text(
                "SELECT nome, total_itens FROM case_checklists WHERE id=:c"), {"c": ck_id})).mappings().first()
            n = (await db2.execute(text(
                "SELECT count(*) FROM case_checklist_items WHERE case_checklist_id=:c"), {"c": ck_id})).scalar()
            print("persistido_nome=", row and row["nome"], "| itens_no_banco=", n)


asyncio.run(main())
