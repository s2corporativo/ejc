# ── app/services/ai/agent/hitl_state.py ──────────────────────────────────────
# Estado RETOMÁVEL do HITL (Human-in-the-Loop) do agente — achado H1 / Sugestão 1.
#
# PROBLEMA (H1): antes a aprovação de uma tool de ESCRITA era por NOME e o loop
# RE-RODAVA do zero ao retomar — o modelo podia gerar ARGS diferentes dos que o
# humano viu/aprovou e executá-los. A aprovação passa a vincular-se ao `tool_call`
# EXATO (nome + args):
#
#   1) Caminho PREFERIDO (Redis disponível): quando uma write-tool precisa de
#      confirmação, persistimos o ESTADO do loop (transcrição em espaço real +
#      tool_call pendente + budget acumulado) sob um `token` opaco com TTL curto.
#      Ao retomar com {token, decisao}, o loop CARREGA o estado e executa
#      EXATAMENTE o tool_call persistido — sem re-rodar as tools de leitura.
#
#   2) Caminho FALLBACK (Redis indisponível): não há estado; a aprovação vincula-se
#      a um HASH de (nome + args). O loop re-roda, mas só executa a write-tool se o
#      tool_call recém-gerado casar com o hash aprovado (divergência → recusa
#      segura). Fecha o H1 mesmo sem Redis.
#
# ⚠️ LGPD: o estado no Redis contém PII em ESPAÇO REAL (a transcrição do agente).
# Fica no VPS (Redis INTERNO — o mesmo do rate_limit/ai_cache/Celery), com TTL
# curto, e NUNCA é logado. Só o próprio loop (no VPS) lê e reidrata. Nenhum
# conteúdo do estado vai a provider externo nem à observabilidade.
from __future__ import annotations

import hashlib
import json
import logging
from uuid import uuid4

from app.core.config import get_settings

logger = logging.getLogger("ejc.ai.agent.hitl")

_PREFIXO = "agente:hitl:"


def hash_tool_call(nome: str, args: dict | None) -> str:
    """Hash estável de (nome + args) — vincula a aprovação aos ARGS exatos.
    Ordena as chaves para independer da ordem de serialização (achado H1)."""
    bruto = json.dumps(
        {"nome": nome or "", "args": args or {}},
        ensure_ascii=False, sort_keys=True, default=str,
    )
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


async def _cliente():
    """Cliente Redis assíncrono (curto timeout) — mesmo padrão do ai_cache.
    None em qualquer falha (import/conexão): o chamador cai no fallback por hash."""
    try:
        import redis.asyncio as aioredis
        s = get_settings()
        return aioredis.from_url(
            s.REDIS_URL, socket_connect_timeout=1.0, socket_timeout=1.0,
            decode_responses=True,
        )
    except Exception:
        return None


async def salvar(estado: dict, ttl: int | None = None) -> str | None:
    """Persiste `estado` (dict JSON-serializável, com PII em espaço real) sob um
    token opaco com TTL curto. Retorna o token, ou None se o Redis estiver
    indisponível (→ o chamador usa o fallback por hash). NUNCA loga o estado."""
    cli = await _cliente()
    if cli is None:
        return None
    token = uuid4().hex
    if ttl is None:
        ttl = int(getattr(get_settings(), "AI_AGENT_HITL_TTL_SEGUNDOS", 900) or 900)
    try:
        await cli.set(
            _PREFIXO + token,
            json.dumps(estado, ensure_ascii=False, default=str),
            ex=ttl,
        )
        return token
    except Exception as e:  # Redis caiu no meio → fallback por hash
        logger.warning("[hitl] persistência de estado falhou: %s", type(e).__name__)
        return None
    finally:
        try:
            await cli.aclose()
        except Exception:
            pass


async def carregar(token: str) -> dict | None:
    """Carrega e REMOVE (one-shot) o estado do token. None se ausente/expirado/
    Redis down. A remoção evita retomada dupla do mesmo passo pendente."""
    if not token:
        return None
    cli = await _cliente()
    if cli is None:
        return None
    chave = _PREFIXO + token
    try:
        bruto = await cli.get(chave)
        if not bruto:
            return None
        try:
            await cli.delete(chave)
        except Exception:
            pass  # a expiração por TTL cobre a limpeza
        return json.loads(bruto)
    except Exception as e:
        logger.warning("[hitl] leitura de estado falhou: %s", type(e).__name__)
        return None
    finally:
        try:
            await cli.aclose()
        except Exception:
            pass
