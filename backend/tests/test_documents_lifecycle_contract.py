"""Contrato de entrada do lifecycle documental consolidado.

Os fluxos de exclusão/guarda são exercitados comportamentalmente em
``test_ged_rag_pendencias.py``. Regras de vínculo da tela global ficam em
Vitest co-localizado com ``Documentos.tsx``. Este arquivo mantém somente o
contrato Pydantic que precisa falhar antes de qualquer acesso ao banco.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.routers.documents import DocumentPatchRequest


def test_patch_documento_expoe_somente_metadados_editaveis():
    assert set(DocumentPatchRequest.model_fields) == {
        "titulo",
        "tipo",
        "confidencialidade",
    }


@pytest.mark.parametrize(
    "campo",
    [
        "case_id",
        "client_id",
        "filename",
        "filepath",
        "mimetype",
        "size_bytes",
        "uploaded_by",
        "drive_file_id",
        "deleted_at",
        "versao",
        "versao_grupo_id",
        "versao_anterior_id",
    ],
)
def test_patch_documento_rejeita_campos_estruturais_e_fisicos(campo: str):
    with pytest.raises(ValidationError):
        DocumentPatchRequest(**{campo: "valor-arbitrario"})


def test_patch_documento_rejeita_case_id_nulo_tambem():
    with pytest.raises(ValidationError):
        DocumentPatchRequest(case_id=None)
