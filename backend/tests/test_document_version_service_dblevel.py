"""Versionamento documental explícito contra PostgreSQL real.

Gate igual aos demais *_dblevel.py: só executa com RUN_DB_TESTS=1. Cada cenário
usa engine NullPool e IDs próprios para não contaminar o pool/event loop global.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.document import DocConfidencialidade, Document
from app.services.document_version_service import (
    DocumentoAnteriorObsoletoError,
    DocumentoContextoDivergenteError,
    DocumentoGrupoInconsistenteError,
    preparar_nova_versao,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


def _documento(
    doc_id: str,
    *,
    grupo_id: str | None = None,
    versao: int = 1,
    anterior_id: str | None = None,
    deleted_at=None,
) -> Document:
    return Document(
        id=doc_id,
        titulo=f"Documento versão {versao}",
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


async def _limpar_grupo(db, grupo_id: str) -> None:
    await db.execute(
        text(
            "DELETE FROM documents "
            "WHERE versao_grupo_id = :grupo OR id = :grupo"
        ),
        {"grupo": grupo_id},
    )
    await db.commit()


@pytest.mark.asyncio
async def test_sequencia_explicita_e_predecessor_obsoleto():
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    raiz_id = str(uuid4())
    v2_id = str(uuid4())
    v3_id = str(uuid4())
    try:
        async with Session() as db:
            db.add(_documento(raiz_id, grupo_id=raiz_id))
            await db.commit()

            v2 = _documento(v2_id)
            info2 = await preparar_nova_versao(
                db, v2, documento_anterior_id=raiz_id
            )
            assert info2.versao == 2
            assert v2.versao_grupo_id == raiz_id
            assert v2.versao_anterior_id == raiz_id
            db.add(v2)
            await db.commit()

            stale = _documento(str(uuid4()))
            with pytest.raises(DocumentoAnteriorObsoletoError):
                await preparar_nova_versao(
                    db, stale, documento_anterior_id=raiz_id
                )
            await db.rollback()

            v3 = _documento(v3_id)
            info3 = await preparar_nova_versao(
                db, v3, documento_anterior_id=v2_id
            )
            assert info3.versao == 3
            assert v3.versao_anterior_id == v2_id
            db.add(v3)
            await db.commit()

            await _limpar_grupo(db, raiz_id)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_duas_criacoes_concorrentes_nao_recebem_mesma_versao():
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    raiz_id = str(uuid4())
    try:
        async with Session() as setup:
            setup.add(_documento(raiz_id, grupo_id=raiz_id))
            await setup.commit()

        async def tentar(doc_id: str):
            async with Session() as db:
                novo = _documento(doc_id)
                try:
                    info = await preparar_nova_versao(
                        db, novo, documento_anterior_id=raiz_id
                    )
                    db.add(novo)
                    await asyncio.sleep(0.05)
                    await db.commit()
                    return ("ok", info.versao)
                except DocumentoAnteriorObsoletoError:
                    await db.rollback()
                    return ("obsoleto", None)

        resultados = await asyncio.gather(
            tentar(str(uuid4())),
            tentar(str(uuid4())),
        )
        assert sorted(r[0] for r in resultados) == ["obsoleto", "ok"]
        assert [r[1] for r in resultados if r[0] == "ok"] == [2]

        async with Session() as db:
            quantidade_v2 = await db.scalar(
                select(func.count(Document.id)).where(
                    Document.versao_grupo_id == raiz_id,
                    Document.versao == 2,
                )
            )
            assert quantidade_v2 == 1
            await _limpar_grupo(db, raiz_id)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_grupo_com_numero_duplicado_falha_fechado():
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    raiz_id = str(uuid4())
    v2a_id = str(uuid4())
    v2b_id = str(uuid4())
    try:
        async with Session() as db:
            db.add_all(
                [
                    _documento(raiz_id, grupo_id=raiz_id),
                    _documento(v2a_id, grupo_id=raiz_id, versao=2, anterior_id=raiz_id),
                    _documento(v2b_id, grupo_id=raiz_id, versao=2, anterior_id=raiz_id),
                ]
            )
            await db.commit()

            novo = _documento(str(uuid4()))
            with pytest.raises(DocumentoGrupoInconsistenteError):
                await preparar_nova_versao(
                    db, novo, documento_anterior_id=v2a_id
                )
            await db.rollback()
            await _limpar_grupo(db, raiz_id)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_numero_de_versao_soft_deleted_nao_e_reutilizado():
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    raiz_id = str(uuid4())
    v2_id = str(uuid4())
    try:
        async with Session() as db:
            db.add_all(
                [
                    _documento(raiz_id, grupo_id=raiz_id),
                    _documento(
                        v2_id,
                        grupo_id=raiz_id,
                        versao=2,
                        anterior_id=raiz_id,
                        deleted_at=datetime.now(timezone.utc),
                    ),
                ]
            )
            await db.commit()

            v3 = _documento(str(uuid4()))
            info = await preparar_nova_versao(
                db, v3, documento_anterior_id=raiz_id
            )
            assert info.versao == 3
            assert v3.versao == 3
            db.add(v3)
            await db.commit()

            await _limpar_grupo(db, raiz_id)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_contexto_do_novo_documento_deve_ser_igual_ao_predecessor():
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    raiz_id = str(uuid4())
    try:
        async with Session() as db:
            db.add(_documento(raiz_id, grupo_id=raiz_id))
            await db.commit()

            novo = _documento(str(uuid4()))
            novo.case_id = str(uuid4())
            with pytest.raises(DocumentoContextoDivergenteError):
                await preparar_nova_versao(
                    db, novo, documento_anterior_id=raiz_id
                )
            await db.rollback()
            await _limpar_grupo(db, raiz_id)
    finally:
        await engine.dispose()
