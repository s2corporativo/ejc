# ── app/services/providers/ollama_provider.py ────────────────────────────────
# Provedor Ollama — modelos locais (DeepSeek R1, Qwen, Gemma, Mistral, Llama).
# Comunicação via API REST do Ollama (httpx, já presente no projeto).
# Soberania de dados: NENHUM dado sai do servidor.
from __future__ import annotations
import json
import logging
from typing import AsyncGenerator

import httpx
from app.core.config import get_settings

logger = logging.getLogger("ejc.ai.ollama")
settings = get_settings()

# Cache: modelos disponíveis no servidor Ollama atual
_modelos_cache: list[str] | None = None


async def modelos_disponiveis() -> list[str]:
    """Lista os modelos instalados no Ollama (ex: ['qwen2.5:14b', 'gemma3:9b'])."""
    global _modelos_cache
    if _modelos_cache is not None:
        return _modelos_cache
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            r.raise_for_status()
            _modelos_cache = [m["name"] for m in r.json().get("models", [])]
            return _modelos_cache
    except Exception as e:
        logger.debug(f"Ollama indisponível: {e}")
        return []


def _invalidar_cache():
    global _modelos_cache
    _modelos_cache = None


async def chat(
    messages: list[dict],
    model: str,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    timeout: int | None = None,
) -> tuple[str, dict]:
    """
    Envia mensagens ao modelo local via Ollama /api/chat.
    Retorna (resposta_texto, usage_dict).
    Levanta RuntimeError se o modelo não estiver disponível.
    """
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    to = timeout or settings.OLLAMA_TIMEOUT
    try:
        async with httpx.AsyncClient(timeout=to) as c:
            r = await c.post(f"{settings.OLLAMA_BASE_URL}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
            texto = data.get("message", {}).get("content", "")
            usage = {
                "input_tokens":  data.get("prompt_eval_count"),
                "output_tokens": data.get("eval_count"),
                "model": model,
                "provider": "ollama",
                "duracao_s": round(data.get("total_duration", 0) / 1e9, 1),
            }
            return texto, usage
    except httpx.TimeoutException:
        raise RuntimeError(f"Ollama timeout ({to}s) — modelo {model} muito lento")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"Ollama HTTP {e.response.status_code} — {model}")
    except Exception as e:
        raise RuntimeError(f"Ollama indisponível: {e}")


async def health() -> bool:
    """True se o Ollama está rodando e tem ao menos um modelo instalado."""
    modelos = await modelos_disponiveis()
    return len(modelos) > 0
