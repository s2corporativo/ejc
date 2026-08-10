from __future__ import annotations

from pathlib import Path

import pytest

from app.models.audit_log import AuditLog
from app.models.document import DocConfidencialidade, Document
from app.services import document_ingestion_service as ingestion_svc
from app.services.document_ingestion_service import preparar_ingestao_documento_local
from app.services.document_persistence_service import (
    ConteudoDocumentoPreparado,
    DadosPersistenciaDocumento,
    PersistenciaDocumentoInvalidaError,
    persistir_documento_local,
)
from app.services.document_storage_uow import EstadoStorageLocal


class StreamBytes:
    def __init__(self, conteudo: bytes) -> None:
        self._conteudo = conteudo
        self._offset = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            raise AssertionError("persistência não pode provocar leitura ilimitada")
        if self._offset >= len(self._conteudo):
            return b""
        fim = min(self._offset + size, len(self._conteudo))
        chunk = self._conteudo[self._offset:fim]
        self._offset = fim
        return chunk


class FakeDB:
    def __init__(self, *, commit_error: BaseException | None = None, rollback_error: BaseException | None = None):
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0
        self.commit_error = commit_error
        self.rollback_error = rollback_error

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1
        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self) -> None:
        self.rollbacks += 1
        if self.rollback_error is not None:
            raise self.rollback_error


async def _ingestao(tmp_path: Path, monkeypatch, conteudo: bytes = b"%PDF-1.7\nconteudo"):
    monkeypatch.setattr(
        ingestion_svc,
        "validar_conteudo",
        lambda ext, amostra: "application/pdf",
    )
    return await preparar_ingestao_documento_local(
        StreamBytes(conteudo),
        filename="parte-cpf-sentinela.pdf",
        upload_root=tmp_path,
        max_bytes=1024 * 1024,
    )


def _dados(**overrides) -> DadosPersistenciaDocumento:
    dados = {
        "titulo": "Petição inicial",
        "tipo": "peticao",
        "confidencialidade": DocConfidencialidade.normal,
        "uploaded_by": None,
        "user_role": "advogado",
    }
    dados.update(overrides)
    return DadosPersistenciaDocumento(**dados)


@pytest.mark.asyncio
async def test_raiz_commitada_confirma_storage_e_audit_minimo(tmp_path: Path, monkeypatch):
    ingestao = await _ingestao(tmp_path, monkeypatch)
    db = FakeDB()

    documento = await persistir_documento_local(
        db,  # type: ignore[arg-type]
        ingestao,
        dados=_dados(),
        conteudo=ConteudoDocumentoPreparado(
            ocr_text="texto sanitizado",
            ocr_utilizado=True,
            metadados_extraidos={"origem": "teste"},
        ),
    )

    assert documento.versao == 1
    assert documento.versao_grupo_id == documento.id
    assert documento.versao_anterior_id is None
    assert documento.ocr_text == "texto sanitizado"
    assert documento.ocr_utilizado is True
    assert documento.metadados_extraidos == {"origem": "teste"}
    assert ingestao.storage.estado is EstadoStorageLocal.CONFIRMADO
    assert ingestao.full_path.exists()
    assert db.commits == 1
    assert db.rollbacks == 0

    docs = [obj for obj in db.added if isinstance(obj, Document)]
    audits = [obj for obj in db.added if isinstance(obj, AuditLog)]
    assert docs == [documento]
    assert len(audits) == 1
    audit = audits[0]
    assert audit.acao == "UPLOAD"
    assert audit.entidade == "documents"
    assert audit.registro_id == documento.id
    serializado = repr({"detalhes": audit.detalhes, "dados_depois": audit.dados_depois})
    assert "parte-cpf-sentinela" not in serializado
    assert ingestao.filepath not in serializado
    assert "Petição inicial" not in serializado


@pytest.mark.asyncio
async def test_falha_de_commit_faz_rollback_e_compensa_arquivo(tmp_path: Path, monkeypatch):
    ingestao = await _ingestao(tmp_path, monkeypatch)
    db = FakeDB(commit_error=RuntimeError("commit-sentinela"))

    with pytest.raises(RuntimeError, match="commit-sentinela"):
        await persistir_documento_local(
            db,  # type: ignore[arg-type]
            ingestao,
            dados=_dados(),
        )

    assert db.commits == 1
    assert db.rollbacks == 1
    assert ingestao.storage.estado is EstadoStorageLocal.COMPENSADO
    assert not ingestao.full_path.exists()
    assert not list(tmp_path.rglob(".*.uploading"))


@pytest.mark.asyncio
async def test_metadado_invalido_e_compensado_antes_de_promocao(tmp_path: Path, monkeypatch):
    ingestao = await _ingestao(tmp_path, monkeypatch)
    staging = ingestao.storage.caminho_staging_para_validacao
    assert staging.exists()
    db = FakeDB()

    with pytest.raises(PersistenciaDocumentoInvalidaError, match="titulo excede"):
        await persistir_documento_local(
            db,  # type: ignore[arg-type]
            ingestao,
            dados=_dados(titulo="x" * 256),
        )

    assert db.commits == 0
    assert db.rollbacks == 1
    assert db.added == []
    assert ingestao.storage.estado is EstadoStorageLocal.COMPENSADO
    assert not staging.exists()
    assert not ingestao.full_path.exists()


@pytest.mark.asyncio
async def test_conteudo_tipado_invalido_tambem_compensa_staging(tmp_path: Path, monkeypatch):
    ingestao = await _ingestao(tmp_path, monkeypatch)
    db = FakeDB()

    with pytest.raises(PersistenciaDocumentoInvalidaError, match="ocr_utilizado"):
        await persistir_documento_local(
            db,  # type: ignore[arg-type]
            ingestao,
            dados=_dados(),
            conteudo=ConteudoDocumentoPreparado(
                ocr_utilizado="false",  # type: ignore[arg-type]
            ),
        )

    assert db.commits == 0
    assert db.rollbacks == 1
    assert ingestao.storage.estado is EstadoStorageLocal.COMPENSADO
    assert not list(tmp_path.rglob(".*.uploading"))


@pytest.mark.asyncio
async def test_falha_de_rollback_nao_mascara_erro_de_commit(tmp_path: Path, monkeypatch):
    ingestao = await _ingestao(tmp_path, monkeypatch)
    db = FakeDB(
        commit_error=RuntimeError("erro-original-commit"),
        rollback_error=RuntimeError("erro-interno-rollback"),
    )

    with pytest.raises(RuntimeError, match="erro-original-commit") as exc:
        await persistir_documento_local(
            db,  # type: ignore[arg-type]
            ingestao,
            dados=_dados(),
        )

    assert "erro-interno-rollback" not in str(exc.value)
    assert db.rollbacks == 1
    assert ingestao.storage.estado is EstadoStorageLocal.COMPENSADO
    assert not ingestao.full_path.exists()
