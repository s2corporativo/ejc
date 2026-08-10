"""Busca/paginação do GED contra PostgreSQL real."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.document import DocConfidencialidade, Document
from app.services.document_search_service import (
    FiltrosBuscaDocumentos,
    paginar_documentos,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)

IDS = [
    "00000000-0000-0000-0000-000000009901",
    "00000000-0000-0000-0000-000000009902",
    "00000000-0000-0000-0000-000000009903",
]


def _doc(doc_id: str, titulo: str, criado: datetime) -> Document:
    return Document(
        id=doc_id,
        titulo=titulo,
        filename=f"{doc_id}.pdf",
        filepath=f"2026/08/{doc_id}.pdf",
        mimetype="application/pdf",
        size_bytes=10,
        confidencialidade=DocConfidencialidade.normal,
        created_at=criado,
    )


@pytest.mark.asyncio
async def test_busca_literal_e_paginacao_estavel():
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    instante = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    try:
        async with Session() as db:
            try:
                db.add_all(
                    [
                        _doc(IDS[0], "Contrato 100%_final", instante),
                        _doc(IDS[1], "Contrato 100XXfinal", instante),
                        _doc(IDS[2], "Outro documento", instante),
                    ]
                )
                await db.commit()

                base = select(Document).where(Document.id.in_(IDS))

                literal = await paginar_documentos(
                    db,
                    base,
                    filtros=FiltrosBuscaDocumentos(search="100%_"),
                    page=1,
                    page_size=20,
                )
                assert literal.total == 1
                assert [d.id for d in literal.itens] == [IDS[0]]

                primeira = await paginar_documentos(
                    db,
                    base,
                    filtros=FiltrosBuscaDocumentos(),
                    page=1,
                    page_size=2,
                )
                segunda = await paginar_documentos(
                    db,
                    base,
                    filtros=FiltrosBuscaDocumentos(),
                    page=2,
                    page_size=2,
                )

                assert primeira.total == 3
                assert segunda.total == 3
                assert [d.id for d in primeira.itens] == [IDS[2], IDS[1]]
                assert [d.id for d in segunda.itens] == [IDS[0]]
                assert set(d.id for d in primeira.itens).isdisjoint(
                    d.id for d in segunda.itens
                )
            finally:
                await db.execute(delete(Document).where(Document.id.in_(IDS)))
                await db.commit()
    finally:
        await engine.dispose()
