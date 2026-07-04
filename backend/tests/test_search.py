"""Busca global (GET /search) — validação de contrato SEM banco.

Cobre o que não depende de dados: validação do query param `tipo` (422) e o
curto-circuito de cliente_externo (resultados vazios antes de tocar o banco).
Usa um app FastAPI mínimo com o router REAL (mesma abordagem de
test_rate_limit.py): dependency_overrides substitui auth e db, e a request
passa pela rota de verdade — inclusive validação de Query e o wrapper do
slowapi (@limiter.limit).

A cobertura com dados reais (parte/cpf/processo/escopo) está em
test_search_dblevel.py — regexp_replace e o SQL cru da tabela `processes`
são Postgres-only, então lá exige RUN_DB_TESTS=1.
"""
from __future__ import annotations

import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.routers import search as search_router


def _montar_app(role: str = "advogado"):
    """App mínimo com o router real de busca; auth/db substituíveis."""
    app = FastAPI()
    app.include_router(search_router.router)

    estado = {"user": types.SimpleNamespace(
        id="user-teste", role=types.SimpleNamespace(value=role))}

    async def _db_fake():
        # Nunca deve ser usado nos cenários deste módulo (422 corta antes do
        # handler; cliente_externo retorna antes de tocar o banco). Se algum
        # teste chegar a consultar, explode com AttributeError em None.
        yield None

    app.dependency_overrides[get_current_user] = lambda: estado["user"]
    app.dependency_overrides[get_db] = _db_fake
    return app, estado


def test_tipo_invalido_retorna_422():
    app, _ = _montar_app()
    client = TestClient(app)
    r = client.get("/search", params={"q": "fulano", "tipo": "banana"})
    assert r.status_code == 422
    # O erro aponta o parâmetro certo (pattern do Query).
    assert any(e.get("loc", [])[-1] == "tipo" for e in r.json()["detail"])


@pytest.mark.parametrize("tipo", ["tudo", "parte", "cpf", "processo"])
def test_tipos_validos_aceitos_para_cliente_externo(tipo):
    """Os 4 tipos passam na validação; cliente_externo recebe vazio em todos
    (o portal do cliente tem visão própria) sem nunca tocar o banco."""
    app, _ = _montar_app(role="cliente_externo")
    client = TestClient(app)
    r = client.get("/search", params={"q": "qualquer coisa", "tipo": tipo})
    assert r.status_code == 200
    body = r.json()
    assert body["resultados"] == []
    assert body["tipo"] == tipo
    assert body["q"] == "qualquer coisa"


def test_tipo_default_e_tudo_e_resposta_inclui_tipo():
    """Regressão de contrato: sem `tipo` na query, o default é 'tudo' e a
    resposta passou a incluir o campo 'tipo' (consumido pelo CommandPalette)."""
    app, _ = _montar_app(role="cliente_externo")
    client = TestClient(app)
    r = client.get("/search", params={"q": "abc"})
    assert r.status_code == 200
    assert r.json()["tipo"] == "tudo"


def test_q_curto_retorna_422():
    app, _ = _montar_app()
    client = TestClient(app)
    r = client.get("/search", params={"q": "a", "tipo": "parte"})
    assert r.status_code == 422
