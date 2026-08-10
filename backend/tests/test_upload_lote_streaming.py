"""Regressões de streaming na camada compartilhada de upload em lote."""
from __future__ import annotations

import hashlib
from io import BytesIO

import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.services import upload_lote_service as lote
from app.services.document_upload_stream import CHUNK_UPLOAD_BYTES

ENTIDADE_ID = "e1111111-1111-1111-1111-111111111111"


class _UploadSemReadIlimitado:
    def __init__(self, filename: str, conteudo: bytes):
        self.filename = filename
        self._buffer = BytesIO(conteudo)
        self.tamanhos: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.tamanhos.append(size)
        if size < 0:
            raise AssertionError("processar_lote não pode materializar upload inteiro")
        return self._buffer.read(size)


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "UPLOAD_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(st, "MAX_UPLOAD_MB", 8, raising=False)
    return tmp_path


async def test_lote_valido_le_stream_em_chunks_e_promove_sem_staging(upload_dir):
    conteudo = b"texto" * (CHUNK_UPLOAD_BYTES // 5 + 100)
    upload = _UploadSemReadIlimitado("peticao.txt", conteudo)

    validos, duplicados, erros = await lote.processar_lote(
        [upload],
        max_arquivos=5,
        extensoes_permitidas={".txt"},
        existing_hashes=set(),
        storage_subdir="raio-x",
        entidade_id=ENTIDADE_ID,
    )

    assert erros == []
    assert duplicados == []
    assert len(validos) == 1
    assert upload.tamanhos
    assert set(upload.tamanhos) == {CHUNK_UPLOAD_BYTES}
    assert validos[0].sha256 == hashlib.sha256(conteudo).hexdigest()
    assert (upload_dir / validos[0].filepath).read_bytes() == conteudo
    assert list(upload_dir.rglob("*.uploading")) == []


async def test_duplicado_descarta_staging_e_nao_cria_destino(upload_dir):
    conteudo = b"duplicado"
    digest = hashlib.sha256(conteudo).hexdigest()

    validos, duplicados, erros = await lote.processar_lote(
        [_UploadSemReadIlimitado("repetido.txt", conteudo)],
        max_arquivos=5,
        extensoes_permitidas={".txt"},
        existing_hashes={digest},
        storage_subdir="raio-x",
        entidade_id=ENTIDADE_ID,
    )

    assert validos == []
    assert duplicados == ["repetido.txt"]
    assert erros == []
    assert [p for p in upload_dir.rglob("*") if p.is_file()] == []


async def test_mime_invalido_descarta_staging(monkeypatch, upload_dir):
    def rejeitar(ext: str, amostra: bytes) -> str:
        del ext, amostra
        raise HTTPException(415, "conteúdo incompatível")

    monkeypatch.setattr(lote, "validar_conteudo", rejeitar)

    validos, duplicados, erros = await lote.processar_lote(
        [_UploadSemReadIlimitado("arquivo.pdf", b"nao-e-pdf")],
        max_arquivos=5,
        extensoes_permitidas={".pdf"},
        existing_hashes=set(),
        storage_subdir="raio-x",
        entidade_id=ENTIDADE_ID,
    )

    assert validos == []
    assert duplicados == []
    assert erros == [{"arquivo": "arquivo.pdf", "erro": "conteúdo incompatível"}]
    assert [p for p in upload_dir.rglob("*") if p.is_file()] == []


async def test_falha_na_promocao_remove_staging_e_propaga_infra(monkeypatch, upload_dir):
    def falhar_promocao(staging, destino):
        del staging, destino
        raise OSError("falha simulada")

    monkeypatch.setattr(lote, "promover_staging", falhar_promocao)

    with pytest.raises(OSError, match="falha simulada"):
        await lote.processar_lote(
            [_UploadSemReadIlimitado("arquivo.txt", b"conteudo")],
            max_arquivos=5,
            extensoes_permitidas={".txt"},
            existing_hashes=set(),
            storage_subdir="raio-x",
            entidade_id=ENTIDADE_ID,
        )

    assert [p for p in upload_dir.rglob("*") if p.is_file()] == []


async def test_teto_interrompe_antes_de_persistir_chunk_excedente(monkeypatch, upload_dir):
    st = get_settings()
    monkeypatch.setattr(st, "MAX_UPLOAD_MB", 1, raising=False)
    conteudo = b"x" * (1024 * 1024 + 1)

    validos, duplicados, erros = await lote.processar_lote(
        [_UploadSemReadIlimitado("grande.txt", conteudo)],
        max_arquivos=5,
        extensoes_permitidas={".txt"},
        existing_hashes=set(),
        storage_subdir="raio-x",
        entidade_id=ENTIDADE_ID,
    )

    assert validos == []
    assert duplicados == []
    assert erros == [{"arquivo": "grande.txt", "erro": "Excede 1 MB"}]
    assert [p for p in upload_dir.rglob("*") if p.is_file()] == []
