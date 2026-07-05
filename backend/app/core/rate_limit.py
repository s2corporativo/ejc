# ── app/core/rate_limit.py ────────────────────────────────────────────────────
# Rate limiting via slowapi. Usa o MESMO obter_ip_real do anti-brute-force
# (respeita X-Forwarded-For do Nginx) — sem isso, atrás do proxy todos os
# clientes compartilhariam o limite de 127.0.0.1.
#
# DOIS backends de contagem, escolhidos por RATE_LIMIT_REDIS_ENABLED:
#   • memória (default) — fixed-window por processo; correto só com --workers 1.
#   • Redis — fixed-window atômico (Lua) COMPARTILHADO entre processos, o que
#     torna seguro rodar uvicorn com >1 worker. Redis fora do ar → fallback
#     gracioso para o contador em memória (nunca bloqueia por falha de infra).
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import logging
import math
import threading
import time

from fastapi import Depends, HTTPException, Request
from slowapi import Limiter

from app.core.config import get_settings
from app.core.security import get_current_user
from app.services.security_service import obter_ip_real

logger = logging.getLogger("ejc.rate_limit")


def _key_por_ip_real(request) -> str:
    return obter_ip_real(request)


limiter = Limiter(key_func=_key_por_ip_real)


# ── rate_limit() — dependency FastAPI, sem decorator ─────────────────────────
# O decorator @limiter.limit do slowapi embrulha o endpoint e, combinado com
# PEP 563 (`from __future__ import annotations`, usado em todos os routers),
# faz o FastAPI resolver as anotações-string contra os globals do wrapper do
# slowapi → NameError na montagem das rotas (ver commits 3d0df67 / 11da80f).
# SlowAPIMiddleware com default_limits também não serve: aplicaria limite a
# TODAS as rotas do app indiscriminadamente.
#
# Por isso os endpoints de IA/varredura usam esta dependency dirigida:
# contador fixed-window de 60s, por (rota, usuário-ou-IP) — em memória ou no
# Redis conforme RATE_LIMIT_REDIS_ENABLED (ver consumir()/_consumir_redis).

_JANELA_SEGUNDOS = 60
_MAX_ENTRADAS = 4096  # gatilho de limpeza das janelas expiradas
_janelas: dict[tuple[str, str], tuple[float, int]] = {}
_lock = threading.Lock()


def _agora() -> float:
    # Indireção para os testes poderem avançar o relógio (monkeypatch).
    return time.monotonic()


def _limpar_janelas() -> None:
    """Reseta todos os contadores (uso em testes)."""
    with _lock:
        _janelas.clear()


def _consumir(nome: str, chave: str, max_por_minuto: int) -> None:
    """Núcleo do fixed-window: consome 1 unidade da cota (nome, chave) e lança
    429 se o limite do minuto foi excedido. Compartilhado pelo rate limit por
    usuário JWT (rate_limit) e pelo rate limit por API key (rag_public)."""
    agora = _agora()
    with _lock:
        if len(_janelas) > _MAX_ENTRADAS:  # poda janelas velhas (evita crescer sem limite)
            for k in [k for k, (ini, _) in _janelas.items() if agora - ini >= _JANELA_SEGUNDOS]:
                del _janelas[k]
            # Teto DURO (auditoria P3): se após a poda tudo ainda está
            # "fresco" (só possível com chaves forjadas em massa, ex.: IP
            # spoofado), remove as janelas mais antigas — o invariante de
            # memória não pode depender do modo de chave.
            if len(_janelas) > _MAX_ENTRADAS:
                excedente = len(_janelas) - _MAX_ENTRADAS
                for k in sorted(_janelas, key=lambda k: _janelas[k][0])[:excedente]:
                    del _janelas[k]
        inicio, contagem = _janelas.get((nome, chave), (agora, 0))
        if agora - inicio >= _JANELA_SEGUNDOS:
            inicio, contagem = agora, 0
        contagem += 1
        _janelas[(nome, chave)] = (inicio, contagem)
    if contagem > max_por_minuto:
        restante = max(1, math.ceil(_JANELA_SEGUNDOS - (agora - inicio)))
        raise HTTPException(
            status_code=429,
            detail=(
                f"Limite de {max_por_minuto} requisições por minuto excedido "
                "para esta operação. Aguarde alguns instantes e tente novamente."
            ),
            headers={"Retry-After": str(restante)},
        )


