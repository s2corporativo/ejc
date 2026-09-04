"""Invariantes do Núcleo Único de IA (IA-04 Fase 4).

Trava regressões silenciosas ao adicionar/alterar agentes, prompts, tarefas e
roteamento: todo alias resolve, todo prompt_key existe, toda tarefa tem config,
toda skill existe, e agentes jurídicos com afirmação normativa exigem fonte.
"""
from app.services.system_prompts import SYSTEM_PROMPTS, TarefaIA, get_configuracao
from app.services.system_prompts.router import CONFIGURACOES
from app.services.ai.core.agent_registry import AGENT_REGISTRY
from app.services.ai.core.skill_registry import SKILL_REGISTRY
from app.services.ai.core.intent_classifier import (
    TASK_TYPE_PARA_AGENTE, _KEYWORDS_PARA_AGENTE, classify_intent,
)

# Agentes jurídicos que produzem afirmação normativa (lei/súmula/precedente) e,
# portanto, DEVEM exigir fonte e validar citações. Técnicos e de comunicação
# ficam de fora por natureza (não citam jurisprudência).
_AGENTES_NORMATIVOS = {
    "ConsumerLawAgent", "TaxLawAgent", "SocialSecurityAgent", "CorporateLawAgent",
    "LaborLawAgent", "CriminalLawAgent", "FamilyLawAgent",
    "AdministrativeLawAgent", "SuccessionLawAgent", "RealEstateLawAgent",
    "ConstitutionalLawAgent", "SpecialCourtsAgent", "CivilLawAgent",
    "TrafficLawAgent", "HealthLawAgent", "MedicalLawAgent", "AgrarianLawAgent",
    "AgribusinessLawAgent", "ElectoralLawAgent", "InternationalLawAgent",
    "ContractLawAgent",
    "RAGResearchAgent", "LegalWritingAgent", "JurimetryAgent",
    # I5/B5 (análise E2E 03/09): prazo (CPC/CLT/regimento) e base legal
    # LGPD/OAB são afirmação normativa — exigem fonte e gate de citações.
    "ProcessAgent", "SecurityLGPDOABAgent",
}

# TarefaIA que correspondem a uma ÁREA jurídica com prompt DEDICADO. Cada uma
# deve resolver para um prompt_key próprio em SYSTEM_PROMPTS — nunca o genérico
# "analise_caso" (isso caracterizaria uma "entrada morta": tarefa de área que,
# na prática, cai no prompt genérico e perde a especialização).
_TAREFAS_DE_AREA = {
    TarefaIA.AMBIENTAL, TarefaIA.TRABALHISTA, TarefaIA.CRIMINAL, TarefaIA.FAMILIA,
    TarefaIA.ADMINISTRATIVO, TarefaIA.SUCESSOES, TarefaIA.IMOBILIARIO,
    TarefaIA.CONSTITUCIONAL, TarefaIA.JUIZADOS, TarefaIA.CIVEL,
}


def test_todo_alias_aponta_para_agente_registrado():
    for alias, nome in TASK_TYPE_PARA_AGENTE.items():
        assert nome in AGENT_REGISTRY, f"alias '{alias}' → agente inexistente '{nome}'"


def test_toda_keyword_aponta_para_agente_registrado():
    for _palavras, nome in _KEYWORDS_PARA_AGENTE:
        assert nome in AGENT_REGISTRY, f"keyword → agente inexistente '{nome}'"


def test_todo_prompt_key_existe_em_system_prompts():
    for nome, ag in AGENT_REGISTRY.items():
        assert ag.prompt_key in SYSTEM_PROMPTS, \
            f"{nome}: prompt_key '{ag.prompt_key}' ausente em SYSTEM_PROMPTS"


def test_toda_tarefa_padrao_tem_configuracao():
    for nome, ag in AGENT_REGISTRY.items():
        assert ag.tarefa_padrao in CONFIGURACOES, \
            f"{nome}: TarefaIA '{ag.tarefa_padrao}' sem entrada em CONFIGURACOES"


def test_toda_skill_de_agente_existe_no_registry():
    for nome, ag in AGENT_REGISTRY.items():
        for skill in ag.skills:
            assert skill in SKILL_REGISTRY, \
                f"{nome}: skill '{skill}' ausente em SKILL_REGISTRY"


def test_agentes_normativos_exigem_fonte_e_validam_citacoes():
    for nome in _AGENTES_NORMATIVOS:
        ag = AGENT_REGISTRY[nome]
        assert ag.exige_fonte, f"{nome} deveria exigir fonte (afirmação normativa)"
        assert "validate_citations" in ag.skills, \
            f"{nome} deveria ter 'validate_citations' no pipeline"
        assert "retrieve_rag_sources" in ag.skills, \
            f"{nome} deveria recuperar fontes do RAG antes de afirmar"


def test_classify_intent_sempre_roteia_para_agente_valido():
    # Nunca falha: task/domain desconhecidos e mensagem vazia caem no default.
    amostras = [
        ("", None, ""),
        ("desconhecido_xyz", "inexistente", "texto qualquer"),
        ("consumidor", None, ""),
        ("report", "tributario", ""),
    ]
    for task, dom, msg in amostras:
        r = classify_intent(task_type=task, domain=dom, mensagem=msg)
        assert r.agente in AGENT_REGISTRY
        assert r.tarefa in CONFIGURACOES


def test_prompt_key_das_novas_areas_carrega_barreira():
    # Prompts das áreas especializadas devem embutir a identidade/regras (BASE_PROMPT).
    for key in ("consumidor", "tributario", "previdenciario", "empresarial",
                "trabalhista", "criminal", "familia",
                "administrativo", "sucessoes", "imobiliario",
                "constitucional", "juizados", "civel",
                "transito", "saude", "medico", "agrario",
                "agronegocio", "eleitoral", "internacional", "contratual"):
        texto = SYSTEM_PROMPTS[key]
        assert "IDENTIDADE" in texto and "RASCUNHO" in texto.upper(), \
            f"prompt '{key}' sem barreira anti-alucinação/aviso de rascunho"


def test_tarefa_de_area_nao_cai_no_prompt_generico():
    # Blinda a classe de bug "entrada morta": toda TarefaIA de ÁREA jurídica
    # resolve para um prompt_key REAL em SYSTEM_PROMPTS e NÃO para o genérico
    # "analise_caso" (que perderia a especialização por área).
    for tarefa in _TAREFAS_DE_AREA:
        cfg = get_configuracao(tarefa)
        assert cfg.prompt_key in SYSTEM_PROMPTS, \
            f"TarefaIA '{tarefa.value}': prompt_key '{cfg.prompt_key}' ausente em SYSTEM_PROMPTS"
        assert cfg.prompt_key != "analise_caso", \
            f"TarefaIA de área '{tarefa.value}' caiu no prompt genérico 'analise_caso'"
        assert cfg.prompt_key == tarefa.value, \
            f"TarefaIA de área '{tarefa.value}': prompt_key '{cfg.prompt_key}' divergente da área"
