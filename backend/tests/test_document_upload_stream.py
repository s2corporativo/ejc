"""Contrato da primitiva de streaming documental."""
from __future__ import annotations

import hashlib
from io import BytesIO

import pytest

from app.services.document_upload_stream import (
    AMOSTRA_MAGIC_BYTES,
    CHUNK_UPLOAD_BYTES,
    UploadExcedeLimiteError,
    UploadVazioError,
    descartar_staging,
    promover_staging,
    receber_em_staging,
)


class _StreamRastreado:
    def __init__(self, conteudo: bytes):
        self._buffer = BytesIO(conteudo)
        self.tamanhos_solicitados: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.tamanhos_solicitados.append(size)
        if size < 0:
            raise AssertionError("leitura ilimitada proibida")
        return self._buffer.read(size)


async def test_streaming_usa_chunks_limitados_hash_incremental_e_amostra(tmp_path):
    conteudo = b"a" * (CHUNK_UPLOAD_BYTES * 2 + 37)
    stream = _StreamRastreado(conteudo)

    staging = await receber_em_staging(
        stream,
        diretorio=tmp_path,
        suffix=".pdf",
        max_bytes=len(conteudo),
    )

    assert stream.tamanhos_solicitados
    assert set(stream.tamanhos_solicitados) == {CHUNK_UPLOAD_BYTES}
    assert staging.size_bytes == len(conteudo)
    assert staging.sha256 == hashlib.sha256(conteudo).hexdigest()
    assert staging.amostra_inicial == conteudo[:AMOSTRA_MAGIC_BYTES]
    assert staging.caminho.read_bytes() == conteudo
    assert staging.caminho.name.startswith(".")
    assert staging.caminho.name.endswith(".pdf.uploading")
    assert staging.caminho.stat().st_mode & 0o777 == 0o600

    descartar_staging(staging)
    assert not staging.caminho.exists()


async def test_limite_e_verificado_antes_de_gravar_chunk_excedente(tmp_path):
    conteudo = b"x" * (CHUNK_UPLOAD_BYTES + 1)
    stream = _StreamRastreado(conteudo)

    with pytest.raises(UploadExcedeLimiteError):
        await receber_em_staging(
            stream,
            diretorio=tmp_path,
            suffix=".txt",
            max_bytes=CHUNK_UPLOAD_BYTES,
        )

    assert list(tmp_path.glob("*.uploading")) == []
    assert list(tmp_path.iterdir()) == []


async def test_arquivo_vazio_remove_staging(tmp_path):
    with pytest.raises(UploadVazioError):
        await receber_em_staging(
            _StreamRastreado(b""),
            diretorio=tmp_path,
            suffix=".txt",
            max_bytes=1024,
        )

    assert list(tmp_path.iterdir()) == []


async def test_promocao_move_staging_para_destino_final_no_mesmo_diretorio(tmp_path):
    staging = await receber_em_staging(
        _StreamRastreado(b"conteudo"),
        diretorio=tmp_path,
        suffix=".txt",
        max_bytes=1024,
    )
    final = tmp_path / "documento-final.txt"

    promover_staging(staging, final)

    assert final.read_bytes() == b"conteudo"
    assert not staging.caminho.exists()


async def test_promocao_nao_sobrescreve_destino_existente(tmp_path):
    staging = await receber_em_staging(
        _StreamRastreado(b"novo"),
        diretorio=tmp_path,
        suffix=".txt",
        max_bytes=1024,
    )
    final = tmp_path / "documento-final.txt"
    final.write_bytes(b"original")

    with pytest.raises(FileExistsError, match="já existe"):
        promover_staging(staging, final)

    assert final.read_bytes() == b"original"
    assert staging.caminho.read_bytes() == b"novo"
    descartar_staging(staging)


async def test_promocao_entre_diretorios_e_rejeitada_sem_mover_staging(tmp_path):
    origem = tmp_path / "origem"
    destino = tmp_path / "destino"
    destino.mkdir()
    staging = await receber_em_staging(
        _StreamRastreado(b"conteudo"),
        diretorio=origem,
        suffix=".txt",
        max_bytes=1024,
    )

    with pytest.raises(ValueError, match="compartilhar diretório"):
        promover_staging(staging, destino / "final.txt")

    assert staging.caminho.exists()
    descartar_staging(staging)


@pytest.mark.parametrize(
    "suffix",
    ["../.pdf", "/.pdf", ".pdf/fora", "\\fora.pdf"],
)
async def test_suffix_inseguro_e_rejeitado_antes_de_criar_staging(tmp_path, suffix):
    with pytest.raises(ValueError, match="suffix inválido"):
        await receber_em_staging(
            _StreamRastreado(b"conteudo"),
            diretorio=tmp_path,
            suffix=suffix,
            max_bytes=1024,
        )

    assert list(tmp_path.iterdir()) == []
