from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.services.ai.core.agent_registry import AGENT_REGISTRY
from app.services.ai.core.task_policy_catalog import (
    effective_intelligence,
    effective_rag,
    list_task_policies,
    resolve_task_policy,
)


def test_catalog_covers_every_agent_with_unique_canonical_task():
    policies = list_task_policies()
    assert len(policies) == len(AGENT_REGISTRY)
    assert {policy["agent"] for policy in policies} == set(AGENT_REGISTRY)
    canonical = [policy["canonical_task"] for policy in policies]
    assert len(canonical) == len(set(canonical))
    assert all(policy["hitl_required"] is True for policy in policies)
    assert all(policy["canonical_endpoint"] == "/api/v1/ai/core/task" for policy in policies)


def test_public_catalog_never_exposes_prompt_model_key_or_handler():
    forbidden = {"prompt", "prompt_key", "model", "provider", "key", "handler"}
    for policy in list_task_policies():
        assert forbidden.isdisjoint(policy)
        serialized = str(policy).lower()
        assert "api_key" not in serialized
        assert "system_prompt" not in serialized


def test_research_forces_rag_but_other_agents_preserve_explicit_choice():
    research = resolve_task_policy("RAGResearchAgent")
    document = resolve_task_policy("DocumentAgent")
    assert research.rag_policy == "required"
    assert effective_rag(False, research) is True
    assert document.rag_policy == "optional"
    assert effective_rag(False, document) is False


def test_intelligence_floor_is_applied_and_invalid_value_returns_422():
    writing = resolve_task_policy("LegalWritingAgent")
    document = resolve_task_policy("DocumentAgent")
    assert writing.minimum_intelligence == "alto"
    assert effective_intelligence("padrao", writing) == "alto"
    assert effective_intelligence("maximo", writing) == "maximo"
    assert effective_intelligence("padrao", document) == "padrao"
    with pytest.raises(HTTPException) as exc:
        effective_intelligence("turbo-inexistente", writing)
    assert exc.value.status_code == 422


def test_sensitive_and_restricted_agents_are_explicit():
    assert resolve_task_policy("CriminalLawAgent").sensitivity == "confidential"
    assert resolve_task_policy("BankForensicsAgent").sensitivity == "confidential"
    assert resolve_task_policy("RepairAgent").sensitivity == "restricted"
    assert resolve_task_policy("UIUXAgent").sensitivity == "internal"


def test_orchestrator_applies_effective_policy_without_replacing_original_task_type():
    source = (
        Path(__file__).parents[1]
        / "app/services/ai/core/orchestrator.py"
    ).read_text(encoding="utf-8")
    assert "resolve_task_policy(agente.nome)" in source
    assert "usar_rag=usar_rag_efetivo" in source
    assert "nivel_inteligencia=nivel_inteligencia_efetivo" in source
    assert '"task_type": task_type' in source
    assert '"task_type_canonico": task_policy.canonical_task' in source
    assert '"governanca_ia": task_policy.public_dict()' in source


def test_app_mounts_policy_introspection_inside_ai_core():
    from app.main import app

    paths = {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
    }
    assert "/api/ai/core/task-policies" in paths
    assert "/api/ai/core/task-policies/{agent_name}" in paths
