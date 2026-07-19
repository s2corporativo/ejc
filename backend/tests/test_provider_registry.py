from __future__ import annotations


def test_registry_externos_sao_suportados():
    from app.services.ai.provider_registry import PROVIDERS_EXTERNOS, PROVIDERS_SUPORTADOS
    assert PROVIDERS_EXTERNOS <= set(PROVIDERS_SUPORTADOS)
    assert [p for p in PROVIDERS_SUPORTADOS if p not in PROVIDERS_EXTERNOS] == ["ollama"]


def test_runtime_compartilha_registro():
    from app.main import app  # noqa: F401
    from app.services import ai_gateway, ai_skill_service
    from app.services.ai import adversarial, provider_policy, provider_registry

    assert ai_gateway._PROVIDERS_EXTERNOS is provider_registry.PROVIDERS_EXTERNOS
    assert ai_gateway._PROVIDERS_SUPORTADOS is provider_registry.PROVIDERS_SUPORTADOS
    assert provider_policy.PROVIDERS_EXTERNOS is provider_registry.PROVIDERS_EXTERNOS
    assert adversarial._PROVIDERS_CONHECIDOS is provider_registry.PROVIDERS_SUPORTADOS
    assert ai_skill_service._ENGINE_PROVIDER == {
        p: p for p in provider_registry.PROVIDERS_SUPORTADOS
    }


def test_kill_switch_bloqueia_externos(monkeypatch):
    from app.core.config import get_settings
    from app.services.ai.provider_registry import PROVIDERS_EXTERNOS, provider_elegivel

    settings = get_settings()
    monkeypatch.setattr(settings, "AI_EXTERNAL_PROVIDERS_ALLOWED", False)
    monkeypatch.setattr(settings, "ANTHROPIC_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "x")
    monkeypatch.setattr(settings, "MARITACA_ENABLED", True)
    monkeypatch.setattr(settings, "MARITACA_API_KEY", "x")
    assert all(not provider_elegivel(p) for p in PROVIDERS_EXTERNOS)


def test_gateway_permanece_fail_closed(monkeypatch):
    from app.main import app  # noqa: F401
    from app.core.config import get_settings
    from app.services import ai_gateway

    settings = get_settings()
    monkeypatch.setattr(settings, "AI_EXTERNAL_PROVIDERS_ALLOWED", False)
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)
    assert ai_gateway._resolver_cadeia("analise_juridica", None, None) == []
