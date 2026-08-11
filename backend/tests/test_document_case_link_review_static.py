"""Guardas estáticas contra regressões de metadados no vínculo documental."""
from __future__ import annotations

from pathlib import Path


SERVICE = Path(__file__).parents[1] / "app/services/document_case_link_service.py"


def test_conflitos_nao_formatam_titulos_de_peca_ou_prova():
    src = SERVICE.read_text(encoding="utf-8")
    assert "LegalDoc.id, LegalDoc.titulo" not in src
    assert "Prova.id, Prova.titulo" not in src
    assert "ref.titulo" not in src
    assert "prova.titulo" not in src
