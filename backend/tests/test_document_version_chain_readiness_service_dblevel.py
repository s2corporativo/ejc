"""Preflight complementar da cadeia de versões contra PostgreSQL real."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.document import DocConfidencialidade, Document
from app.services.document_version_chain_readiness_service import (
    auditar_linearidade_versionamento,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


def _doc(
    doc_id: str,
    *,
    grupo_id: str,
    versao: int,
    anterior_id: str | None = None,
    deleted_at=None,
) -> Document:
    return Document(
        id=doc_id,
        titulo="Documento sintético linearidade",
        filename=f"{doc_id}.pdf",
        filepath=f"2026/08/{doc_id}.pdf",
        mimetype="application/pdf",
        size_bytes=10,
        confidencialidade=DocConfidencialidade.normal,
        versao=versao,
        versao_grupo_id=grupo_id,
        versao_anterior_id=anterior_id,
        deleted_at=deleted_at,
    )


@pytest.mark.asyncio
async def test_preflight_detecta_ramificacao_salto_e_ponta_deletada_sem_commit():
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as db:
            baseline = await auditar_linearidade_versionamento(db)

            # Grupo 1: v2 e v3 apontam para v1 => uma ramificação. A aresta
            # v1 -> v3 também é um salto de versão inválido.
            g1 = str(uuid4())
            g1_v2 = str(uuid4())
            g1_v3 = str(uuid4())

            # Grupo 2: ponta histórica v2 está soft-deleted e v1 segue ativa.
            g2 = str(uuid4())
            g2_v2 = str(uuid4())

            db.add_all(
                [
                    _doc(g1, grupo_id=g1, versao=1),
                    _doc(g1_v2, grupo_id=g1, versao=2, anterior_id=g1),
                    _doc(g1_v3, grupo_id=g1, versao=3, anterior_id=g1),
                    _doc(g2, grupo_id=g2, versao=1),
                    _doc(
                        g2_v2,
                        grupo_id=g2,
                        versao=2,
                        anterior_id=g2,
                        deleted_at=datetime.now(timezone.utc),
                    ),
                ]
            )
            await db.flush()

            depois = await auditar_linearidade_versionamento(db)

            assert (
                depois.predecessores_com_multiplos_sucessores
                == baseline.predecessores_com_multiplos_sucessores + 1
            )
            assert depois.arestas_versao_invalidas == baseline.arestas_versao_invalidas + 1
            assert (
                depois.grupos_ponta_historica_deletada
                == baseline.grupos_ponta_historica_deletada + 1
            )
            assert depois.cadeia_linear is False

            await db.rollback()
            final = await auditar_linearidade_versionamento(db)
            assert final == baseline
    finally:
        await engine.dispose()
