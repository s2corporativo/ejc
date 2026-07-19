# ── app/services/ai/provider_registry_runtime.py ──────────────────────────────
from __future__ import annotations

import logging

from app.services.ai.provider_registry import (
    PROVIDERS_EXTERNOS,
    PROVIDERS_SUPORTADOS,
    provider_elegivel,
)

logger = logging.getLogger("ejc.ai.provider_registry")
_INSTALADO = False


def instalar() -> None:
    global _INSTALADO
    if _INSTALADO:
        return

    from app.services import ai_gateway, ai_skill_service
    from app.services.ai import adversarial, provider_policy

    ai_gateway._PROVIDERS_EXTERNOS = PROVIDERS_EXTERNOS
    ai_gateway._PROVIDERS_SUPORTADOS = PROVIDERS_SUPORTADOS
    ai_gateway._provider_elegivel = provider_elegivel

    provider_policy.PROVIDERS_EXTERNOS = PROVIDERS_EXTERNOS
    provider_policy.PROVIDERS_SUPORTADOS = PROVIDERS_SUPORTADOS
    provider_policy.AIProviderPolicy._elegivel = staticmethod(provider_elegivel)

    adversarial._PROVIDERS_CONHECIDOS = PROVIDERS_SUPORTADOS
    ai_skill_service._ENGINE_PROVIDER = {p: p for p in PROVIDERS_SUPORTADOS}

    _INSTALADO = True
    logger.info("ProviderRegistry único conectado ao runtime")