# ── Backend Redis (fixed-window atômico, compartilhado entre workers) ─────────
# INCR + EXPIRE-no-primeiro-hit num único round-trip via Lua (atômico: sem a
# corrida em que a chave é criada mas nunca expira). Retorna (contagem, ttl).
_LUA_FIXED_WINDOW = """
local c = redis.call('INCR', KEYS[1])
if c == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return {c, redis.call('TTL', KEYS[1])}
"""

_redis_client = None  # cache do cliente async (lazy, reaproveitado entre requests)


async def _get_redis():
    """Cliente redis.asyncio cacheado. Qualquer falha de import/conexão → None
    (o chamador cai para o contador em memória)."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis.asyncio as aioredis
        cli = aioredis.from_url(
            get_settings().REDIS_URL,
            socket_connect_timeout=1.0, socket_timeout=1.0,
        )
        _redis_client = cli
        return cli
    except Exception:
        return None


async def _consumir_redis(nome: str, chave: str, max_por_minuto: int) -> bool:
    """Consome 1 unidade da cota no Redis. Lança 429 se exceder. Retorna True
    se o Redis atendeu; False (sem lançar) se o Redis falhou — sinal para o
    chamador cair no contador em memória (fail-open para local, nunca ilimitado)."""
    cli = await _get_redis()
    if cli is None:
        return False
    try:
        contagem, ttl = await cli.eval(
            _LUA_FIXED_WINDOW, 1, f"rl:{nome}:{chave}", _JANELA_SEGUNDOS,
        )
    except Exception as e:
        # Redis caiu no meio → invalida o cache (reconecta na próxima) e delega.
        # Fecha o cliente antigo p/ não vazar pool de conexões sob flapping.
        global _redis_client
        _redis_client = None
        try:
            await cli.aclose()
        except Exception:
            pass
        logger.warning("[rate_limit] Redis indisponível (%s) — usando contador "
                       "em memória neste processo", type(e).__name__)
        return False
    if int(contagem) > max_por_minuto:
        restante = max(1, int(ttl) if int(ttl) > 0 else _JANELA_SEGUNDOS)
        raise HTTPException(
            status_code=429,
            detail=(
                f"Limite de {max_por_minuto} requisições por minuto excedido "
                "para esta operação. Aguarde alguns instantes e tente novamente."
            ),
            headers={"Retry-After": str(restante)},
        )
    return True


async def consumir(nome: str, chave: str, max_por_minuto: int) -> None:
    """Consome cota (rota, chave). Usa o Redis quando habilitado e disponível;
    caso contrário (flag off ou Redis fora do ar) o contador em memória. Ambos
    lançam HTTPException 429 ao exceder o limite do minuto."""
    if get_settings().RATE_LIMIT_REDIS_ENABLED:
        if await _consumir_redis(nome, chave, max_por_minuto):
            return
    _consumir(nome, chave, max_por_minuto)


def rate_limit(nome: str, max_por_minuto: int):
    """Dependency de rate limit por rota: `dependencies=[Depends(rate_limit("x", 5))]`.

    A chave preferencial é o usuário autenticado; sem usuário, cai para o IP
    real (X-Forwarded-For). A auth entra como sub-dependency (get_current_user):
    o cache de dependências do FastAPI garante que ela roda UMA vez por request
    mesmo quando o handler também a declara, e requisição sem token válido leva
    401 ANTES de consumir cota do limite.
    """

    async def _dep(request: Request, cu=Depends(get_current_user)) -> None:
        # cu nunca é None hoje (get_current_user lança 401), mas o fallback por
        # IP fica como defesa caso a auth passe a ser opcional em alguma rota.
        chave = f"user:{cu.id}" if cu is not None else f"ip:{obter_ip_real(request)}"
        await consumir(nome, chave, max_por_minuto)

    return _dep
