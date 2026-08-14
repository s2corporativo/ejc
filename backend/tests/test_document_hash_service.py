from __future__ import annotations

import asyncio
import hashlib
import os
import threading
from pathlib import Path

import pytest

from app.services import document_hash_service as svc


@pytest.mark.asyncio
async def test_hash_streaming_retorna_sha_e_tamanho(tmp_path: Path):
    conteudo = b"A" * (svc.CHUNK_HASH_BYTES * 2 + 37)
    caminho = tmp_path / "2026" / "08" / "documento.pdf"
    caminho.parent.mkdir(parents=True)
    caminho.write_bytes(conteudo)

    resultado = await svc.calcular_sha256_local(
        tmp_path,
        "2026/08/documento.pdf",
        expected_size=len(conteudo),
    )

    assert resultado.sha256 == hashlib.sha256(conteudo).hexdigest()
    assert resultado.size_bytes == len(conteudo)


@pytest.mark.asyncio
async def test_tamanho_divergente_falha_sem_expor_path(tmp_path: Path):
    caminho = tmp_path / "cliente-cpf-sentinela.pdf"
    caminho.write_bytes(b"conteudo")

    with pytest.raises(svc.HashMetadataMismatchError) as exc:
        await svc.calcular_sha256_local(
            tmp_path,
            "cliente-cpf-sentinela.pdf",
            expected_size=999,
        )

    assert "sentinela" not in str(exc.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filepath",
    [
        "../fora.pdf",
        "/etc/passwd",
        r"2026\08\arquivo.pdf",
        "gdrive:arquivo.pdf",
        "2026/./arquivo.pdf",
        "2026/../arquivo.pdf",
        "",
    ],
)
async def test_filepath_invalido_e_rejeitado(tmp_path: Path, filepath: str):
    with pytest.raises(svc.HashPathInvalidoError):
        await svc.calcular_sha256_local(tmp_path, filepath)


@pytest.mark.asyncio
async def test_arquivo_ausente_nao_vaza_nome(tmp_path: Path):
    with pytest.raises(svc.HashArquivoIndisponivelError) as exc:
        await svc.calcular_sha256_local(tmp_path, "segredo-sentinela.pdf")
    assert "sentinela" not in str(exc.value)


@pytest.mark.asyncio
async def test_diretorio_nao_e_aceito_como_arquivo(tmp_path: Path):
    diretorio = tmp_path / "2026" / "08" / "pasta.pdf"
    diretorio.mkdir(parents=True)

    with pytest.raises(svc.HashArquivoIndisponivelError):
        await svc.calcular_sha256_local(tmp_path, "2026/08/pasta.pdf")


@pytest.mark.asyncio
async def test_symlink_final_e_rejeitado_quando_nofollow_existe(tmp_path: Path):
    if not hasattr(os, "O_NOFOLLOW"):
        pytest.skip("plataforma sem O_NOFOLLOW")

    alvo = tmp_path / "real.pdf"
    alvo.write_bytes(b"conteudo")
    link = tmp_path / "link.pdf"
    link.symlink_to(alvo)

    with pytest.raises(svc.HashArquivoIndisponivelError):
        await svc.calcular_sha256_local(tmp_path, "link.pdf")


@pytest.mark.asyncio
async def test_cancelamento_aguarda_thread_antes_de_propagar(monkeypatch, tmp_path: Path):
    iniciou = threading.Event()
    liberar = threading.Event()
    finalizou = threading.Event()

    def hash_lento(*args, **kwargs):
        iniciou.set()
        liberar.wait(timeout=5)
        finalizou.set()
        return svc.HashDocumentoCalculado(sha256="0" * 64, size_bytes=1)

    monkeypatch.setattr(svc, "_calcular_sync", hash_lento)

    tarefa = asyncio.create_task(
        svc.calcular_sha256_local(tmp_path, "arquivo.pdf")
    )
    await asyncio.to_thread(iniciou.wait, 2)
    assert iniciou.is_set()

    tarefa.cancel()
    await asyncio.sleep(0)
    assert not tarefa.done()
    assert not finalizou.is_set()

    liberar.set()
    with pytest.raises(asyncio.CancelledError):
        await tarefa
    assert finalizou.is_set()
