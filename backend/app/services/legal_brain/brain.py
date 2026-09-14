from __future__ import annotations

from app.core.taxonomia import normalizar_area
from app.services.ai.core.ejc_skill_catalog import resolve_native_skill_plan

from .area_specializations import resolve_area_specialization
from .contracts import LegalBrainPlan
from .issue_engine import identify_legal_issues
from .research_loop import build_clarification_plan, build_research_plan


def build_legal_brain_plan(
    *,
    task_type: str,
    message: str,
    domain: str | None = None,
    module_key: str | None = None,
    surface: str | None = None,
    max_research_cycles: int = 3,
) -> LegalBrainPlan:
    """Compõe plano determinístico usando apenas fontes canônicas do EJC.

    O catálogo nativo permanece a fonte operacional. Quando uma área canônica
    ainda não possui ``NativeSkillSpec`` próprio, o plano pode apenas REFERENCIAR
    um prompt especializado já existente em ``SYSTEM_PROMPTS``; essa referência
    é shadow/diagnóstica e não injeta prompt no runtime.
    """

    native_plan = resolve_native_skill_plan(
        task_type=task_type,
        domain=domain,
        message=message,
        module_key=module_key,
        surface=surface,
    )
    canonical_requested_area = (
        normalizar_area(domain)
        or normalizar_area(task_type)
        or native_plan.legal_area
    )
    area = canonical_requested_area or native_plan.legal_area or domain
    specialization = resolve_area_specialization(canonical_requested_area)

    issues = identify_legal_issues(message, area=area)
    plans = tuple(
        build_clarification_plan(issue)
        if issue.key == "saneamento_inicial"
        else build_research_plan(issue, max_cycles=max_research_cycles)
        for issue in issues
    )

    warnings: list[str] = []
    if not native_plan.legal_area and specialization is None:
        warnings.append("area_juridica_nao_confirmada")
    if specialization is not None and not native_plan.legal_area:
        warnings.append("area_com_especializacao_existente_ainda_sem_skill_nativa")
    if any(issue.key == "saneamento_inicial" for issue in issues):
        warnings.append("questao_juridica_requer_saneamento")

    specialization_metadata = None
    if specialization is not None:
        specialization_metadata = {
            "area": specialization.area,
            "prompt_key": specialization.prompt_key,
            "inherited_from": specialization.inherited_from,
            "source": specialization.source,
            "requires_human_review": specialization.requires_human_review,
            "runtime_injected": False,
        }

    return LegalBrainPlan(
        area=area,
        issues=issues,
        native_skill_names=native_plan.skill_names,
        research_plans=plans,
        warnings=tuple(warnings),
        metadata={
            "engine": "legal_brain_v1",
            "deterministic": True,
            "requires_human_review": True,
            "area_specialization": specialization_metadata,
        },
    )
