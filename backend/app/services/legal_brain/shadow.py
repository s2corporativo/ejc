from __future__ import annotations

from typing import Any

from app.services.ai.core.orchestrator import orchestrator

from .brain import build_legal_brain_plan


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

    plan = build_legal_brain_plan(
        task_type=task_type,
        domain=str(domain) if domain is not None else None,
        message=mensagem,
        module_key=str(params.get("module_key") or "") or None,
        surface=str(params.get("surface") or "") or None,
    )

    result = await orchestrator.run(**kwargs)
    enriched = dict(result)
    enriched["legal_brain_shadow"] = plan.to_dict()
    return enriched
