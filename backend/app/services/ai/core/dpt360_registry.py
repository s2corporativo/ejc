"""Registro explícito das competências DPT no Núcleo Único de IA.

A instalação é chamada somente pelo serviço DPT antes de `orchestrator.run`.
Não cria executor, gateway, provider ou política HITL paralelos.
"""
from __future__ import annotations

from app.services.system_prompts import TarefaIA

DPT_SKILL_NAMES = frozenset(
    {
        "build_company_legal_context",
        "apply_dpt_legal_protocol",
        "preflight_legal_consistency",
        "dpt_adversarial_review",
    }
)

_REGISTERED = False


def ensure_dpt360_registered() -> None:
    global _REGISTERED
    if _REGISTERED:
        return

    from app.services.ai.core.agent_registry import AGENT_REGISTRY, AgenteInterno
    from app.services.ai.core.intent_classifier import TASK_TYPE_PARA_AGENTE
    from app.services.ai.core.skill_registry import SKILL_REGISTRY, Skill

    skills = {
        "build_company_legal_context": Skill(
            "build_company_legal_context",
            "Usar projeção minimizada do DPT Legal Twin como contexto empresarial autorizado",
            "client_id + projeção factual já submetida a RBAC/ABAC",
            "contexto empresarial sem PII documental",
            riscos="médio — contexto de cliente; mínimo necessário",
            pre_condicoes="empresa visível no escopo do advogado",
            pos_condicoes="sem CPF/CNPJ pessoal, contato, OCR ou segredo documental",
            handler=None,
        ),
        "apply_dpt_legal_protocol": Skill(
            "apply_dpt_legal_protocol",
            "Estruturar identificação, fatos, evidências, questões, fontes, teses, objeções, riscos, conclusão e HITL",
            "contexto + pergunta do advogado",
            "produto jurídico estruturado sem chain-of-thought livre",
            riscos="alto — mérito jurídico",
            pos_condicoes="rascunho; lacunas e insuficiência probatória explícitas",
            handler=None,
        ),
        "preflight_legal_consistency": Skill(
            "preflight_legal_consistency",
            "Verificar fatos sem prova, citações, vigência, datas, contradições e documentos essenciais",
            "rascunho jurídico + fontes disponíveis",
            "checklist de inconsistências e revisão humana",
            riscos="alto — não substitui conferência profissional",
            pos_condicoes="não corrige nem publica automaticamente",
            handler=None,
        ),
        "dpt_adversarial_review": Skill(
            "dpt_adversarial_review",
            "Submeter teses e conclusão a objeções adversariais antes do HITL",
            "produto jurídico estruturado",
            "objeções, fragilidades e pontos para revisão",
            riscos="alto — crítica de IA não é validação humana",
            pos_condicoes="se crítica indisponível, registrar alerta e manter revisão humana obrigatória",
            handler=None,
        ),
    }
    assert set(skills) == DPT_SKILL_NAMES
    for name, skill in skills.items():
        SKILL_REGISTRY.setdefault(name, skill)

    AGENT_REGISTRY.setdefault(
        "DPTEnterpriseAgent",
        AgenteInterno(
            nome="DPTEnterpriseAgent",
            descricao="DPT Empresarial 360: análise empresarial multidisciplinar, Conselho, diagnóstico e pré-flight.",
            dominios=[
                "dpt360",
                "conselho_empresarial",
                "diagnostico_empresarial",
                "preflight_empresarial",
            ],
            tarefa_padrao=TarefaIA.ANALISE_CASO,
            prompt_key="empresarial",
            exige_fonte=True,
            roles_permitidos=["superadmin", "admin", "socio", "advogado"],
            skills=[
                "classify_intent",
                "build_company_legal_context",
                "apply_dpt_legal_protocol",
                "retrieve_rag_sources",
                "sanitize_for_external_provider",
                "check_pii_residual",
                "select_ai_provider",
                "call_model",
                "validate_citations",
                "preflight_legal_consistency",
                "dpt_adversarial_review",
                "mark_as_draft",
                "log_ai_interaction",
            ],
        ),
    )

    for alias in (
        "dpt360",
        "conselho_empresarial",
        "diagnostico_empresarial",
        "preflight_empresarial",
    ):
        TASK_TYPE_PARA_AGENTE.setdefault(alias, "DPTEnterpriseAgent")

    _REGISTERED = True
