"""Manifesto auditável das rotas montadas no FastAPI."""
from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute


def build_route_manifest(app: FastAPI) -> dict[str, Any]:
    routes: list[dict[str, Any]] = []
    identities: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = sorted(m for m in (route.methods or set()) if m not in {"HEAD", "OPTIONS"})
        for method in methods:
            identity = f"{method} {route.path}"
            identities.append(identity)
            routes.append(
                {
                    "method": method,
                    "path": route.path,
                    "name": route.name,
                    "tags": list(route.tags or []),
                    "deprecated": bool(route.deprecated),
                }
            )
    duplicates = sorted(key for key, count in Counter(identities).items() if count > 1)
    return {
        "total": len(routes),
        "duplicates": duplicates,
        "routes": sorted(routes, key=lambda item: (item["path"], item["method"])),
    }
