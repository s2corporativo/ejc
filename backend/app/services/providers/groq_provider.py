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
    # `content` pode vir None (ex.: resposta cortada por tool-call/filtro de
    # conteúdo) sem `choices` estar vazio — escapava desta guarda e virava
    # "sucesso" com texto vazio, cacheado pelo TTL inteiro sem o fallback
    # nunca disparar (auditoria de segurança, 18/08; mesma classe de bug já
    # corrigida no Ollama na auditoria de provedores, 18/08).
    if not (texto or "").strip():
        raise RuntimeError(f"Groq retornou conteúdo vazio — modelo {model}")
    usage = {
        "input_tokens":  resp.usage.prompt_tokens if resp.usage else None,
        "output_tokens": resp.usage.completion_tokens if resp.usage else None,
        "model": model,
        "provider": "groq",
    }
    return texto, usage


async def transcrever(
    file_bytes: bytes,
    filename: str,
    *,
    language: str = "pt",
    model: str | None = None,
    timeout: int | None = None,
) -> tuple[str, dict]:
    """Transcreve mídia pelo endpoint oficial de Speech-to-Text do Groq.

    O binário vive apenas na memória desta requisição. Consentimento, tamanho,
    extensão e kill-switch de provedor externo são validados no AI Gateway —
    esta camada limita-se ao adaptador do SDK.
    """
    if not file_bytes:
        raise ValueError("Mídia vazia.")
    model = model or settings.GROQ_TRANSCRIPTION_MODEL
    client = get_client()
    resp = await client.audio.transcriptions.create(
        file=(filename, file_bytes),
        model=model,
        language=language,
        response_format="json",
        temperature=0.0,
        timeout=timeout or settings.AUDIO_TRANSCRIPTION_TIMEOUT,
    )
    texto = (getattr(resp, "text", None) or "").strip()
    if not texto:
        raise RuntimeError("Groq retornou transcrição vazia")
    return texto, {"model": model, "provider": "groq", "language": language}


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
