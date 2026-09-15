"""Agentes transversais jurídicos — provas e revisão judicial simulada."""

from app.services.ai.core.agent_registry import AGENT_REGISTRY
from app.services.ai.core.intent_classifier import classify_intent
from app.services.system_prompts import SYSTEM_PROMPTS


def test_evidence_agent_e_read_only_por_design_do_nucleo_e_exige_fontes():
    ag = AGENT_REGISTRY["EvidenceAgent"]
    assert ag.exige_fonte is True
    assert ag.prompt_key == "provas"
    assert "retrieve_rag_sources" in ag.skills
    assert "validate_citations" in ag.skills
    assert "generate_legal_draft" not in ag.skills
    assert "apply_authorized_patch" not in ag.skills


def test_judicial_review_agent_nao_e_agente_de_sentenca_ou_predicao():
    ag = AGENT_REGISTRY["JudicialReviewAgent"]
    assert ag.exige_fonte is True
    assert ag.prompt_key == "revisao_judicial"
    prompt = SYSTEM_PROMPTS[ag.prompt_key].lower()
    assert "sem afirmar ou prever" in prompt
    assert "nunca produza sentença fictícia" in prompt
    assert "probabilidade de vitória" in prompt


def test_aliases_roteiam_para_agentes_transversais():
    assert classify_intent("provas", mensagem="auditar").agente == "EvidenceAgent"
    assert classify_intent("revisao_judicial", mensagem="revisar").agente == "JudicialReviewAgent"
    # Keywords só atuam quando task/domain não selecionaram agente explicitamente;
    # `chat` continua CaseAgent por compatibilidade com o contrato existente.
    assert classify_intent("desconhecido", mensagem="quais provas faltam neste caso?").agente == "EvidenceAgent"
    assert classify_intent("desconhecido", mensagem="analise pela perspectiva do magistrado").agente == "JudicialReviewAgent"


def test_agentes_transversais_dependem_de_caso_concreto():
    assert classify_intent("provas", mensagem="x").precisa_caso is True
    assert classify_intent("revisao_judicial", mensagem="x").precisa_caso is True
