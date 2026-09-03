"""Compatibilidade entre a API histórica /api e o contrato canônico /api/v1."""
from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_EXEMPT_PREFIXES = ("/api/health", "/api/docs", "/api/openapi.json")

# ── Poda por telemetria (S4 da análise E2E 03/09/2026) ───────────────────────
# API_ROTAS_DEPRECIADAS: CSV de "METODO /api/caminho" (sufixo "*" = prefixo).
# Rotas listadas respondem com `Deprecation: true` e, se API_ROTAS_SUNSET
# estiver definido, `Sunset: <data HTTP>` — o ciclo é: 90 dias sem uso em
# /architecture/uso-rotas → entra aqui → remoção. Nada é removido por este
# middleware.
_cache_depreciadas: dict[str, tuple[set[tuple[str, str]], tuple[tuple[str, str], ...]]] = {}


def _parse_depreciadas(csv: str):
    if csv in _cache_depreciadas:
        return _cache_depreciadas[csv]
    exatas: set[tuple[str, str]] = set()
    prefixos: list[tuple[str, str]] = []
    for item in (csv or "").split(","):
        item = item.strip()
        if not item:
            continue
        partes = item.split(None, 1)
        if len(partes) != 2:
            continue
        metodo, caminho = partes[0].upper(), partes[1].strip()
        if caminho.endswith("*"):
            prefixos.append((metodo, caminho[:-1]))
        else:
            exatas.add((metodo, caminho))
    _cache_depreciadas[csv] = (exatas, tuple(prefixos))
    return _cache_depreciadas[csv]


def rota_depreciada(metodo: str, caminho: str) -> bool:
    """Consulta a lista configurada (Settings) — caminho já normalizado /api/...."""
    from app.core.config import get_settings

    csv = str(getattr(get_settings(), "API_ROTAS_DEPRECIADAS", "") or "")
    if not csv:
        return False
    exatas, prefixos = _parse_depreciadas(csv)
    metodo = (metodo or "").upper()
    if (metodo, caminho) in exatas:
        return True
    return any(m == metodo and caminho.startswith(p) for m, p in prefixos)


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

        caminho_interno = str(scope.get("path") or "")
        depreciada = rota_depreciada(str(scope.get("method") or ""), caminho_interno)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if depreciada and not legacy_request:
                    from app.core.config import get_settings

                    headers.append((b"deprecation", b"true"))
                    sunset = str(getattr(get_settings(), "API_ROTAS_SUNSET", "") or "")
                    if sunset:
                        headers.append((b"sunset", sunset.encode("utf-8")))
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
