"""Cobertura das skills e agentes nativos do EJC."""
from __future__ import annotations

from app.services.module_registry import MODULE_REGISTRY
from app.services.ai.core.agent_registry import AGENT_REGISTRY
from app.services.ai.core.dpt360_registry import DPT_SKILL_NAMES
from app.services.ai.core.ejc_skill_catalog import (
    LEGAL_AREA_SPECS,
    MODULE_SKILL_SPECS,
    native_skill_coverage,
    native_skill_specs,
    resolve_native_skill_plan,
)
from app.services.ai.core.intent_classifier import classify_intent
from app.services.ai.core.skill_registry import SKILL_REGISTRY


EXPECTED_LEGAL_AREAS = {
    "empresarial",
    "civel",
    "penal",
    "trabalhista",
    "administrativo",
    "bancario",
    "tributario",
    "ambiental",
    "consumidor",
    "familia",
    "imobiliario",
    "previdenciario",
    "digital_lgpd",
    "transito",
}

AREA_AGENTS = {
    "empresarial": "CorporateLawAgent",
    "civel": "CivilLawAgent",
    "penal": "CriminalLawAgent",
    "trabalhista": "LaborLawAgent",
    "administrativo": "AdministrativeLawAgent",
    "bancario": "BankForensicsAgent",
    "tributario": "TaxLawAgent",
    "ambiental": "EnvironmentalLawAgent",
    "consumidor": "ConsumerLawAgent",
    "familia": "FamilyLawAgent",
    "imobiliario": "RealEstateLawAgent",
    "previdenciario": "SocialSecurityAgent",
    "digital_lgpd": "DigitalLGPDAgent",
    "transito": "TrafficLawAgent",
}


def test_catalogo_cobre_todos_os_ramos_e_modulos() -> None:
    module_keys = {str(item["module_key"]) for item in MODULE_REGISTRY}

    assert set(LEGAL_AREA_SPECS) == EXPECTED_LEGAL_AREAS
    assert set(MODULE_SKILL_SPECS) == module_keys
    assert len(LEGAL_AREA_SPECS) == 14
    # 34 módulos = 35 anteriores - biblioteca - whatsapp + sala-juridica
    # (pente fino 2026-07, onda 2 — paridade com o moduleRegistry do frontend).
    assert len(MODULE_SKILL_SPECS) == 34
    assert len(native_skill_specs()) == 48

    coverage = native_skill_coverage()
    assert coverage["complete"] is True
    assert coverage["total_native_skills"] == 48
    assert coverage["legal_areas"]["missing"] == []
    assert coverage["modules"]["missing"] == []


def test_resolver_combina_ramo_e_modulo_sem_llm() -> None:
    plan = resolve_native_skill_plan(
        task_type="chat",
        domain="ambiental",
        message="Analisar o auto dentro do caso.",
        module_key="casos",
    )

    assert plan.legal_area == "ambiental"
    assert plan.module_key == "casos"
    assert plan.skill_names == ("ramo_ambiental", "modulo_casos")
    assert len(plan.prompt_blocks) == 2


def test_resolver_aceita_alias_de_tela_e_keywords() -> None:
    plan = resolve_native_skill_plan(
        task_type="chat",
        domain=None,
        message="Preparar recurso para a JARI sobre multa de trânsito.",
        surface="processos",
    )

    assert plan.legal_area == "transito"
    assert plan.module_key == "casos"
    assert "ramo_transito" in plan.skill_names
    assert "modulo_casos" in plan.skill_names


def test_prompts_nativos_preservam_regras_juridicas_e_operacionais() -> None:
    for spec in LEGAL_AREA_SPECS.values():
        assert "Não invente" in spec.system_prompt
        assert "revisão humana obrigatória" in spec.system_prompt
        assert spec.oab_restricted is True

    for spec in MODULE_SKILL_SPECS.values():
        assert "Não alegue que registro" in spec.system_prompt
        assert "confirmação humana" in spec.system_prompt
        assert spec.oab_restricted is False


def test_registry_central_inclui_todas_as_skills_nativas() -> None:
    expected_names = {spec.name for spec in native_skill_specs()}
    registered_names = set(SKILL_REGISTRY)
    dpt_present = registered_names & DPT_SKILL_NAMES

    assert expected_names <= registered_names
    assert "resolve_native_skills" in SKILL_REGISTRY
    assert SKILL_REGISTRY["resolve_native_skills"].handler is not None

    # O catálogo nativo continua tendo exatamente 28 skills centrais + 48
    # nativas. O DPT é uma extensão registrada sob demanda; como os registries
    # são globais no processo de teste, sua presença depende da ordem da suíte.
    # Quando presente, a extensão deve aparecer de forma atômica (as 4 ou
    # nenhuma), nunca parcialmente.
    assert dpt_present in (set(), set(DPT_SKILL_NAMES))
    base_registry = registered_names - DPT_SKILL_NAMES
    assert len(base_registry) == 28 + len(expected_names)
    assert len(registered_names) == len(base_registry) + len(dpt_present)


def test_coordenador_e_especialistas_estao_registrados() -> None:
    coordinator = AGENT_REGISTRY["EJCCoordinatorAgent"]
    assert "resolve_native_skills" in coordinator.skills

    for area, agent_name in AREA_AGENTS.items():
        agent = AGENT_REGISTRY[agent_name]
        assert f"ramo_{area}" in agent.skills


def test_roteamento_dedica_ambiental_digital_e_transito() -> None:
    assert classify_intent("chat", "ambiental", "").agente == "EnvironmentalLawAgent"
    assert classify_intent("chat", "digital_lgpd", "").agente == "DigitalLGPDAgent"
    assert classify_intent("chat", "transito", "").agente == "TrafficLawAgent"
    assert classify_intent("modulo", None, "Abrir o módulo").agente == "EJCCoordinatorAgent"


def test_rota_compartilhada_resolve_para_modulo_canonico() -> None:
    """Regressão da onda 2: conhecimento e victory-vault compartilham a rota
    /inteligencia?tab=conhecimento — o alias de rota deve resolver para o
    módulo CANÔNICO (primeiro no MODULE_REGISTRY), nunca para o carona."""
    from app.services.ai.core.ejc_skill_catalog import MODULE_ALIASES, _normalize

    assert MODULE_ALIASES[_normalize("/inteligencia?tab=conhecimento")] == "conhecimento"
    # Chaves e nomes continuam resolvendo para si mesmos.
    assert MODULE_ALIASES["victory_vault"] == "victory-vault"
