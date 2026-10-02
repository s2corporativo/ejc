from unittest.mock import AsyncMock

import pytest

from app.services.legal_brain.contracts import (
    FactualFitReview,
    ResearchPlan,
    ResearchStep,
)
from app.services.legal_brain.rag_research import (
    _record_from_rag,
    apply_factual_fit_review,
    execute_research_plan_with_rag,
)
from app.services.legal_brain.research_loop import (
    evaluate_research_coverage,
    evaluate_research_coverage_by_issue,
    uncovered_issues,
)


def _rec(issue, source_class="legislacao_oficial", **extra):
    base = {
        "issue_key": issue,
        "source_id": f"src-{issue}-{source_class}",
        "source_class": source_class,
        "validity_verified": True,
    }
    base.update(extra)
    return base


def test_cobertura_por_questao_nao_deixa_fonte_de_uma_cobrir_outra():
    records = [_rec("q1")]
    # Agregado global (legado) enxerga fonte primária mesmo para q2.
    assert evaluate_research_coverage(records).primary_source is True

    por_questao = evaluate_research_coverage_by_issue(records, issue_keys=("q1", "q2"))
    assert por_questao["q1"].primary_source is True
    assert por_questao["q1"].current_validity is True
    assert por_questao["q2"].primary_source is False
    assert por_questao["q2"].current_validity is False
    assert uncovered_issues(por_questao) == ("q1", "q2")


def test_cobertura_por_questao_fail_closed_sem_issue_key_ou_proveniencia():
    sem_chave = {"source_id": "x", "source_class": "legislacao_oficial", "validity_verified": True}
    sem_prov = {"issue_key": "q1", "source_class": "legislacao_oficial", "validity_verified": True}
    res = evaluate_research_coverage_by_issue([sem_chave, sem_prov, "lixo"], issue_keys=("q1",))
    assert set(res) == {"q1"}
    assert res["q1"].primary_source is False
    assert res["q1"].current_validity is False


def test_cobertura_por_questao_completa_somente_com_todas_as_dimensoes():
    records = [
        _rec("q1"),
        _rec("q1", "jurisprudencia_oficial", stance="favoravel", factual_fit_reviewed=True),
        _rec("q1", "precedente_vinculante", stance="adverso"),
    ]
    res = evaluate_research_coverage_by_issue(records, issue_keys=("q1", "q2"))
    assert res["q1"].complete is True
    assert res["q2"].complete is False
    assert uncovered_issues(res) == ("q2",)


def test_record_rag_carrega_issue_key():
    item = {"doc_id": "d1", "titulo": "T", "categoria": "legislacao"}
    assert _record_from_rag(item, purpose="fonte_primaria", issue_key="q9")["issue_key"] == "q9"
    assert _record_from_rag(item, purpose="fonte_primaria")["issue_key"] is None


@pytest.mark.asyncio
async def test_execute_expoe_cobertura_por_questao(monkeypatch):
    from app.services import ai_service

    monkeypatch.setattr(ai_service, "buscar_contexto_rag", AsyncMock(return_value=[]))
    plan = ResearchPlan(
        "q7", "civil", 1,
        (ResearchStep(1, "fonte_primaria", "c", ("legislacao_oficial",)),),
        ("x",),
    )
    result = await execute_research_plan_with_rag(object(), plan)
    assert result["coverage_by_issue"]["q7"]["complete"] is False
    assert result["coverage_by_issue"]["q7"]["primary_source"] is False


@pytest.mark.asyncio
async def test_max_cycles_repete_passos_vazios_ate_o_limite(monkeypatch):
    from app.services import ai_service

    item = {"doc_id": "d1", "titulo": "T", "categoria": "legislacao", "fonte": "https://x"}
    # Passo c1 vem vazio no 1º ciclo e preenche no 2º; c2 sempre traz algo.
    respostas = {
        "c1": [[], [dict(item, doc_id="d1")], [dict(item, doc_id="d1b")]],
        "c2": [[dict(item, doc_id="d2")]],
    }

    async def fake(db, query, **kw):
        fila = respostas[query]
        return fila.pop(0) if fila else []

    retrieve = AsyncMock(side_effect=fake)
    monkeypatch.setattr(ai_service, "buscar_contexto_rag", retrieve)
    plan = ResearchPlan(
        "q1", "civil", 3,
        (
            ResearchStep(1, "fonte_primaria", "c1", ()),
            ResearchStep(2, "validade_temporal", "c2", ()),
        ),
        ("x",),
    )
    result = await execute_research_plan_with_rag(object(), plan)
    # ciclo 1: c1 (vazio) + c2; ciclo 2: c1 repetido (preenche) e encerra.
    assert retrieve.await_count == 3
    assert {r["source_id"] for r in result["records"]} == {"d1", "d2"}
    assert {s["cycle"] for s in result["executed_steps"]} == {1, 2}


