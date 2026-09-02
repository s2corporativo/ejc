"""Contrato frontend do Portal de Assinaturas — Issue #1075 (ASS-00).

Trava que a UI realmente renderiza o conteúdo antes de confirmar a visualização,
rehidrata o gate do servidor e não volta ao antigo fluxo de mero download.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PORTAL = ROOT / "frontend/src/pages/portal/PortalAssinaturas.tsx"


def _fonte() -> str:
    return PORTAL.read_text(encoding="utf-8")


def test_portal_renderiza_antes_de_confirmar_visualizacao():
    fonte = _fonte()

    assert "/signatures/${s.id}/documento" in fonte
    assert 'responseType: "blob"' in fonte
    assert '"Ver documento"' in fonte
    assert "<iframe" in fonte or "<img" in fonte
    assert "onLoad={() => confirmarVisualizacao(preview.id)}" in fonte
    assert "/signatures/${sigId}/documento-visualizado" in fonte
    assert "link.click()" not in fonte
    assert 'target = "_blank"' not in fonte


def test_portal_reidrata_gate_da_fonte_canonica():
    fonte = _fonte()

    assert "documento_visualizado_em?: string | null" in fonte
    assert "if (item.documento_visualizado_em) proximo.add(item.id)" in fonte
    assert "Boolean(s.documento_visualizado_em) || visualizados.has(s.id)" in fonte
    assert "disabled={!foiVisualizado" in fonte
    assert "Abra e leia o documento antes de assinar" in fonte


def test_portal_trata_blob_de_erro_e_formato_sem_preview():
    fonte = _fonte()

    assert "async function detalheRespostaBlob" in fonte
    assert "data instanceof Blob" in fonte
    assert "validateStatus:" in fonte
    assert "[403, 404, 410, 415].includes(status)" in fonte
    assert "preview_disponivel?: boolean" in fonte
    assert "Solicite ao escritório uma versão PDF" in fonte


def test_portal_loading_por_documento_e_layout_responsivo():
    fonte = _fonte()

    assert "useState<Set<string>>" in fonte
    assert "viewing.has(s.id)" in fonte
    assert "flex flex-col sm:flex-row" in fonte
    assert "w-full sm:w-auto" in fonte
