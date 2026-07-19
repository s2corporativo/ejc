from __future__ import annotations


def test_registry_respeita_kill_switch(monkeypatch):
    from app.core.config import get_settings
    from app.services.ai.provider_registry import PROVIDERS_EXTERNOS, provider_elegivel

    settings = get_settings()
    monkeypatch.setattr(settings, "AI_EXTERNAL_PROVIDERS_ALLOWED", False)
    monkeypatch.setattr(settings, "ANTHROPIC_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "x")
    monkeypatch.setattr(settings, "MARITACA_ENABLED", True)
    monkeypatch.setattr(settings, "MARITACA_API_KEY", "x")

    assert all(not provider_elegivel(provider) for provider in PROVIDERS_EXTERNOS)


def test_gateway_continua_fail_closed(monkeypatch):
    from app.main import app  # noqa: F401
    from app.core.config import get_settings
    from app.services import ai_gateway

    settings = get_settings()
    monkeypatch.setattr(settings, "AI_EXTERNAL_PROVIDERS_ALLOWED", False)
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)
    assert ai_gateway._resolver_cadeia("analise_juridica", None, None) == []
