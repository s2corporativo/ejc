"""Compatibilidade entre a API histórica /api e o contrato canônico /api/v1."""
from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_EXEMPT_PREFIXES = ("/api/health", "/api/docs", "/api/openapi.json")


class APIVersionCompatibilityMiddleware:
    """Expõe /api/v1 reusando as rotas atuais e sinaliza o prefixo legado.

    A migração é reversível: nenhum router é duplicado e /api continua ativo.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        original_path = str(scope.get("path") or "")
        canonical_request = original_path == "/api/v1" or original_path.startswith("/api/v1/")
        legacy_request = (
            original_path.startswith("/api/")
            and not canonical_request
            and not original_path.startswith(_EXEMPT_PREFIXES)
        )

        if canonical_request:
            rewritten = dict(scope)
            suffix = original_path[len("/api/v1") :] or ""
            rewritten["path"] = f"/api{suffix}"
            raw_path = rewritten["path"].encode("utf-8")
            rewritten["raw_path"] = raw_path
            scope = rewritten

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if canonical_request:
                    headers.append((b"content-location", original_path.encode("utf-8")))
                    headers.append((b"x-ejc-api-version", b"1"))
                elif legacy_request:
                    successor = f"/api/v1{original_path[len('/api'):]}"
                    headers.extend(
                        [
                            (b"deprecation", b"true"),
                            (b"link", f'<{successor}>; rel="successor-version"'.encode("utf-8")),
                            (b"x-ejc-api-version", b"legacy"),
                        ]
                    )
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
