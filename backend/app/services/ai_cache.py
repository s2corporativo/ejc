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

from app.services.runtime_helpers import cliente_redis

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


def _modo_cacheavel(modo) -> bool:
    """NIA-06 (auditoria 03/10): o modo EFETIVO da chamada — tarefa reforçada
    pelo sigilo do caso — também decide. Sem isto, uma tarefa mapeada para
    MASCARAMENTO por override, num caso LOCAL_COMPLETO, gravava no Redis a
    resposta local em claro. Só MASCARAMENTO (irreversível) é cacheável."""
    if modo is None:
        return True
    from app.services.ai.sanitization_policy import ModoSanitizacao
    return modo == ModoSanitizacao.MASCARAMENTO


def chave(task_type: str, messages: list[dict], *, modo_sanitizacao=None,
          **params) -> str:
    """Hash estável da requisição. Ordena params para independer da ordem.

    `modo_sanitizacao` é o modo EFETIVO da chamada (None = só a política da
    tarefa). Chaves não-cacheáveis continuam determinísticas para
    observabilidade/testes, mas usam prefixo próprio reconhecido por obter/gravar.
    """
    payload = {
        "task_type": task_type,
        "messages": messages,
        "params": {k: params[k] for k in sorted(params)},
    }
    if modo_sanitizacao is not None:
        payload["modo"] = str(getattr(modo_sanitizacao, "value", modo_sanitizacao))
    bruto = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    try:
        cacheavel = _tarefa_cacheavel(task_type) and _modo_cacheavel(modo_sanitizacao)
    except Exception:
        cacheavel = False  # fail-closed, como em _tarefa_cacheavel
    prefixo = _PREFIXO if cacheavel else _PREFIXO_NAO_CACHEAVEL
    return prefixo + hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def _nao_cacheavel(chave_req: str) -> bool:
    return (chave_req or "").startswith(_PREFIXO_NAO_CACHEAVEL)


async def _cliente():
    return await cliente_redis(get_settings)


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
