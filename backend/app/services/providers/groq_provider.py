# ── app/services/providers/groq_provider.py ──────────────────────────────────
# Provedor Groq (nuvem) — wraper do SDK oficial groq-python.
# Usado pelo AI Gateway como provedor de nuvem / fallback.
from __future__ import annotations
import logging
from typing import Optional

from groq import AsyncGroq
from app.core.config import get_settings

logger = logging.getLogger("ejc.ai.groq")
settings = get_settings()

_client: Optional[AsyncGroq] = None


def get_client() -> AsyncGroq:
    global _client
    if _client is None:
        if not settings.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY não configurada")
        _client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    return _client


async def chat(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    timeout: int | None = None,
) -> tuple[str, dict]:
    """
    Envia mensagens ao Groq e retorna (resposta_texto, usage_dict).
    Levanta RuntimeError se a API falhar — AI Gateway trata o fallback.
    """
    model = model or settings.GROQ_MODEL
    if len(" ".join(m.get("content", "") for m in messages)) > 20_000:
        model = settings.GROQ_MODEL_LARGE

    client = get_client()
    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout or settings.GROQ_TIMEOUT,
    )
    if not resp.choices:
        raise RuntimeError("Groq retornou resposta vazia")
    texto = resp.choices[0].message.content
    usage = {
        "input_tokens":  resp.usage.prompt_tokens if resp.usage else None,
        "output_tokens": resp.usage.completion_tokens if resp.usage else None,
        "model": model,
        "provider": "groq",
    }
    return texto, usage


async def health() -> bool:
    """Verifica se a API Groq está acessível e a chave é válida."""
    try:
        client = get_client()
        await client.chat.completions.create(
            model=settings.GROQ_MODEL,   # modelo configurado (evita hardcode desatualizado)
            messages=[{"role": "user", "content": "ok"}],
            max_tokens=1,
            timeout=5,
        )
        return True
    except Exception:
        return False
