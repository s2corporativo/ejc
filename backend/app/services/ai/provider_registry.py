# ── app/services/ai/provider_registry.py ─────────────────────────────────────
from __future__ import annotations

from app.core.config import get_settings

PROVIDERS_SUPORTADOS: tuple[str, ...] = ("ollama", "anthropic", "maritaca", "groq")
PROVIDERS_EXTERNOS: frozenset[str] = frozenset({"anthropic", "groq", "maritaca"})


def provider_elegivel(provider: str) -> bool:
    """Fonte única de habilitação, credencial e kill-switch por provedor."""
    s = get_settings()
    if provider == "ollama":
        return bool(s.OLLAMA_ENABLED)
    if provider == "anthropic":
        return bool(
            s.ANTHROPIC_ENABLED
            and s.ANTHROPIC_API_KEY
            and s.AI_EXTERNAL_PROVIDERS_ALLOWED
        )
    if provider == "groq":
        return bool(s.GROQ_API_KEY and s.AI_EXTERNAL_PROVIDERS_ALLOWED)
    if provider == "maritaca":
        return bool(
            s.MARITACA_ENABLED
            and s.MARITACA_API_KEY
            and s.AI_EXTERNAL_PROVIDERS_ALLOWED
        )
    return False
