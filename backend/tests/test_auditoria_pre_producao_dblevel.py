"""Auditoria pré-produção — validação ROW-LEVEL (Postgres real, RUN_DB_TESTS=1).

1. /auth/refresh nega usuário soft-deletado (item 10 — filtro deleted_at nos
   fluxos manuais de auth, mesmo padrão do get_current_user).

(O teste do webhook Z-API foi removido junto com o vendor Z-API.)

Mesmo padrão dos demais *_dblevel.py (SQL cru + AsyncSessionLocal).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request, Response
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    """Isola o engine async do loop-por-função (ver test_search_dblevel.py)."""
    from app.core.database import engine
    await engine.dispose()
    yield
    await engine.dispose()


def _req(path: str) -> Request:
    return Request({
        "type": "http", "method": "POST", "path": path, "headers": [],
        "query_string": b"", "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80), "scheme": "http",
    })


# ── 1. Refresh nega usuário soft-deletado ─────────────────────────────────────

async def test_refresh_usuario_soft_deletado_401():
    from app.core.database import AsyncSessionLocal
    from app.core.security import create_refresh_token
    from app.routers.auth import RefreshRequest, refresh

    uid = str(uuid4())
    token, jti = create_refresh_token(uid)
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("INSERT INTO users (id, email, hashed_password, full_name, "
                 "role, is_active, deleted_at) VALUES (:id, :email, 'x', "
                 "'Soft Deletado', 'advogado', true, now())"),
            {"id": uid, "email": f"del-{uid[:8]}@teste.local"},
        )
        await db.execute(
            text("INSERT INTO refresh_tokens (id, user_id, jti, expires_at, "
                 "revoked) VALUES (:id, :uid, :jti, :exp, false)"),
            {"id": str(uuid4()), "uid": uid, "jti": jti,
             "exp": datetime.now(timezone.utc) + timedelta(days=7)},
        )
        await db.commit()
        try:
            with pytest.raises(HTTPException) as exc:
                await refresh(RefreshRequest(refresh_token=token),
                              _req("/auth/refresh"), Response(), db=db)
            assert exc.value.status_code == 401
        finally:
            await db.rollback()
            await db.execute(text("DELETE FROM refresh_tokens WHERE user_id = :id"), {"id": uid})
            await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
            await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
            await db.commit()


# ── 2. Webhook Z-API — REMOVIDO (vendor Z-API descontinuado) ──────────────────
