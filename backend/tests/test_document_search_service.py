from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.document import DocConfidencialidade, Document
from app.services.document_search_service import (
    FiltrosBuscaDocumentos,
    MAX_BUSCA_CARACTERES,
    aplicar_filtros,
    normalizar_busca,
    validar_paginacao,
)


def _sql(query) -> str:
    return str(
        query.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_busca_vazia_e_normalizada():
    assert normalizar_busca(None) is None
    assert normalizar_busca("   ") is None
    assert normalizar_busca("  contrato  ") == "contrato"


def test_busca_excessiva_falha_fechado():
    with pytest.raises(ValueError, match="limite"):
        normalizar_busca("x" * (MAX_BUSCA_CARACTERES + 1))


def test_filtros_preservam_predicado_previo_de_autorizacao():
    base = select(Document).where(Document.uploaded_by == "usuario-sentinela")
    query = aplicar_filtros(
        base,
        FiltrosBuscaDocumentos(
            case_id="caso-sentinela",
            client_id="cliente-sentinela",
            tipo="contrato",
            confidencialidade=DocConfidencialidade.normal,
            data_inicio=date(2026, 8, 1),
            data_fim=date(2026, 8, 10),
            classificacao_pendente=False,
        ),
    )
    sql = _sql(query)

    assert "documents.uploaded_by = 'usuario-sentinela'" in sql
    assert "documents.case_id = 'caso-sentinela'" in sql
    assert "documents.client_id = 'cliente-sentinela'" in sql
    assert "documents.tipo = 'contrato'" in sql
    assert "documents.tipo IS NOT NULL" in sql
    assert "ORDER BY documents.created_at DESC, documents.id DESC" in sql


def test_curingas_de_usuario_sao_escapados_como_literais():
    query = aplicar_filtros(
        select(Document),
        FiltrosBuscaDocumentos(search=r"100%_final\teste"),
    )
    sql = _sql(query)

    assert "ESCAPE" in sql
    assert r"100\%\_final\\teste" in sql


@pytest.mark.parametrize(
    ("page", "page_size"),
    [(0, 20), (-1, 20), (1, 0), (1, 101), (True, 20), (1, True)],
)
def test_paginacao_invalida_e_rejeitada(page, page_size):
    with pytest.raises(ValueError):
        validar_paginacao(page, page_size)


def test_paginacao_valida_aceita_teto():
    validar_paginacao(1, 1)
    validar_paginacao(999, 100)
