"""Regressão LGPD: busca `tipo=tudo` não expõe clientes a estagiário."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import Request
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


def _req() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/search",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    from app.core.database import engine

    await engine.dispose()
    yield
    await engine.dispose()


async def test_tudo_estagiario_nao_recebe_clientes():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.search import busca_global

    tok = f"Zzu{uuid4().hex[:6]}"
    user_id = str(uuid4())
    client_id = str(uuid4())
    case_id = str(uuid4())

    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
                "VALUES (:id, :email, 'x', 'Estagiário Busca', 'estagiario', true)"
            ),
            {"id": user_id, "email": f"busca-{user_id[:8]}@teste.local"},
        )
        await db.execute(
            text(
                "INSERT INTO clients (id, tipo, nome, email, status) "
                "VALUES (:id, 'PF', :nome, :email, 'ativo')"
            ),
            {
                "id": client_id,
                "nome": f"{tok} Cliente Tudo",
                "email": f"{client_id[:8]}@teste.local",
            },
        )
        await db.execute(
            text(
                "INSERT INTO cases (id, titulo, area, status, client_id, "
                "advogado_responsavel_id) VALUES "
                "(:id, :titulo, 'civil', 'ativo', :client_id, :user_id)"
            ),
            {
                "id": case_id,
                "titulo": f"{tok} Caso Tudo",
                "client_id": client_id,
                "user_id": user_id,
            },
        )
        await db.commit()

        try:
            user = (
                await db.execute(select(User).where(User.id == user_id))
            ).scalar_one()
            response = await busca_global(
                request=_req(),
                q=tok,
                tipo="tudo",
                limit=6,
                db=db,
                cu=user,
            )
            assert "cliente" not in {
                item["tipo"] for item in response["resultados"]
            }
            assert [
                (item["tipo"], item["id"])
                for item in response["resultados"]
            ] == [("caso", case_id)]
        finally:
            await db.execute(
                text("DELETE FROM case_partes WHERE case_id = :id"),
                {"id": case_id},
            )
            await db.execute(
                text("DELETE FROM processes WHERE case_id = :id"),
                {"id": case_id},
            )
            await db.execute(
                text("DELETE FROM cases WHERE id = :id"),
                {"id": case_id},
            )
            await db.execute(
                text("DELETE FROM audit_logs WHERE user_id = :id"),
                {"id": user_id},
            )
            await db.execute(
                text("DELETE FROM users WHERE id = :id"),
                {"id": user_id},
            )
            await db.execute(
                text("DELETE FROM clients WHERE id = :id"),
                {"id": client_id},
            )
            await db.commit()
