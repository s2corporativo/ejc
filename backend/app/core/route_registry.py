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
# Mantemos a MATRIZ HISTÓRICA de seis pares para que uma reclassificação nunca
# apague silenciosamente uma decisão arquitetural. Cada par precisa estar em um
# de três estados: (a) equivalente e não resolvido → violação se ambos ativos;
# (b) consolidado/resolvido → reintrodução dos dois lados é regressão; ou
# (c) explicitamente classificado como CONTRATOS DISTINTOS após reauditoria.
_PARES_SEMANTICOS = (
    # prefixo A, prefixo B, motivo histórico da comparação
    ("/ai", "/ia", "Superfícies de IA historicamente tratadas como paralelas."),
    ("/teses", "/teses-v4", "Motor de teses com versão paralela."),
    ("/data-rooms", "/data-room-v4", "Data Room com versão paralela."),
    ("/intelligence", "/intelligence-v3", "Inteligência com versão paralela."),
    ("/diplomacia", "/diplomacia-v3", "Diplomacia jurídica com versão paralela."),
    ("/conhecimento", "/rag", "Conhecimento e RAG historicamente comparados."),
)

# Decisão de 19/08/2026 após reauditoria do contrato efetivo:
# - `/ia` concentra saúde/status operacional de provedores enquanto `/ai`
#   expõe operações jurídicas e análise. Compartilhar o tema "IA" não torna os
#   contratos equivalentes.
# - `/conhecimento` é ingestão/curadoria; `/rag` é consulta, recuperação e
#   governança. Remover um dos lados por semelhança nominal perderia função.
# Mantê-los aqui, em vez de apagar os pares da matriz, preserva a trilha de
# decisão exigida pelo teste de governança arquitetural.
_PARES_DISTINTOS: set[tuple[str, str]] = {
    ("/ai", "/ia"),
    ("/conhecimento", "/rag"),
}

# Pares cuja consolidação já foi decidida/documentada. Se ambos os prefixos
# voltarem ao runtime, isso é regressão e bloqueia o gate.
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


def _par_em(conjunto: set[tuple[str, str]], a: str, b: str) -> bool:
    return (a, b) in conjunto or (b, a) in conjunto


def auditar_semantica(app: FastAPI) -> dict[str, Any]:
    """Audita colisões literais e decisões semânticas da superfície.

    Compatibilidade: mantém a chave histórica ``resolvidos`` (pares resolvidos
    que hoje coexistem) e acrescenta ``distintos`` e
    ``resolvidos_reintroduzidos`` para o contrato novo. Uma reintrodução de par
    já consolidado é bloqueante, assim como duplicata literal ou par equivalente
    sem decisão.
    """
    manifest = build_route_manifest(app)
    rotas = manifest["routes"]
    violacoes: list[dict[str, str]] = []
    resolvidos: list[dict[str, str]] = []
    distintos: list[dict[str, str]] = []
    resolvidos_reintroduzidos: list[dict[str, str]] = []

    for a, b, motivo in _PARES_SEMANTICOS:
        ambos_ativos = _prefixo_ativo(rotas, a) and _prefixo_ativo(rotas, b)

        if _par_em(_PARES_DISTINTOS, a, b):
            if ambos_ativos:
                distintos.append(
                    {"prefixo_a": a, "prefixo_b": b, "motivo": motivo}
                )
            continue

        if _par_em(_PARES_RESOLVIDOS, a, b):
            if ambos_ativos:
                item = {"prefixo_a": a, "prefixo_b": b, "motivo": motivo}
                # Chave histórica preservada para consumidores/testes antigos.
                resolvidos.append(item)
                # Contrato novo deixa explícito que a coexistência de uma
                # família já consolidada é regressão bloqueante.
                resolvidos_reintroduzidos.append(item)
            continue

        if ambos_ativos:
            violacoes.append({"prefixo_a": a, "prefixo_b": b, "motivo": motivo})

    bloqueios_literais = list(manifest["duplicates"])
    return {
        "ok": not bloqueios_literais and not violacoes and not resolvidos_reintroduzidos,
        "pares_avaliados": len(_PARES_SEMANTICOS),
        "duplicatas_literais": bloqueios_literais,
        "violacoes": violacoes,
        "resolvidos": resolvidos,
        "distintos": distintos,
        "resolvidos_reintroduzidos": resolvidos_reintroduzidos,
    }
