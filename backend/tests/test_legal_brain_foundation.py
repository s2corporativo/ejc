import pytest

from app.eval.legal_bench import LegalBenchCase, score_structured_answer, summarize
from app.services.legal_brain import (
    CaseAssertion,
    EvidenceState,
    PrecedentPropositionStatus,
    build_legal_brain_plan,
    build_research_plan,
    evaluate_proposition_validity,
    evaluate_research_coverage,
    identify_legal_issues,
    transition_assertion,
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


def test_saneamento_inicial_nao_dispara_pesquisa_de_precedentes():
    plan = build_legal_brain_plan(
        task_type="analise_juridica",
        message="Relato ainda incompleto",
    )
    purposes = {step.purpose for research in plan.research_plans for step in research.steps}
    assert purposes == {"saneamento_fatico"}
    assert "precedente_favoravel" not in purposes
    assert "precedente_adverso" not in purposes


def test_issue_engine_usa_fronteira_de_palavra_e_nao_substring():
    issues = identify_legal_issues(
        "O escritório recebeu aprovação interna do texto.",
        area="civil",
    )
    keys = {issue.key for issue in issues}
    assert "competencia_rito" not in keys
    assert "prova_onus_lacunas" not in keys


def test_questoes_transversais_nao_somem_quando_area_e_informada():
    issues = identify_legal_issues(
        "Pedido de liminar com prova documental.",
        area="familia",
    )
    keys = {issue.key for issue in issues}
    assert "tutela_urgencia" in keys
    assert "prova_onus_lacunas" in keys


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


def test_research_coverage_exige_proveniencia_e_booleanos_nativos():
    sem_proveniencia = evaluate_research_coverage(
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
    assert sem_proveniencia.complete is False

    cobertura = evaluate_research_coverage(
        [
            {
                "source_id": "norma-1",
                "source_class": "legislacao_oficial",
                "validity_verified": True,
                "factual_fit_reviewed": True,
            },
            {
                "source_id": "precedente-1",
                "source_class": "jurisprudencia_oficial",
                "stance": "favoravel",
            },
            {
                "source_id": "precedente-2",
                "source_class": "jurisprudencia_oficial",
                "stance": "adverso",
            },
        ]
    )
    assert cobertura.complete is True

    strings_nao_sao_true = evaluate_research_coverage(
        [
            {
                "source_id": "norma-2",
                "source_class": "legislacao_oficial",
                "validity_verified": "false",
                "factual_fit_reviewed": "false",
            }
        ]
    )
    assert strings_nao_sao_true.current_validity is False
    assert strings_nao_sao_true.factual_fit is False


def test_precedent_validity_sem_proveniencia_falha_fechado():
    result = evaluate_proposition_validity(
        "prop-1", [{"tipo": "supera", "outro": ""}]
    )
    assert result.status == PrecedentPropositionStatus.NAO_VERIFICADA
    assert result.related_source_ids == ()


def test_precedent_validity_prioriza_superacao_explicita():
    result = evaluate_proposition_validity(
        "prop-1",
        [
            {"tipo": "confirma", "outro": "src-confirmacao"},
            {"tipo": "limita", "outro": "src-limitacao"},
            {"tipo": "supera", "outro": "src-superacao"},
        ],
    )
    assert result.status == PrecedentPropositionStatus.SUPERADA
    assert result.decisive_relation == "supera"
    assert "src-superacao" in result.related_source_ids


def test_inferencia_ia_nao_vira_fato_confirmado_diretamente():
    assertion = CaseAssertion(
        id="fato-1",
        text="Hipótese produzida pela IA",
        state=EvidenceState.INFERENCIA_IA,
    )
    with pytest.raises(ValueError, match="transição probatória inválida"):
        transition_assertion(
            assertion,
            EvidenceState.CONFIRMADO,
            reviewer_user_id="adv-1",
            reviewed_at="2026-09-13T20:00:00-03:00",
        )


def test_construtor_nao_aceita_estado_validado_sem_trilha_humana():
    with pytest.raises(ValueError, match="revisor autenticado"):
        CaseAssertion(
            id="fato-1",
            text="Fato",
            state=EvidenceState.CONFIRMADO,
        )


def test_validacao_humana_exige_identidade_e_data():
    assertion = CaseAssertion(
        id="fato-1",
        text="Hipótese produzida pela IA",
        state=EvidenceState.INFERENCIA_IA,
    )
    with pytest.raises(ValueError, match="revisor autenticado"):
        transition_assertion(assertion, EvidenceState.VALIDADO_ADVOGADO)

    reviewed = transition_assertion(
        assertion,
        EvidenceState.VALIDADO_ADVOGADO,
        reviewer_user_id="adv-1",
        reviewed_at="2026-09-13T20:00:00-03:00",
    )
    assert reviewed.state == EvidenceState.VALIDADO_ADVOGADO
    assert reviewed.validated_by_user_id == "adv-1"


def test_legal_brain_reutiliza_catalogo_nativo_e_metadata_e_imutavel():
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
    with pytest.raises(TypeError):
        plan.metadata["requires_human_review"] = False


def test_legal_bench_pune_fato_inventado_e_adversarial_sem_fonte():
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
            "adverse_research_done": True,
            "research_records": [
                {"source_class": "jurisprudencia_oficial", "stance": "adverso"}
            ],
            "conclusion_status": "conclusivo",
        },
    )
    assert score.issue_recall == 1.0
    assert score.source_precision == 1.0
    assert score.fact_grounding == 0.5
    assert score.adverse_coverage == 0.0
    assert score.uncertainty_compliance == 0.0
    assert summarize([score])["n"] == 1


def test_legal_bench_reconhece_adversarial_com_proveniencia():
    case = LegalBenchCase(
        id="bench-2",
        area="civil",
        prompt="Caso sintético",
        requires_adverse_research=True,
        source_scoring_enabled=False,
    )
    score = score_structured_answer(
        case,
        {
            "research_records": [
                {
                    "source_id": "precedente-adverso-1",
                    "source_class": "jurisprudencia_oficial",
                    "stance": "adverso",
                }
            ],
            "conclusion_status": "sem_conclusao_segura",
        },
    )
    assert score.adverse_coverage == 1.0