@pytest.mark.asyncio
async def test_max_cycles_um_nao_repete_e_limite_nunca_excedido(monkeypatch):
    from app.services import ai_service

    item = {"doc_id": "d1", "titulo": "T", "categoria": "legislacao"}
    contador = {"n": 0}

    async def fake(db, query, **kw):
        contador["n"] += 1
        # sempre algo novo no passo "a", sempre vazio no passo "b"
        return [dict(item, doc_id=f"n{contador['n']}")] if query == "a" else []

    monkeypatch.setattr(ai_service, "buscar_contexto_rag", AsyncMock(side_effect=fake))
    steps = (
        ResearchStep(1, "fonte_primaria", "a", ()),
        ResearchStep(2, "validade_temporal", "b", ()),
    )
    um = await execute_research_plan_with_rag(object(), ResearchPlan("q", "c", 1, steps, ("x",)))
    assert contador["n"] == 2
    assert all(s["cycle"] == 1 for s in um["executed_steps"])

    contador["n"] = 0
    tres = await execute_research_plan_with_rag(object(), ResearchPlan("q", "c", 3, steps, ("x",)))
    # ciclo 2 repete só "b" (vazio, sem progresso) e para: nunca passa de 3 ciclos.
    assert contador["n"] == 3
    assert max(s["cycle"] for s in tres["executed_steps"]) <= 3


def _review(**kw):
    base = dict(
        issue_key="q1", source_id="d1", fits=True,
        reviewed_by_user_id="adv-1", reviewed_at="2026-10-02T10:00:00Z", stance="favoravel",
    )
    base.update(kw)
    return FactualFitReview(**base)


@pytest.mark.parametrize("campo", ["reviewed_by_user_id", "reviewed_at", "issue_key", "source_id"])
def test_revisao_exige_revisor_data_e_chaves(campo):
    with pytest.raises(ValueError):
        _review(**{campo: "   "})


def test_revisao_rejeita_posicao_invalida_e_fits_nao_booleano():
    with pytest.raises(ValueError):
        _review(stance="talvez")
    with pytest.raises(ValueError):
        _review(fits="sim")


def test_apply_factual_fit_review_registra_sem_mutar_e_alimenta_cobertura():
    item = {"doc_id": "d1", "titulo": "T", "categoria": "jurisprudencia", "fonte": "https://stj"}
    record = _record_from_rag(item, purpose="aderencia_fatica", issue_key="q1")
    assert record["factual_fit_reviewed"] is False

    novo = apply_factual_fit_review(record, _review())
    assert record["factual_fit_reviewed"] is False and record["stance"] is None
    assert novo["factual_fit_reviewed"] is True
    assert novo["factual_fit"] is True
    assert novo["stance"] == "favoravel"
    assert novo["factual_fit_reviewed_by"] == "adv-1"
    assert novo["factual_fit_reviewed_at"] == "2026-10-02T10:00:00Z"
    cov = evaluate_research_coverage_by_issue([novo], issue_keys=("q1",))["q1"]
    assert cov.factual_fit is True


def test_apply_factual_fit_review_fail_closed_em_divergencia():
    record = _record_from_rag({"doc_id": "d1", "titulo": "T"}, purpose="p", issue_key="q1")
    with pytest.raises(ValueError):
        apply_factual_fit_review(record, _review(source_id="outro"))
    with pytest.raises(ValueError):
        apply_factual_fit_review(record, _review(issue_key="q2"))
    sem_questao = _record_from_rag({"doc_id": "d1", "titulo": "T"}, purpose="p")
    with pytest.raises(ValueError):
        apply_factual_fit_review(sem_questao, _review())
