"""Manifesto auditável das rotas montadas no FastAPI."""
from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute


def _is_api_route(route: Any) -> bool:
    """Aceita APIRoute tradicional e contexto efetivo dos routers lazy."""
    if isinstance(route, APIRoute):
        return True
    return isinstance(getattr(route, "original_route", None), APIRoute)


def build_route_manifest(app: FastAPI) -> dict[str, Any]:
    routes: list[dict[str, Any]] = []
    identities: list[str] = []
    for route in app.routes:
        if not _is_api_route(route):
            continue
        methods = sorted(
            method
            for method in (getattr(route, "methods", None) or set())
            if method not in {"HEAD", "OPTIONS"}
        )
        for method in methods:
            identity = f"{method} {route.path}"
            identities.append(identity)
            routes.append(
                {
                    "method": method,
                    "path": route.path,
                    "name": getattr(route, "name", None),
                    "tags": list(getattr(route, "tags", None) or []),
                    "deprecated": bool(getattr(route, "deprecated", False)),
                }
            )
    duplicates = sorted(key for key, count in Counter(identities).items() if count > 1)
    return {
        "total": len(routes),
        "duplicates": duplicates,
        "routes": sorted(routes, key=lambda item: (item["path"], item["method"])),
    }
