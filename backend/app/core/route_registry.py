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


# ── Auditoria SEMÂNTICA de superfície (consolidação 12/08/2026) ─────────────
# O gate literal (`duplicates`) pega dois routers respondendo o MESMO path.
# Ele NÃO pega o caso mais perigoso no EJC: dois módulos diferentes servindo
# contratos SEMELHANTES em prefixos NOMINALMENTE distintos (ex.: /ai vs. /ia,
# /teses vs. /teses-v4) — que se espalham silenciosamente pelo frontend.
# Os pares abaixo são a lista NOMINAL de equivalências de domínio. Enquanto
# um par estiver ATIVO nos dois lados, `auditar_semantica()` reporta; qualquer
# consolidação deve registrar a decisão aqui (remover um lado ou mover o par
# para `_PARES_RESOLVIDOS`).
_PARES_SEMANTICOS = (
    # prefixo A, prefixo B, motivo da equivalência
    ("/ai", "/ia", "Dois assistentes de IA no mesmo contrato público."),
    ("/teses", "/teses-v4", "Motor de teses com versão paralela."),
    ("/data-rooms", "/data-room-v4", "Data Room com versão paralela."),
    ("/intelligence", "/intelligence-v3", "Inteligência com versão paralela."),
    ("/diplomacia", "/diplomacia-v3", "Diplomacia jurídica com versão paralela."),
    ("/conhecimento", "/rag", "Base de conhecimento espelhada no RAG público."),
)

# Pares cuja coexistência foi DECIDIDA (ex.: migração gradual com redirects).
# Cada entrada é (prefixo_a, prefixo_b).
_PARES_RESOLVIDOS: set[tuple[str, str]] = {
    # Consolidação 12/08/2026 (docs/consolidacao/MAPA_VERDADE_V1.md): routers
    # paralelos comprovadamente órfãos removidos para app/routers/_dead_code/
    # (varredura de consumidores em frontend/backend antes da remoção).
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
    """Compara a superfície montada com os pares de equivalência nominal.

    Retorna `{ "violacoes": [...], "resolvidos": [...], "pares_avaliados": N }`.
    Uma violação exige decisão explícita: consolidar em um único contrato ou
    registrar o par em `_PARES_RESOLVIDOS` com justificativa.
    """
    manifest = build_route_manifest(app)
    rotas = manifest["routes"]
    violacoes: list[dict[str, str]] = []
    resolvidos: list[dict[str, str]] = []
    for a, b, motivo in _PARES_SEMANTICOS:
        if (a, b) in _PARES_RESOLVIDOS or (b, a) in _PARES_RESOLVIDOS:
            if _prefixo_ativo(rotas, a) and _prefixo_ativo(rotas, b):
                resolvidos.append(
                    {"prefixo_a": a, "prefixo_b": b, "motivo": motivo}
                )
            continue
        if _prefixo_ativo(rotas, a) and _prefixo_ativo(rotas, b):
            violacoes.append({"prefixo_a": a, "prefixo_b": b, "motivo": motivo})
    return {
        "pares_avaliados": len(_PARES_SEMANTICOS),
        "violacoes": violacoes,
        "resolvidos": resolvidos,
    }
