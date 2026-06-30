# ── app/services/providers/anthropic_provider.py ─────────────────────────────
# Provider Anthropic (Claude) — mesmo contrato de groq_provider/ollama_provider:
#   chat(messages, model, temperature, max_tokens) -> (texto, usage_dict)
# Converte mensagens formato OpenAI [{role,content}] → API Anthropic (system separado).
# Cliente lazy: só inicializa quando há ANTHROPIC_API_KEY. Sem chave → erro claro
# (o gateway faz fallback para Groq na cadeia).
from __future__ import annotations
import os
import asyncio

_client = None
_DEFAULT = os.getenv("ANTHROPIC_MODEL_RAPIDO", "claude-haiku-4-5-20251001")


def _get_client():
    global _client
    if _client is None:
        import anthropic  # import tardio: só quando realmente usado
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
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
    return bool(os.getenv("ANTHROPIC_API_KEY", ""))


async def chat(messages: list[dict], model: str | None,
               temperature: float, max_tokens: int) -> tuple[str, dict]:
    system, conv = _split_system(messages)
    mdl = model or _DEFAULT

    def _call():
        client = _get_client()
        kwargs = dict(model=mdl, max_tokens=max_tokens, temperature=temperature, messages=conv)
        if system:
            kwargs["system"] = system
        return client.messages.create(**kwargs)

    # SDK síncrono → roda em thread para não bloquear o event loop.
    resp = await asyncio.to_thread(_call)
    texto = resp.content[0].text if resp.content else ""
    usage = {
        "model": mdl,
        "input_tokens": getattr(resp.usage, "input_tokens", None),
        "output_tokens": getattr(resp.usage, "output_tokens", None),
    }
    return texto, usage
