"""Preflight de storage contra PostgreSQL real, com rollback integral."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.document import DocConfidencialidade, Document
from app.services.document_storage_readiness_service import auditar_storage_documental

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


def _doc(
    doc_id: str,
    *,
    filepath: str,
    drive_file_id: str | None = None,
) -> Document:
    return Document(
        id=doc_id,
        titulo="Documento sintético storage",
        filename=f"{doc_id}.pdf",
        filepath=filepath,
        mimetype="application/pdf",
        size_bytes=10,
        confidencialidade=DocConfidencialidade.normal,
        drive_file_id=drive_file_id,
    )


@pytest.mark.asyncio
async def test_preflight_detecta_metadados_inconsistentes_sem_commit():
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    token = uuid4().hex
    try:
        async with Session() as db:
            baseline = await auditar_storage_documental(db)

            path_local_duplicado = f"auditoria/{token}/duplicado.pdf"
            drive_id_duplicado = f"drive-{token}"

            db.add_all(
                [
                    _doc(str(uuid4()), filepath=path_local_duplicado),
                    _doc(str(uuid4()), filepath=path_local_duplicado),
                    _doc(
                        str(uuid4()),
                        filepath=f"drive://casos/{token}/a.pdf",
                        drive_file_id=drive_id_duplicado,
                    ),
                    _doc(
                        str(uuid4()),
                        filepath=f"drive://casos/{token}/b.pdf",
                        drive_file_id=drive_id_duplicado,
                    ),
                    _doc(
                        str(uuid4()),
                        filepath=f"auditoria/{token}/drive-sem-marcador.pdf",
                        drive_file_id=f"drive-sem-marcador-{token}",
                    ),
                    _doc(
                        str(uuid4()),
                        filepath=f"drive://casos/{token}/marcador-sem-id.pdf",
                        drive_file_id=None,
                    ),
                ]
            )
            await db.flush()

            depois = await auditar_storage_documental(db)

            assert depois.documentos_ativos == baseline.documentos_ativos + 6
            assert depois.ativos_drive == baseline.ativos_drive + 3
            assert depois.ativos_local == baseline.ativos_local + 2
            assert depois.drive_id_duplicado == baseline.drive_id_duplicado + 1
            assert depois.drive_id_sem_marcador == baseline.drive_id_sem_marcador + 1
            assert depois.marcador_drive_sem_id == baseline.marcador_drive_sem_id + 1
            assert (
                depois.paths_ativos_duplicados
                == baseline.paths_ativos_duplicados + 1
            )
            assert depois.metadados_consistentes is False

            await db.rollback()
            final = await auditar_storage_documental(db)
            assert final == baseline
    finally:
        await engine.dispose()
