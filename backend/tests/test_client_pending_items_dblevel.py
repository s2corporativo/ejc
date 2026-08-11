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


async def test_criar_pending_item_case_id_vazio_tambem_valida():
    """Achado do CodeRabbit: `if body.case_id:` (truthy) deixava "" passar
    direto pro INSERT sem validar — client_pending_items.case_id não tem FK,
    então gravava referência inválida em vez de rejeitar com 422."""
    from app.core.database import AsyncSessionLocal
    from app.routers.pending_items import PendingItemCreate, create_pending_item

    tok = f"PiVazio{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db)
        cli = await _criar_cliente(db, f"Cliente PiVazio {tok}")
        await db.commit()
        try:
            u_socio = await _carregar_user(db, socio)
            with pytest.raises(HTTPException) as exc:
                await create_pending_item(
                    cli, PendingItemCreate(title="X", case_id=""), db, u_socio)
            assert exc.value.status_code == 422
        finally:
            await _limpar(db, client_ids=[cli], user_ids=[socio])


async def test_atualizar_pending_item_rejeita_null_explicito_em_campo_not_null():
    """title/type/status são NOT NULL na tabela; {"status": null} não pode
    passar da validação Pydantic e virar UPDATE ... SET status=NULL (500 sem
    tratamento) — achado do code-reviewer."""
    from pydantic import ValidationError
    from app.routers.pending_items import PendingItemUpdate

    with pytest.raises(ValidationError):
        PendingItemUpdate(title=None)
    with pytest.raises(ValidationError):
        PendingItemUpdate(type=None)
    with pytest.raises(ValidationError):
        PendingItemUpdate(status=None)
    # Omitir o campo (não enviá-lo) continua válido — só null explícito falha.
    ok = PendingItemUpdate(description="apenas isso mudou")
    assert ok.model_dump(exclude_unset=True) == {"description": "apenas isso mudou"}


async def test_atualizar_pending_item_case_id_editavel_e_validado():
    from app.core.database import AsyncSessionLocal
    from app.routers.pending_items import (
        PendingItemCreate, PendingItemUpdate, create_pending_item, update_pending_item,
    )

    tok = f"PiCase{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db)
        cli_a = await _criar_cliente(db, f"Cliente A {tok}")
        cli_b = await _criar_cliente(db, f"Cliente B {tok}")
        caso_de_a = await _criar_caso(db, cli_a, f"Caso A {tok}")
        caso_de_b = await _criar_caso(db, cli_b, f"Caso B {tok}")
        await db.commit()
        try:
            u_socio = await _carregar_user(db, socio)
            criado = await create_pending_item(
                cli_a, PendingItemCreate(title="X"), db, u_socio)

            # Vincular a um caso do MESMO cliente: ok.
            await update_pending_item(
                cli_a, criado["id"], PendingItemUpdate(case_id=caso_de_a), db, u_socio)
            row = (await db.execute(text(
                "SELECT case_id FROM client_pending_items WHERE id = :id"
            ), {"id": criado["id"]})).mappings().first()
            assert row["case_id"] == caso_de_a

            # Vincular a caso de OUTRO cliente: 422.
            with pytest.raises(HTTPException) as exc:
                await update_pending_item(
                    cli_a, criado["id"], PendingItemUpdate(case_id=caso_de_b), db, u_socio)
            assert exc.value.status_code == 422

            # Desvincular (case_id=None explícito): ok.
            await update_pending_item(
                cli_a, criado["id"], PendingItemUpdate(case_id=None), db, u_socio)
            row = (await db.execute(text(
                "SELECT case_id FROM client_pending_items WHERE id = :id"
            ), {"id": criado["id"]})).mappings().first()
            assert row["case_id"] is None
        finally:
            await _limpar(db, case_ids=[caso_de_a, caso_de_b], client_ids=[cli_a, cli_b],
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


async def test_pending_items_rejeita_client_id_inexistente_mesmo_sob_visao_total():
    """Achado do Codex: visão total (gestão/secretaria) dispensava a checagem
    de EXISTÊNCIA do cliente, não só a de vínculo — client_pending_items.
    client_id não tem FK, então um client_id arbitrário criava registro órfão
    e listagens de cliente inexistente devolviam 200 em vez de 404."""
    from app.core.database import AsyncSessionLocal
    from app.routers.pending_items import PendingItemCreate, create_pending_item, list_pending_items

    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db)
        await db.commit()
        try:
            u_socio = await _carregar_user(db, socio)
            client_id_inexistente = str(uuid4())

            with pytest.raises(HTTPException) as exc:
                await list_pending_items(client_id_inexistente, None, db, u_socio)
            assert exc.value.status_code == 404

            with pytest.raises(HTTPException) as exc:
                await create_pending_item(
                    client_id_inexistente, PendingItemCreate(title="X"), db, u_socio)
            assert exc.value.status_code == 404

            # Nenhum registro órfão deve ter sido criado.
            orfaos = (await db.execute(text(
                "SELECT COUNT(*) FROM client_pending_items WHERE client_id = :cid"
            ), {"cid": client_id_inexistente})).scalar()
            assert orfaos == 0
        finally:
            await _limpar(db, user_ids=[socio])


async def test_delete_pending_item_inexistente_nao_grava_audit_log():
    """Achado do Codex: o UPDATE (soft delete) sem WHERE afetar linha alguma
    ainda gravava um audit log "DELETE" e devolvia {"ok": True} — o log
    (imutável, WORM) passava a afirmar uma exclusão que nunca aconteceu."""
    from app.core.database import AsyncSessionLocal
    from app.routers.pending_items import delete_pending_item

    tok = f"PiDel{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db)
        cli = await _criar_cliente(db, f"Cliente PiDel {tok}")
        await db.commit()
        try:
            u_socio = await _carregar_user(db, socio)
            item_id_inexistente = str(uuid4())

            with pytest.raises(HTTPException) as exc:
                await delete_pending_item(cli, item_id_inexistente, db, u_socio)
            assert exc.value.status_code == 404

            logs = (await db.execute(text(
                "SELECT COUNT(*) FROM audit_logs WHERE registro_id = :rid"
            ), {"rid": item_id_inexistente})).scalar()
            assert logs == 0
        finally:
            await _limpar(db, client_ids=[cli], user_ids=[socio])
