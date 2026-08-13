from pathlib import Path


def test_event_subscriber_patch_usa_ocr_completo():
    """O hook efetivo de análise documental não pode reenviar OCR cortado.

    O router legado ainda é grande e sensível; o app aplica, no startup, uma
    substituição explícita do hook de background para enviar `ocr_text` completo
    ao pipeline moderno de `analisar_caso`, que já monta dossiê para documentos
    longos. Este teste protege a correção contra regressão.
    """
    source = Path("app/services/event_subscribers.py").read_text(encoding="utf-8")
    hook = Path("app/services/document_analysis_hook.py").read_text(encoding="utf-8")

    # O adapter do boot aponta o símbolo legado do router para a função única
    # centralizada — nunca para uma cópia que corte o OCR.
    assert "documents_router._analisar_doc_bg = analisar_documento_bg" in source
    assert "def analisar_documento_bg(" in hook
    assert "texto_documento=ocr_text," in hook
    assert "texto_documento=ocr_text[:" not in hook
    assert "ocr_text[:4000]" not in hook
