"""Curadoria RAG — paginação/filtro de confiança no SQL (não em Python).

Regressão do pente fino (2026-07): em `GET /ia-governanca/rag-curadoria` o
filtro `confianca` era aplicado em Python DEPOIS do offset/limit do banco, então
o `total` retornado ignorava o filtro (contava todos os docs) e páginas ficavam
inconsistentes. O filtro passou a ser aplicado no SQL — `total` e páginas
refletem o recorte.

Postgres real via `AsyncSessionLocal` (o filtro usa operadores JSONB, PG-only).
Sem RUN_DB_TESTS=1, pula (nunca conecta em produção).
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db, role: str = "socio") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Curadoria Teste', :role, true)"),
        {"id": uid, "email": f"cur-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _criar_doc(db, categoria: str, confianca: str) -> str:
    from app.models.rag import KnowledgeDoc
    did = str(uuid4())
    db.add(KnowledgeDoc(
        id=did, titulo=f"Doc {did[:8]}", categoria=categoria,
        status_indexacao="indexado", extra={"confidence_level": confianca},
    ))
    return did


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def test_filtro_confianca_no_sql_corrige_total_e_paginas():
    from app.core.database import AsyncSessionLocal
    from app.routers.ia_governanca import listar_curadoria

    cat = f"catteste_{uuid4().hex[:8]}"  # isola dos demais docs da base
    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "socio")
        alta_ids = [await _criar_doc(db, cat, "alta") for _ in range(3)]
        baixa_ids = [await _criar_doc(db, cat, "baixa") for _ in range(2)]
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            # Sem filtro: 5 docs na categoria.
            todos = await listar_curadoria(
                page=1, page_size=2, categoria=cat, confianca=None,
                busca=None, db=db, cu=cu,
            )
            assert todos["total"] == 5

            # Com filtro: total reflete SÓ os "alta" (3), mesmo com page_size < total.
            page1 = await listar_curadoria(
                page=1, page_size=2, categoria=cat, confianca="alta",
                busca=None, db=db, cu=cu,
            )
            assert page1["total"] == 3
            assert len(page1["data"]) == 2
            assert all(i["confidence_level"] == "alta" for i in page1["data"])

            # Página 2 traz o 3º "alta" (paginação correta pós-filtro).
            page2 = await listar_curadoria(
                page=2, page_size=2, categoria=cat, confianca="alta",
                busca=None, db=db, cu=cu,
            )
            assert len(page2["data"]) == 1
            assert page2["data"][0]["confidence_level"] == "alta"
        finally:
            for did in alta_ids + baixa_ids:
                await db.execute(text("DELETE FROM knowledge_docs WHERE id = :id"), {"id": did})
            await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
            await db.commit()
