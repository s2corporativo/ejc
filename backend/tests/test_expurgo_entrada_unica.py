"""Expurgo LGPD de rascunhos abandonados da Entrada Única (Issue #647).

services/entrada_expurgo_service.py::expurgar_rascunhos_entrada_unica.

NÃO edita tests/test_entrada_unica.py (tocado pelo PR #679 aberto) — arquivo
NOVO, harness aiosqlite copiado por REFERÊNCIA do padrão dos vizinhos.

Cobertura pedida pela issue:
  - batch com case_id preenchido NUNCA é tocado, mesmo velho/erro/concluido;
  - Document com client_id preenchido (mesmo sem case_id) não é removido —
    dupla checagem no nível do Document;
  - batch dentro da janela de retenção (recente) não é tocado;
  - batch fora da janela, sem case_id, status erro/concluido → removido
    (arquivo físico + registro), com dry_run=False;
  - dry_run=True não apaga nada, só conta;
  - dict de resultado com as chaves certas e contagens corretas.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import Base
from app.models.document import DocConfidencialidade, Document
from app.models.document_intake import DocumentIntakeBatch, DocumentIntakeItem
from app.services.entrada_expurgo_service import expurgar_rascunhos_entrada_unica

_TABELAS = [
    Document.__table__, DocumentIntakeBatch.__table__, DocumentIntakeItem.__table__,
]


@pytest.fixture
async def sessao_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABELAS))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    """UPLOAD_DIR isolado por teste — nunca toca o volume real."""
    monkeypatch.setattr(get_settings(), "UPLOAD_DIR", str(tmp_path))
    return tmp_path


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _velho(dias: int = 45) -> datetime:
    return _agora() - timedelta(days=dias)


def _recente(dias: int = 5) -> datetime:
    return _agora() - timedelta(days=dias)


def _escrever_arquivo(upload_dir, filepath: str, conteudo: bytes = b"x" * 100):
    full = upload_dir / filepath
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(conteudo)
    return full


async def _semear(
    db, upload_dir, *,
    batch_id="b1", doc_id="d1", item_id="i1",
    batch_status="erro", batch_case_id=None, batch_updated_at=None,
    doc_case_id=None, doc_client_id=None, filepath=None,
    size_bytes=100, criar_arquivo_fisico=True,
):
    """Semeia 1 batch + 1 Document + 1 DocumentIntakeItem vinculando os dois."""
    filepath = filepath or f"2026/08/{doc_id}.pdf"
    batch = DocumentIntakeBatch(
        id=batch_id, case_id=batch_case_id, status=batch_status,
        created_by="u1", document_count=1,
        updated_at=batch_updated_at or _velho(),
        resultado={"entrada_unica": {"fatos": "Relato do cliente com dado pessoal."}},
    )
    doc = Document(
        id=doc_id, titulo="Comprovante", filename=f"{doc_id}.pdf", filepath=filepath,
        size_bytes=size_bytes, case_id=doc_case_id, client_id=doc_client_id,
        confidencialidade=DocConfidencialidade.confidencial,
    )
    item = DocumentIntakeItem(
        id=item_id, batch_id=batch_id, document_id=doc_id,
        filename=f"{doc_id}.pdf", original_filename=f"{doc_id}.pdf",
        extension=".pdf", size_bytes=size_bytes, sha256="0" * 64,
    )
    db.add_all([batch, doc, item])
    await db.commit()
    if criar_arquivo_fisico:
        _escrever_arquivo(upload_dir, filepath)
    return batch, doc, item


# ── regra inegociável: case_id no batch → nunca toca ──────────────────────────

@pytest.mark.anyio
@pytest.mark.parametrize("status", ["erro", "concluido"])
async def test_batch_com_case_id_nunca_e_tocado(sessao_db, upload_dir, status):
    await _semear(
        sessao_db, upload_dir, batch_case_id="caso-1", batch_status=status,
        batch_updated_at=_velho(90),  # bem além da janela — só o case_id protege
    )

    resultado = await expurgar_rascunhos_entrada_unica(
        sessao_db, dias=30, dry_run=False,
    )

    assert resultado["batches_removidos"] == 0
    assert resultado["documentos_removidos"] == 0
    assert await sessao_db.get(DocumentIntakeBatch, "b1") is not None
    assert await sessao_db.get(Document, "d1") is not None
    assert await sessao_db.get(DocumentIntakeItem, "i1") is not None
    assert (upload_dir / "2026/08/d1.pdf").exists()


# ── dupla checagem: client_id no Document → não remove ────────────────────────

@pytest.mark.anyio
async def test_documento_com_client_id_nao_e_removido(sessao_db, upload_dir):
    await _semear(
        sessao_db, upload_dir, doc_client_id="cliente-1",  # batch.case_id=None (órfão)
        batch_status="concluido", batch_updated_at=_velho(),
    )

    resultado = await expurgar_rascunhos_entrada_unica(
        sessao_db, dias=30, dry_run=False,
    )

    assert resultado["batches_removidos"] == 0
    assert resultado["documentos_removidos"] == 0
    assert await sessao_db.get(Document, "d1") is not None
    assert await sessao_db.get(DocumentIntakeBatch, "b1") is not None
    assert (upload_dir / "2026/08/d1.pdf").exists()


# ── janela de retenção ─────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_batch_recente_nao_e_tocado(sessao_db, upload_dir):
    await _semear(
        sessao_db, upload_dir, batch_status="erro", batch_updated_at=_recente(5),
    )

    resultado = await expurgar_rascunhos_entrada_unica(
        sessao_db, dias=30, dry_run=False,
    )

    assert resultado["batches_removidos"] == 0
    assert resultado["documentos_removidos"] == 0
    assert await sessao_db.get(DocumentIntakeBatch, "b1") is not None
    assert await sessao_db.get(Document, "d1") is not None
    assert (upload_dir / "2026/08/d1.pdf").exists()


# ── caso positivo: fora da janela, sem case_id, status expurgável ─────────────

@pytest.mark.anyio
@pytest.mark.parametrize("status", ["erro", "concluido"])
async def test_batch_expirado_e_removido(sessao_db, upload_dir, status):
    await _semear(
        sessao_db, upload_dir, batch_status=status, batch_updated_at=_velho(45),
        size_bytes=250,
    )

    resultado = await expurgar_rascunhos_entrada_unica(
        sessao_db, dias=30, dry_run=False,
    )

    assert resultado["batches_removidos"] == 1
    assert resultado["documentos_removidos"] == 1
    assert resultado["bytes_liberados"] == 250
    assert await sessao_db.get(DocumentIntakeBatch, "b1") is None
    assert await sessao_db.get(Document, "d1") is None
    assert await sessao_db.get(DocumentIntakeItem, "i1") is None
    assert not (upload_dir / "2026/08/d1.pdf").exists()


@pytest.mark.anyio
async def test_arquivo_fisico_ja_ausente_nao_e_fatal(sessao_db, upload_dir):
    """FileNotFoundError no os.remove é não-fatal — o registro é removido
    mesmo assim (o arquivo pode já ter sumido antes desta execução)."""
    await _semear(
        sessao_db, upload_dir, batch_updated_at=_velho(45),
        criar_arquivo_fisico=False,
    )

    resultado = await expurgar_rascunhos_entrada_unica(
        sessao_db, dias=30, dry_run=False,
    )

    assert "erro" not in resultado
    assert resultado["batches_removidos"] == 1
    assert resultado["documentos_removidos"] == 1
    assert await sessao_db.get(DocumentIntakeBatch, "b1") is None
    assert await sessao_db.get(Document, "d1") is None


# ── dry_run=True: só conta, nunca apaga ────────────────────────────────────────

@pytest.mark.anyio
async def test_dry_run_nao_apaga_nada(sessao_db, upload_dir):
    await _semear(
        sessao_db, upload_dir, batch_updated_at=_velho(45), size_bytes=250,
    )

    resultado = await expurgar_rascunhos_entrada_unica(
        sessao_db, dias=30, dry_run=True,
    )

    assert resultado["dry_run"] is True
    assert resultado["batches_removidos"] == 1
    assert resultado["documentos_removidos"] == 1
    assert resultado["bytes_liberados"] == 250
    # nada foi tocado de verdade:
    assert await sessao_db.get(DocumentIntakeBatch, "b1") is not None
    assert await sessao_db.get(Document, "d1") is not None
    assert await sessao_db.get(DocumentIntakeItem, "i1") is not None
    assert (upload_dir / "2026/08/d1.pdf").exists()


async def test_dry_run_e_o_default():
    import inspect
    assinatura = inspect.signature(expurgar_rascunhos_entrada_unica)
    assert assinatura.parameters["dry_run"].default is True


# ── formato do dict de resultado ───────────────────────────────────────────────

@pytest.mark.anyio
async def test_resultado_tem_chaves_e_contagens_certas(sessao_db, upload_dir):
    await _semear(
        sessao_db, upload_dir, batch_updated_at=_velho(45), size_bytes=250,
    )

    resultado = await expurgar_rascunhos_entrada_unica(
        sessao_db, dias=30, dry_run=True,
    )

    assert set(resultado.keys()) == {
        "dry_run", "batches_removidos", "documentos_removidos",
        "bytes_liberados", "mais_antigo_dias", "corte",
    }
    assert isinstance(resultado["batches_removidos"], int)
    assert isinstance(resultado["documentos_removidos"], int)
    assert isinstance(resultado["bytes_liberados"], int)
    assert resultado["mais_antigo_dias"] is not None
    assert resultado["mais_antigo_dias"] >= 44  # semeado com _velho(45)
    # corte é ISO parseável e ~30 dias atrás:
    corte = datetime.fromisoformat(resultado["corte"])
    assert corte < datetime.now(timezone.utc) - timedelta(days=29)


@pytest.mark.anyio
async def test_resultado_sem_batches_qualificados_tem_mais_antigo_none(
    sessao_db, upload_dir,
):
    await _semear(sessao_db, upload_dir, batch_updated_at=_recente(5))

    resultado = await expurgar_rascunhos_entrada_unica(
        sessao_db, dias=30, dry_run=True,
    )

    assert resultado["batches_removidos"] == 0
    assert resultado["mais_antigo_dias"] is None
