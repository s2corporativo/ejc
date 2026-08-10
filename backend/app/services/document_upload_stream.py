"""Primitiva de streaming para ingestão documental.

Este módulo não conhece FastAPI, banco, caso, cliente ou regra de negócio do
GED. Sua responsabilidade é limitada a receber um stream assíncrono, impor um
teto duro antes de gravar o chunk excedente, calcular SHA-256 incremental e
manter somente uma pequena amostra inicial para validação por magic bytes.

O arquivo nasce em staging oculto. O chamador só deve promovê-lo ao destino
final depois das validações de domínio (duplicidade, MIME, autorização etc.).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol
from uuid import uuid4

logger = logging.getLogger(__name__)

CHUNK_UPLOAD_BYTES = 1024 * 1024
AMOSTRA_MAGIC_BYTES = 2048


class StreamUploadAssincrono(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


class UploadVazioError(ValueError):
    """O stream terminou sem qualquer byte."""


class UploadExcedeLimiteError(ValueError):
    """O próximo chunk faria o upload ultrapassar o teto configurado."""

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        super().__init__("upload excede o limite configurado")


@dataclass(frozen=True, slots=True)
class UploadEmStaging:
    caminho: Path
    size_bytes: int
    sha256: str
    amostra_inicial: bytes


def _suffix_seguro(suffix: str) -> str:
    valor = (suffix or "").lower()
    if not valor:
        return ""
    if (
        not valor.startswith(".")
        or len(valor) > 16
        or "/" in valor
        or "\\" in valor
        or valor in {".", ".."}
    ):
        raise ValueError("suffix inválido para staging")
    return valor


def descartar_staging(arquivo: UploadEmStaging) -> None:
    """Remove staging; ausência é idempotente, outros erros são propagados."""

    try:
        arquivo.caminho.unlink()
    except FileNotFoundError:
        pass


def _descartar_caminho_best_effort(caminho: Path) -> None:
    """Cleanup de exceção/cancelamento sem mascarar a falha original."""

    try:
        caminho.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        # O path não é logado; nem traceback é emitido para evitar path interno.
        logger.error("Falha ao remover staging documental após erro")


def _criar_staging_aberto(caminho: Path) -> BinaryIO:
    """Cria inode 0600, O_EXCL, antes do primeiro ponto de cancelamento async."""

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    fd = os.open(caminho, flags, 0o600)
    try:
        return os.fdopen(fd, "wb")
    except BaseException:
        os.close(fd)
        _descartar_caminho_best_effort(caminho)
        raise


async def _aguardar_io_thread(func, *args):
    """Conclui a operação de disco antes de propagar cancelamento do request.

    ``asyncio.to_thread`` não interrompe a chamada síncrona que já começou.
    Fechar/unlinkar o arquivo enquanto essa thread ainda escreve criaria outra
    corrida. Por isso o cancelamento externo é adiado somente até a operação de
    I/O corrente terminar; em seguida ele é propagado normalmente.
    """

    tarefa = asyncio.create_task(asyncio.to_thread(func, *args))
    try:
        return await asyncio.shield(tarefa)
    except asyncio.CancelledError:
        try:
            await tarefa
        finally:
            raise


async def _escrever_chunk(arquivo: BinaryIO, chunk: bytes) -> None:
    escritos = await _aguardar_io_thread(arquivo.write, chunk)
    if escritos != len(chunk):
        raise OSError("escrita incompleta no staging documental")


def promover_staging(arquivo: UploadEmStaging, destino_final: Path) -> None:
    """Promove no mesmo diretório sem aceitar sobrescrita conhecida."""

    origem_parent = arquivo.caminho.parent.resolve()
    destino_parent = destino_final.parent.resolve()
    if origem_parent != destino_parent:
        raise ValueError("staging e destino final precisam compartilhar diretório")
    if os.path.lexists(destino_final):
        raise FileExistsError("destino final de upload já existe")
    os.replace(arquivo.caminho, destino_final)


async def receber_em_staging(
    upload: StreamUploadAssincrono,
    *,
    diretorio: Path,
    suffix: str,
    max_bytes: int,
) -> UploadEmStaging:
    """Recebe o upload em chunks com memória O(CHUNK_UPLOAD_BYTES).

    O inode 0600 é criado de modo síncrono/atômico antes do primeiro ``await``.
    Depois disso, as escritas são delegadas ao executor e concluídas antes de
    propagar eventual cancelamento. Em qualquer falha o path é removido sem
    mascarar a exceção original.
    """

    if max_bytes < 0:
        raise ValueError("max_bytes não pode ser negativo")
    suffix = _suffix_seguro(suffix)
    diretorio.mkdir(parents=True, exist_ok=True)
    staging = diretorio / f".{uuid4().hex}{suffix}.uploading"

    digest = hashlib.sha256()
    amostra = bytearray()
    total = 0
    concluido = False
    arquivo_sync = _criar_staging_aberto(staging)

    try:
        while True:
            chunk = await upload.read(CHUNK_UPLOAD_BYTES)
            if not chunk:
                break
            novo_total = total + len(chunk)
            if novo_total > max_bytes:
                raise UploadExcedeLimiteError(max_bytes)

            digest.update(chunk)
            if len(amostra) < AMOSTRA_MAGIC_BYTES:
                faltam = AMOSTRA_MAGIC_BYTES - len(amostra)
                amostra.extend(chunk[:faltam])

            await _escrever_chunk(arquivo_sync, chunk)
            total = novo_total

        if total == 0:
            raise UploadVazioError("arquivo vazio")

        # BufferedWriter pode manter bytes no buffer; flush também respeita o
        # mesmo protocolo de cancelamento antes de devolver o staging ao caller.
        await _aguardar_io_thread(arquivo_sync.flush)
        concluido = True
        return UploadEmStaging(
            caminho=staging,
            size_bytes=total,
            sha256=digest.hexdigest(),
            amostra_inicial=bytes(amostra),
        )
    finally:
        # Nenhuma operação de thread fica pendente quando chegamos aqui.
        try:
            arquivo_sync.close()
        finally:
            if not concluido:
                _descartar_caminho_best_effort(staging)
