"""Auditoria pré-produção — validação ROW-LEVEL (Postgres real, RUN_DB_TESTS=1).

1. /auth/refresh nega usuário soft-deletado (item 10 — filtro deleted_at nos
   fluxos manuais de auth, mesmo padrão do get_current_user).
2. Webhook Z-API: lookup de telefone filtrado no SQL (item 8) — cliente com
   telefone formatado NÃO vira lead duplicado; número desconhecido vira lead.

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


# ── 2. Webhook Z-API — lookup por telefone no SQL ─────────────────────────────

class _FakeWebhookRequest:
    def __init__(self, body: dict):
        self._body = body

    async def json(self):
        return self._body


async def _leads_com_whatsapp(db, telefone: str) -> int:
    return (await db.execute(
        text("SELECT count(*) FROM clients WHERE whatsapp = :tel "
             "AND origem = 'whatsapp'"), {"tel": telefone},
    )).scalar_one()


async def _limpar_webhook(db, telefone: str, client_id: str | None = None):
    await db.execute(
        text("DELETE FROM notifications WHERE mensagem LIKE :tel"),
        {"tel": f"%{telefone}%"},
    )
    await db.execute(
        text("DELETE FROM clients WHERE whatsapp = :tel AND origem = 'whatsapp'"),
        {"tel": telefone},
    )
    if client_id:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})
    await db.commit()


async def test_webhook_telefone_cadastrado_formatado_nao_cria_lead(monkeypatch):
    """O match por sufixo de 8 dígitos ignora a máscara salva no cadastro."""
    from app.core.config import get_settings
    from app.core.database import AsyncSessionLocal
    from app.routers.webhooks import zapi_inbound

    monkeypatch.setattr(get_settings(), "ZAPI_CLIENT_TOKEN", "tok-teste")
    sufixo = uuid4().int % 10**8
    telefone = f"5531{sufixo:08d}"
    cid = str(uuid4())
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("INSERT INTO clients (id, tipo, nome, email, status, whatsapp) "
                 "VALUES (:id, 'PF', 'Cliente Webhook', :email, 'ativo', :wa)"),
            {"id": cid, "email": f"{cid[:8]}@teste.local",
             "wa": f"(31) {sufixo // 10000:04d}-{sufixo % 10000:04d}"},
        )
        await db.commit()
    try:
        resp = await zapi_inbound(
            _FakeWebhookRequest({"phone": telefone,
                                 "text": {"message": "olá"},
                                 "senderName": "Já Cliente"}),
            client_token="tok-teste",
        )
        assert resp == {"ok": True}
        async with AsyncSessionLocal() as db:
            assert await _leads_com_whatsapp(db, telefone) == 0
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar_webhook(db, telefone, cid)


async def test_webhook_telefone_desconhecido_cria_lead(monkeypatch):
    from app.core.config import get_settings
    from app.core.database import AsyncSessionLocal
    from app.routers.webhooks import zapi_inbound

    monkeypatch.setattr(get_settings(), "ZAPI_CLIENT_TOKEN", "tok-teste")
    telefone = f"5531{uuid4().int % 10**8:08d}"
    try:
        resp = await zapi_inbound(
            _FakeWebhookRequest({"phone": telefone,
                                 "text": {"message": "quero um orçamento"},
                                 "senderName": "Lead Novo"}),
            client_token="tok-teste",
        )
        assert resp == {"ok": True}
        async with AsyncSessionLocal() as db:
            assert await _leads_com_whatsapp(db, telefone) == 1
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar_webhook(db, telefone)
