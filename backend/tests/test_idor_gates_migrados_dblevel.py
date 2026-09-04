"""IDOR — gates de ownership adicionados aos sub-recursos migrados (row-level).

Trava contra regressão o isolamento entre advogados nos handlers que passaram a
usar `verificar_acesso_caso`: extratos, honorários-calc, kanban, checklists e
dossiê estratégico. Um advogado SEM vínculo com o caso deve receber 403.

Postgres é OBRIGATÓRIO (mesmo padrão dos demais *_dblevel.py: chama o handler
direto com AsyncSessionLocal). Sem RUN_DB_TESTS=1, pula.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


# ── Helpers (SQL cru, como nos demais *_dblevel.py) ─────────────────────────────

async def _criar_user(db, role: str = "advogado") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'IDOR Teste', :role, true)"),
        {"id": uid, "email": f"idor-{uid[:8]}@teste.local", "role": role},
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


async def _criar_caso(db, client_id: str, titulo: str, resp_id: str) -> str:
    case_id = str(uuid4())
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id, "
             "advogado_responsavel_id) VALUES "
             "(:id, :titulo, 'civil', 'em_instrucao', :cid, :resp)"),
        {"id": case_id, "titulo": titulo, "cid": client_id, "resp": resp_id},
    )
    return case_id


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, *, case_ids=(), user_ids=(), client_ids=()):
    for cid in case_ids:
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    for uid in user_ids:
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def _cenario(db, tok: str):
    resp_adv = await _criar_user(db, "advogado")
    outro_adv = await _criar_user(db, "advogado")
    cli = await _criar_cliente(db, f"Cliente IDOR {tok}")
    caso = await _criar_caso(db, cli, f"Caso IDOR {tok}", resp_id=resp_adv)
    await db.commit()
    return resp_adv, outro_adv, cli, caso


# ── extratos: GET /extratos/detalhado/{case_id} ─────────────────────────────────

async def test_extrato_caso_respeita_ownership():
    from app.core.database import AsyncSessionLocal
    from app.routers.extratos import extrato_caso

    async with AsyncSessionLocal() as db:
        resp_adv, outro_adv, cli, caso = await _cenario(db, f"Ext{uuid4().hex[:6]}")
        try:
            # Responsável enxerga o extrato.
            r = await extrato_caso(caso, db, await _carregar_user(db, resp_adv))
            assert "resumo" in r
            # Advogado sem vínculo → 403 (gate verificar_acesso_caso).
            with pytest.raises(HTTPException) as exc:
                await extrato_caso(caso, db, await _carregar_user(db, outro_adv))
            assert exc.value.status_code == 403
        finally:
            await _limpar(db, case_ids=[caso],
                          user_ids=[resp_adv, outro_adv], client_ids=[cli])


# ── honorarios_oab: GET /honorarios-oab/cases/{case_id}/provisionamento ─────────

async def test_provisionamento_respeita_ownership():
    from app.core.database import AsyncSessionLocal
    from app.routers.honorarios_oab import provisionamento

    async with AsyncSessionLocal() as db:
        resp_adv, outro_adv, cli, caso = await _cenario(db, f"Prov{uuid4().hex[:6]}")
        try:
            r = await provisionamento(caso, None, db, await _carregar_user(db, resp_adv))
            assert "ok" in r
            with pytest.raises(HTTPException) as exc:
                await provisionamento(caso, None, db, await _carregar_user(db, outro_adv))
            assert exc.value.status_code == 403
        finally:
            await _limpar(db, case_ids=[caso],
                          user_ids=[resp_adv, outro_adv], client_ids=[cli])


# ── kanban: PATCH /v1/cases/{case_id}/kanban ────────────────────────────────────

async def test_kanban_update_respeita_ownership():
    from app.core.database import AsyncSessionLocal
    from app.routers.kanban import update_case_kanban

    async with AsyncSessionLocal() as db:
        resp_adv, outro_adv, cli, caso = await _cenario(db, f"Kb{uuid4().hex[:6]}")
        body = {"kanban_column": "Em andamento", "kanban_position": 1}
        try:
            r = await update_case_kanban(caso, dict(body), db, await _carregar_user(db, resp_adv))
            assert r["ok"] is True
            with pytest.raises(HTTPException) as exc:
                await update_case_kanban(caso, dict(body), db, await _carregar_user(db, outro_adv))
            assert exc.value.status_code == 403
        finally:
            await _limpar(db, case_ids=[caso],
                          user_ids=[resp_adv, outro_adv], client_ids=[cli])


# ── checklists: GET /checklists/casos/{case_id} ─────────────────────────────────

async def test_checklists_do_caso_respeita_ownership():
    from app.core.database import AsyncSessionLocal
    from app.routers.checklists import checklists_do_caso

    async with AsyncSessionLocal() as db:
        resp_adv, outro_adv, cli, caso = await _cenario(db, f"Ck{uuid4().hex[:6]}")
        try:
            r = await checklists_do_caso(caso, None, db, await _carregar_user(db, resp_adv))
            assert isinstance(r, list)
            with pytest.raises(HTTPException) as exc:
                await checklists_do_caso(caso, None, db, await _carregar_user(db, outro_adv))
            assert exc.value.status_code == 403
        finally:
            await _limpar(db, case_ids=[caso],
                          user_ids=[resp_adv, outro_adv], client_ids=[cli])


# ── dossie_estrategico: GET /dossie/{case_id} ───────────────────────────────────

async def test_dossie_obter_atual_respeita_ownership():
    from app.core.database import AsyncSessionLocal
    from app.routers.dossie_estrategico import obter_atual

    async with AsyncSessionLocal() as db:
        resp_adv, outro_adv, cli, caso = await _cenario(db, f"Ds{uuid4().hex[:6]}")
        try:
            # Advogado sem vínculo → 403 antes de qualquer consulta ao dossiê.
            with pytest.raises(HTTPException) as exc:
                await obter_atual(caso, db, await _carregar_user(db, outro_adv))
            assert exc.value.status_code == 403
        finally:
            await _limpar(db, case_ids=[caso],
                          user_ids=[resp_adv, outro_adv], client_ids=[cli])
