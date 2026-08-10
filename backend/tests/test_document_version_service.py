from __future__ import annotations

import pytest

from app.models.document import DocConfidencialidade, Document
from app.services.document_version_service import (
    DocumentoVersaoError,
    configurar_documento_raiz,
    preparar_nova_versao,
)


def _novo(doc_id: str) -> Document:
    return Document(
        id=doc_id,
        titulo="Documento teste",
        filename="documento.pdf",
        filepath=f"2026/08/{doc_id}.pdf",
        mimetype="application/pdf",
        size_bytes=10,
        confidencialidade=DocConfidencialidade.normal,
    )


def test_configurar_raiz_usa_proprio_id_como_grupo():
    documento = _novo("00000000-0000-0000-0000-000000000001")

    info = configurar_documento_raiz(documento)

    assert info.grupo_id == documento.id
    assert info.versao == 1
    assert info.anterior_id is None
    assert documento.versao == 1
    assert documento.versao_grupo_id == documento.id
    assert documento.versao_anterior_id is None


def test_configurar_raiz_sem_id_falha_fechado():
    documento = _novo("")

    with pytest.raises(DocumentoVersaoError, match="sem identificador"):
        configurar_documento_raiz(documento)


@pytest.mark.asyncio
async def test_documento_nao_pode_versionar_a_si_mesmo():
    documento = _novo("00000000-0000-0000-0000-000000000002")

    with pytest.raises(DocumentoVersaoError, match="versionar a si mesmo"):
        await preparar_nova_versao(
            None,  # type: ignore[arg-type] — falha antes de qualquer acesso ao DB
            documento,
            documento_anterior_id=documento.id,
        )
