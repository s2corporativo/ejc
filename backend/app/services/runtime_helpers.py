"""Primitivas de infraestrutura sem compartilhar estado/escopos de credenciais."""
from __future__ import annotations


async def cliente_redis(get_settings):
    """Cliente curto, sem conexão antecipada; None se configuração/import falhar."""
    try:
        import redis.asyncio as aioredis
        settings = get_settings()
        return aioredis.from_url(
            settings.REDIS_URL, socket_connect_timeout=1.0, socket_timeout=1.0,
            decode_responses=True,
        )
    except Exception:
        return None


def refresh_oauth_if_needed(creds, request_factory):
    """Renova a credencial recebida; não altera a seleção de identidade/escopo."""
    if not creds.valid and getattr(creds, "refresh_token", None):
        creds.refresh(request_factory())
    return creds


async def com_engine_limpo(coro):
    """Descarta o pool no loop que executou a coroutine, inclusive após erro."""
    from app.core.database import engine
    try:
        return await coro
    finally:
        await engine.dispose()

