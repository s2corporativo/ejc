from pathlib import Path


def test_event_subscriber_patch_usa_ocr_completo():
    """O hook efetivo de análise documental não pode reenviar OCR cortado.

    O router legado ainda é grande e sensível; o app aplica, no startup, uma
    substituição do símbolo legado do router pela implementação única e
    centralizada de `document_analysis_hook.analisar_documento_bg`, que encaminha
    `ocr_text` integral (sem corte) ao pipeline moderno de `analisar_caso`, que
    já monta dossiê para documentos longos. Este teste protege a correção contra
    regressão nas duas camadas: o patch de boot e o payload do hook.
    """
    source = Path("app/services/event_subscribers.py").read_text(encoding="utf-8")

    assert "documents_router._analisar_doc_bg = analisar_documento_bg" in source
    hook = Path("app/services/document_analysis_hook.py").read_text(encoding="utf-8")
    assert "texto_documento=ocr_text," in hook
    assert "texto_documento=ocr_text[:" not in hook
    assert "ocr_text[:4000]" not in hook
