"""Preflight de versionamento contra PostgreSQL real.

O teste mede deltas sobre o estado inicial do banco e mantém todas as anomalias
sintéticas dentro de uma transação que é revertida no final.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.document import DocConfidencialidade, Document
from app.services.document_version_audit_service import auditar_versionamento_documental

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


def _doc(
    doc_id: str,
    *,
    grupo_id: str | None,
    versao: int,
    anterior_id: str | None = None,
    client_id: str | None = None,
) -> Document:
    return Document(
        id=doc_id,
        titulo="Documento sintético de auditoria",
        filename=f"{doc_id}.pdf",
        filepath=f"2026/08/{doc_id}.pdf",
        mimetype="application/pdf",
        size_bytes=10,
        confidencialidade=DocConfidencialidade.normal,
        client_id=client_id,
        versao=versao,
        versao_grupo_id=grupo_id,
        versao_anterior_id=anterior_id,
    )


@pytest.mark.asyncio
async def test_preflight_detecta_anomalias_sem_persistir_dados():
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as db:
            baseline = await auditar_versionamento_documental(db)

            client_id = str(uuid4())
            await db.execute(
                text(
                    "INSERT INTO clients (id, tipo, nome, email, status) "
                    "VALUES (:id, 'PF', 'Cliente sintético auditoria', :email, 'ativo')"
                ),
                {"id": client_id, "email": f"{client_id[:8]}@teste.local"},
            )

            clean = str(uuid4())
            legado = str(uuid4())
            grupo_sem_raiz = str(uuid4())
            filho_sem_raiz = str(uuid4())
            raiz_invalida = str(uuid4())
            duplicado = str(uuid4())
            dup_v2a = str(uuid4())
            dup_v2b = str(uuid4())
            multi = str(uuid4())
            multi_v2 = str(uuid4())
            grupo_a = str(uuid4())
            grupo_b = str(uuid4())
            fora_grupo = str(uuid4())
            contexto = str(uuid4())
            contexto_v2 = str(uuid4())
            invalido = str(uuid4())
            ciclo_a = str(uuid4())
            ciclo_b = str(uuid4())

            db.add_all(
                [
                    _doc(clean, grupo_id=clean, versao=1),
                    _doc(legado, grupo_id=None, versao=1),
                    _doc(filho_sem_raiz, grupo_id=grupo_sem_raiz, versao=2),
                    _doc(raiz_invalida, grupo_id=raiz_invalida, versao=2),
                    _doc(duplicado, grupo_id=duplicado, versao=1),
                    _doc(dup_v2a, grupo_id=duplicado, versao=2, anterior_id=duplicado),
                    _doc(dup_v2b, grupo_id=duplicado, versao=2, anterior_id=duplicado),
                    _doc(multi, grupo_id=multi, versao=1),
                    _doc(multi_v2, grupo_id=multi, versao=2),
                    _doc(grupo_a, grupo_id=grupo_a, versao=1),
                    _doc(grupo_b, grupo_id=grupo_b, versao=1),
                    _doc(fora_grupo, grupo_id=grupo_a, versao=2, anterior_id=grupo_b),
                    _doc(contexto, grupo_id=contexto, versao=1, client_id=client_id),
                    _doc(
                        contexto_v2,
                        grupo_id=contexto,
                        versao=2,
                        anterior_id=contexto,
                        client_id=None,
                    ),
                    _doc(invalido, grupo_id=invalido, versao=0),
                    _doc(ciclo_a, grupo_id=ciclo_a, versao=1),
                    _doc(ciclo_b, grupo_id=ciclo_a, versao=2),
                ]
            )
            await db.flush()

            await db.execute(
                text("UPDATE documents SET versao_anterior_id = :b WHERE id = :a"),
                {"a": ciclo_a, "b": ciclo_b},
            )
            await db.execute(
                text("UPDATE documents SET versao_anterior_id = :a WHERE id = :b"),
                {"a": ciclo_a, "b": ciclo_b},
            )

            depois = await auditar_versionamento_documental(db)

            assert depois.total_documentos == baseline.total_documentos + 17
            assert depois.documentos_sem_grupo == baseline.documentos_sem_grupo + 1
            assert (
                depois.grupos_sem_raiz_canonica
                == baseline.grupos_sem_raiz_canonica + 1
            )
            assert (
                depois.raizes_canonicas_invalidas
                == baseline.raizes_canonicas_invalidas + 1
            )
            assert depois.numeracoes_duplicadas == baseline.numeracoes_duplicadas + 1
            assert (
                depois.grupos_contexto_inconsistente
                == baseline.grupos_contexto_inconsistente + 1
            )
            assert depois.grupos_multiplas_raizes == baseline.grupos_multiplas_raizes + 1
            assert depois.predecessores_ausentes == baseline.predecessores_ausentes
            assert depois.predecessores_fora_grupo == baseline.predecessores_fora_grupo + 1
            assert (
                depois.predecessores_contexto_divergente
                == baseline.predecessores_contexto_divergente + 1
            )
            assert depois.cadeias_ciclicas == baseline.cadeias_ciclicas + 2
            assert depois.versoes_invalidas == baseline.versoes_invalidas + 1
            assert depois.apto_para_constraint is False

            await db.rollback()
            final = await auditar_versionamento_documental(db)
            assert final == baseline
    finally:
        await engine.dispose()
