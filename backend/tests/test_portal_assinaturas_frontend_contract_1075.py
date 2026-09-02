"""Contrato frontend do Portal de Assinaturas — Issue #1075 (ASS-00).

O backend já exige `documento_visualizado_em` antes de assinar. Este teste
impede que a UI volte a oferecer assinatura sem uma forma de abrir o conteúdo.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PORTAL = ROOT / "frontend/src/pages/portal/PortalAssinaturas.tsx"


def test_portal_oferece_visualizacao_antes_de_assinar():
    fonte = PORTAL.read_text(encoding="utf-8")

    assert "/signatures/${s.id}/documento" in fonte
    assert 'responseType: "blob"' in fonte
    assert '"Ver documento"' in fonte
    assert "visualizados.has(s.id)" in fonte
    assert "Abra e leia o documento antes de assinar" in fonte
    assert "disabled={!foiVisualizado" in fonte
