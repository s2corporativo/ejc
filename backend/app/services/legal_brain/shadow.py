from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from app.services.ai.core.orchestrator import orchestrator

from .brain import build_legal_brain_plan
from .contracts import LegalBrainPlan

# Logger dedicado: telemetria agregada de divergência (sem PII, sem texto).
telemetry_logger = logging.getLogger("ejc.legal_brain.shadow")

REPORT_VERSION = 1
_GAP_KEY = "saneamento_inicial"


def _count(value: Any) -> int:
    return len(value) if isinstance(value, (list, tuple)) else 0


def compare_shadow(
    legacy_response: Mapping[str, Any] | None, plan: LegalBrainPlan
) -> dict[str, Any]:
    """Relatório de divergência determinístico, apenas com contagens e chaves.

    Nunca copia texto do usuário nem da resposta legada: só chaves estáticas do
    plano (issue keys, códigos de warning) e inteiros/booleanos.
    """

    legacy = legacy_response if isinstance(legacy_response, Mapping) else {}
    legacy_fontes = _count(legacy.get("fontes"))
    legacy_alertas = _count(legacy.get("alertas"))

    issue_keys = sorted({issue.key for issue in plan.issues})
    gap_issue_keys = [k for k in issue_keys if k == _GAP_KEY]
    plan_requires_evidence = any(
        issue.required_evidence for issue in plan.issues
    ) or any(rp.steps for rp in plan.research_plans)

    divergences: list[str] = []
    if plan_requires_evidence and legacy_fontes == 0:
        divergences.append("legado_sem_fontes_plano_exige_evidencia")
    if plan.warnings and legacy_alertas == 0:
        divergences.append("legado_sem_alertas_plano_alerta")
    if gap_issue_keys:
        divergences.append("plano_marca_lacuna_de_saneamento")

    return {
        "version": REPORT_VERSION,
        "area": plan.area,
        "issues_count": len(plan.issues),
        "issue_keys": issue_keys,
        "research_gap_count": len(gap_issue_keys),
        "research_plans_count": len(plan.research_plans),
        "plan_warning_codes": sorted(plan.warnings),
        "plan_requires_evidence": plan_requires_evidence,
        "legacy_fontes_count": legacy_fontes,
        "legacy_alertas_count": legacy_alertas,
        "divergences": divergences,
        "diverged": bool(divergences),
    }


def _emit_telemetry(report: dict[str, Any]) -> None:
    telemetry_logger.info("legal_brain_shadow_divergence", extra={"shadow_report": report})


async def run_shadow_ai_task(**kwargs: Any) -> dict[str, Any]:
    """Executa o núcleo único e anexa diagnóstico determinístico opt-in.

    O adapter NÃO altera prompt, contexto, provider, RAG, validação, HITL ou
    AILog do ``SingleAICoreOrchestrator``. O plano do Legal Brain é calculado
    localmente e anexado apenas à resposta deste entrypoint explícito, para QA,
    benchmark e comparação antes da ativação no runtime canônico.
    """

    task_type = str(kwargs.get("task_type") or "")
    mensagem = str(kwargs.get("mensagem") or "")
    domain = kwargs.get("domain")
    params = dict(kwargs.get("params") or {})

    plan: LegalBrainPlan | None
    try:
        plan = build_legal_brain_plan(
            task_type=task_type,
            domain=str(domain) if domain is not None else None,
            message=mensagem,
            module_key=str(params.get("module_key") or "") or None,
            surface=str(params.get("surface") or "") or None,
        )
    except Exception:  # noqa: BLE001 - shadow jamais derruba a resposta legada
        plan = None
        telemetry_logger.warning("legal_brain_shadow_plan_failed", exc_info=True)

    result = await orchestrator.run(**kwargs)
    if plan is None:
        return result

    try:
        enriched = dict(result)
        enriched["legal_brain_shadow"] = plan.to_dict()
        _emit_telemetry(compare_shadow(result, plan))
    except Exception:  # noqa: BLE001 - shadow jamais derruba a resposta legada
        telemetry_logger.warning("legal_brain_shadow_telemetry_failed", exc_info=True)
        return result
    return enriched
