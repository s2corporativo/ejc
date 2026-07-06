# ── app/core/request_context.py ──────────────────────────────────────────────
# Contexto por requisição (ContextVar) — hoje guarda apenas o IP real do cliente.
#
# Motivo (item 1.1 da auditoria funcional): criar_audit_log() só recebia o IP
# explicitamente em auth.py (LOGIN/LOGIN_FALHA/TROCA_SENHA/TOTP). Todos os demais
# ~40 call-sites (CREATE/UPDATE/DELETE/UPLOAD/DOWNLOAD/CONFLITO_CHECK...) gravavam
# ip=NULL. Em vez de tocar em 40 assinaturas de handler, capturamos o IP uma vez
# por requisição num ContextVar e criar_audit_log usa esse valor como fallback.
#
# Middleware PURO-ASGI (não BaseHTTPMiddleware): roda na MESMA task do endpoint,
# então o ContextVar propaga de forma confiável, sem depender da versão do
# Starlette (BaseHTTPMiddleware tem histórico de não propagar ContextVars).
from __future__ import annotations
from contextvars import ContextVar
from typing import Optional

from starlette.types import ASGIApp, Receive, Scope, Send

# Default None → criar_audit_log mantém o comportamento anterior fora de um
# request HTTP (ex.: jobs do scheduler), sem quebrar nada.
_client_ip: ContextVar[Optional[str]] = ContextVar("ejc_client_ip", default=None)


def set_client_ip(ip: Optional[str]) -> None:
    _client_ip.set(ip)


def get_client_ip() -> Optional[str]:
    return _client_ip.get()


def parse_client_ip(xff: str, x_real_ip: str, client_host: Optional[str]) -> str:
    """IP real do cliente atrás de UM proxy reverso confiável (o Nginx do host).

    Fonte única da verdade — reusada por security_service.obter_ip_real e pelo
    ClientIPMiddleware, para não divergirem.

    O Nginx usa ``proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for``,
    que ANEXA o endereço do peer imediato ao FINAL da lista. Logo o ÚLTIMO item
    do X-Forwarded-For é o único não-forjável (posto pelo nosso Nginx); os itens
    anteriores são controlados pelo cliente. Confiar no PRIMEIRO item permitia
    spoof de IP (bypass de rate-limit por IP, IP falso em audit logs LGPD,
    poisoning do alerta de novo dispositivo). Por isso pegamos o último salto.
    """
    if xff:
        partes = [p.strip() for p in xff.split(",") if p.strip()]
        if partes:
            return partes[-1]
    if x_real_ip:
        return x_real_ip.strip()
    return client_host or "0.0.0.0"


def _extrai_ip(scope: Scope) -> str:
    """IP real do cliente a partir do scope ASGI, respeitando proxy reverso."""
    headers = {
        k.decode("latin1").lower(): v.decode("latin1")
        for k, v in scope.get("headers", [])
    }
    client = scope.get("client")
    return parse_client_ip(
        headers.get("x-forwarded-for", ""),
        headers.get("x-real-ip", ""),
        client[0] if client else None,
    )


class ClientIPMiddleware:
    """Captura o IP real por requisição HTTP num ContextVar, para que
    criar_audit_log preencha o IP em TODOS os eventos de auditoria."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = _client_ip.set(_extrai_ip(scope))
        try:
            await self.app(scope, receive, send)
        finally:
            _client_ip.reset(token)
