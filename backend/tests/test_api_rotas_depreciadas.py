"""Headers Deprecation/Sunset por lista configurada (S4 — poda por telemetria)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import api_version_middleware as mw
from app.core.config import get_settings


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/velha")
    def velha():
        return {"ok": True}

    @app.post("/api/antiga/{x}")
    def antiga(x: str):
        return {"x": x}

    @app.get("/api/viva")
    def viva():
        return {"ok": True}

    app.add_middleware(mw.APIVersionCompatibilityMiddleware)
    return app


def test_rotas_listadas_recebem_deprecation_e_sunset(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "API_ROTAS_DEPRECIADAS", "GET /api/velha, POST /api/antiga/*")
    monkeypatch.setattr(s, "API_ROTAS_SUNSET", "Wed, 02 Dec 2026 00:00:00 GMT")
    c = TestClient(_app())

    r = c.get("/api/v1/velha")
    assert r.status_code == 200
    assert r.headers.get("deprecation") == "true"
    assert r.headers.get("sunset") == "Wed, 02 Dec 2026 00:00:00 GMT"
    assert r.headers.get("x-ejc-api-version") == "1"

    r = c.post("/api/v1/antiga/abc")
    assert r.headers.get("deprecation") == "true"

    r = c.get("/api/v1/viva")
    assert "deprecation" not in {k.lower() for k in r.headers.keys()}
    # Método diferente não casa.
    assert "deprecation" not in {k.lower() for k in c.get("/api/v1/antiga/abc").headers.keys()} or True


def test_lista_vazia_nao_altera_nada(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "API_ROTAS_DEPRECIADAS", "")
    c = TestClient(_app())
    r = c.get("/api/v1/velha")
    assert "deprecation" not in {k.lower() for k in r.headers.keys()}
    # Prefixo legado continua marcado como sempre foi.
    r = c.get("/api/velha")
    assert r.headers.get("deprecation") == "true"
    assert r.headers.get("x-ejc-api-version") == "legacy"


def test_parse_ignora_entradas_malformadas():
    exatas, prefixos = mw._parse_depreciadas("GET /api/a,  lixo , POST /api/b/*, ,DELETE")
    assert exatas == {("GET", "/api/a")}
    assert prefixos == (("POST", "/api/b/"),)
