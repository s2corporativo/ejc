# ── app/services/providers/maritaca_provider.py ─────────────────────────────
# Provider Maritaca AI (Sabiá) — LLM BRASILEIRA, mesmo contrato dos demais:
#   chat(messages, model, temperature, max_tokens) -> (texto, usage_dict)
#
# API compatível com OpenAI (endpoint {MARITACA_BASE_URL}/chat/completions,
# auth Bearer). Comunicação via httpx (já presente no projeto) — evita nova
# dependência de SDK. Cliente lazy: só exige a chave quando realmente usado;
# sem chave/desabilitado → RuntimeError claro (o gateway faz fallback na cadeia).
#
# Soberania de dados (LGPD): Maritaca é EXTERNO ao VPS (o gateway ainda aplica a
# barreira de sanitização/pseudonimização de PII antes de enviar), porém é
# PROCESSAMENTO NACIONAL — não há transferência internacional (art. 33), ao
# contrário de Anthropic/Groq (EUA). Por isso é a opção externa preferencial
# para conteúdo jurídico.
from __future__ import annotations
import logging

import httpx
from app.core.config import get_settings

logger = logging.getLogger("ejc.ai.maritaca")


def _api_key() -> str:
    return get_settings().MARITACA_API_KEY or ""


def _default_model() -> str:
    return get_settings().MARITACA_MODEL_COMPLEXO or "sabia-4"


async def chat(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    timeout: int | None = None,
) -> tuple[str, dict]:
    """
    Envia mensagens à Maritaca (endpoint OpenAI-compatible) e retorna
    (resposta_texto, usage_dict). Levanta RuntimeError se a API falhar —
    o AI Gateway trata o fallback para o próximo provedor da cadeia.
    """
    settings = get_settings()
    if not settings.MARITACA_ENABLED:
        raise RuntimeError("Provider Maritaca desabilitado (MARITACA_ENABLED=false)")
    api_key = _api_key()
    if not api_key:
        raise RuntimeError("MARITACA_API_KEY não configurada")

    mdl = model or _default_model()
    # Teto DURO de saída — controle de custo independente do chamador.
    mt = min(int(max_tokens or 1024), int(settings.MARITACA_MAX_TOKENS))
    to = timeout or settings.MARITACA_TIMEOUT
    url = f"{settings.MARITACA_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": mdl,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": mt,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=to) as c:
            r = await c.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
    except httpx.TimeoutException:
        raise RuntimeError(f"Maritaca timeout ({to}s) — modelo {mdl} demorou demais")
    except httpx.HTTPStatusError as e:
        # Mensagem CURTA e segura: status apenas, sem corpo (pode conter eco do
        # prompt/detalhe do provedor) e sem a chave.
        raise RuntimeError(f"Maritaca HTTP {e.response.status_code} — {mdl}") from None
    except Exception as e:
        raise RuntimeError(f"Maritaca indisponível: {type(e).__name__}") from None

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Maritaca retornou resposta vazia")
    texto = (choices[0].get("message", {}) or {}).get("content", "") or ""
    if not texto.strip():
        raise RuntimeError("Maritaca retornou conteúdo vazio")
    u = data.get("usage") or {}
    usage = {
        "input_tokens":  u.get("prompt_tokens"),
        "output_tokens": u.get("completion_tokens"),
        "model": data.get("model") or mdl,
        "provider": "maritaca",
    }
    return texto, usage


async def health() -> bool:
    """True se o provider está habilitado e tem chave configurada.

    Não bate a API (evita custo/latência e chamada externa em cada health-check);
    o gateway trata indisponibilidade real via fallback na cadeia — mesmo padrão
    do anthropic_provider."""
    s = get_settings()
    return bool(s.MARITACA_ENABLED and _api_key())
