# ── app/services/observability/langfuse_client.py ────────────────────────────
# Wrapper de tracing Langfuse SELF-HOSTED para o AI Gateway (Fase 6).
#
# PRINCÍPIOS
#   1. NO-OP por padrão: se LANGFUSE_ENABLED=false ou faltarem chaves, NADA é
#      importado/conectado e todas as funções retornam sem efeito. O tracing
#      JAMAIS pode quebrar o fluxo de IA — todo erro do SDK é engolido (log).
#   2. LGPD: por padrão só metadados (task_type, provider, modelo, tokens,
#      latência, custo, sucesso/erro) vão ao Langfuse. Prompt/resposta crus só
#      quando LANGFUSE_CAPTURE_CONTENT=true, e SEMPRE após a MESMA sanitização
#      PII do gateway (sanitizar_pii). Nunca ecoamos conteúdo sem sanitizar.
#   3. Self-hosted: LANGFUSE_HOST aponta para o serviço no docker-compose. Nunca
#      cloud.langfuse.com — o AILog interno continua sendo a trilha legal (LGPD).
from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger("ejc.ai.observability")

# Cliente Langfuse memoizado (None = não inicializado / indisponível).
_client: Any = None
_client_tentado = False


def habilitado() -> bool:
    """True só quando ligado E com as duas chaves presentes."""
    s = get_settings()
    return bool(s.LANGFUSE_ENABLED and s.LANGFUSE_PUBLIC_KEY and s.LANGFUSE_SECRET_KEY)


def capturar_conteudo() -> bool:
    """True = pode enviar input/output (SANITIZADOS) ao Langfuse."""
    return bool(get_settings().LANGFUSE_CAPTURE_CONTENT)


def _get_client() -> Any:
    """Inicializa o SDK Langfuse sob demanda. NUNCA levanta: falha → None."""
    global _client, _client_tentado
    if _client is not None:
        return _client
    if _client_tentado:  # já tentamos e falhou; não re-tenta a cada chamada
        return None
    _client_tentado = True
    if not habilitado():
        return None
    s = get_settings()
    try:
        from langfuse import Langfuse  # import tardio: só quando ligado

        _client = Langfuse(
            host=s.LANGFUSE_HOST,
            public_key=s.LANGFUSE_PUBLIC_KEY,
            secret_key=s.LANGFUSE_SECRET_KEY,
        )
        logger.info("[Langfuse] cliente self-hosted inicializado (host=%s)", s.LANGFUSE_HOST)
        return _client
    except Exception as e:  # ImportError, config inválida, etc. — nunca quebra IA
        logger.warning("[Langfuse] indisponível, tracing desligado: %s", str(e)[:200])
        return None


def _sanitizar_conteudo(messages: list[dict] | str | None) -> Any:
    """Sanitiza conteúdo antes de enviar ao Langfuse (mesma barreira do gateway).
    Retorna None se captura desligada ou entrada vazia."""
    if messages is None or not capturar_conteudo():
        return None
    from app.services.sanitizer import sanitizar_pii

    if isinstance(messages, str):
        limpo, _ = sanitizar_pii(messages)
        return limpo
    limpos = []
    for m in messages:
        conteudo = (m.get("content", "") or "") if isinstance(m, dict) else str(m)
        limpo, _ = sanitizar_pii(conteudo)
        novo = dict(m) if isinstance(m, dict) else {"content": conteudo}
        novo["content"] = limpo
        limpos.append(novo)
    return limpos


def montar_metadata(
    *,
    provider: str,
    model: str | None,
    task_type: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    duracao_ms: int | None = None,
    fallback_ativado: bool = False,
    fallback_motivo: str | None = None,
    custo_estimado_brl: float | None = None,
    sucesso: bool = True,
    erro: str | None = None,
    tier: str | None = None,
    roteamento_score: int | None = None,
) -> dict:
    """Metadata PURO (sem PII) — testável sem SDK. Só campos operacionais."""
    meta = {
        "task_type": task_type,
        "provider": provider,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duracao_ms": duracao_ms,
        "fallback_ativado": fallback_ativado,
        "fallback_motivo": fallback_motivo,
        "custo_estimado_brl": custo_estimado_brl,
        "sucesso": sucesso,
        "erro": erro,
        "tier": tier,
        "roteamento_score": roteamento_score,
    }
    return {k: v for k, v in meta.items() if v is not None}


def novo_trace(name: str, metadata: dict | None = None) -> Any:
    """Abre um trace. Retorna handle (ou None se desligado/indisponível)."""
    client = _get_client()
    if client is None:
        return None
    try:
        return client.trace(name=name, metadata=metadata or {})
    except Exception as e:
        logger.warning("[Langfuse] novo_trace falhou: %s", str(e)[:200])
        return None


def registrar_generation(
    trace: Any,
    *,
    name: str,
    model: str | None,
    metadata: dict,
    input_messages: list[dict] | None = None,
    output_text: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> None:
    """Registra a chamada bem-sucedida como generation no trace. NO-OP se trace None."""
    if trace is None:
        return
    try:
        usage = None
        if input_tokens is not None or output_tokens is not None:
            usage = {"input": input_tokens or 0, "output": output_tokens or 0, "unit": "TOKENS"}
        trace.generation(
            name=name,
            model=model,
            input=_sanitizar_conteudo(input_messages),
            output=_sanitizar_conteudo(output_text),
            usage=usage,
            metadata=metadata,
        )
    except Exception as e:
        logger.warning("[Langfuse] registrar_generation falhou: %s", str(e)[:200])


def registrar_evento(trace: Any, *, name: str, metadata: dict) -> None:
    """Registra um evento (ex.: fallback entre provedores) no trace. NO-OP se None."""
    if trace is None:
        return
    try:
        trace.event(name=name, metadata=metadata)
    except Exception as e:
        logger.warning("[Langfuse] registrar_evento falhou: %s", str(e)[:200])


def flush() -> None:
    """Força o envio dos eventos pendentes (fire-and-forget). NO-OP se desligado."""
    client = _get_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception as e:
        logger.warning("[Langfuse] flush falhou: %s", str(e)[:200])


def _reset_para_testes() -> None:
    """Zera o cache do cliente (uso EXCLUSIVO de testes)."""
    global _client, _client_tentado
    _client = None
    _client_tentado = False
