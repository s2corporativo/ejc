# ── app/services/ai_cache.py ─────────────────────────────────────────────────
# Cache de resposta do AI Gateway (opt-in, Redis) — dedup de chamadas idênticas.
#
# Chaveado por SHA-256 de (task_type + parâmetros + messages): a mesma
# requisição, dentro do TTL, reusa a resposta em vez de gastar tokens/latência
# no provedor. NUNCA quebra o fluxo de IA: qualquer falha (Redis fora, import,
# serialização) é engolida e a chamada segue normalmente (mesmo espírito do
# dispatcher/embeddings/langfuse). Só respostas bem-sucedidas são gravadas.
#
# Regra LGPD crítica:
#   respostas de tarefas com pseudonimização REVERSÍVEL não podem ser cacheadas.
#   O gateway reidrata a resposta com PII real antes de devolvê-la ao chamador,
#   mas o mapa de reidratação vive somente na request. Um cache hit posterior não
#   possui esse mapa e, pior, persistiria PII real no Redis. Portanto, tais chaves
#   recebem prefixo NO-CACHE e obter/gravar tornam-se NO-OP.
from __future__ import annotations

import hashlib
import json
import logging

from app.core.config import get_settings

logger = logging.getLogger("ejc.ai.cache")

_PREFIXO = "ai:resp:"
_PREFIXO_NAO_CACHEAVEL = "ai:nocache:"


def habilitado() -> bool:
    s = get_settings()
    return bool(getattr(s, "AI_RESPONSE_CACHE_ENABLED", False))


def _tarefa_cacheavel(task_type: str) -> bool:
    """False quando a resposta pode ser reidratada com dado pessoal real.

    A política é consultada pela mesma fonte usada pelo gateway. O fallback da
    política é EXTERNO_PSEUDONIMIZADO; assim, tarefa desconhecida também fica
    protegida. LOCAL_COMPLETO (sigilo reforçado) também NÃO é cacheável (A6):
    o conteúdo trafega EM CLARO para o provedor local e a resposta pode carregar
    dado pessoal real — persistir isso no Redis contraria a política de que o
    conteúdo dessas áreas não sai do processo. Só MASCARAMENTO (irreversível)
    é cacheável.
    """
    try:
        from app.services.ai.sanitization_policy import ModoSanitizacao, modo_para_task
        modo = modo_para_task(task_type)
        return modo not in (
            ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
            ModoSanitizacao.EXTRACAO_LOCAL,
            ModoSanitizacao.LOCAL_COMPLETO,
        )
    except Exception:
        # Fail-closed: falha ao determinar a política nunca autoriza persistir
        # uma resposta potencialmente reidratada.
        return False


def chave(task_type: str, messages: list[dict], **params) -> str:
    """Hash estável da requisição. Ordena params para independer da ordem.

    Chaves não-cacheáveis continuam determinísticas para observabilidade/testes,
    mas usam prefixo próprio reconhecido por obter/gravar.
    """
    payload = {
        "task_type": task_type,
        "messages": messages,
        "params": {k: params[k] for k in sorted(params)},
    }
    bruto = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    prefixo = _PREFIXO if _tarefa_cacheavel(task_type) else _PREFIXO_NAO_CACHEAVEL
    return prefixo + hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def _nao_cacheavel(chave_req: str) -> bool:
    return (chave_req or "").startswith(_PREFIXO_NAO_CACHEAVEL)


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
    if _nao_cacheavel(chave_req) or not habilitado():
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
    if _nao_cacheavel(chave_req) or not habilitado():
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
