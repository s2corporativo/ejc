"""Outbox durável para eliminação física de documentos após hard purge.

O banco confirma ``AuditLog + outbox + DELETE documents`` em uma única
transação. Somente depois o worker processa o objeto físico. Isso evita os dois
modos perigosos: apagar storage antes de um commit que pode falhar, ou apagar a
linha e perder para sempre a intenção de limpeza após crash.
"""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.document import Document, DocumentStorageOperation
from app.services import google_drive as gd


class StorageOperationTransientError(RuntimeError):
    pass


class StorageOperationInvalidaError(RuntimeError):
    pass


def _remote_path(document: Document) -> str | None:
    raw = str(document.filepath or "")
    if not raw.startswith("drive://"):
        return None
    valor = raw[len("drive://") :].strip()
    if not valor or valor == str(document.drive_file_id or ""):
        return None
    return valor


def criar_operacao_purge(
    document: Document,
    *,
    requested_by: str | None,
) -> DocumentStorageOperation:
    """Captura identidade física antes do hard delete sem executar I/O."""

    if document.drive_file_id:
        kind = "drive"
        locator = _remote_path(document) or str(document.drive_file_id)
        drive_file_id = str(document.drive_file_id)
    else:
        kind = "local"
        locator = str(document.filepath or "").strip()
        drive_file_id = None

    if not locator:
        raise StorageOperationInvalidaError("documento sem identidade de storage")

    material = f"purge\0{document.id}\0{kind}\0{locator}\0{drive_file_id or ''}"
    operation_key = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return DocumentStorageOperation(
        id=str(uuid4()),
        operation_key=operation_key,
        document_id=document.id,
        storage_kind=kind,
        storage_locator=locator,
        drive_file_id=drive_file_id,
        status="pending",
        requested_by=requested_by,
    )


def _local_path_confinado(locator: str) -> Path:
    settings = get_settings()
    raiz = Path(settings.UPLOAD_DIR).resolve()
    destino = (raiz / locator).resolve()
    try:
        destino.relative_to(raiz)
    except ValueError as exc:
        raise StorageOperationInvalidaError("locator local fora da raiz de uploads") from exc
    return destino


async def _apagar_local(locator: str) -> None:
    caminho = _local_path_confinado(locator)

    def _unlink() -> None:
        try:
            caminho.unlink()
        except FileNotFoundError:
            pass

    await asyncio.to_thread(_unlink)


async def _apagar_drive(operation: DocumentStorageOperation) -> None:
    file_id = str(operation.drive_file_id or "").strip()
    if not file_id:
        raise StorageOperationInvalidaError("operação Drive sem file_id")
    remote_path = str(operation.storage_locator or "").strip()
    if remote_path == file_id:
        remote_path = None
    try:
        await asyncio.to_thread(gd.delete_file, file_id, remote_path=remote_path)
    except gd.DriveObjetoNaoEncontradoError:
        # Idempotência: objeto já ausente satisfaz a intenção de purge.
        return
    except gd.DriveIndisponivelError as exc:
        raise StorageOperationTransientError("storage remoto indisponível") from exc
    except Exception as exc:
        raise StorageOperationTransientError("falha transitória no storage remoto") from exc


async def processar_operacao_storage(operation_id: str) -> str:
    """Processa uma operação de outbox de forma idempotente e retry-safe."""

    async with AsyncSessionLocal() as db:
        operation = (
            await db.execute(
                select(DocumentStorageOperation)
                .where(DocumentStorageOperation.id == operation_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if operation is None:
            return "missing"
        if operation.status == "done":
            return "done"

        operation.status = "processing"
        operation.attempts = int(operation.attempts or 0) + 1
        operation.last_error_code = None
        await db.commit()

        try:
            if operation.storage_kind == "local":
                await _apagar_local(operation.storage_locator)
            elif operation.storage_kind == "drive":
                await _apagar_drive(operation)
            else:
                raise StorageOperationInvalidaError("tipo de storage desconhecido")
        except StorageOperationInvalidaError:
            operation.status = "failed"
            operation.last_error_code = "invalid_operation"
            await db.commit()
            return "failed"
        except StorageOperationTransientError:
            operation.status = "failed"
            operation.last_error_code = "storage_unavailable"
            await db.commit()
            raise
        except OSError as exc:
            operation.status = "failed"
            operation.last_error_code = "storage_io_error"
            await db.commit()
            raise StorageOperationTransientError("falha transitória de I/O") from exc

        operation.status = "done"
        operation.processed_at = datetime.now(timezone.utc)
        operation.last_error_code = None
        await db.commit()
        return "done"
