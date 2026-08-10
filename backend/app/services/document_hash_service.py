"""Hash streaming de documentos já persistidos em storage local.

Destinado ao futuro backfill/rescan de arquivos legados. Não conhece SQLAlchemy,
Document, FastAPI ou Google Drive. O caller fornece raiz confiável + filepath
persistido e pode exigir que o tamanho físico coincida com o metadado do banco.

O módulo não retorna path em erro e não materializa o arquivo inteiro em memória.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

CHUNK_HASH_BYTES = 1024 * 1024


class HashDocumentoError(RuntimeError):
    pass


class HashPathInvalidoError(HashDocumentoError):
    pass


class HashArquivoIndisponivelError(HashDocumentoError):
    pass


class HashMetadataMismatchError(HashDocumentoError):
    pass


@dataclass(frozen=True, slots=True)
class HashDocumentoCalculado:
    sha256: str
    size_bytes: int


def _resolver_path_local(upload_root: Path, filepath: str) -> Path:
    bruto = str(filepath or "").strip()
    rel = PurePosixPath(bruto)
    if (
        not bruto
        or rel.is_absolute()
        or "\\" in bruto
        or ":" in bruto
        or any(part in {"", ".", ".."} for part in rel.parts)
    ):
        raise HashPathInvalidoError("filepath documental inválido")

    raiz = upload_root.resolve()
    candidato = raiz.joinpath(*rel.parts)
    try:
        resolvido = candidato.resolve(strict=False)
        resolvido.relative_to(raiz)
    except (OSError, ValueError):
        raise HashPathInvalidoError("filepath documental inválido") from None
    return candidato


def _calcular_sync(
    upload_root: Path,
    filepath: str,
    expected_size: int | None,
) -> HashDocumentoCalculado:
    caminho = _resolver_path_local(upload_root, filepath)

    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    try:
        fd = os.open(caminho, flags)
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
        raise HashArquivoIndisponivelError("arquivo local indisponível para hash") from None

    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise HashArquivoIndisponivelError("arquivo local indisponível para hash")
        if expected_size is not None:
            if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size < 0:
                raise ValueError("expected_size inválido")
            if info.st_size != expected_size:
                raise HashMetadataMismatchError("tamanho físico diverge do metadado documental")

        digest = hashlib.sha256()
        total = 0
        with os.fdopen(fd, "rb", closefd=False) as handle:
            while True:
                chunk = handle.read(CHUNK_HASH_BYTES)
                if not chunk:
                    break
                digest.update(chunk)
                total += len(chunk)
        return HashDocumentoCalculado(
            sha256=digest.hexdigest(),
            size_bytes=total,
        )
    finally:
        os.close(fd)


async def calcular_sha256_local(
    upload_root: Path,
    filepath: str,
    *,
    expected_size: int | None = None,
) -> HashDocumentoCalculado:
    """Calcula SHA-256 sem bloquear o event loop e com cancelamento ordenado."""

    tarefa = asyncio.create_task(
        asyncio.to_thread(_calcular_sync, upload_root, filepath, expected_size)
    )
    try:
        return await asyncio.shield(tarefa)
    except asyncio.CancelledError:
        # to_thread não pode ser interrompida com segurança. Aguardar o FD fechar
        # evita trabalho de I/O órfão enquanto o caller já segue com teardown.
        try:
            await tarefa
        finally:
            raise
