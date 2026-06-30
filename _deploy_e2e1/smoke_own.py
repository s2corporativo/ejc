import asyncio
from app.core.database import AsyncSessionLocal
from app.core.ownership import verificar_acesso_caso
from sqlalchemy import text


class U:
    pass


def mkuser(uid, role):
    u = U()
    u.id = uid
    u.role = type("R", (), {"value": role})()
    return u


async def main():
    async with AsyncSessionLocal() as db:
        row = (await db.execute(text(
            "SELECT id, advogado_responsavel_id FROM cases WHERE deleted_at IS NULL LIMIT 1"
        ))).mappings().first()
        cid = row["id"]
        tem_resp = row["advogado_responsavel_id"] is not None
        print("caso=", cid[:8], "tem_responsavel=", tem_resp)

        # gestão (socio) deve passar sempre
        try:
            c = await verificar_acesso_caso(db, mkuser("zzz", "socio"), cid)
            print("gestao_socio:", "PASSOU (ok)", c.id[:8])
        except Exception as e:
            print("gestao_socio: ERRO", getattr(e, "status_code", ""), e)

        # advogado que NÃO é o responsável deve ser bloqueado (se o caso tem responsável)
        try:
            await verificar_acesso_caso(db, mkuser("intruso-id", "advogado"), cid)
            print("advogado_intruso:", "PASSOU", "(esperado só se caso sem responsável)")
        except Exception as e:
            print("advogado_intruso:", "BLOQUEADO", getattr(e, "status_code", ""))

        # caso inexistente -> 404
        try:
            await verificar_acesso_caso(db, mkuser("zzz", "socio"), "nao-existe-xyz")
            print("inexistente: PASSOU (inesperado)")
        except Exception as e:
            print("inexistente:", "404?", getattr(e, "status_code", ""))


asyncio.run(main())
