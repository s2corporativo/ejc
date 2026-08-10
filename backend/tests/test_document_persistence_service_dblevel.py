"""Persistência canônica do GED contra PostgreSQL real.

Os commits do service ocorrem dentro de SAVEPOINTs de uma transação externa da
conexão. Ao final, o rollback externo remove Document/AuditLog sintéticos sem
executar DELETE contra a trilha WORM.
"""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.document import DocConfidencialidade, Document
from app.services import document_ingestion_service as ingestion_svc
from app.services.document_ingestion_service import preparar_ingestao_documento_local
from app.services.document_persistence_service import (
    ConteudoDocumentoPreparado,
    DadosPersistenciaDocumento,
    persistir_documento_local,
)
from app.services.document_storage_uow import EstadoStorageLocal
from app.services.document_version_service import DocumentoAnteriorNaoEncontradoError

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


class StreamBytes:
    def __init__(self, conteudo: bytes) -> None:
        self._conteudo = conteudo
        self._offset = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            raise AssertionError("persistência DB não pode materializar upload")
        if self._offset >= len(self._conteudo):
            return b""
        fim = min(self._offset + size, len(self._conteudo))
        chunk = self._conteudo[self._offset:fim]
        self._offset = fim
        return chunk


async def _preparar(tmp_path: Path, monkeypatch, nome: str, conteudo: bytes):
    monkeypatch.setattr(
        ingestion_svc,
        "validar_conteudo",
        lambda ext, amostra: "application/pdf",
    )
    return await preparar_ingestao_documento_local(
        StreamBytes(conteudo),
        filename=nome,
        upload_root=tmp_path,
        max_bytes=1024 * 1024,
    )


def _dados(*, predecessor: str | None = None) -> DadosPersistenciaDocumento:
    return DadosPersistenciaDocumento(
        titulo="Documento processual sintético",
        tipo="peticao",
        confidencialidade=DocConfidencialidade.normal,
        uploaded_by=None,
        user_role="advogado",
        documento_anterior_id=predecessor,
    )


@pytest.mark.asyncio
async def test_raiz_e_v2_commitam_document_audit_e_storage_sem_vazar_filename(
    tmp_path: Path,
    monkeypatch,
):
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    caminhos_confirmados: list[Path] = []
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            Session = async_sessionmaker(
                bind=conn,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            try:
                raiz_ing = await _preparar(
                    tmp_path,
                    monkeypatch,
                    "parte-cpf-raiz-sentinela.pdf",
                    b"%PDF-raiz",
                )
                async with Session() as db:
                    raiz = await persistir_documento_local(
                        db,
                        raiz_ing,
                        dados=_dados(),
                        conteudo=ConteudoDocumentoPreparado(
                            ocr_text="texto sanitizado raiz"
                        ),
                    )
                    caminhos_confirmados.append(raiz_ing.full_path)

                    persistida = await db.scalar(
                        select(Document).where(Document.id == raiz.id)
                    )
                    audit = await db.scalar(
                        select(AuditLog).where(
                            AuditLog.entidade == "documents",
                            AuditLog.registro_id == raiz.id,
                            AuditLog.acao == "UPLOAD",
                        )
                    )

                    assert persistida is not None
                    assert persistida.versao == 1
                    assert persistida.versao_grupo_id == raiz.id
                    assert persistida.versao_anterior_id is None
                    assert persistida.ocr_text == "texto sanitizado raiz"
                    assert raiz_ing.storage.estado is EstadoStorageLocal.CONFIRMADO
                    assert raiz_ing.full_path.exists()
                    assert audit is not None
                    serializado = repr(
                        {
                            "detalhes": audit.detalhes,
                            "dados_antes": audit.dados_antes,
                            "dados_depois": audit.dados_depois,
                        }
                    )
                    assert "parte-cpf-raiz-sentinela" not in serializado
                    assert raiz_ing.filepath not in serializado
                    assert "Documento processual sintético" not in serializado

                v2_ing = await _preparar(
                    tmp_path,
                    monkeypatch,
                    "parte-cpf-v2-sentinela.pdf",
                    b"%PDF-v2",
                )
                async with Session() as db:
                    v2 = await persistir_documento_local(
                        db,
                        v2_ing,
                        dados=_dados(predecessor=raiz.id),
                    )
                    caminhos_confirmados.append(v2_ing.full_path)

                    persistida_v2 = await db.scalar(
                        select(Document).where(Document.id == v2.id)
                    )
                    assert persistida_v2 is not None
                    assert persistida_v2.versao == 2
                    assert persistida_v2.versao_grupo_id == raiz.id
                    assert persistida_v2.versao_anterior_id == raiz.id
                    assert v2_ing.storage.estado is EstadoStorageLocal.CONFIRMADO
                    assert v2_ing.full_path.exists()

                await outer.rollback()

                # A transação externa removeu inclusive os AuditLogs sem DELETE.
                async with engine.connect() as check_conn:
                    doc_count = await check_conn.scalar(
                        select(Document.id).where(Document.id.in_([raiz.id, v2.id])).limit(1)
                    )
                    audit_count = await check_conn.scalar(
                        select(AuditLog.id)
                        .where(AuditLog.registro_id.in_([raiz.id, v2.id]))
                        .limit(1)
                    )
                    assert doc_count is None
                    assert audit_count is None
            finally:
                if outer.is_active:
                    await outer.rollback()
    finally:
        for caminho in caminhos_confirmados:
            caminho.unlink(missing_ok=True)
        await engine.dispose()


@pytest.mark.asyncio
async def test_predecessor_inexistente_reverte_db_e_compensa_staging(
    tmp_path: Path,
    monkeypatch,
):
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            Session = async_sessionmaker(
                bind=conn,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            ingestao = await _preparar(
                tmp_path,
                monkeypatch,
                "parte-cpf-falha-sentinela.pdf",
                b"%PDF-falha",
            )
            doc_id = ingestao.doc_id
            try:
                async with Session() as db:
                    with pytest.raises(DocumentoAnteriorNaoEncontradoError):
                        await persistir_documento_local(
                            db,
                            ingestao,
                            dados=_dados(predecessor=str(uuid4())),
                        )

                    assert await db.scalar(
                        select(Document.id).where(Document.id == doc_id)
                    ) is None
                    assert await db.scalar(
                        select(AuditLog.id).where(AuditLog.registro_id == doc_id)
                    ) is None

                assert ingestao.storage.estado is EstadoStorageLocal.COMPENSADO
                assert not ingestao.full_path.exists()
                assert not list(tmp_path.rglob(".*.uploading"))
            finally:
                await outer.rollback()
    finally:
        await engine.dispose()
