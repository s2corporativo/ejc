"""Busca/paginação do GED contra PostgreSQL real."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

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
    ids = [str(uuid4()) for _ in range(3)]
    id_literal = ids[0]
    ordem_esperada = sorted(ids, reverse=True)
    try:
        async with Session() as db:
            try:
                db.add_all(
                    [
                        _doc(id_literal, "Contrato 100%_final", instante),
                        _doc(ids[1], "Contrato 100XXfinal", instante),
                        _doc(ids[2], "Outro documento", instante),
                    ]
                )
                await db.commit()

                base = select(Document).where(Document.id.in_(ids))

                literal = await paginar_documentos(
                    db,
                    base,
                    filtros=FiltrosBuscaDocumentos(search="100%_"),
                    page=1,
                    page_size=20,
                )
                assert literal.total == 1
                assert [d.id for d in literal.itens] == [id_literal]

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
                assert [d.id for d in primeira.itens] == ordem_esperada[:2]
                assert [d.id for d in segunda.itens] == ordem_esperada[2:]
                assert set(d.id for d in primeira.itens).isdisjoint(
                    d.id for d in segunda.itens
                )
            finally:
                await db.execute(delete(Document).where(Document.id.in_(ids)))
                await db.commit()
    finally:
        await engine.dispose()
