"""Invariantes do Núcleo Único de IA (IA-04 Fase 4).

Trava regressões silenciosas ao adicionar/alterar agentes, prompts, tarefas e
roteamento: todo alias resolve, todo prompt_key existe, toda tarefa tem config,
toda skill existe, e agentes jurídicos com afirmação normativa exigem fonte.
"""
from app.services.system_prompts import SYSTEM_PROMPTS, TarefaIA
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
    "RAGResearchAgent", "LegalWritingAgent", "JurimetryAgent",
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
                "administrativo", "sucessoes", "imobiliario"):
        texto = SYSTEM_PROMPTS[key]
        assert "IDENTIDADE" in texto and "RASCUNHO" in texto.upper(), \
            f"prompt '{key}' sem barreira anti-alucinação/aviso de rascunho"
