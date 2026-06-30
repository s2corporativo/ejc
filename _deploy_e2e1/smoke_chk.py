import asyncio
from app.core.database import AsyncSessionLocal
from app.services.ai_service import buscar_contexto_rag
from app.services import ai_gateway
from app.routers.checklists import _SYS_CHECKLIST, _parse_itens
from sqlalchemy import text


async def main():
    async with AsyncSessionLocal() as db:
        caso = (await db.execute(text(
            "SELECT id, area, fase FROM cases WHERE deleted_at IS NULL ORDER BY created_at LIMIT 1"
        ))).mappings().first()
        area = (caso["area"] if caso else None) or "civil"
        print("caso_area=", area)
        ctx = await buscar_contexto_rag(db, f"{area} requisitos peticao documentos obrigatorios prazos", limite=5)
        print("rag_chunks=", len(ctx or []))
        ctx_txt = "\n".join("- " + (str(c.get("conteudo") or "")[:200]) for c in (ctx or []))
        user = f"Area: {area}. Gere 8 itens.\n\nCONTEXTO:\n{ctx_txt or '(sem)'}"
        resp = await ai_gateway.chat(
            messages=[{"role": "system", "content": _SYS_CHECKLIST}, {"role": "user", "content": user}],
            task_type="resumo", temperature=0.3, max_tokens=1500,
        )
        itens = _parse_itens(resp.texto)
        print("modelo=", resp.provedor, resp.modelo)
        print("itens_gerados=", len(itens))
        for it in itens[:4]:
            print("  -", str(it.get("texto"))[:80], "|", it.get("categoria"), "| obrig=", it.get("obrigatorio"))


asyncio.run(main())
