from pathlib import Path


def test_event_subscriber_patch_usa_ocr_completo():
    """O hook efetivo de análise documental não pode reenviar OCR cortado.

    O router legado ainda é grande e sensível; o app aplica, no startup, uma
    substituição explícita do hook de background para enviar `ocr_text` completo
    ao pipeline moderno de `analisar_caso`, que já monta dossiê para documentos
    longos. Este teste protege a correção contra regressão.
    """
    source = Path("app/services/event_subscribers.py").read_text(encoding="utf-8")

    assert "documents_router._analisar_doc_bg = _analisar_doc_bg_sem_corte" in source
    assert "texto_documento=ocr_text," in source
    assert "texto_documento=ocr_text[:" not in source
    assert "ocr_text[:4000]" not in source
