"""Gates de ownership de LEITURA nos sub-recursos do caso (row-level).

Trava contra regressão o isolamento entre advogados nos GETs que agregam dados
sensíveis do caso: movimentos, linha-do-tempo e teses-sugeridas. Um advogado
sem vínculo com o caso NÃO pode ler nenhum deles.

Contratos distintos, ambos encodados aqui:
  • /movimentos e /linha-do-tempo usam _filtro_visibilidade → advogado sem
    vínculo recebe 404 (a query não retorna o caso; nada vaza).
  • /teses-sugeridas usa verificar_acesso_caso → advogado sem vínculo recebe 403.

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
             "VALUES (:id, :email, 'x', 'Sub Teste', :role, true)"),
        {"id": uid, "email": f"sub-{uid[:8]}@teste.local", "role": role},
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
             "(:id, :titulo, 'civil', 'ativo', :cid, :resp)"),
        {"id": case_id, "titulo": titulo, "cid": client_id, "resp": resp_id},
    )
    return case_id


async def _criar_movimento(db, case_id: str, descricao: str) -> None:
    await db.execute(
        text("INSERT INTO case_movimentos (id, case_id, tipo, descricao) "
             "VALUES (:id, :cid, 'nota', :desc)"),
        {"id": str(uuid4()), "cid": case_id, "desc": descricao},
    )


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, *, case_ids=(), user_ids=(), client_ids=()):
    for cid in case_ids:
        await db.execute(text("DELETE FROM case_movimentos WHERE case_id = :id"), {"id": cid})
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


# ── /movimentos ────────────────────────────────────────────────────────────────

async def test_movimentos_respeita_ownership():
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import listar_movimentos

    tok = f"Mov{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        resp_adv = await _criar_user(db, "advogado")
        outro_adv = await _criar_user(db, "advogado")
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente Mov {tok}")
        caso = await _criar_caso(db, cli, f"Caso mov {tok}", resp_id=resp_adv)
        await _criar_movimento(db, caso, f"Peticao inicial {tok}")
        await db.commit()
        try:
            # Responsável enxerga os movimentos.
            movs = await listar_movimentos(caso, db, await _carregar_user(db, resp_adv))
            assert [m["descricao"] for m in movs] == [f"Peticao inicial {tok}"]
            # Gestão vê qualquer caso.
            assert len(await listar_movimentos(caso, db, await _carregar_user(db, socio))) == 1
            # Advogado sem vínculo → 404 (não vaza os movimentos).
            with pytest.raises(HTTPException) as exc:
                await listar_movimentos(caso, db, await _carregar_user(db, outro_adv))
            assert exc.value.status_code == 404
        finally:
            await _limpar(db, case_ids=[caso],
                          user_ids=[resp_adv, outro_adv, socio], client_ids=[cli])


# ── /linha-do-tempo ────────────────────────────────────────────────────────────

async def test_linha_do_tempo_respeita_ownership():
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import linha_do_tempo

    tok = f"Ldt{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        resp_adv = await _criar_user(db, "advogado")
        outro_adv = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, f"Cliente Ldt {tok}")
        caso = await _criar_caso(db, cli, f"Caso ldt {tok}", resp_id=resp_adv)
        await _criar_movimento(db, caso, f"Evento {tok}")
        await db.commit()
        try:
            # Responsável obtém a cronologia.
            r = await linha_do_tempo(caso, db, await _carregar_user(db, resp_adv))
            assert r["case_id"] == caso
            # Advogado sem vínculo → 404.
            with pytest.raises(HTTPException) as exc:
                await linha_do_tempo(caso, db, await _carregar_user(db, outro_adv))
            assert exc.value.status_code == 404
        finally:
            await _limpar(db, case_ids=[caso],
                          user_ids=[resp_adv, outro_adv], client_ids=[cli])


# ── /teses-sugeridas ───────────────────────────────────────────────────────────

async def test_teses_sugeridas_respeita_ownership():
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import teses_sugeridas

    tok = f"Tes{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        resp_adv = await _criar_user(db, "advogado")
        outro_adv = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, f"Cliente Tes {tok}")
        caso = await _criar_caso(db, cli, f"Caso tes {tok}", resp_id=resp_adv)
        await db.commit()
        try:
            # Responsável obtém a sugestão (fail-safe: pode vir vazia).
            r = await teses_sugeridas(caso, 5, db, await _carregar_user(db, resp_adv))
            assert "teses" in r
            # Advogado sem vínculo → 403 (gate verificar_acesso_caso).
            with pytest.raises(HTTPException) as exc:
                await teses_sugeridas(caso, 5, db, await _carregar_user(db, outro_adv))
            assert exc.value.status_code == 403
        finally:
            await _limpar(db, case_ids=[caso],
                          user_ids=[resp_adv, outro_adv], client_ids=[cli])
