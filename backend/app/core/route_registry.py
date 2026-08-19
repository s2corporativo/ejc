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


# ── Auditoria SEMÂNTICA de superfície ─────────────────────────────────────────
# O gate literal (`duplicates`) pega dois routers respondendo o MESMO path.
# O gate semântico cobre APENAS pares comprovadamente equivalentes. Prefixos
# parecidos, mas com contratos diferentes, não entram aqui: em 19/08/2026 a
# reauditoria confirmou que `/ia` é essencialmente status operacional enquanto
# `/ai` contém operações jurídicas, e que `/conhecimento` é importação/curadoria
# enquanto `/rag` é consulta/governança. Tratá-los como duplicatas gerava falso
# positivo e incentivava uma remoção perigosa de capacidades distintas.
_PARES_SEMANTICOS = (
    # prefixo A, prefixo B, motivo da equivalência
    ("/teses", "/teses-v4", "Motor de teses com versão paralela."),
    ("/data-rooms", "/data-room-v4", "Data Room com versão paralela."),
    ("/intelligence", "/intelligence-v3", "Inteligência com versão paralela."),
    ("/diplomacia", "/diplomacia-v3", "Diplomacia jurídica com versão paralela."),
)

# Pares cuja consolidação já foi decidida/documentada. Permanecem na lista
# somente para detectar reintrodução acidental de ambos os lados no runtime.
_PARES_RESOLVIDOS: set[tuple[str, str]] = {
    ("/teses", "/teses-v4"),
    ("/data-rooms", "/data-room-v4"),
    ("/diplomacia", "/diplomacia-v3"),
    ("/intelligence", "/intelligence-v3"),
}


def _prefixo_ativo(routes: list[dict[str, Any]], prefixo: str) -> bool:
    """Há rota com o prefixo dado (match exato ou hierárquico)."""
    prefixo = prefixo.rstrip("/")
    return any(
        item["path"] == prefixo or item["path"].startswith(prefixo + "/")
        for item in routes
    )


def auditar_semantica(app: FastAPI) -> dict[str, Any]:
    """Audita colisões literais e equivalências semânticas comprovadas.

    `ok=false` significa dívida NOVA/bloqueante: rota literal duplicada ou dois
    contratos equivalentes ativos sem decisão registrada. Pares já consolidados
    que reapareçam são reportados em `resolvidos_reintroduzidos`, para tornar a
    regressão visível sem fingir que são uma nova decisão arquitetural.
    """
    manifest = build_route_manifest(app)
    rotas = manifest["routes"]
    violacoes: list[dict[str, str]] = []
    resolvidos_reintroduzidos: list[dict[str, str]] = []

    for a, b, motivo in _PARES_SEMANTICOS:
        ambos_ativos = _prefixo_ativo(rotas, a) and _prefixo_ativo(rotas, b)
        if not ambos_ativos:
            continue
        if (a, b) in _PARES_RESOLVIDOS or (b, a) in _PARES_RESOLVIDOS:
            resolvidos_reintroduzidos.append(
                {"prefixo_a": a, "prefixo_b": b, "motivo": motivo}
            )
            continue
        violacoes.append({"prefixo_a": a, "prefixo_b": b, "motivo": motivo})

    bloqueios_literais = list(manifest["duplicates"])
    return {
        "ok": not bloqueios_literais and not violacoes and not resolvidos_reintroduzidos,
        "pares_avaliados": len(_PARES_SEMANTICOS),
        "duplicatas_literais": bloqueios_literais,
        "violacoes": violacoes,
        "resolvidos_reintroduzidos": resolvidos_reintroduzidos,
    }
