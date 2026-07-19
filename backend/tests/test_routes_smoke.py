"""Smoke de routers: TODAS as rotas GET do app montado respondem sem 500 a
uma requisição NÃO autenticada.

Duas garantias por rota:
1. Segurança — rota fora dos PREFIXOS_PUBLICOS responde exatamente 401 do
   AuthMiddleware (nenhum handler protegido executa sem JWT, nenhum dado vaza).
2. Robustez — rota pública nunca devolve 500: responde 2xx/3xx/401/403/404/422
   (ou 503 deliberado do readiness quando o DB está fora).

Sem Postgres local, rotas públicas que dependem de DB são PULADAS com razão
explícita; no CI com RUN_DB_TESTS=1 (job db-validation) elas rodam completas
e um 5xx vira falha real.
"""
from __future__ import annotations

import os
import re

import pytest
from fastapi.testclient import TestClient

from app.core.auth_middleware import _is_publica
from app.core.fastapi_compat import is_api_route
from app.main import app

RUN_DB = bool(os.getenv("RUN_DB_TESTS"))

# TestClient FORA de `with`: o lifespan (check_db, feriados, scheduler) não
# roda — mesmo padrão dos demais testes sem banco desta suíte.
client = TestClient(app, raise_server_exceptions=False)

# Statuses aceitáveis para rota PÚBLICA sem credencial/DB: sucesso, redirect,
# recusa de credencial (API key/token de link) ou validação de parâmetro.
_PUBLIC_OK = {200, 204, 301, 302, 307, 308, 400, 401, 403, 404, 405, 410, 422, 429}


def _rotas_get() -> list:
    """Uma amostra concreta por rota GET do app ({param} → '1')."""
    vistos: set[str] = set()
    params = []
    for route in app.routes:
        if not is_api_route(route) or "GET" not in getattr(route, "methods", set()):
            continue
        path = getattr(route, "path", "")
        if not path or path in vistos:
            continue
        vistos.add(path)
        sample = re.sub(r"\{[^}]+\}", "1", path)
        params.append(pytest.param(path, sample, id=f"GET {path}"))
    return params


def test_app_tem_volume_plausivel_de_rotas_get():
    """Sanidade do coletor: o app monta centenas de GETs; se isto despencar,
    o smoke abaixo estaria varrendo um app vazio sem ninguém notar."""
    assert len(_rotas_get()) > 200


@pytest.mark.parametrize("route_path,sample", _rotas_get())
def test_get_sem_autenticacao_nunca_500(route_path: str, sample: str):
    resp = client.get(sample)

    if not _is_publica(sample):
        # Middleware global: sem Bearer, a rota protegida responde 401 ANTES
        # de qualquer handler/DB. Qualquer outra coisa é furo de autenticação
        # (2xx/404 executou handler) ou crash pré-auth (5xx).
        assert resp.status_code == 401, (
            f"GET {sample} (rota {route_path}) protegida respondeu "
            f"{resp.status_code} sem token — esperado 401 do AuthMiddleware"
        )
        return

    # Rota pública: o handler executa de verdade.
    if resp.status_code >= 500:
        # /api/health/ready devolve 503 POR CONTRATO quando o DB está fora.
        if resp.status_code == 503 and route_path == "/api/health/ready":
            if RUN_DB:
                pytest.fail(
                    "readiness 503 com RUN_DB_TESTS=1 — banco do CI fora do ar?"
                )
            return
        if not RUN_DB:
            pytest.skip(
                f"rota pública {route_path} respondeu {resp.status_code} sem "
                "Postgres local — rode com RUN_DB_TESTS=1 para validar completa"
            )
        pytest.fail(
            f"GET {sample} (rota {route_path}) pública respondeu "
            f"{resp.status_code} — 5xx nunca é aceitável"
        )

    assert resp.status_code in _PUBLIC_OK, (
        f"GET {sample} (rota {route_path}) pública respondeu inesperado "
        f"{resp.status_code}"
    )
