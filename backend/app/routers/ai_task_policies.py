"""Introspecção segura das políticas declarativas do Núcleo Único de IA."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import require_roles
from app.models.user import User
from app.services.ai.core.task_policy_catalog import (
    list_task_policies,
    resolve_task_policy,
)

# Incluído dentro de ai_core.router; prefixo final: /ai/core/task-policies.
router = APIRouter(tags=["IA — Governança de Tarefas"])
_staff = require_roles(["secretaria"])


@router.get("/task-policies")
async def task_policies(cu: User = Depends(_staff)):
    """Metadados internos; nunca prompts, handlers, modelos ou chaves."""
    policies = list_task_policies()
    return {
        "total": len(policies),
        "policies": policies,
        "notice": "Toda saída permanece sujeita à revisão humana obrigatória.",
    }


@router.get("/task-policies/{agent_name}")
async def task_policy(agent_name: str, cu: User = Depends(_staff)):
    try:
        policy = resolve_task_policy(agent_name)
    except KeyError as exc:
        raise HTTPException(404, "Agente não registrado") from exc
    return policy.public_dict()
