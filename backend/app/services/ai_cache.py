# ── app/services/ai_cache.py ─────────────────────────────────────────────────
# Cache de resposta do AI Gateway (opt-in, Redis) — dedup de chamadas idênticas.
#
# Chaveado por SHA-256 de (task_type + parâmetros + messages): a mesma
# requisição, dentro do TTL, reusa a resposta em vez de gastar tokens/latência
# no provedor. NUNCA quebra o fluxo de IA: qualquer falha (Redis fora, import,
# serialização) é engolida e a chamada segue normalmente (mesmo espírito do
# dispatcher/embeddings/langfuse). Só respostas bem-sucedidas são gravadas.
#
# Nota LGPD: o Redis é interno (mesmo do rate_limit/Celery). A chave é um hash
# (não expõe o prompt); o valor guarda o texto da resposta e metadados. Como o
# conteúdo já trafega para provedores externos hoje, o cache interno não cria
# nova superfície de exposição. Só é ativado com AI_RESPONSE_CACHE_ENABLED=true.
from __future__ import annotations

import hashlib
import json
import logging

from app.core.config import get_settings

logger = logging.getLogger("ejc.ai.cache")

_PREFIXO = "ai:resp:"


def habilitado() -> bool:
    s = get_settings()
    return bool(getattr(s, "AI_RESPONSE_CACHE_ENABLED", False))


def chave(task_type: str, messages: list[dict], **params) -> str:
    """Hash estável da requisição. Ordena params para independer da ordem."""
    payload = {
        "task_type": task_type,
        "messages": messages,
        "params": {k: params[k] for k in sorted(params)},
    }
    bruto = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return _PREFIXO + hashlib.sha256(bruto.encode("utf-8")).hexdigest()


async def _cliente():
    """Cliente Redis assíncrono (curto timeout). None em qualquer falha."""
    try:
        import redis.asyncio as aioredis
        s = get_settings()
        return aioredis.from_url(
            s.REDIS_URL, socket_connect_timeout=1.0, socket_timeout=1.0,
            decode_responses=True,
        )
    except Exception:
        return None


async def obter(chave_req: str) -> dict | None:
    """Retorna o dict da resposta cacheada, ou None (miss/erro/desligado)."""
    if not habilitado():
        return None
    cli = await _cliente()
    if cli is None:
        return None
    try:
        bruto = await cli.get(chave_req)
        return json.loads(bruto) if bruto else None
    except Exception as e:
        logger.debug("[ai_cache] leitura falhou (ignorada): %s", str(e)[:120])
        return None
    finally:
        try:
            await cli.aclose()
        except Exception:
            pass


async def gravar(chave_req: str, valor: dict) -> None:
    """Grava a resposta com TTL curto. Silencioso em qualquer falha."""
    if not habilitado():
        return
    cli = await _cliente()
    if cli is None:
        return
    try:
        ttl = int(get_settings().AI_RESPONSE_CACHE_TTL or 300)
        await cli.set(chave_req, json.dumps(valor, ensure_ascii=False, default=str), ex=ttl)
    except Exception as e:
        logger.debug("[ai_cache] gravação falhou (ignorada): %s", str(e)[:120])
    finally:
        try:
            await cli.aclose()
        except Exception:
            pass
