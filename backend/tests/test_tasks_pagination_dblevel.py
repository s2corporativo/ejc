"""Tarefa 2 — paginação por cursor em /tasks (integração PostgreSQL).

Sem RUN_DB_TESTS=1 os testes DB pulam — mas o gate exige execução REAL com
Postgres (RUN_DB_TESTS=1 + DATABASE_URL apontando para cópia sintética, NUNCA
produção; SCHEMA_CHECK_DATABASE_URL idem para test_schema_sync).

Contrato:
  - legado (sem pagination=cursor): mesmo shape {"data": [...]}, sem limite novo
  - cursor: {"data", "page_size", "has_more", "next_cursor"} — SEM total
  - concatenação das páginas cursor == conjunto visível do legado, sem
    duplicatas (dataset imutável), mesma ordem total
    (data_limite ASC NULLS LAST, created_at ASC NULLS LAST, id ASC)
  - autorização reaplicada a cada página: cursor de outro usuário é inválido;
    filtro de visibilidade (tasks.py:118-130, IMUTÁVEL nesta fase) aplica-se
    a todas as páginas
  - semântica live: edição concorrente entre páginas NÃO promete snapshot
    (documentado; o teste só prova que não quebra a paginação)
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.routers.tasks import listar

_pg = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)

ORDER = "data_limite:asc_nulls_last,created_at:asc,id:asc"


async def _criar_user(db, role: str, rotulo: str) -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', :nome, :role, true)"),
        {"id": uid, "email": f"cur-{rotulo}-{uid[:8]}@teste.local", "role": role,
         "nome": f"Cursor {rotulo}"},
    )
    return uid


async def _carregar_user(db, uid: str):
    from app.models.user import User
    from sqlalchemy import select
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _criar_caso(db, dono: str, titulo: str) -> str:
    cid = str(uuid4())
    cliente = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, nome, responsavel_id, tipo, status) "
             "VALUES (:id, :n, :dono, 'PF', 'ativo')"),
        {"id": cliente, "n": f"Cliente {titulo}", "dono": dono},
    )
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, prioridade, "
             "client_id, advogado_responsavel_id, proxima_acao, created_at) VALUES "
             "(:id, :t, 'civil', 'aberto', 'media', :cli, :dono, 'Ação sintética', now())"),
        {"id": cid, "t": titulo, "cli": cliente, "dono": dono},
    )
    return cid


async def _criar_task(db, *, titulo, case_id=None, resp=None, criado=None,
                      data_limite=None, status="a_fazer", created_at=None):
    tid = str(uuid4())
    await db.execute(
        text("INSERT INTO tasks (id, titulo, status, prioridade, data_limite, "
             "case_id, responsavel_id, criado_por, created_at) VALUES "
             "(:id, :t, :st, 'media', :dl, :cid, :resp, :criado, :cat)"),
        {"id": tid, "t": titulo, "st": status, "dl": data_limite, "cid": case_id,
         "resp": resp, "criado": criado or resp,
         "cat": created_at or datetime.now(timezone.utc)},
    )
    return tid


async def _limpar(db, *, user_ids=()):
    for uid in user_ids:
        await db.execute(
            text("DELETE FROM tasks WHERE responsavel_id = :u OR criado_por = :u "
                 "OR case_id IN (SELECT id FROM cases WHERE advogado_responsavel_id = :u)"),
            {"u": uid})
        await db.execute(
            text("DELETE FROM cases WHERE advogado_responsavel_id = :u"), {"u": uid})
        await db.execute(
            text("DELETE FROM clients WHERE responsavel_id = :u"), {"u": uid})
        await db.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


@_pg
async def test_legado_shape_e_sem_limite_novo():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        a1 = await _criar_user(db, "advogado", "a1")
        caso_a = await _criar_caso(db, a1, "Caso A cursor")
        for i in range(7):  # mais que o page_size do cursor (5)
            await _criar_task(db, titulo=f"T legado {i}", case_id=caso_a,
                              resp=a1, data_limite=date(2026, 11, 1) + timedelta(days=i))
        await db.commit()
        try:
            cu = await _carregar_user(db, a1)
            out_legado = await listar(case_id=None, minhas=False, db=db, cu=cu)
            assert isinstance(out_legado, dict) and "data" in out_legado
            # shape legado NÃO ganhou campo novo de paginação nem limite novo
            assert "has_more" not in out_legado
            assert "next_cursor" not in out_legado
            assert len(out_legado["data"]) == 7
        finally:
            await _limpar(db, user_ids=[a1])


@_pg
async def test_cursor_concatenacao_igual_legado_sem_duplicatas():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        a1 = await _criar_user(db, "advogado", "a1")
        caso_a = await _criar_caso(db, a1, "Caso A concat")
        # empatadas: mesma data_limite → desempate por created_at/id decide
        mesmo_instante = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        ids_criados = []
        for i in range(12):
            dl = date(2026, 11, 1) if i % 3 else date(2026, 11, 2)
            tid = await _criar_task(db, titulo=f"T conc {i}", case_id=caso_a,
                                    resp=a1, data_limite=dl,
                                    created_at=mesmo_instante)
            ids_criados.append(tid)
        # avulsas e NULL data_limite (NULLS LAST → fim da ordem)
        await _criar_task(db, titulo="T avulsa", resp=a1, criado=a1,
                          data_limite=None)
        await _criar_task(db, titulo="T caso null dl", case_id=caso_a, resp=a1,
                          data_limite=None)
        await db.commit()
        try:
            cu = await _carregar_user(db, a1)
            legado = await listar(case_id=None, minhas=False, db=db, cu=cu)
            ids_legado = [t["id"] for t in legado["data"]]
            assert len(ids_legado) == 14

            paginas = []
            cursor = None
            saltos = 0
            while saltos < 10:
                out = await listar(case_id=None, minhas=False, pagination="cursor",
                                   cursor=cursor, page_size=5, db=db, cu=cu)
                paginas.extend(out["data"])
                if not out["has_more"]:
                    assert out["next_cursor"] is None
                    break
                cursor = out["next_cursor"]
                saltos += 1
            ids_cursor = [t["id"] for t in paginas]

            # MESMO CONJUNTO visível, sem duplicatas (o legado não promete
            # ordem total — sem desempate por id em empates; o cursor sim)
            assert sorted(ids_cursor) == sorted(ids_legado)
            assert len(ids_cursor) == len(set(ids_cursor))
            # ordem do cursor é determinística: 2ª execução idêntica
            paginas2: list = []
            cursor = None
            while True:
                out = await listar(case_id=None, minhas=False, pagination="cursor",
                                   cursor=cursor, page_size=5, db=db, cu=cu)
                paginas2.extend(out["data"])
                if not out["has_more"]:
                    break
                cursor = out["next_cursor"]
            assert [t["id"] for t in paginas2] == ids_cursor
            # NULL data_limite por último (NULLS LAST)
            assert paginas[-1]["data_limite"] is None
            # shape cursor: sem total, com campos novos
            out1 = await listar(case_id=None, minhas=False, pagination="cursor",
                                cursor=None, page_size=5, db=db, cu=cu)
            assert "total" not in out1
            assert out1["page_size"] == 5
            assert len(out1["data"]) == 5  # n, não n+1
        finally:
            await _limpar(db, user_ids=[a1])


@_pg
async def test_cursor_de_outro_usuario_e_rejeitado():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        a1 = await _criar_user(db, "advogado", "a1")
        a2 = await _criar_user(db, "advogado", "a2")
        caso_a = await _criar_caso(db, a1, "Caso A only")
        caso_b = await _criar_caso(db, a2, "Caso B only")
        for i in range(6):
            await _criar_task(db, titulo=f"A{i}", case_id=caso_a, resp=a1,
                              data_limite=date(2026, 11, 5))
            await _criar_task(db, titulo=f"B{i}", case_id=caso_b, resp=a2,
                              data_limite=date(2026, 11, 5))
        await db.commit()
        try:
            cu1 = await _carregar_user(db, a1)
            cu2 = await _carregar_user(db, a2)
            p1_a1 = await listar(case_id=None, minhas=False, pagination="cursor",
                                 cursor=None, page_size=3, db=db, cu=cu1)
            assert p1_a1["has_more"] is True
            # A2 tenta continuar a navegação de A1 → inválido
            with pytest.raises(HTTPException):
                await listar(case_id=None, minhas=False, pagination="cursor",
                             cursor=p1_a1["next_cursor"], page_size=3,
                             db=db, cu=cu2)
            # A1 com filtro trocado → inválido (invalidação por filtro)
            with pytest.raises(HTTPException):
                await listar(case_id=caso_b, minhas=False, pagination="cursor",
                             cursor=p1_a1["next_cursor"], page_size=3,
                             db=db, cu=cu1)
        finally:
            await _limpar(db, user_ids=[a1, a2])


@_pg
async def test_autorizacao_reaplicada_a_cada_pagina():
    """A1 nunca recebe tarefa do caso B (de A2) em NENHUMA página."""
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        a1 = await _criar_user(db, "advogado", "a1")
        a2 = await _criar_user(db, "advogado", "a2")
        caso_a = await _criar_caso(db, a1, "Caso A vis")
        caso_b = await _criar_caso(db, a2, "Caso B vis")
        for i in range(9):  # atravessa ≥2 páginas
            await _criar_task(db, titulo=f"A{i}", case_id=caso_a, resp=a1,
                              data_limite=date(2026, 11, 8))
            await _criar_task(db, titulo=f"B{i}", case_id=caso_b, resp=a2,
                              data_limite=date(2026, 11, 8))
        await db.commit()
        try:
            cu1 = await _carregar_user(db, a1)
            cu2 = await _carregar_user(db, a2)
            vistos_a1, vistos_a2 = [], []
            cursor = None
            while True:
                out = await listar(case_id=None, minhas=False, pagination="cursor",
                                   cursor=cursor, page_size=4, db=db, cu=cu1)
                vistos_a1.extend(t["titulo"] for t in out["data"])
                if not out["has_more"]:
                    break
                cursor = out["next_cursor"]
            cursor = None
            while True:
                out = await listar(case_id=None, minhas=False, pagination="cursor",
                                   cursor=cursor, page_size=4, db=db, cu=cu2)
                vistos_a2.extend(t["titulo"] for t in out["data"])
                if not out["has_more"]:
                    break
                cursor = out["next_cursor"]
            assert all(t.startswith("A") for t in vistos_a1)
            assert all(t.startswith("B") for t in vistos_a2)
            assert len(vistos_a1) == 9 and len(vistos_a2) == 9
        finally:
            await _limpar(db, user_ids=[a1, a2])


@_pg
async def test_ultimo_item_pagina_e_has_more_n_plus_1():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        a1 = await _criar_user(db, "advogado", "a1")
        caso_a = await _criar_caso(db, a1, "Caso A n+1")
        for i in range(5):  # exatamente page_size
            await _criar_task(db, titulo=f"N{i}", case_id=caso_a, resp=a1,
                              data_limite=date(2026, 11, 9))
        await db.commit()
        try:
            cu = await _carregar_user(db, a1)
            out = await listar(case_id=None, minhas=False, pagination="cursor",
                               cursor=None, page_size=5, db=db, cu=cu)
            assert len(out["data"]) == 5
            assert out["has_more"] is False
            assert out["next_cursor"] is None
        finally:
            await _limpar(db, user_ids=[a1])


@_pg
async def test_cursor_tamper_rejeitado_na_rota():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        a1 = await _criar_user(db, "advogado", "a1")
        caso_a = await _criar_caso(db, a1, "Caso A tamper")
        await _criar_task(db, titulo="única", case_id=caso_a, resp=a1,
                          data_limite=date(2026, 11, 10))
        await db.commit()
        try:
            cu = await _carregar_user(db, a1)
            with pytest.raises(HTTPException):
                await listar(case_id=None, minhas=False, pagination="cursor",
                             cursor="lixo.assassinado", page_size=5,
                             db=db, cu=cu)
        finally:
            await _limpar(db, user_ids=[a1])
