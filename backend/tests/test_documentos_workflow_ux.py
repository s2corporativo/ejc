"""Regressões do workflow simplificado de Documentos/GED (Issue #1369)."""
from __future__ import annotations

import inspect

from app.models.document import DocConfidencialidade, Document
from app.routers import documentos_workflow
from app.services.document_ux_service import motivos_atencao, status_operacional


def _doc(**overrides) -> Document:
    base = dict(
        id="d1",
        titulo="Contrato",
        filename="contrato.pdf",
        filepath="2026/09/d1.pdf",
        confidencialidade=DocConfidencialidade.normal,
        case_id="c1",
        client_id="cli1",
        tipo="contrato",
        analysis_status="completed",
        integrity_status="verified",
        malware_scan_status="clean",
        rag_status="not_indexed",
        legal_hold=False,
    )
    base.update(overrides)
    return Document(**base)


def test_status_humano_ready_processing_attention():
    assert status_operacional(_doc()) == "ready"
    assert status_operacional(_doc(analysis_status="processing")) == "processing"
    assert status_operacional(_doc(tipo=None)) == "attention"
    assert status_operacional(_doc(integrity_status="divergent")) == "attention"


def test_motivos_atencao_sao_codigos_estaveis_sem_conteudo():
    doc = _doc(
        case_id=None,
        tipo=None,
        analysis_status="failed",
        integrity_status="divergent",
        malware_scan_status="unavailable",
    )
    assert motivos_atencao(doc) == [
        "sem_caso",
        "sem_tipo",
        "analise_falhou",
        "integridade_atencao",
        "seguranca_atencao",
    ]


def test_serializador_da_lista_nao_expoe_storage_ocr_ou_outbox():
    payload = documentos_workflow._serializar_lista(_doc())
    proibidos = {
        "filepath",
        "drive_file_id",
        "drive_link",
        "ocr_text",
        "storage_locator",
        "operation_key",
    }
    assert proibidos.isdisjoint(payload)
    assert payload["operational_status"] == "ready"


def test_router_expoe_apenas_contratos_ux_declarados():
    rotas = {
        (rota.path, metodo)
        for rota in documentos_workflow.router.routes
        for metodo in (getattr(rota, "methods", None) or [])
    }
    esperadas = {
        ("/documents/workflow/stats", "GET"),
        ("/documents/workflow/inbox", "GET"),
        ("/documents/workflow/upload", "POST"),
        ("/documents/{doc_id}/versions", "GET"),
        ("/documents/{doc_id}/history", "GET"),
    }
    assert esperadas <= rotas


def test_historico_publico_do_workflow_nao_serializa_payload_worm():
    fonte = inspect.getsource(documentos_workflow.historico_documento)
    assert '"action": item.acao' in fonte
    assert '"created_at": item.created_at' in fonte
    assert "dados_antes" not in fonte
    assert "dados_depois" not in fonte
    assert "item.ip" not in fonte


def test_override_de_duplicidade_e_registrado_antes_da_persistencia():
    fonte = inspect.getsource(documentos_workflow.upload_workflow)
    pos_override = fonte.index('"DUPLICATE_OVERRIDE"')
    pos_persistencia = fonte.index("document = await persistir_documento_local")
    assert pos_override < pos_persistencia
    assert "permitir_duplicado" in fonte
    assert "documento_anterior_id" in fonte


def test_main_registra_workflow_explicitamente():
    import app.main as main

    fonte = inspect.getsource(main)
    assert "from app.routers import documentos_workflow" in fonte
    assert "app.include_router(documentos_workflow.router, prefix=API)" in fonte
