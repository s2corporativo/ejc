"""Regressão do achado 9 da auditoria (pending-items do cliente):
  • payload sem schema aceitava qualquer string em type/status → agora 422
    para vocabulário fora do fechado;
  • case_id não era conferido contra o cliente da URL (podia apontar caso de
    outro cliente) → agora 422;
  • escritas não geravam audit log → agora geram.

Postgres é OBRIGATÓRIO. Sem RUN_DB_TESTS=1, pula.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db, role: str = "socio") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Pending Teste', :role, true)"),
        {"id": uid, "email": f"pend-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _criar_cliente(db, nome: str) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status) "
             "VALUES (:id, 'PF', :nome, :email, 'ativo')"),
        {"id": cid, "nome": nome, "email": f"{cid[:8]}@teste.local"},
    )
    return cid


async def _criar_caso(db, client_id: str, titulo: str) -> str:
    case_id = str(uuid4())
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id) "
             "VALUES (:id, :titulo, 'civil', 'aberto', :cid)"),
        {"id": case_id, "titulo": titulo, "cid": client_id},
    )
    return case_id


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return await db.get(User, uid)


async def _limpar(db, *, case_ids=(), user_ids=(), client_ids=()):
    for cid in client_ids:
        await db.execute(text("DELETE FROM client_pending_items WHERE client_id = :id"), {"id": cid})
    for cid in case_ids:
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM cases WHERE client_id = :id"), {"id": cid})
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(
            text("DELETE FROM audit_logs WHERE user_id IN "
                 "(SELECT id FROM users WHERE client_id = :id)"),
            {"id": cid})
        await db.execute(text("DELETE FROM users WHERE client_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    for uid in user_ids:
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def test_criar_pending_item_valida_vocabulario_fechado():
    from pydantic import ValidationError
    from app.routers.pending_items import PendingItemCreate

    with pytest.raises(ValidationError):
        PendingItemCreate(title="X", type="tipo-invalido")
    with pytest.raises(ValidationError):
        PendingItemCreate(title="X", status="status-invalido")
    # Válido: aceita o vocabulário conhecido.
    ok = PendingItemCreate(title="Contrato social", type="documento", status="pendente")
    assert ok.type == "documento" and ok.status == "pendente"


async def test_criar_pending_item_case_id_precisa_pertencer_ao_cliente():
    from app.core.database import AsyncSessionLocal
    from app.routers.pending_items import PendingItemCreate, create_pending_item

    tok = f"Pi{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db)
        cli_a = await _criar_cliente(db, f"Cliente A {tok}")
        cli_b = await _criar_cliente(db, f"Cliente B {tok}")
        caso_de_b = await _criar_caso(db, cli_b, f"Caso B {tok}")
        await db.commit()
        try:
            u_socio = await _carregar_user(db, socio)
            # case_id do cliente B numa pendência criada para o cliente A → 422.
            with pytest.raises(HTTPException) as exc:
                await create_pending_item(
                    cli_a, PendingItemCreate(title="X", case_id=caso_de_b), db, u_socio)
            assert exc.value.status_code == 422
        finally:
            await _limpar(db, case_ids=[caso_de_b], client_ids=[cli_a, cli_b],
                          user_ids=[socio])


async def test_criar_e_atualizar_pending_item_gera_audit_log():
    from app.core.database import AsyncSessionLocal
    from app.routers.pending_items import (
        PendingItemCreate, PendingItemUpdate, create_pending_item, update_pending_item,
    )

    tok = f"PiLog{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db)
        cli = await _criar_cliente(db, f"Cliente PiLog {tok}")
        await db.commit()
        try:
            u_socio = await _carregar_user(db, socio)
            criado = await create_pending_item(
                cli, PendingItemCreate(title="Procuração"), db, u_socio)
            await update_pending_item(
                cli, criado["id"], PendingItemUpdate(status="concluido"), db, u_socio)

            logs = (await db.execute(text(
                "SELECT acao FROM audit_logs WHERE registro_id = :rid ORDER BY created_at"
            ), {"rid": criado["id"]})).scalars().all()
            assert "CREATE" in logs and "UPDATE" in logs
        finally:
            await _limpar(db, client_ids=[cli], user_ids=[socio])
