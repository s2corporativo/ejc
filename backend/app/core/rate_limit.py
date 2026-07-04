# ── app/core/rate_limit.py ────────────────────────────────────────────────────
# Rate limiting via slowapi. Usa o MESMO obter_ip_real do anti-brute-force
# (respeita X-Forwarded-For do Nginx) — sem isso, atrás do proxy todos os
# clientes compartilhariam o limite de 127.0.0.1.
#
# Storage em memória (default) = compatível com uvicorn --workers 1.
# NÃO aumentar workers sem migrar o storage para Redis (storage_uri).
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import math
import threading
import time

from fastapi import Depends, HTTPException, Request
from slowapi import Limiter

from app.core.security import get_current_user
from app.services.security_service import obter_ip_real


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
# contador fixed-window de 60s em memória, por (rota, usuário-ou-IP).
#
# LIMITAÇÃO (igual à do slowapi acima): contadores em memória de UM processo.
# O app roda com uvicorn --workers 1; NÃO aumentar workers sem migrar este
# storage (e o do slowapi) para Redis.

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

    return _dep
