from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.services import document_extraction_adapter as adapter
from app.services import document_ingestion_service as ingestion_svc
from app.services import documento_service
from app.services.document_ingestion_service import preparar_ingestao_documento_local
from app.services.document_storage_uow import EstadoStorageInvalidoError


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


async def _ingestao(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        ingestion_svc,
        "validar_conteudo",
        lambda ext, amostra: "application/pdf",
    )
    return await preparar_ingestao_documento_local(
        StreamBytes(b"%PDF-adapter"),
        filename="parte-cpf-sentinela.pdf",
        upload_root=tmp_path,
        max_bytes=1024,
    )


@pytest.mark.asyncio
async def test_adapter_usa_staging_e_retorna_apenas_texto_sanitizado(
    tmp_path: Path,
    monkeypatch,
):
    ingestao = await _ingestao(tmp_path, monkeypatch)
    observado = {}

    async def fake_extrair(path, mimetype, **kwargs):
        caminho = Path(path)
        observado.update(
            path=caminho,
            mimetype=mimetype,
            enriquecer_rag=kwargs.get("enriquecer_rag"),
            user_id=kwargs.get("user_id"),
        )
        assert caminho.exists()
        assert caminho.name.startswith(".")
        assert caminho.name.endswith(".uploading")
        return {
            "_texto_sanitizado": "texto sanitizado",
            "analise": "resultado que o adapter não deve propagar",
            "entidades": ["sentinela"],
        }

    monkeypatch.setattr(documento_service, "extrair_e_analisar", fake_extrair)

    resultado = await adapter.extrair_texto_compatibilidade(
        None,  # type: ignore[arg-type]
        ingestao,
        user_id="usuario-sentinela",
    )

    assert resultado.status is adapter.StatusExtracaoTexto.SUCESSO
    assert resultado.ocr_text == "texto sanitizado"
    assert observado["mimetype"] == "application/pdf"
    assert observado["enriquecer_rag"] is False
    assert observado["user_id"] == "usuario-sentinela"
    assert not hasattr(resultado, "analise")
    ingestao.storage.compensar()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ({}, adapter.StatusExtracaoTexto.SEM_TEXTO),
        ({"_texto_sanitizado": None}, adapter.StatusExtracaoTexto.SEM_TEXTO),
        ({"_texto_sanitizado": "   "}, adapter.StatusExtracaoTexto.SEM_TEXTO),
        ({"_texto_sanitizado": 123}, adapter.StatusExtracaoTexto.INDISPONIVEL),
        ([], adapter.StatusExtracaoTexto.INDISPONIVEL),
    ],
)
async def test_adapter_classifica_resultados_sem_conteudo_util(
    tmp_path: Path,
    monkeypatch,
    payload,
    status,
):
    ingestao = await _ingestao(tmp_path, monkeypatch)

    async def fake_extrair(*args, **kwargs):
        return payload

    monkeypatch.setattr(documento_service, "extrair_e_analisar", fake_extrair)
    resultado = await adapter.extrair_texto_compatibilidade(
        None,  # type: ignore[arg-type]
        ingestao,
        user_id=None,
    )

    assert resultado.status is status
    assert resultado.ocr_text is None
    ingestao.storage.compensar()


@pytest.mark.asyncio
async def test_excecao_fail_soft_nao_vaza_mensagem_path_ou_filename(
    tmp_path: Path,
    monkeypatch,
    caplog,
):
    ingestao = await _ingestao(tmp_path, monkeypatch)

    async def fake_extrair(*args, **kwargs):
        raise RuntimeError(
            "erro-secreto /opt/ejc/uploads/parte-cpf-sentinela.pdf provider-chave"
        )

    monkeypatch.setattr(documento_service, "extrair_e_analisar", fake_extrair)

    resultado = await adapter.extrair_texto_compatibilidade(
        None,  # type: ignore[arg-type]
        ingestao,
        user_id=None,
    )

    assert resultado.status is adapter.StatusExtracaoTexto.INDISPONIVEL
    assert resultado.ocr_text is None
    assert "erro-secreto" not in caplog.text
    assert "/opt/ejc" not in caplog.text
    assert "cpf-sentinela" not in caplog.text
    assert "provider-chave" not in caplog.text
    assert "RuntimeError" in caplog.text
    ingestao.storage.compensar()


@pytest.mark.asyncio
async def test_cancelled_error_nao_e_convertido_em_fail_soft(tmp_path: Path, monkeypatch):
    ingestao = await _ingestao(tmp_path, monkeypatch)

    async def fake_extrair(*args, **kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(documento_service, "extrair_e_analisar", fake_extrair)

    with pytest.raises(asyncio.CancelledError):
        await adapter.extrair_texto_compatibilidade(
            None,  # type: ignore[arg-type]
            ingestao,
            user_id=None,
        )

    ingestao.storage.compensar()


@pytest.mark.asyncio
async def test_adapter_nao_pode_rodar_depois_da_promocao(tmp_path: Path, monkeypatch):
    ingestao = await _ingestao(tmp_path, monkeypatch)
    ingestao.promover()

    with pytest.raises(EstadoStorageInvalidoError):
        await adapter.extrair_texto_compatibilidade(
            None,  # type: ignore[arg-type]
            ingestao,
            user_id=None,
        )

    ingestao.storage.compensar()
