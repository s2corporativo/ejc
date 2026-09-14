from __future__ import annotations

from app.services.ai.core.ejc_skill_catalog import resolve_native_skill_plan

from .contracts import LegalBrainPlan
from .issue_engine import identify_legal_issues
from .research_loop import build_research_plan


def build_legal_brain_plan(
    *,
    task_type: str,
    message: str,
    domain: str | None = None,
    module_key: str | None = None,
    surface: str | None = None,
    max_research_cycles: int = 3,
) -> LegalBrainPlan:
    """Compõe um plano determinístico sem duplicar o núcleo de IA.

    O catálogo nativo continua sendo a fonte canônica de skills. Esta função
    apenas acrescenta questões e plano de pesquisa estruturado para o mesmo
    ``SingleAICoreOrchestrator`` consumir em shadow/active mode.
    """

    native_plan = resolve_native_skill_plan(
        task_type=task_type,
        domain=domain,
        message=message,
        module_key=module_key,
        surface=surface,
    )
    area = native_plan.legal_area or domain
    issues = identify_legal_issues(message, area=area)
    plans = tuple(
        build_research_plan(issue, max_cycles=max_research_cycles)
        for issue in issues
    )

    warnings: list[str] = []
    if not native_plan.legal_area:
        warnings.append("area_juridica_nao_confirmada")
    if any(issue.key == "saneamento_inicial" for issue in issues):
        warnings.append("questao_juridica_requer_saneamento")

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
        },
    )
