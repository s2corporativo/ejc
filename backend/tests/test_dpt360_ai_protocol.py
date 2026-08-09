import json

from app.services.ai.core.dpt360_protocol import build_dpt_instruction, parse_structured_content
from app.services.ai.core.dpt360_registry import ensure_dpt360_registered


def test_protocolo_nao_solicita_chain_of_thought_e_exige_produto_estruturado():
    prompt = build_dpt_instruction(
        action="conselho",
        company_context={"casos_abertos": 2, "regra": "não presumir regularidade"},
        question="Quais são os maiores riscos?",
        area="empresarial",
    )
    assert "NÃO exponha raciocínio interno" in prompt
    assert '"fatos"' in prompt
    assert '"objecoes"' in prompt
    assert '"revisao_humana"' in prompt


def test_parse_estruturado_nao_conserta_json_invalido():
    assert parse_structured_content("não é json") is None
    payload = {"fatos": [], "conclusao": "rascunho"}
    assert parse_structured_content(json.dumps(payload)) == payload
    assert parse_structured_content(f"```json\n{json.dumps(payload)}\n```") == payload


def test_registro_dpt_extende_nucleo_unico_de_forma_idempotente():
    ensure_dpt360_registered()
    ensure_dpt360_registered()

    from app.services.ai.core.agent_registry import AGENT_REGISTRY
    from app.services.ai.core.intent_classifier import TASK_TYPE_PARA_AGENTE
    from app.services.ai.core.skill_registry import SKILL_REGISTRY

    agent = AGENT_REGISTRY["DPTEnterpriseAgent"]
    assert agent.exige_fonte is True
    assert "mark_as_draft" in agent.skills
    assert "validate_citations" in agent.skills
    assert TASK_TYPE_PARA_AGENTE["conselho_empresarial"] == "DPTEnterpriseAgent"
    assert "apply_dpt_legal_protocol" in SKILL_REGISTRY
    assert "preflight_legal_consistency" in SKILL_REGISTRY
    assert "dpt_adversarial_review" in SKILL_REGISTRY
