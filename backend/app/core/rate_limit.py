# ── app/core/rate_limit.py ────────────────────────────────────────────────────
# Rate limiting via slowapi. Usa o MESMO obter_ip_real do anti-brute-force
# (respeita X-Forwarded-For do Nginx) — sem isso, atrás do proxy todos os
# clientes compartilhariam o limite de 127.0.0.1.
#
# Storage em memória (default) = compatível com uvicorn --workers 1.
# NÃO aumentar workers sem migrar o storage para Redis (storage_uri).
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
from slowapi import Limiter

from app.services.security_service import obter_ip_real


def _key_por_ip_real(request) -> str:
    return obter_ip_real(request)


limiter = Limiter(key_func=_key_por_ip_real)
