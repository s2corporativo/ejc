# ── app/services/providers/anthropic_provider.py ─────────────────────────────
# Provider Anthropic (Claude) — mesmo contrato de groq_provider/ollama_provider:
#   chat(messages, model, temperature, max_tokens) -> (texto, usage_dict)
# Converte mensagens formato OpenAI [{role,content}] → API Anthropic (system separado).
# Cliente lazy: só inicializa quando há ANTHROPIC_API_KEY. Sem chave → erro claro
# (o gateway faz fallback para Groq na cadeia).
#
# API 2026: nos modelos "modernos" (Opus 4.7+, Sonnet 5, Fable/Mythos 5) os
# parâmetros temperature/top_p/top_k foram REMOVIDOS (HTTP 400 se enviados).
# O controle de raciocínio passa a ser thinking adaptativo + output_config.effort.
from __future__ import annotations
import os
import asyncio

from app.core.config import get_settings

_client = None

# Modelos que usam a superfície nova da API (sem temperature; adaptive thinking).
_MODERN_PREFIXES = (
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-sonnet-5",
    "claude-fable-5",
    "claude-mythos-5",
)


def _is_modern(model: str) -> bool:
    return model.startswith(_MODERN_PREFIXES)


def _api_key() -> str:
    """Chave Anthropic: prioriza a Settings tipada (.env carregado pelo pydantic);
    cai para os.getenv (ex.: docker env_file exporta no ambiente do processo)."""
    return get_settings().ANTHROPIC_API_KEY or os.getenv("ANTHROPIC_API_KEY", "")


def _default_model() -> str:
    return get_settings().ANTHROPIC_MODEL_RAPIDO or "claude-haiku-4-5-20251001"


def _get_client():
    global _client
    if _client is None:
        import anthropic  # import tardio: só quando realmente usado
        api_key = _api_key()
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY não configurada")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """Separa mensagens 'system' (Anthropic usa param próprio) das demais."""
    system_parts, conv = [], []
    for m in messages or []:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            if content:
                system_parts.append(content)
        else:
            conv.append({"role": "assistant" if role == "assistant" else "user",
                         "content": content})
    if not conv:  # Anthropic exige ao menos 1 mensagem de usuário
        conv = [{"role": "user", "content": "(sem conteúdo)"}]
    return "\n\n".join(system_parts), conv


async def health() -> bool:
    return bool(_api_key())


async def chat(messages: list[dict], model: str | None,
               temperature: float, max_tokens: int) -> tuple[str, dict]:
    """Mesmo contrato dos demais providers. Nos modelos modernos (Opus 4.7+,
    Sonnet 5, Fable 5) `temperature` é IGNORADA — a API a rejeita com 400; o
    raciocínio é controlado por thinking adaptativo + effort (ANTHROPIC_EFFORT)."""
    system, conv = _split_system(messages)
    mdl = model or _default_model()

    def _call():
        client = _get_client()
        kwargs = dict(model=mdl, messages=conv)
        if system:
            # Prompt caching: bloco system com cache_control — leituras repetidas
            # do mesmo prefixo (system prompt + base legal + RAG do caso) custam
            # ~10% do preço. Prefixos curtos apenas não cacheiam (sem erro).
            kwargs["system"] = [{
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }]
        if _is_modern(mdl):
            effort = (get_settings().ANTHROPIC_EFFORT or "high").lower()
            # O thinking adaptativo consome o MESMO budget de max_tokens da
            # resposta → piso de 8192 para o texto não truncar no meio.
            kwargs["max_tokens"] = max(max_tokens, 8192)
            # extra_body: compatível com qualquer versão do SDK python (evita
            # TypeError em SDKs que ainda não tipam thinking/output_config).
            kwargs["extra_body"] = {
                "thinking": {"type": "adaptive"},
                "output_config": {"effort": effort},
            }
        else:
            # Modelos legados (Haiku 4.5, Sonnet/Opus 4.6 e anteriores): a
            # temperature continua válida; effort não é suportado (erra no Haiku).
            kwargs["max_tokens"] = max_tokens
            kwargs["temperature"] = temperature
        return client.messages.create(**kwargs)

    # SDK síncrono → roda em thread para não bloquear o event loop.
    resp = await asyncio.to_thread(_call)
    # A resposta pode conter blocos "thinking" antes do texto — nunca ler
    # content[0] às cegas: concatena apenas os blocos de tipo "text".
    texto = "".join(
        getattr(b, "text", "") for b in (resp.content or [])
        if getattr(b, "type", "") == "text"
    )
    u = getattr(resp, "usage", None)
    usage = {
        "model": mdl,
        "input_tokens": getattr(u, "input_tokens", None),
        "output_tokens": getattr(u, "output_tokens", None),
        # Transparência de custo do prompt caching (leitura ≈ 10% do preço).
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", None),
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", None),
    }
    return texto, usage
