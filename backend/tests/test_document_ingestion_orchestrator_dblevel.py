"""Pipeline canônico local contra PostgreSQL real.

O service commita em SAVEPOINTs de uma transação externa. O rollback final da
conexão remove Documents/AuditLogs sintéticos sem executar DELETE contra WORM.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.document import DocConfidencialidade, Document
from app.services import document_ingestion_orchestrator as orchestrator
from app.services import document_ingestion_service as ingestion_svc
from app.services.document_extraction_adapter import (
    ResultadoExtracaoTexto,
    StatusExtracaoTexto,
)
from app.services.document_persistence_service import DadosPersistenciaDocumento

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


class StreamBytes:
    def __init__(self, conteudo: bytes) -> None:
        self.conteudo = conteudo
        self.offset = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            raise AssertionError("pipeline DB não pode materializar upload")
        if self.offset >= len(self.conteudo):
            return b""
        fim = min(self.offset + size, len(self.conteudo))
        chunk = self.conteudo[self.offset:fim]
        self.offset = fim
        return chunk


def _dados(predecessor: str | None = None) -> DadosPersistenciaDocumento:
    return DadosPersistenciaDocumento(
        titulo="Documento pipeline DB",
        tipo="peticao",
        confidencialidade=DocConfidencialidade.normal,
        user_role="advogado",
        documento_anterior_id=predecessor,
    )


@pytest.mark.asyncio
async def test_pipeline_raiz_e_v2_com_audit_e_rollback_externo(
    tmp_path: Path,
    monkeypatch,
):
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    arquivos: list[Path] = []

    monkeypatch.setattr(
        ingestion_svc,
        "validar_conteudo",
        lambda ext, amostra: "application/pdf",
    )

    async def extrair_fake(db, ingestao, *, user_id):
        assert ingestao.storage.caminho_staging_para_validacao.exists()
        return ResultadoExtracaoTexto(
            StatusExtracaoTexto.SUCESSO,
            ocr_text="texto sanitizado pipeline DB",
        )

    monkeypatch.setattr(orchestrator, "extrair_texto_compatibilidade", extrair_fake)

    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            Session = async_sessionmaker(
                bind=conn,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            raiz_id: str | None = None
            v2_id: str | None = None
            try:
                async with Session() as db:
                    raiz = await orchestrator.ingerir_documento_local(
                        db,
                        StreamBytes(b"%PDF-pipeline-raiz"),
                        filename="arquivo-raiz.pdf",
                        upload_root=tmp_path,
                        max_bytes=1024,
                        dados=_dados(),
                    )
                    raiz_id = raiz.documento.id
                    arquivos.append(tmp_path / raiz.documento.filepath)

                    assert raiz.documento.versao == 1
                    assert raiz.documento.versao_grupo_id == raiz_id
                    assert raiz.documento.ocr_text == "texto sanitizado pipeline DB"
                    assert arquivos[-1].exists()

                async with Session() as db:
                    v2 = await orchestrator.ingerir_documento_local(
                        db,
                        StreamBytes(b"%PDF-pipeline-v2"),
                        filename="arquivo-v2.pdf",
                        upload_root=tmp_path,
                        max_bytes=1024,
                        dados=_dados(predecessor=raiz_id),
                    )
                    v2_id = v2.documento.id
                    arquivos.append(tmp_path / v2.documento.filepath)

                    assert v2.documento.versao == 2
                    assert v2.documento.versao_grupo_id == raiz_id
                    assert v2.documento.versao_anterior_id == raiz_id
                    assert arquivos[-1].exists()

                    documentos = (
                        await db.execute(
                            select(Document).where(Document.id.in_([raiz_id, v2_id]))
                        )
                    ).scalars().all()
                    audits = (
                        await db.execute(
                            select(AuditLog).where(
                                AuditLog.entidade == "documents",
                                AuditLog.registro_id.in_([raiz_id, v2_id]),
                                AuditLog.acao == "UPLOAD",
                            )
                        )
                    ).scalars().all()
                    assert len(documentos) == 2
                    assert len(audits) == 2

                await outer.rollback()

                async with engine.connect() as check:
                    assert await check.scalar(
                        select(Document.id)
                        .where(Document.id.in_([raiz_id, v2_id]))
                        .limit(1)
                    ) is None
                    assert await check.scalar(
                        select(AuditLog.id)
                        .where(AuditLog.registro_id.in_([raiz_id, v2_id]))
                        .limit(1)
                    ) is None
            finally:
                if outer.is_active:
                    await outer.rollback()
    finally:
        for arquivo in arquivos:
            arquivo.unlink(missing_ok=True)
        await engine.dispose()
