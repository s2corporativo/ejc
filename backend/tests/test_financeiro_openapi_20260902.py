"""Contrato de segurança das rotas novas do Financeiro — PR #1378.

Complementa o gate global de paridade: além de declarar path+método em
ADICOES_INTENCIONAIS, trava as dependências de autenticação e o gate de papel
das leituras gerenciais.
"""
from __future__ import annotations

import inspect

import pytest


def _deps_flat(dep, out: set[str], depth: int = 0) -> None:
    if dep is None or depth > 6:
        return
    for item in getattr(dep, "dependencies", []) or []:
        call = getattr(item, "call", None)
        if call is not None:
            out.add(getattr(call, "__name__", type(call).__name__))
        _deps_flat(item, out, depth + 1)


def _auth_deps(path: str, method: str) -> list[str]:
    from app.main import app

    for route in app.routes:
        if getattr(route, "path", None) != path:
            continue
        if method not in (getattr(route, "methods", None) or set()):
            continue
        nomes: set[str] = set()
        _deps_flat(getattr(route, "dependant", None), nomes)
        return sorted(nomes)
    raise AssertionError(f"rota não montada: {method} {path}")


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/fees/{fee_id}/pagamentos", "GET"),
        ("/api/financeiro/demonstrativo", "GET"),
        ("/api/financeiro/fechamento-inteligente", "GET"),
    ],
)
def test_rotas_financeiras_novas_exigem_autenticacao(path, method):
    deps = _auth_deps(path, method)
    assert "HTTPBearer" in deps
    assert "get_current_user" in deps
    assert "get_db" in deps


def test_demonstrativo_e_fechamento_preservam_gate_financeiro_backend():
    from app.routers import financeiro_consolidado

    for handler in (
        financeiro_consolidado.demonstrativo_gerencial,
        financeiro_consolidado.fechamento_inteligente,
    ):
        fonte = inspect.getsource(handler)
        assert "_exigir_financeiro(cu)" in fonte


def test_subledger_preserva_filtro_de_visibilidade_backend():
    from app.routers import fees

    fonte = inspect.getsource(fees.listar_pagamentos)
    assert "_fee_visivel(db, fee_id, cu)" in fonte
