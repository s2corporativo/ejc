from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.models.document import DocConfidencialidade, Document
from app.services import document_ingestion_orchestrator as orchestrator
from app.services import document_ingestion_service as ingestion_svc
from app.services.document_extraction_adapter import (
    ResultadoExtracaoTexto,
    StatusExtracaoTexto,
)
from app.services.document_ingestion_service import MalwareDetectadoError
from app.services.document_persistence_service import DadosPersistenciaDocumento
from app.services.document_storage_uow import EstadoStorageLocal
from app.services.malware_scan_service import (
    MalwareScanStatus,
    ResultadoMalwareScan,
)


class StreamBytes:
    def __init__(self, conteudo: bytes) -> None:
        self.conteudo = conteudo
        self.offset = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            raise AssertionError("orquestrador não pode materializar upload")
        if self.offset >= len(self.conteudo):
            return b""
        fim = min(self.offset + size, len(self.conteudo))
        chunk = self.conteudo[self.offset:fim]
        self.offset = fim
        return chunk


class FakeDB:
    def __init__(self, *, commit_error: BaseException | None = None) -> None:
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0
        self.commit_error = commit_error

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1
        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self) -> None:
        self.rollbacks += 1


class ScannerFalso:
    def __init__(self, status: MalwareScanStatus) -> None:
        self.status = status
        self.calls = 0

    async def escanear(self, caminho: Path) -> ResultadoMalwareScan:
        self.calls += 1
        assert caminho.exists()
        assert caminho.name.endswith(".uploading")
        return ResultadoMalwareScan(self.status)


def _dados() -> DadosPersistenciaDocumento:
    return DadosPersistenciaDocumento(
        titulo="Documento orquestrado",
        tipo="peticao",
        confidencialidade=DocConfidencialidade.normal,
        user_role="advogado",
    )


def _mime_pdf(monkeypatch) -> None:
    monkeypatch.setattr(
        ingestion_svc,
        "validar_conteudo",
        lambda ext, amostra: "application/pdf",
    )


