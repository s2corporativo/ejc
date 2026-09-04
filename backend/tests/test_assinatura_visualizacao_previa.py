"""Regressão ASS-01/ASS-00: assinatura exige visualização efetiva do conteúdo.

O GET do arquivo NÃO basta para satisfazer o gate: download, popup bloqueado ou
formato não renderizável não provam leitura. O timestamp só é gravado pelo POST
`/documento-visualizado`, acionado pela UI depois do evento de carga do preview.
"""
from __future__ import annotations

import inspect

from app.routers import signatures as sig


def _corpo(fn):
    return inspect.getsource(fn)


def test_assinar_exige_visualizacao_previa_registrada():
    src = _corpo(sig.assinar)
    assert "sr.documento_visualizado_em is None" in src
    assert "status_code=422" in src
    assert "visualizador do Portal" in src or "visualizado" in src


def test_assinar_repoe_visualizacao_no_comprovante():
    src = _corpo(sig.assinar)
    assert "documento_visualizado_em" in src
    assert "sr.documento_visualizado_em.isoformat()" in src


def test_get_documento_nao_confirma_visualizacao():
    """Mero GET/download não pode satisfazer o requisito probatório."""
    src = _corpo(sig.visualizar_documento)
    assert "sr.documento_visualizado_em =" not in src
    assert "criar_audit_log" not in src
    assert "content_disposition_type=\"inline\"" in src
    assert "Cache-Control" in src


def test_confirmacao_visualizacao_grava_so_primeira_vez():
    src = _corpo(sig.confirmar_visualizacao_documento)
    assert "sr.documento_visualizado_em is None" in src
    assert "sr.documento_visualizado_em = datetime.now(timezone.utc)" in src
    assert '"VISUALIZAR"' in src
    assert "await db.commit()" in src


def test_preview_rejeita_formato_nao_renderizavel():
    assert sig._preview_media_type("application/pdf", "termo.pdf") == "application/pdf"
    assert sig._preview_media_type("image/png", "foto.png") == "image/png"
    assert sig._preview_media_type("application/octet-stream", "legado.pdf") == "application/pdf"
    assert sig._preview_media_type(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "contrato.docx",
    ) is None
    assert sig._preview_media_type("text/html", "pagina.html") is None


def test_listagem_expoe_estado_canonico_da_visualizacao():
    src = _corpo(sig.listar)
    assert '"documento_visualizado_em": s.documento_visualizado_em' in src
    assert '"preview_disponivel"' in src
    assert "_preview_media_type" in src
