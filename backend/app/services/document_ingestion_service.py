"""Preparação canônica de ingestão documental local.

Esta camada concentra somente responsabilidades físicas e determinísticas do
upload GED: nome original como metadado, extensão allowlisted, ID/path gerados
pelo servidor, recepção streaming, SHA-256 e MIME derivado do conteúdo.

Autorização, tipo jurídico, confidencialidade, OCR, versionamento, persistência
``Document`` e AuditLog continuam fora desta etapa até o cutover do router.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import Self
from uuid import uuid4

from app.services.document_content_policy import (
    exigir_extensao_permitida,
    validar_conteudo,
)
from app.services.document_storage_uow import DocumentStorageUnitOfWork
from app.services.document_upload_stream import StreamUploadAssincrono


def normalizar_nome_original(filename: str | None, fallback: str) -> str:
    """Normaliza somente metadado; nunca usa o nome do cliente no path físico."""

    nome = (filename or fallback).replace("\\", "/").rsplit("/", 1)[-1].strip()
    return (nome or fallback)[:255]


def _destino_confinado(root: Path, rel: Path) -> Path:
    """Prova defesa em profundidade mesmo com path atualmente server-side."""

    raiz = root.resolve()
    destino = (raiz / rel).resolve()
    try:
        destino.relative_to(raiz)
    except ValueError as exc:
        raise ValueError("destino de ingestão escapou da raiz configurada") from exc
    return destino


@dataclass(slots=True)
class IngestaoDocumentoLocal:
    """Metadados físicos + lifecycle compensável de um upload preparado."""

    doc_id: str
    filename: str
    ext: str
    mimetype: str
    filepath: str
    storage: DocumentStorageUnitOfWork

    @property
    def size_bytes(self) -> int:
        return self.storage.size_bytes

    @property
    def sha256(self) -> str:
        return self.storage.sha256

    @property
    def full_path(self) -> Path:
        return self.storage.destino_final

    def promover(self) -> None:
        self.storage.promover()

    def confirmar(self) -> None:
        self.storage.confirmar()

    async def __aenter__(self) -> Self:
        await self.storage.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        return await self.storage.__aexit__(exc_type, exc, tb)


async def preparar_ingestao_documento_local(
    upload: StreamUploadAssincrono,
    *,
    filename: str | None,
    upload_root: Path,
    max_bytes: int,
    agora: datetime | None = None,
) -> IngestaoDocumentoLocal:
    """Prepara upload GED sem persistir banco ou expor path derivado do cliente.

    Em falha de magic bytes/MIME o staging é compensado antes de propagar o
    erro da política de conteúdo. O caller deve usar o retorno como ``async with``
    e chamar ``confirmar()`` somente após commit de ``Document`` + AuditLog.
    """

    ext = exigir_extensao_permitida(filename)
    doc_id = str(uuid4())
    instante = agora or datetime.now(timezone.utc)
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)

    rel = Path(f"{instante.year}") / f"{instante.month:02d}" / f"{doc_id}{ext}"
    full = _destino_confinado(upload_root, rel)
    nome_original = normalizar_nome_original(filename, f"documento{ext}")

    storage = await DocumentStorageUnitOfWork.iniciar(
        upload,
        destino_final=full,
        suffix=ext,
        max_bytes=max_bytes,
    )
    try:
        mimetype = validar_conteudo(ext, storage.amostra_inicial)
    except BaseException:
        storage.compensar()
        raise

    return IngestaoDocumentoLocal(
        doc_id=doc_id,
        filename=nome_original,
        ext=ext,
        mimetype=mimetype,
        filepath=str(rel),
        storage=storage,
    )
