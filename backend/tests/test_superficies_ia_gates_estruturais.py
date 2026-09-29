"""Onda 4.2 — Invariante estrutural das superfícies geradoras de conteúdo jurídico.

Objetivo (plano mestre, seção 4.2): uma rota nova que produza conteúdo jurídico
via Núcleo Único de IA deve quebrar o CI se nascer sem os gates canônicos.

O que este teste trava (fail-closed, descoberta automática — não depende de
lista manual de endpoints):

1. SUPERFÍCIE DE IA: toda rota cujo módulo de endpoint importa/consome o
   núcleo de IA (ai_gateway, SingleAICore, orquestrador, _gateway_json,
   app.services.ai) é considerada superfície geradora de conteúdo jurídico.

2. REGRA A (autenticação): toda rota de superfície de IA precisa ter
   `get_current_user` na árvore de dependências (direto, via include_router
   ou via wrapper de papéis). Rota anônima de IA = regressão bloqueante.

3. REGRA C (ownership/sigilo): se o módulo expõe rota com `case_id`
   (path ou assinatura), o MÓDULO precisa conter algum gate canônico de
   ownership/sigilo — verificar_acesso_caso, ownership inline
   (advogado_responsavel/auxiliar), preparação de escopo (_preparar_caso,
   _get_case→verificar_acesso_caso), cliente_id_visivel ou scoping de AILog
   por user_id. Módulo novo de IA exposto a case_id sem nenhum gate = falha.

Combinado com test_rotas_registro_explicito.py (toda rota nova exige entrada
justificada no registro explícito), test_agentes_invariantes.py (agentes
normativos exigem fonte e citação), test_ai_gateway_barreira.py (sanitização
antes de provider externo) e test_ai_idor_case_id_gates.py (gates por endpoint
conhecido), este arquivo fecha o ciclo da invariante global de IA.
"""
from __future__ import annotations

import inspect
import sys
from functools import lru_cache

from fastapi.routing import APIRoute

MARKERS_GATEWAY = (
    "ai_gateway",
    "SingleAICore",
    "single_ai_core",
    "orquestrador",
    "_gateway_json",
    "from app.services.ai",
)

MARKERS_OWNERSHIP = (
    "verificar_acesso_caso",
    "advogado_responsavel_id",
    "advogado_auxiliar_id",
    "verificar_acesso_cliente",
    "cliente_id_visivel",
    "_preparar_caso",
    "_get_case(",
    "AILog.user_id == cu.id",
)


def _deps_flat(dep, out: set[str], depth: int = 0) -> None:
    if dep is None or depth > 6:
        return
    call = getattr(dep, "call", None)
    if call is not None:
        out.add(getattr(call, "__name__", type(call).__name__))
    for sub in getattr(dep, "dependencies", []) or []:
        _deps_flat(sub, out, depth + 1)


@lru_cache(maxsize=None)
def _fonte_modulo(modname: str | None) -> str:
    if not modname:
        return ""
    mod = sys.modules.get(modname)
    if mod is None:
        return ""
    try:
        return inspect.getsource(mod)
    except (OSError, TypeError):
        return ""


def _superficie_ia(endpoint) -> bool:
    src = _fonte_modulo(getattr(endpoint, "__module__", None))
    if not src:
        return False
    return any(m in src for m in MARKERS_GATEWAY)


def test_invariante_superficies_ia():
    from app.main import app

    superficies: list[tuple[str, str, APIRoute, set[str]]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None or not _superficie_ia(endpoint):
            continue
        for metodo in sorted(route.methods or {"GET"}):
            if metodo in ("HEAD", "OPTIONS"):
                continue
            deps: set[str] = set()
            _deps_flat(getattr(route, "dependant", None), deps)
            superficies.append((metodo, route.path, route, deps))

    # A descoberta automática não pode regredir a zero (mudança de marker ou
    # de montagem). Hoje são dezenas de rotas que tocam o núcleo de IA.
    assert len(superficies) >= 10, (
        "invariante de IA perdeu a visibilidade da superfície "
        f"(encontradas {len(superficies)}); revise MARKERS_GATEWAY"
    )

    sem_auth = []
    com_case_sem_gate_modulo = []
    modulos_com_case: set[str] = set()

    # Regra A — autenticação obrigatória em TODA rota de IA.
    for metodo, path, route, deps in superficies:
        if "get_current_user" not in deps:
            sem_auth.append(f"{metodo} {path}")

    # Regra C — módulo com rota case_id precisa de gate canônico no módulo.
    for metodo, path, route, _deps in superficies:
        endpoint = route.endpoint
        aceita_case = "case_id" in path
        if not aceita_case:
            try:
                sig = inspect.signature(endpoint)
            except (TypeError, ValueError):
                sig = None
            if sig and "case_id" in sig.parameters:
                aceita_case = True
        if aceita_case:
            modulos_com_case.add(endpoint.__module__)

    for modname in modulos_com_case:
        src = _fonte_modulo(modname)
        if src and not any(g in src for g in MARKERS_OWNERSHIP):
            com_case_sem_gate_modulo.append(modname)

    assert not sem_auth, (
        "rotas de superfície de IA sem get_current_user: " + ", ".join(sem_auth)
    )
    assert not com_case_sem_gate_modulo, (
        "módulos de IA com case_id sem nenhum gate canônico de ownership: "
        + ", ".join(com_case_sem_gate_modulo)
    )
