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
