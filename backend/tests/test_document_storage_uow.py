from __future__ import annotations

from pathlib import Path

import pytest

from app.services.document_storage_uow import (
    CompensacaoStorageError,
    DocumentStorageUnitOfWork,
    EstadoStorageInvalidoError,
    EstadoStorageLocal,
)


class StreamBytes:
    def __init__(self, conteudo: bytes) -> None:
        self._conteudo = conteudo
        self._offset = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            raise AssertionError("a UoW não pode solicitar leitura ilimitada")
        if self._offset >= len(self._conteudo):
            return b""
        fim = min(self._offset + size, len(self._conteudo))
        chunk = self._conteudo[self._offset:fim]
        self._offset = fim
        return chunk


async def _uow(tmp_path: Path, nome: str = "destino.pdf") -> DocumentStorageUnitOfWork:
    return await DocumentStorageUnitOfWork.iniciar(
        StreamBytes(b"%PDF-1.7\nconteudo-juridico"),
        destino_final=tmp_path / nome,
        suffix=".pdf",
        max_bytes=1024 * 1024,
    )


@pytest.mark.asyncio
async def test_confirmacao_preserva_destino_final(tmp_path: Path):
    uow = await _uow(tmp_path)

    async with uow:
        assert uow.estado is EstadoStorageLocal.STAGING
        assert uow.sha256
        assert uow.size_bytes > 0
        assert uow.amostra_inicial.startswith(b"%PDF")

        uow.promover()
        assert uow.estado is EstadoStorageLocal.PROMOVIDO
        assert uow.destino_final.exists()

        uow.confirmar()
        assert uow.estado is EstadoStorageLocal.CONFIRMADO

    assert uow.destino_final.exists()


@pytest.mark.asyncio
async def test_saida_sem_confirmar_compensa_destino_promovido(tmp_path: Path):
    uow = await _uow(tmp_path)

    async with uow:
        uow.promover()
        assert uow.destino_final.exists()

    assert uow.estado is EstadoStorageLocal.COMPENSADO
    assert not uow.destino_final.exists()


@pytest.mark.asyncio
async def test_excecao_apos_promocao_remove_arquivo_e_preserva_excecao(tmp_path: Path):
    uow = await _uow(tmp_path)

    with pytest.raises(ValueError, match="falha de commit simulada"):
        async with uow:
            uow.promover()
            raise ValueError("falha de commit simulada")

    assert uow.estado is EstadoStorageLocal.COMPENSADO
    assert not uow.destino_final.exists()


@pytest.mark.asyncio
async def test_saida_ainda_em_staging_remove_arquivo_temporario(tmp_path: Path):
    uow = await _uow(tmp_path)
    assert list(tmp_path.glob("*.uploading")) or list(tmp_path.glob(".*.uploading"))

    async with uow:
        pass

    assert uow.estado is EstadoStorageLocal.COMPENSADO
    assert not list(tmp_path.glob("*.uploading"))
    assert not list(tmp_path.glob(".*.uploading"))


@pytest.mark.asyncio
async def test_compensacao_e_idempotente(tmp_path: Path):
    uow = await _uow(tmp_path)
    uow.promover()

    assert uow.compensar() is True
    assert uow.estado is EstadoStorageLocal.COMPENSADO
    assert uow.compensar() is True
    assert not uow.destino_final.exists()


@pytest.mark.asyncio
async def test_confirmado_nunca_e_removido_por_compensacao_tardia(tmp_path: Path):
    uow = await _uow(tmp_path)
    uow.promover()
    uow.confirmar()

    assert uow.compensar() is True
    assert uow.estado is EstadoStorageLocal.CONFIRMADO
    assert uow.destino_final.exists()


@pytest.mark.asyncio
async def test_transicoes_invalidas_falham_fechado(tmp_path: Path):
    uow = await _uow(tmp_path)

    with pytest.raises(EstadoStorageInvalidoError):
        uow.confirmar()

    uow.promover()
    with pytest.raises(EstadoStorageInvalidoError):
        uow.promover()

    uow.compensar()


@pytest.mark.asyncio
async def test_falha_de_cleanup_sem_excecao_original_e_visivel(tmp_path: Path, monkeypatch):
    uow = await _uow(tmp_path)

    def falhar_unlink(self, *args, **kwargs):
        raise OSError("path-sentinela-nao-deve-vazar")

    monkeypatch.setattr(Path, "unlink", falhar_unlink)

    with pytest.raises(CompensacaoStorageError, match="falha ao compensar storage documental") as exc:
        async with uow:
            pass

    assert "path-sentinela" not in str(exc.value)


@pytest.mark.asyncio
async def test_falha_de_cleanup_nao_mascara_excecao_original(tmp_path: Path, monkeypatch):
    uow = await _uow(tmp_path)

    def falhar_unlink(self, *args, **kwargs):
        raise OSError("detalhe-interno")

    monkeypatch.setattr(Path, "unlink", falhar_unlink)

    with pytest.raises(RuntimeError, match="erro de banco original"):
        async with uow:
            raise RuntimeError("erro de banco original")
