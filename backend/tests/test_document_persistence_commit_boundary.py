from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.models.document import DocConfidencialidade
from app.services import document_ingestion_service as ingestion_svc
from app.services.document_ingestion_service import preparar_ingestao_documento_local
from app.services.document_persistence_service import (
    DadosPersistenciaDocumento,
    persistir_documento_local,
)
from app.services.document_storage_uow import EstadoStorageLocal


class StreamBytes:
    def __init__(self, conteudo: bytes) -> None:
        self.conteudo = conteudo
        self.offset = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            raise AssertionError("leitura ilimitada não permitida")
        if self.offset >= len(self.conteudo):
            return b""
        fim = min(self.offset + size, len(self.conteudo))
        chunk = self.conteudo[self.offset:fim]
        self.offset = fim
        return chunk


class CancelAfterCommitDB:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1
        atual = asyncio.current_task()
        assert atual is not None
        asyncio.get_running_loop().call_soon(atual.cancel)

    async def rollback(self) -> None:
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_cancelamento_solicitado_apos_commit_nao_compensa_arquivo(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(
        ingestion_svc,
        "validar_conteudo",
        lambda ext, amostra: "application/pdf",
    )
    ingestao = await preparar_ingestao_documento_local(
        StreamBytes(b"%PDF-boundary"),
        filename="arquivo.pdf",
        upload_root=tmp_path,
        max_bytes=1024,
    )
    db = CancelAfterCommitDB()

    tarefa = asyncio.create_task(
        persistir_documento_local(
            db,  # type: ignore[arg-type]
            ingestao,
            dados=DadosPersistenciaDocumento(
                titulo="Documento boundary",
                tipo="peticao",
                confidencialidade=DocConfidencialidade.normal,
                user_role="advogado",
            ),
        )
    )

    try:
        try:
            await tarefa
        except asyncio.CancelledError:
            # O cancelamento pode ser entregue na saída do async context, mas a
            # confirmação síncrona já deve ter ocorrido depois do commit.
            pass

        assert db.commits == 1
        assert ingestao.storage.estado is EstadoStorageLocal.CONFIRMADO
        assert ingestao.full_path.exists()
        assert db.rollbacks == 0
    finally:
        ingestao.full_path.unlink(missing_ok=True)
