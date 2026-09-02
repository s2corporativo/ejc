"""Regressões estruturais da onda de governança do GED.

Testes rápidos complementam os testes de integração DB/HTTP: impedem retorno a
padrões que já causaram perda de evidência ou wiring incorreto.
"""
from pathlib import Path

from app.models.document import Document, DocumentStorageOperation
from app.services.document_storage_operation_service import criar_operacao_purge

ROOT = Path(__file__).resolve().parents[1]


def _source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_model_documento_expoe_gates_de_governanca():
    for atributo in (
        "legal_hold",
        "retention_until",
        "malware_scan_status",
        "analysis_status",
        "integrity_status",
        "rag_status",
    ):
        assert hasattr(Document, atributo)
    assert DocumentStorageOperation.__tablename__ == "document_storage_operations"


def test_outbox_captura_storage_sem_apagar_objeto():
    doc = Document(
        id="doc-1",
        titulo="sentinela",
        filename="arquivo.pdf",
        filepath="2026/09/doc-1.pdf",
        confidencialidade="confidencial",
    )
    op = criar_operacao_purge(doc, requested_by="u1")
    assert op.document_id == "doc-1"
    assert op.storage_kind == "local"
    assert op.storage_locator == "2026/09/doc-1.pdf"
    assert len(op.operation_key) == 64


def test_rescan_celery_nao_reutiliza_task_rag():
    src = _source("app/tasks/rescan_tasks.py")
    assert 'name="app.tasks.document_rescan"' in src
    assert "rescan_documentos_task.delay(batch_id)" in src
    assert "indexar_documento_task" not in src


def test_ingestao_canonica_nao_chama_llm_para_extrair_ocr():
    src = _source("app/services/document_extraction_adapter.py")
    assert "documento_service" not in src
    assert "extrair_texto" in src
    assert "extrair_xml" in src


def test_trash_bloqueia_hold_e_retem_outbox_antes_do_delete():
    src = _source("app/routers/trash.py")
    assert "Documento sob legal hold" in src
    assert "Documento ainda está dentro do prazo de retenção" in src
    assert "criar_operacao_purge" in src
    assert "agendar_purge_storage" in src
