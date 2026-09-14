from app.eval.legal_bench import LegalBenchCase, score_structured_answer, summarize
from app.services.legal_brain import (
    PrecedentPropositionStatus,
    build_legal_brain_plan,
    build_research_plan,
    evaluate_proposition_validity,
    evaluate_research_coverage,
    identify_legal_issues,
)


def test_issue_engine_nao_conclui_merito_e_expoe_lacunas():
    issues = identify_legal_issues(
        "Cliente teve cobrança bancária, juros e negativação e precisa de liminar.",
        area="bancario",
    )
    keys = {issue.key for issue in issues}
    assert "bancario_contrato_encargos" in keys
    assert "tutela_urgencia" in keys
    for issue in issues:
        assert issue.required_questions
        assert issue.required_evidence


def test_issue_engine_sem_match_retorna_saneamento_em_vez_de_inventar():
    issues = identify_legal_issues("Relato ainda incompleto", area=None)
    assert len(issues) == 1
    assert issues[0].key == "saneamento_inicial"
    assert issues[0].area == "nao_definida"


def test_research_plan_exige_fonte_validade_e_contraditorio():
    issue = identify_legal_issues(
        "Há discussão de prescrição e prova documental.", area="civil"
    )[0]
    plan = build_research_plan(issue, max_cycles=4)
    purposes = {step.purpose for step in plan.steps}
    assert "fonte_primaria" in purposes
    assert "validade_temporal" in purposes
    assert "precedente_favoravel" in purposes
    assert "precedente_adverso" in purposes
    assert plan.max_cycles == 4
    assert "INSUFICIENTE" in plan.insufficient_evidence_message


def test_research_coverage_so_fecha_com_flags_explicitas():
    coverage = evaluate_research_coverage(
        [
            {
                "source_class": "legislacao_oficial",
                "validity_verified": True,
                "factual_fit_reviewed": True,
            },
            {"source_class": "jurisprudencia_oficial", "stance": "favoravel"},
            {"source_class": "jurisprudencia_oficial", "stance": "adverso"},
        ]
    )
    assert coverage.complete is True


def test_precedent_validity_sem_proveniencia_falha_fechado():
    result = evaluate_proposition_validity(
        "prop-1", [{"relation": "overruled_by", "source_id": ""}]
    )
    assert result.status == PrecedentPropositionStatus.NAO_VERIFICADA
    assert result.related_source_ids == ()


def test_precedent_validity_prioriza_superacao_explicita():
    result = evaluate_proposition_validity(
        "prop-1",
        [
            {"relation": "confirmed_by", "source_id": "src-confirmacao"},
            {"relation": "limited_by", "source_id": "src-limitacao"},
            {"relation": "overruled_by", "source_id": "src-superacao"},
        ],
    )
    assert result.status == PrecedentPropositionStatus.SUPERADA
    assert result.decisive_relation == "overruled_by"
    assert "src-superacao" in result.related_source_ids


def test_legal_brain_reutiliza_catalogo_nativo_sem_segundo_gateway():
    plan = build_legal_brain_plan(
        task_type="analise_juridica",
        domain="bancario",
        message="Revisar financiamento, juros, CET, prova e eventual tutela.",
        module_key="inteligencia",
    )
    assert plan.metadata["engine"] == "legal_brain_v1"
    assert plan.metadata["deterministic"] is True
    assert plan.issues
    assert plan.research_plans


def test_legal_bench_pune_fato_inventado_e_ausencia_de_adversarial():
    case = LegalBenchCase(
        id="bench-1",
        area="consumidor",
        prompt="Caso sintético",
        expected_issue_keys=("tutela_urgencia",),
        expected_source_ids=("fonte-1",),
        allowed_fact_ids=("fato-1",),
        requires_adverse_research=True,
        has_missing_evidence=True,
    )
    score = score_structured_answer(
        case,
        {
            "issue_keys": ["tutela_urgencia"],
            "source_ids": ["fonte-1"],
            "fact_ids": ["fato-1", "fato-inventado"],
            "adverse_research_done": False,
            "conclusion_status": "conclusivo",
        },
    )
    assert score.issue_recall == 1.0
    assert score.source_precision == 1.0
    assert score.fact_grounding == 0.5
    assert score.adverse_coverage == 0.0
    assert score.uncertainty_compliance == 0.0
    assert summarize([score])["n"] == 1
