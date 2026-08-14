from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.document import DocConfidencialidade, Document
from app.services.document_version_service import preparar_nova_versao

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


def _doc(doc_id: str) -> Document:
    return Document(
        id=doc_id,
        titulo="Documento autoflush",
        filename=f"{doc_id}.pdf",
        filepath=f"2026/08/{doc_id}.pdf",
        mimetype="application/pdf",
        size_bytes=10,
        confidencialidade=DocConfidencialidade.normal,
    )


@pytest.mark.asyncio
async def test_novo_documento_pode_estar_pending_sem_autoflush_prematuro():
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    raiz_id = str(uuid4())
    novo_id = str(uuid4())
    ids = [raiz_id, novo_id]
    try:
        async with Session() as db:
            raiz = _doc(raiz_id)
            raiz.versao = 1
            raiz.versao_grupo_id = raiz_id
            db.add(raiz)
            await db.commit()

            novo = _doc(novo_id)
            db.add(novo)

            info = await preparar_nova_versao(
                db,
                novo,
                documento_anterior_id=raiz_id,
            )

            assert info.versao == 2
            assert novo.versao == 2
            assert novo.versao_grupo_id == raiz_id
            assert novo.versao_anterior_id == raiz_id

            await db.commit()

            persistido = await db.scalar(
                select(Document).where(Document.id == novo_id)
            )
            assert persistido is not None
            assert persistido.versao == 2
            assert persistido.versao_grupo_id == raiz_id
            assert persistido.versao_anterior_id == raiz_id
    finally:
        async with Session() as db:
            await db.execute(delete(Document).where(Document.id.in_(ids)))
            await db.commit()
        await engine.dispose()
