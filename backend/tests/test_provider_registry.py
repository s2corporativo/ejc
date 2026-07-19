"""Registro único de provedores (provider_registry) — trava contra drift.

Garante que gateway, policy e adversarial consomem a MESMA fonte de verdade —
o bug que a Maritaca quase reintroduziu (lista hardcoded esquecida num ponto).
"""
from __future__ import annotations

from app.core.config import get_settings
from app.services import ai_gateway
from app.services.ai import adversarial, provider_policy, provider_registry


def test_gateway_e_policy_compartilham_o_registro():
    assert ai_gateway._PROVIDERS_EXTERNOS is provider_registry.PROVIDERS_EXTERNOS
    assert provider_policy.PROVIDERS_EXTERNOS is provider_registry.PROVIDERS_EXTERNOS
    assert ai_gateway._PROVIDERS_SUPORTADOS is provider_registry.PROVIDERS_SUPORTADOS
    assert adversarial._PROVIDERS_CONHECIDOS is provider_registry.PROVIDERS_SUPORTADOS


def test_externos_sao_subconjunto_dos_suportados():
    assert provider_registry.PROVIDERS_EXTERNOS <= set(provider_registry.PROVIDERS_SUPORTADOS)


def test_ollama_e_o_unico_local():
    externos = provider_registry.PROVIDERS_EXTERNOS
    locais = [p for p in provider_registry.PROVIDERS_SUPORTADOS if p not in externos]
    assert locais == ["ollama"]


def test_elegibilidade_e_a_mesma_no_gateway_e_na_policy(monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "MARITACA_ENABLED", True, raising=False)
    monkeypatch.setattr(st, "MARITACA_API_KEY", "k", raising=False)
    monkeypatch.setattr(st, "AI_EXTERNAL_PROVIDERS_ALLOWED", True, raising=False)
    for p in provider_registry.PROVIDERS_SUPORTADOS:
        assert ai_gateway._provider_elegivel(p) is provider_policy.AIProviderPolicy._elegivel(p)
        assert ai_gateway._provider_elegivel(p) is provider_registry.provider_elegivel(p)


def test_kill_switch_derruba_todos_os_externos(monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "AI_EXTERNAL_PROVIDERS_ALLOWED", False, raising=False)
    monkeypatch.setattr(st, "ANTHROPIC_ENABLED", True, raising=False)
    monkeypatch.setattr(st, "ANTHROPIC_API_KEY", "k", raising=False)
    monkeypatch.setattr(st, "GROQ_API_KEY", "k", raising=False)
    monkeypatch.setattr(st, "MARITACA_ENABLED", True, raising=False)
    monkeypatch.setattr(st, "MARITACA_API_KEY", "k", raising=False)
    for p in provider_registry.PROVIDERS_EXTERNOS:
        assert provider_registry.provider_elegivel(p) is False
