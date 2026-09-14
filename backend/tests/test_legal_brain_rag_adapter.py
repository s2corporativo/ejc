from unittest.mock import AsyncMock

import pytest

from app.services.legal_brain.contracts import ResearchPlan, ResearchStep
from app.services.legal_brain.rag_research import (
    _record_from_rag,
    execute_research_plan_with_rag,
)


def test_record_rag_preserva_proveniencia_sem_inferir_posicao_ou_aderencia():
    record = _record_from_rag(
        {
            "doc_id": "doc-1",
            "chunk_id": "chunk-1",
            "titulo": "Lei oficial",
            "categoria": "legislacao",
            "fonte": "https://www.planalto.gov.br/ccivil_03/lei/exemplo.htm",
            "extra": {
                "legal_status": "vigente",
                "legal_status_origem": "fonte_oficial",
                "legal_status_verificado_em": "2026-09-14T00:00:00Z",
            },
            "situacao_juridica": {"code": "vigente", "label": "Vigente"},
        },
        purpose="fonte_primaria",
    )

    assert record is not None
    assert record["source_id"] == "doc-1"
    assert record["chunk_id"] == "chunk-1"
    assert record["source_class"] == "legislacao_oficial"
    assert record["validity_verified"] is True
    assert record["stance"] is None
    assert record["factual_fit_reviewed"] is False


def test_record_rag_nao_promove_fonte_sem_autoridade_ou_vigencia_comprovada():
    record = _record_from_rag(
        {
            "doc_id": "doc-ref",
            "chunk_id": "chunk-ref",
            "titulo": "Texto referencial",
            "categoria": "legislacao",
            "fonte": "https://example.invalid/referencia",
            "situacao_juridica": {"code": "vigente"},
        },
        purpose="fonte_primaria",
    )

    assert record is not None
    assert record["source_class"] == "referencial"
    assert record["validity_verified"] is False


@pytest.mark.asyncio
async def test_execute_research_plan_propaga_ownership_e_historico_so_na_validade(monkeypatch):
    from app.services import ai_service

    retrieve = AsyncMock(
        return_value=[
            {
                "doc_id": "doc-1",
                "chunk_id": "chunk-1",
                "titulo": "Fonte",
                "categoria": "jurisprudencia",
                "fonte": "https://www.stj.jus.br/exemplo",
            }
        ]
    )
    monkeypatch.setattr(ai_service, "buscar_contexto_rag", retrieve)

    plan = ResearchPlan(
        issue_key="issue-1",
        area="civil",
        max_cycles=2,
        steps=(
            ResearchStep(1, "precedente_favoravel", "consulta favoravel", ("jurisprudencia_oficial",)),
            ResearchStep(2, "validade_temporal", "consulta vigencia", ("legislacao_oficial",)),
        ),
        stop_when=("pesquisa suficiente",),
    )

    result = await execute_research_plan_with_rag(
        object(),
        plan,
        limit_per_step=4,
        scope_client_id="cli-1",
        scope_case_id="case-1",
    )

    assert retrieve.await_count == 2
    first = retrieve.await_args_list[0].kwargs
    second = retrieve.await_args_list[1].kwargs
    assert first["scope_client_id"] == "cli-1"
    assert first["scope_case_id"] == "case-1"
    assert first["incluir_historico"] is False
    assert second["incluir_historico"] is True
    assert first["incluir_ficticio"] is False
    # Recuperar jurisprudência não basta para declarar posição favorável.
    assert result["coverage"]["supporting_precedent"] is False
    assert result["coverage"]["complete"] is False
    assert result["requires_human_review"] is True


@pytest.mark.asyncio
async def test_saneamento_inicial_nao_consulta_rag(monkeypatch):
    from app.services import ai_service

    retrieve = AsyncMock(return_value=[])
    monkeypatch.setattr(ai_service, "buscar_contexto_rag", retrieve)
    plan = ResearchPlan(
        issue_key="saneamento_inicial",
        area="nao_definida",
        max_cycles=1,
        steps=(
            ResearchStep(1, "clarificar_fatos", "confirmar fatos e documentos", ()),
        ),
        stop_when=("fatos essenciais confirmados",),
    )

    result = await execute_research_plan_with_rag(object(), plan)

    retrieve.assert_not_awaited()
    assert result["records"] == []
    assert result["executed_steps"][0]["skipped"] is True
    assert result["next_gap"] == "fonte_primaria"
