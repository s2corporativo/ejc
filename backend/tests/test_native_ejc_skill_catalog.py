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
    "civil",       # chave canônica (AREAS_CANONICAS); "civel" é alias
    "criminal",    # chave canônica; "penal" é alias
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

# Só as áreas com agente dedicado sobrevivem à consolidação 38→8 de
# 2026-09-06 (escopo definido pelo titular). As demais áreas canônicas
# (ambiental, família, imobiliário, previdenciário, digital_lgpd, trânsito)
# continuam com método de ramo/skill nativa em LEGAL_AREA_SPECS — só não têm
# mais agente de IA dedicado no núcleo (caem no fallback determinístico).
AREA_AGENTS = {
    "empresarial": "CorporateLawAgent",
    "civil": "CivilLawAgent",
    "criminal": "CriminalLawAgent",
    "trabalhista": "LaborLawAgent",
    "administrativo": "AdministrativeLawAgent",
    "bancario": "BankForensicsAgent",
    "tributario": "TaxLawAgent",
    "consumidor": "ConsumerLawAgent",
}


def test_catalogo_cobre_todos_os_ramos_e_modulos() -> None:
    module_keys = {str(item["module_key"]) for item in MODULE_REGISTRY}

    assert set(LEGAL_AREA_SPECS) == EXPECTED_LEGAL_AREAS
    assert set(MODULE_SKILL_SPECS) == module_keys
    assert len(LEGAL_AREA_SPECS) == 14
    # 34 módulos = 34 (onda 2) - noticias (CORTE-4) - victory-vault (CORTE-3)
    # + ajuizamento e ajuizamento-perfis (PR #1536) — paridade com o
    # moduleRegistry do frontend.
    assert len(MODULE_SKILL_SPECS) == 34
    assert len(native_skill_specs()) == 48

    coverage = native_skill_coverage()
    assert coverage["total_native_skills"] == 48
    assert coverage["modules"]["missing"] == []
    # C7: a cobertura agora é medida contra a taxonomia CANÔNICA — e acusa as
    # áreas sem método de ramo em vez de comparar o catálogo consigo mesmo.
    from app.core.taxonomia import AREAS_CANONICAS
    assert coverage["legal_areas"]["expected"] == len(AREAS_CANONICAS)
    assert coverage["legal_areas"]["nao_canonicas"] == []
    faltantes = set(coverage["legal_areas"]["missing"])
    assert faltantes == set(AREAS_CANONICAS) - EXPECTED_LEGAL_AREAS
    assert faltantes, "há áreas canônicas sem método de ramo (decisão de advogado)"
    # `complete` é a métrica ASPIRACIONAL e segue False — é a verdade, e o
    # painel de cobertura deve continuar mostrando isso.
    assert coverage["complete"] is False
    # `estrutura_ok` é a métrica OPERACIONAL, e É True: todo módulo tem método,
    # nenhuma área foge do enum. A separação conserta um defeito real achado no
    # pente fino de 03/09 — `skills_native_ejc_seed` usava `complete` como
    # portão e, como faltam 11 métodos jurídicos, levantava SEMPRE. Em
    # `seed_all` a exceção é engolida como "não-fatal", então as 48 skills
    # nativas VÁLIDAS nunca chegavam a `ejc_skills`: os endpoints de cobertura e
    # `/system-modules/mapa` reportavam 48 linhas que a tabela não tinha,
    # enquanto o método seguia sendo aplicado por outro caminho (o
    # `orchestrator` injeta os blocos de prompt). Catálogo mentindo em silêncio.
    assert coverage["estrutura_ok"] is True, (
        "Se a estrutura quebrar (módulo sem método, área fora do enum), o seed "
        "DEVE recusar — este é o portão legítimo, ao contrário de `complete`."
    )


def test_seed_nativo_gateia_por_estrutura_e_nao_por_completude() -> None:
    """Regressão do defeito: lacuna de CONTEÚDO (área canônica sem método de
    ramo, que "exige advogado") não pode bloquear o seed das 48 que já existem.
    Só defeito de ESTRUTURA bloqueia."""
    import inspect
    from app.seeds import skills_native_ejc_seed

    fonte = inspect.getsource(skills_native_ejc_seed.seed)
    assert 'coverage["estrutura_ok"]' in fonte
    assert 'if not coverage["complete"]' not in fonte


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


def test_aliases_forenses_resolvem_para_chave_canonica() -> None:
    """'civel'/'penal' (nome forense, domain de tela) → skill canônica."""
    for dominio, esperado in (("civel", "ramo_civil"), ("civil", "ramo_civil"),
                              ("penal", "ramo_criminal"), ("criminal", "ramo_criminal")):
        plan = resolve_native_skill_plan(task_type="chat", domain=dominio, message="")
        assert esperado in plan.skill_names, (dominio, plan.skill_names)


def test_empate_de_keywords_nao_escolhe_ramo() -> None:
    """C7: empate entre ramos → None (a ordem do dicionário não decide mérito)."""
    from app.services.ai.core.ejc_skill_catalog import _best_keyword_match
    assert _best_keyword_match("x", {"a": ("x",), "b": ("x",)}) is None
    assert _best_keyword_match("x y", {"a": ("x", "y"), "b": ("x",)}) == "a"
    assert _best_keyword_match("nada", {"a": ("x",)}) is None


def test_roteamento_de_areas_sem_agente_dedicado_cai_no_fallback() -> None:
    # EnvironmentalLawAgent/DigitalLGPDAgent/TrafficLawAgent foram retirados na
    # consolidação 38→8 (2026-09-06, escopo definido pelo titular) — sem
    # keyword na mensagem, o domain sozinho cai no fallback determinístico.
    assert classify_intent("chat", "ambiental", "").agente == "CaseAgent"
    assert classify_intent("chat", "digital_lgpd", "").agente == "CaseAgent"
    assert classify_intent("chat", "transito", "").agente == "CaseAgent"
    assert classify_intent("modulo", None, "Abrir o módulo").agente == "EJCCoordinatorAgent"


def test_rota_compartilhada_resolve_para_modulo_canonico() -> None:
    """Regressão da onda 2 (victory-vault removido em 2026-09-05, CORTE-3): a
    rota /inteligencia?tab=conhecimento resolve para o módulo CANÔNICO."""
    from app.services.ai.core.ejc_skill_catalog import MODULE_ALIASES, _normalize

    assert MODULE_ALIASES[_normalize("/inteligencia?tab=conhecimento")] == "conhecimento"
    # Chaves e nomes continuam resolvendo para si mesmos.
    assert MODULE_ALIASES["conhecimento"] == "conhecimento"
