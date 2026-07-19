# ── app/services/ai/provider_registry.py ─────────────────────────────────────
# REGISTRO ÚNICO de provedores de IA do EJC (achado da revisão 2026-07-19).
#
# Antes, a mesma lista de provedores vivia hardcoded em 4+ pontos (ai_gateway,
# provider_policy, adversarial, ai_skill_service) e a regra de elegibilidade
# estava duplicada byte a byte em dois módulos — cada provedor novo exigia
# atualizar todos em lockstep (a Maritaca quase ficou de fora por isso).
#
# Este módulo é decisão pura (nenhuma chamada de rede/modelo):
#   • PROVIDERS_SUPORTADOS — ordem canônica de fallback (usada quando um
#     provedor não aparece em AI_PROVIDER_PRIORITY);
#   • PROVIDERS_EXTERNOS  — processam dados FORA do VPS → barreira LGPD
#     obrigatória (pseudonimização/mascaramento no ai_gateway);
#   • provider_elegivel() — habilitação + chave + kill-switch de soberania.
#
# Para ADICIONAR um provedor: registrar aqui (tupla + conjunto externo se for o
# caso + ramo de elegibilidade), criar o módulo em services/providers/ e o
# dispatch em ai_gateway._chamar_provedor. Nada mais precisa de lista nova.
from __future__ import annotations

from app.core.config import get_settings

# Ordem canônica: local primeiro; entre externos, Maritaca (Sabiá, PT-BR
# jurídico) antes do Groq (generalista). AI_PROVIDER_PRIORITY sobrepõe.
PROVIDERS_SUPORTADOS: tuple[str, ...] = ("ollama", "anthropic", "maritaca", "groq")

# Provedores que processam dados FORA do VPS → exigem sanitização (LGPD).
PROVIDERS_EXTERNOS: frozenset[str] = frozenset({"anthropic", "groq", "maritaca"})


def provider_elegivel(provider: str) -> bool:
    """Regra ÚNICA de elegibilidade por provedor (habilitação + chave +
    kill-switch AI_EXTERNAL_PROVIDERS_ALLOWED para destinos externos)."""
    s = get_settings()
    if provider == "ollama":
        return bool(s.OLLAMA_ENABLED)
    if provider == "anthropic":
        return bool(
            s.ANTHROPIC_ENABLED and s.ANTHROPIC_API_KEY
            and s.AI_EXTERNAL_PROVIDERS_ALLOWED
        )
    if provider == "groq":
        return bool(s.GROQ_API_KEY and s.AI_EXTERNAL_PROVIDERS_ALLOWED)
    if provider == "maritaca":
        return bool(
            s.MARITACA_ENABLED and s.MARITACA_API_KEY
            and s.AI_EXTERNAL_PROVIDERS_ALLOWED
        )
    return False
