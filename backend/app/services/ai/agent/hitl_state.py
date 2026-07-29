# ── app/services/ai/agent/hitl_state.py ──────────────────────────────────────
# Estado RETOMÁVEL do HITL (Human-in-the-Loop) do agente — achado H1 / Sugestão 1,
# reforçado pela auditoria 2026-07-26 (AI-030/AI-031/AI-032).
#
# A aprovação de uma tool de ESCRITA vincula-se ao `tool_call` EXATO (nome +
# args) e SÓ existe um caminho: estado servidor-side sob token opaco.
#
#   • Redis disponível: quando uma write-tool precisa de confirmação, persistimos
#     o ESTADO do loop (transcrição em espaço real + tool_call pendente + budget
#     acumulado + user_id/case_id/role — AI-031) sob um `token` opaco com TTL
#     curto. Ao retomar com {token, decisao}, o loop CARREGA o estado (consumo
#     ATÔMICO via GETDEL — AI-032), valida que usuário/caso/papel são os MESMOS
#     da pausa e executa EXATAMENTE o tool_call persistido.
#
#   • Redis indisponível: FAIL-CLOSED — nenhuma write-tool executa (AI-030).
#     O antigo fallback por hash de (nome+args) enviado pelo cliente foi
#     ELIMINADO: SHA-256 de dados públicos prova integridade, não autorização —
#     um cliente autenticado podia pré-computar o hash e executar a escrita sem
#     aprovação humana genuína. Sem estado servidor-side, não há aprovação.
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
    indisponível — nesse caso o chamador deve FALHAR FECHADO (AI-030: sem estado
    servidor-side, nenhuma write-tool executa). NUNCA loga o estado."""
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
    except Exception as e:  # Redis caiu no meio → o chamador falha fechado
        logger.warning("[hitl] persistência de estado falhou: %s", type(e).__name__)
        return None
    finally:
        try:
            await cli.aclose()
        except Exception:
            pass


# GET+DEL num único passo server-side — duas retomadas concorrentes com o mesmo
# token nunca leem ambas o estado (AI-032). Usado como fallback quando o cliente
# Redis não expõe GETDEL (redis-server < 6.2).
_LUA_GETDEL = (
    "local v = redis.call('GET', KEYS[1]) "
    "if v then redis.call('DEL', KEYS[1]) end "
    "return v"
)


async def carregar(token: str) -> dict | None:
    """Carrega e REMOVE (one-shot ATÔMICO) o estado do token. None se ausente/
    expirado/Redis down. GET e DELETE acontecem num único comando (GETDEL ou
    script Lua) — o antigo GET seguido de DELETE permitia que duas retomadas
    concorrentes lessem o MESMO estado e executassem a escrita em dobro (AI-032)."""
    if not token:
        return None
    cli = await _cliente()
    if cli is None:
        return None
    chave = _PREFIXO + token
    try:
        try:
            bruto = await cli.getdel(chave)
        except AttributeError:
            # redis-py antigo sem .getdel() → Lua atômico equivalente.
            bruto = await cli.eval(_LUA_GETDEL, 1, chave)
        except Exception as e:
            if "unknown command" not in str(e).lower():
                raise
            # redis-server < 6.2 (sem GETDEL) → Lua atômico equivalente.
            bruto = await cli.eval(_LUA_GETDEL, 1, chave)
        if not bruto:
            return None
        return json.loads(bruto)
    except Exception as e:
        logger.warning("[hitl] leitura de estado falhou: %s", type(e).__name__)
        return None
    finally:
        try:
            await cli.aclose()
        except Exception:
            pass
