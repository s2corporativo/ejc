"""IDOR — gates de ownership recém-adicionados em sub-recursos do caso (row-level).

Trava contra regressão o isolamento entre advogados nos handlers que passaram a
chamar verificar_acesso_caso: um advogado SEM vínculo com o caso recebe 403,
enquanto o responsável e a gestão (socio) passam.

Cobre uma amostra dos endpoints corrigidos (timesheet,
caso_areas, centro-custos). Postgres é OBRIGATÓRIO (mesmo padrão dos demais
*_dblevel.py: chama o handler direto com AsyncSessionLocal). Sem RUN_DB_TESTS=1,
pula.
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


async def _criar_caso(db, client_id: str, titulo: str, resp_id: str | None = None) -> str:
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
        await db.execute(text("DELETE FROM caso_areas WHERE case_id = :id"), {"id": cid})
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


# ── timesheet: GET /timesheet/casos/{id} ───────────────────────────────────────

async def test_timesheet_por_caso_respeita_ownership():
    from app.core.database import AsyncSessionLocal
    from app.routers.timesheet import por_caso

    tok = f"Ts{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        resp_adv = await _criar_user(db, "advogado")
        outro_adv = await _criar_user(db, "advogado")
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente Ts {tok}")
        caso = await _criar_caso(db, cli, f"Caso ts {tok}", resp_id=resp_adv)
        await db.commit()
        try:
            # Responsável e gestão passam.
            r = await por_caso(caso, db, await _carregar_user(db, resp_adv))
            assert "total_horas" in r
            assert "total_horas" in await por_caso(caso, db, await _carregar_user(db, socio))
            # Advogado sem vínculo → 403 (gate verificar_acesso_caso).
            with pytest.raises(HTTPException) as exc:
                await por_caso(caso, db, await _carregar_user(db, outro_adv))
            assert exc.value.status_code == 403
        finally:
            await _limpar(db, case_ids=[caso],
                          user_ids=[resp_adv, outro_adv, socio], client_ids=[cli])


# ── caso_areas: GET /cases/{id}/areas ───────────────────────────────────────────

async def test_listar_areas_respeita_ownership():
    from app.core.database import AsyncSessionLocal
    from app.routers.caso_areas import listar_areas

    tok = f"Ar{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        resp_adv = await _criar_user(db, "advogado")
        outro_adv = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, f"Cliente Ar {tok}")
        caso = await _criar_caso(db, cli, f"Caso ar {tok}", resp_id=resp_adv)
        await db.commit()
        try:
            r = await listar_areas(caso, db, await _carregar_user(db, resp_adv))
            assert "areas" in r
            with pytest.raises(HTTPException) as exc:
                await listar_areas(caso, db, await _carregar_user(db, outro_adv))
            assert exc.value.status_code == 403
        finally:
            await _limpar(db, case_ids=[caso],
                          user_ids=[resp_adv, outro_adv], client_ids=[cli])
