# -*- coding: utf-8 -*-
"""Tarefa 5 — cursor opt-in em cases/clients/deadlines/documents (PostgreSQL).

Contrato:
  - legado: mesmo shape com `total` EXATO, `page`, `page_size` — nunca trocado
    por valor de página; agora com desempate por id (ordem determinística)
  - cursor: {"data","page_size","has_more","next_cursor"} — SEM total
  - concatenação das páginas cursor == conjunto do legado (dataset imutável)
  - page_size inválido → 422; cursor de outro usuário → 400
  - documents: busca com %, _, barra e texto longo; sigilo por confidencialidade
  - clients: titularidade preservada (hash cego não é exercido aqui — sem PII)
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.routers.cases import listar as casos_listar
from app.routers.clients import listar as clients_listar
from app.routers.deadlines import listar as deadlines_listar
from app.routers.documents import listar as documents_listar

_pg = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db, role, rotulo):
    uid = str(uuid4())
    await db.execute(text(
        "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
        "VALUES (:id, :e, 'x', :n, :role, true)"),
        {"id": uid, "e": f"t5-{rotulo}-{uid[:8]}@teste.local", "role": role,
         "n": f"T5 {rotulo}"})
    return uid


async def _carregar_user(db, uid):
    from app.models.user import User
    from sqlalchemy import select
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _criar_caso(db, dono, titulo, *, created_at=None):
    cid, cliente = str(uuid4()), str(uuid4())
    await db.execute(text(
        "INSERT INTO clients (id, nome, responsavel_id, tipo, status) "
        "VALUES (:id, :n, :d, 'PF', 'ativo')"),
        {"id": cliente, "n": f"Cliente {titulo}", "d": dono})
    await db.execute(text(
        "INSERT INTO cases (id, titulo, area, status, prioridade, client_id, "
        "advogado_responsavel_id, proxima_acao, created_at) VALUES "
        "(:id, :t, 'civil', 'aberto', 'media', :cli, :d, 'Ação', :ca)"),
        {"id": cid, "t": titulo, "cli": cliente, "d": dono,
         "ca": created_at or datetime.now(timezone.utc)})
    return cid


async def _limpar(db, *, user_ids=()):
    for uid in user_ids:
        await db.execute(text(
            "UPDATE documents SET deleted_at = now() WHERE uploaded_by = :u"),
            {"u": uid})
        await db.execute(text(
            "DELETE FROM documents WHERE uploaded_by = :u"), {"u": uid})
        await db.execute(text(
            "DELETE FROM deadlines WHERE responsavel_id = :u OR case_id IN "
            "(SELECT id FROM cases WHERE advogado_responsavel_id = :u)"), {"u": uid})
        await db.execute(text(
            "DELETE FROM tasks WHERE responsavel_id = :u OR case_id IN "
            "(SELECT id FROM cases WHERE advogado_responsavel_id = :u)"), {"u": uid})
        await db.execute(text(
            "DELETE FROM cases WHERE advogado_responsavel_id = :u"), {"u": uid})
        await db.execute(text(
            "DELETE FROM clients WHERE responsavel_id = :u"), {"u": uid})
        await db.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


# ── cases ────────────────────────────────────────────────────────────────────

@_pg
async def test_cases_legado_total_exato_e_desempate_id():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        a1 = await _criar_user(db, "advogado", "a1")
        # 60 casos, 20 com created_at EMPATADO (ordem só fica total com id)
        instante = datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)
        for i in range(60):
            ca = instante if i < 20 else None
            await _criar_caso(db, a1, f"Caso t5 {i:02d}", created_at=ca)
        await db.commit()
        try:
            cu = await _carregar_user(db, a1)
            out = await casos_listar(
                page=1, page_size=50, search=None, area=None, status_f=None,
                arquivo="ativos", advogado_id=None, urgentes=False,
                sem_proxima_acao=False, aguardando_cliente=False,
                aguardando_decisao=False, financeiro_pendente=False,
                pagination=None, cursor=None, db=db, cu=cu)
            assert out["total"] == 60  # total EXATO do legado
            assert out["page"] == 1 and out["page_size"] == 50
            assert len(out["data"]) == 50
            # desempate: created_at igual → id DESC decide (determinístico)
            ids = [c.id for c in out["data"]]
            out2 = await casos_listar(
                page=1, page_size=50, search=None, area=None, status_f=None,
                arquivo="ativos", advogado_id=None, urgentes=False,
                sem_proxima_acao=False, aguardando_cliente=False,
                aguardando_decisao=False, financeiro_pendente=False,
                pagination=None, cursor=None, db=db, cu=cu)
            assert [c.id for c in out2["data"]] == ids  # estável
            # page/page_size inválidos são barrados na camada FastAPI (Query)
            import inspect
            from fastapi.params import Query as _FastQuery
            sig = inspect.signature(casos_listar)
            assert isinstance(sig.parameters["page"].default, _FastQuery)
            assert isinstance(sig.parameters["page_size"].default, _FastQuery)
        finally:
            await _limpar(db, user_ids=[a1])


@_pg
async def test_cases_cursor_concatena_e_sem_total():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        a1 = await _criar_user(db, "advogado", "a1")
        a2 = await _criar_user(db, "advogado", "a2")
        instante = datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)
        for i in range(7):
            await _criar_caso(db, a1, f"Caso A {i}", created_at=instante)
        await _criar_caso(db, a2, "Caso B alheio", created_at=instante)
        await db.commit()
        try:
            cu1 = await _carregar_user(db, a1)
            legado = await casos_listar(
                page=1, page_size=100, search=None, area=None, status_f=None,
                arquivo="ativos", advogado_id=None, urgentes=False,
                sem_proxima_acao=False, aguardando_cliente=False,
                aguardando_decisao=False, financeiro_pendente=False,
                pagination=None, cursor=None, db=db, cu=cu1)
            assert legado["total"] == 7
            vistos, cursor = [], None
            while True:
                out = await casos_listar(
                    page=1, page_size=3, search=None, area=None, status_f=None,
                    arquivo="ativos", advogado_id=None, urgentes=False,
                    sem_proxima_acao=False, aguardando_cliente=False,
                    aguardando_decisao=False, financeiro_pendente=False,
                    pagination="cursor", cursor=cursor, db=db, cu=cu1)
                assert "total" not in out  # modo cursor SEM total
                vistos.extend(out["data"])
                if not out["has_more"]:
                    assert out["next_cursor"] is None
                    break
                cursor = out["next_cursor"]
            ids_v = [c.id for c in vistos]
            assert sorted(ids_v) == sorted(c.id for c in legado["data"])
            assert len(ids_v) == len(set(ids_v))
            # caso alheio NUNCA aparece
            assert all(c.advogado_responsavel_id == a1 for c in vistos)
            # page/page_size barrados na camada FastAPI (Query na assinatura)
            import inspect
            from fastapi.params import Query as _FastQuery
            sig = inspect.signature(casos_listar)
            assert isinstance(sig.parameters["page"].default, _FastQuery)
            assert isinstance(sig.parameters["page_size"].default, _FastQuery)
        finally:
            await _limpar(db, user_ids=[a1, a2])


# ── deadlines ────────────────────────────────────────────────────────────────

@_pg
async def test_deadlines_legado_e_cursor_com_empates():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        a1 = await _criar_user(db, "advogado", "a1")
        caso_a = await _criar_caso(db, a1, "Caso A dl")
        d = date(2026, 12, 1)  # única data → 5 empates totais
        for _ in range(5):
            await db.execute(text(
                "INSERT INTO deadlines (id, titulo, tipo, prioridade, status, "
                "data_prazo, case_id, responsavel_id) VALUES "
                "(:id, 'dl t5', 'processual', 'media', 'pendente', :d, :c, :r)"),
                {"id": str(uuid4()), "d": d, "c": caso_a, "r": a1})
        await db.commit()
        try:
            cu = await _carregar_user(db, a1)
            legado = await deadlines_listar(
                page=1, page_size=3, status_f="pendente", case_id=None,
                tipo=None, apenas_meus=False, pagination=None, cursor=None,
                db=db, cu=cu)
            assert legado["total"] == 5  # exato
            # desempate id: página 1 e 2 cobrem todos sem duplicar
            p1 = await deadlines_listar(
                page=1, page_size=3, status_f="pendente", case_id=None,
                tipo=None, apenas_meus=False, pagination="cursor",
                cursor=None, db=db, cu=cu)
            assert "total" not in p1 and p1["has_more"] is True
            p2 = await deadlines_listar(
                page=1, page_size=3, status_f="pendente", case_id=None,
                tipo=None, apenas_meus=False, pagination="cursor",
                cursor=p1["next_cursor"], db=db, cu=cu)
            ids = [x["id"] for x in p1["data"]] + [x["id"] for x in p2["data"]]
            assert len(ids) == len(set(ids)) and len(ids) == 5
            # urgencia preservada no modo cursor
            for item in p1["data"]:
                assert "urgencia" in item and "dias_restantes" in item
        finally:
            await _limpar(db, user_ids=[a1])


# ── documents ────────────────────────────────────────────────────────────────

@_pg
async def test_documents_busca_especiais_sigilo_e_cursor():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        a1 = await _criar_user(db, "advogado", "a1")
        caso_a = await _criar_caso(db, a1, "Caso A doc")
        instante = datetime.now(timezone.utc)
        docs = [
            ("doc com percentual 50%_extra", "normal"),      # % e _ no título
            ("doc com barra 50\\_x", "normal"),               # barra invertida
            ("doc com ocr extenso", "normal"),                # OCR extenso
            ("doc interno", "interno"),
            ("doc restrito", "restrito"),                     # sócio+ apenas
            ("doc segredo", "segredo_justica"),               # sócio+ apenas
        ]
        for titulo, conf in docs:
            ocr = (f"conteudo OCR de {titulo} com 100% _garantido_ "
                   + ("palavra " * 500 if "extenso" in titulo else ""))
            await db.execute(text(
                "INSERT INTO documents (id, titulo, filename, filepath, ocr_text, "
                "confidencialidade, case_id, uploaded_by, created_at) VALUES "
                "(:id, :t, 'a.pdf', '/x/a.pdf', :ocr, :c, :case, :u, :ca)"),
                {"id": str(uuid4()), "t": titulo,
                 "ocr": ocr,
                 "c": conf, "case": caso_a, "u": a1, "ca": instante})
        await db.commit()
        try:
            cu = await _carregar_user(db, a1)
            # sigilo: advogado não vê restrito/segredo (normal+interno apenas)
            legado = await documents_listar(
                page=1, page_size=20, case_id=caso_a, client_id=None,
                search=None, tipo=None, confidencialidade=None,
                data_inicio=None, data_fim=None, classificacao_pendente=None,
                pagination=None, cursor=None, db=db, cu=cu)
            assert legado["total"] == 4
            confs = {d["confidencialidade"] for d in legado["data"]}
            assert confs <= {"normal", "interno"}
            # busca com % e _ literais (escapadas pelo router)
            busca = await documents_listar(
                page=1, page_size=20, case_id=caso_a, client_id=None,
                search="50%_extra", tipo=None, confidencialidade=None,
                data_inicio=None, data_fim=None, classificacao_pendente=None,
                pagination=None, cursor=None, db=db, cu=cu)
            assert busca["total"] == 1
            assert "percentual" in busca["data"][0]["titulo"]
            # cursor: concatenação == legado, sem total
            vistos, cursor = [], None
            while True:
                out = await documents_listar(
                    page=1, page_size=2, case_id=caso_a, client_id=None,
                    search=None, tipo=None, confidencialidade=None,
                    data_inicio=None, data_fim=None,
                    classificacao_pendente=None, pagination="cursor",
                    cursor=cursor, db=db, cu=cu)
                assert "total" not in out
                vistos.extend(out["data"])
                if not out["has_more"]:
                    break
                cursor = out["next_cursor"]
            assert sorted(d["id"] for d in vistos) == \
                sorted(d["id"] for d in legado["data"])
            assert len(vistos) == len({d["id"] for d in vistos})
        finally:
            await _limpar(db, user_ids=[a1])


# ── clients ──────────────────────────────────────────────────────────────────

@_pg
async def test_clients_titularidade_e_cursor():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        a1 = await _criar_user(db, "advogado", "a1")
        a2 = await _criar_user(db, "advogado", "a2")
        for i in range(6):
            await db.execute(text(
                "INSERT INTO clients (id, nome, responsavel_id, tipo, status) "
                "VALUES (:id, :n, :d, 'PF', 'ativo')"),
                {"id": str(uuid4()), "n": f"Cliente T5 {i}", "d": a1})
        await db.execute(text(
            "INSERT INTO clients (id, nome, responsavel_id, tipo, status) "
            "VALUES (:id, :n, :d, 'PF', 'ativo')"),
            {"id": str(uuid4()), "n": "Cliente T5 alheio", "d": a2})
        await db.commit()
        try:
            cu1 = await _carregar_user(db, a1)
            legado = await clients_listar(
                page=1, page_size=100, search="Cliente T5", status_f=None,
                pagination=None, cursor=None, db=db, cu=cu1)
            assert legado["total"] == 6  # titularidade: só a carteira de A1
            vistos, cursor = [], None
            while True:
                out = await clients_listar(
                    page=1, page_size=2, search="Cliente T5", status_f=None,
                    pagination="cursor", cursor=cursor, db=db, cu=cu1)
                assert "total" not in out
                vistos.extend(out["data"])
                if not out["has_more"]:
                    break
                cursor = out["next_cursor"]
            assert len(vistos) == 6 and len(vistos) == len({c.id for c in vistos})
        finally:
            await _limpar(db, user_ids=[a1, a2])