@pytest.mark.asyncio
async def test_pipeline_sucesso_confirma_documento_hash_scan_e_ocr(tmp_path: Path, monkeypatch):
    _mime_pdf(monkeypatch)
    db = FakeDB()
    observado = {}

    async def fake_extracao(db_arg, ingestao, *, user_id):
        observado["estado"] = ingestao.storage.estado
        observado["staging_existe"] = ingestao.storage.caminho_staging_para_validacao.exists()
        return ResultadoExtracaoTexto(
            StatusExtracaoTexto.SUCESSO,
            ocr_text="texto sanitizado do orquestrador",
        )

    monkeypatch.setattr(orchestrator, "extrair_texto_compatibilidade", fake_extracao)

    resultado = await orchestrator.ingerir_documento_local(
        db,  # type: ignore[arg-type]
        StreamBytes(b"%PDF-pipeline"),
        filename="parte-cpf-sentinela.pdf",
        upload_root=tmp_path,
        max_bytes=1024,
        dados=_dados(),
    )

    assert isinstance(resultado.documento, Document)
    assert resultado.documento.ocr_text == "texto sanitizado do orquestrador"
    assert resultado.documento.versao == 1
    assert resultado.sha256 == resultado.documento.id or len(resultado.sha256) == 64
    assert resultado.malware_scan_status is MalwareScanStatus.NAO_SOLICITADO
    assert resultado.extracao.status is StatusExtracaoTexto.SUCESSO
    assert observado == {"estado": EstadoStorageLocal.STAGING, "staging_existe": True}
    assert db.commits == 1
    assert db.rollbacks == 0
    assert resultado.documento.filepath.endswith(".pdf")
    assert (tmp_path / resultado.documento.filepath).exists()

    (tmp_path / resultado.documento.filepath).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_extracao_indisponivel_permanece_fail_soft_e_persiste_sem_ocr(
    tmp_path: Path,
    monkeypatch,
):
    _mime_pdf(monkeypatch)
    db = FakeDB()

    async def fake_extracao(*args, **kwargs):
        return ResultadoExtracaoTexto(StatusExtracaoTexto.INDISPONIVEL)

    monkeypatch.setattr(orchestrator, "extrair_texto_compatibilidade", fake_extracao)

    resultado = await orchestrator.ingerir_documento_local(
        db,  # type: ignore[arg-type]
        StreamBytes(b"%PDF-sem-ocr"),
        filename="arquivo.pdf",
        upload_root=tmp_path,
        max_bytes=1024,
        dados=_dados(),
    )

    assert resultado.extracao.status is StatusExtracaoTexto.INDISPONIVEL
    assert resultado.documento.ocr_text is None
    assert db.commits == 1
    (tmp_path / resultado.documento.filepath).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_cancelamento_na_extracao_compensa_staging_sem_db(tmp_path: Path, monkeypatch):
    _mime_pdf(monkeypatch)
    db = FakeDB()

    async def cancelar(*args, **kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(orchestrator, "extrair_texto_compatibilidade", cancelar)

    with pytest.raises(asyncio.CancelledError):
        await orchestrator.ingerir_documento_local(
            db,  # type: ignore[arg-type]
            StreamBytes(b"%PDF-cancel"),
            filename="arquivo.pdf",
            upload_root=tmp_path,
            max_bytes=1024,
            dados=_dados(),
        )

    assert db.added == []
    assert db.commits == 0
    assert not list(tmp_path.rglob(".*.uploading"))
    assert not list(tmp_path.rglob("*.pdf"))


@pytest.mark.asyncio
async def test_malware_infectado_bloqueia_antes_da_extracao_e_do_db(
    tmp_path: Path,
    monkeypatch,
):
    _mime_pdf(monkeypatch)
    db = FakeDB()
    scanner = ScannerFalso(MalwareScanStatus.INFECTADO)
    extracao_chamada = False

    async def nao_deveria_extrair(*args, **kwargs):
        nonlocal extracao_chamada
        extracao_chamada = True
        return ResultadoExtracaoTexto(StatusExtracaoTexto.SUCESSO, "x")

    monkeypatch.setattr(orchestrator, "extrair_texto_compatibilidade", nao_deveria_extrair)

    with pytest.raises(MalwareDetectadoError):
        await orchestrator.ingerir_documento_local(
            db,  # type: ignore[arg-type]
            StreamBytes(b"%PDF-block"),
            filename="arquivo.pdf",
            upload_root=tmp_path,
            max_bytes=1024,
            dados=_dados(),
            scanner=scanner,
        )

    assert scanner.calls == 1
    assert extracao_chamada is False
    assert db.added == []
    assert db.commits == 0
    assert not list(tmp_path.rglob(".*.uploading"))
    assert not list(tmp_path.rglob("*.pdf"))


@pytest.mark.asyncio
async def test_falha_de_commit_no_pipeline_remove_destino_promovido(tmp_path: Path, monkeypatch):
    _mime_pdf(monkeypatch)
    db = FakeDB(commit_error=RuntimeError("commit-pipeline-falhou"))

    async def fake_extracao(*args, **kwargs):
        return ResultadoExtracaoTexto(StatusExtracaoTexto.SEM_TEXTO)

    monkeypatch.setattr(orchestrator, "extrair_texto_compatibilidade", fake_extracao)

    with pytest.raises(RuntimeError, match="commit-pipeline-falhou"):
        await orchestrator.ingerir_documento_local(
            db,  # type: ignore[arg-type]
            StreamBytes(b"%PDF-commit-fail"),
            filename="arquivo.pdf",
            upload_root=tmp_path,
            max_bytes=1024,
            dados=_dados(),
        )

    assert db.commits == 1
    assert db.rollbacks == 1
    assert not list(tmp_path.rglob(".*.uploading"))
    assert not list(tmp_path.rglob("*.pdf"))
