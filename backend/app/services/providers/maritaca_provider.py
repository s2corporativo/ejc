# ── app/services/providers/maritaca_provider.py ──────────────────────────────
# Provider Maritaca (Sabiá) — IA BRASILEIRA, API OpenAI-compatible.
# Mesmo contrato dos demais providers:
#   chat(messages, model, temperature, max_tokens) -> (texto, usage_dict)
# Endpoint OpenAI-compatible: POST {MARITACA_BASE_URL}/chat/completions
# (Authorization: Bearer). Cliente httpx (sem SDK novo). Erros da API são
# re-lançados como RuntimeError CURTO — sem corpo/stack/chave (o gateway faz
# fallback na cadeia).
#
# PLUGÁVEL: MARITACA_ENABLED=false (default) => provider inelegível no gateway,
# comportamento do sistema idêntico ao atual. Provider EXTERNO ao VPS =>
# entra em _PROVIDERS_EXTERNOS no ai_gateway => passa pela MESMA barreira LGPD
# (pseudonimização). Soberania de dados NÃO é o default nem automática: exige
# DUAS coisas juntas — configurar MARITACA_MODEL/MARITACA_MODEL_RAPIDO nas
# variantes "-br-sp" (processam 100% em território nacional) E ligar o guarda de
# boot MARITACA_EXIGIR_SOBERANIA=true (config.py), com DPA — decisão do titular.
# Os defaults "sabia-4"/"sabiazinho-4" NÃO são soberanos.
from __future__ import annotations
import json
import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger("ejc.ai.maritaca")


def _api_key() -> str:
    return get_settings().MARITACA_API_KEY or ""


def _base_url() -> str:
    return (get_settings().MARITACA_BASE_URL or "https://chat.maritaca.ai/api").rstrip("/")


def _default_model() -> str:
    return get_settings().MARITACA_MODEL or "sabia-4"


def _headers() -> dict[str, str]:
    key = _api_key()
    if not key:
        raise RuntimeError("MARITACA_API_KEY não configurada")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


async def _post(payload: dict[str, Any]) -> dict[str, Any]:
    """POST no endpoint OpenAI-compatible; erro curto e seguro (sem vazar chave)."""
    s = get_settings()
    if not s.MARITACA_ENABLED:
        raise RuntimeError("Provider Maritaca desabilitado (MARITACA_ENABLED=false)")
    url = f"{_base_url()}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=float(s.MARITACA_TIMEOUT)) as client:
            resp = await client.post(url, headers=_headers(), json=payload)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code if e.response is not None else None
        raise RuntimeError(
            "Maritaca API falhou (HTTPStatusError"
            + (f", HTTP {status}" if status else "") + ")"
        ) from None
    except httpx.HTTPError as e:
        raise RuntimeError(f"Maritaca API falhou ({type(e).__name__})") from None


def _usage(data: dict[str, Any], model: str) -> dict[str, Any]:
    u = data.get("usage") or {}
    return {
        "model": data.get("model") or model,
        "input_tokens": u.get("prompt_tokens"),
        "output_tokens": u.get("completion_tokens"),
        "provider": "maritaca",
    }


async def chat(messages: list[dict], model: str | None,
               temperature: float, max_tokens: int) -> tuple[str, dict]:
    """Mesmo contrato dos demais providers → (texto, usage)."""
    mdl = model or _default_model()
    payload = {
        "model": mdl,
        "messages": [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in (messages or [])
        ],
        "max_tokens": int(max_tokens or 1024),
        "temperature": float(temperature),
    }
    data = await _post(payload)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Maritaca retornou resposta vazia")
    texto = (choices[0].get("message") or {}).get("content") or ""
    return texto, _usage(data, mdl)


async def chat_tools(messages: list[dict], model: str | None,
                     max_tokens: int, tools: list[dict]) -> dict:
    """Tool-use no formato OpenAI (Chat Completions). Normaliza a saída para o
    MESMO contrato de anthropic_provider.chat_tools:
      {"text", "tool_calls":[{"id","name","input":dict}], "stop_reason", "usage"}
    stop_reason "tool_use" quando o modelo pede ferramenta; senão "end_turn".

    NB: `tools` deve vir no formato OpenAI
    ([{"type":"function","function":{"name","description","parameters"}}]).
    Ainda NÃO é chamado pelo loop agêntico (chat_agentico usa Anthropic); fica
    pronto para o gancho futuro de rotear o agente pela Maritaca (com conversão
    de schema Anthropic->OpenAI no ponto de fiação)."""
    mdl = model or _default_model()
    payload: dict[str, Any] = {
        "model": mdl,
        "messages": messages,
        "max_tokens": int(max_tokens or 1024),
    }
    if tools:
        payload["tools"] = tools
    data = await _post(payload)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Maritaca retornou resposta vazia")
    choice = choices[0]
    msg = choice.get("message") or {}
    finish = choice.get("finish_reason") or ""
    tool_calls: list[dict] = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args or "{}")
            except json.JSONDecodeError:
                args = {"_raw": args}
        tool_calls.append({
            "id": tc.get("id") or "",
            "name": fn.get("name") or "",
            "input": args or {},
        })
    if tool_calls:
        stop_reason = "tool_use"
    elif finish == "length":
        stop_reason = "max_tokens"  # truncado por max_tokens — nao esconder o corte
    else:
        stop_reason = "end_turn"
    return {
        "text": msg.get("content") or "",
        "tool_calls": tool_calls,
        "stop_reason": stop_reason,
        "usage": _usage(data, mdl),
    }


async def health() -> bool:
    """True se habilitado e com chave (não testa a rede — coerente com anthropic)."""
    s = get_settings()
    return bool(s.MARITACA_ENABLED and _api_key())
