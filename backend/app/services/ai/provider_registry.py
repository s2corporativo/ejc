# ── app/services/ai/provider_registry.py ─────────────────────────────────────
from __future__ import annotations

from app.core.config import get_settings

PROVIDERS_SUPORTADOS: tuple[str, ...] = ("ollama", "anthropic", "maritaca", "groq")
PROVIDERS_EXTERNOS: frozenset[str] = frozenset({"anthropic", "groq", "maritaca"})


def _requisitos(provider: str, s) -> list[tuple[bool, str]]:
    """Requisitos de habilitação por provedor: (satisfeito, motivo_se_faltar).

    Tabela única para as duas perguntas do operador: "posso usar?" e, quando não,
    "o que exatamente falta?". Antes o painel de governança só sabia dizer
    "desabilitado", sem distinguir chave ausente de flag desligada ou de
    kill-switch global (auditoria de provedores, 18/08).
    """
    # Kill-switch GLOBAL (AUD27-P0-1): AI_ENABLED desliga a IA inteira e vale
    # para TODO provedor, inclusive o local. Faltava aqui — e como esta tabela é
    # a fonte única de elegibilidade, quem chega ao gateway pelo caminho oficial
    # (`/ai/core/*` → orchestrator.run → ai_gateway.chat → _provider_elegivel)
    # nunca consultava a flag: desligar a IA pelo kill-switch documentado não
    # impedia a geração no Núcleo Único. `ia_disponivel()` já checava, mas era
    # chamada por adesão voluntária de três routers, não pelo gateway.
    global_ok = (
        bool(s.AI_ENABLED),
        "kill-switch global de IA desligado (AI_ENABLED=false)",
    )
    externo_ok = (
        bool(s.AI_EXTERNAL_PROVIDERS_ALLOWED),
        "kill-switch de provedores externos ligado (AI_EXTERNAL_PROVIDERS_ALLOWED=false)",
    )
    if provider == "ollama":
        return [global_ok, (bool(s.OLLAMA_ENABLED), "OLLAMA_ENABLED=false")]
    if provider == "anthropic":
        return [
            global_ok,
            (bool(s.ANTHROPIC_ENABLED), "ANTHROPIC_ENABLED=false"),
            (bool(s.ANTHROPIC_API_KEY), "ANTHROPIC_API_KEY ausente"),
            externo_ok,
        ]
    if provider == "groq":
        return [
            global_ok,
            (bool(s.GROQ_ENABLED), "GROQ_ENABLED=false"),
            (bool(s.GROQ_API_KEY), "GROQ_API_KEY ausente"),
            externo_ok,
        ]
    if provider == "maritaca":
        return [
            global_ok,
            (bool(s.MARITACA_ENABLED), "MARITACA_ENABLED=false"),
            (bool(s.MARITACA_API_KEY), "MARITACA_API_KEY ausente"),
            externo_ok,
        ]
    return [(False, f"provedor não suportado: {provider}")]


def provider_elegivel(provider: str) -> bool:
    """Fonte única de habilitação, credencial e kill-switch por provedor."""
    return all(ok for ok, _ in _requisitos(provider, get_settings()))


def motivo_inelegivel(provider: str) -> str | None:
    """O que falta para o provedor ficar elegível (None se já está)."""
    faltas = [motivo for ok, motivo in _requisitos(provider, get_settings()) if not ok]
    return "; ".join(faltas) if faltas else None
