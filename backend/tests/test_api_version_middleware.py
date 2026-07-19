from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.api_version_middleware import APIVersionCompatibilityMiddleware


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(APIVersionCompatibilityMiddleware)

    @app.get("/api/ping")
    async def ping():
        return {"ok": True}

    return app


def test_api_v1_rewrites_to_existing_router():
    response = TestClient(_app()).get("/api/v1/ping")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert response.headers["x-ejc-api-version"] == "1"


def test_legacy_api_remains_available_with_successor_header():
    response = TestClient(_app()).get("/api/ping")
    assert response.status_code == 200
    assert response.headers["deprecation"] == "true"
    assert response.headers["link"] == '</api/v1/ping>; rel="successor-version"'
