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


def test_router_must_not_bake_its_own_v1_prefix():
    """Regressão (auditoria 2026-07-26): GET /api/v1/clients/{id}/pending-items
    devolvia 404 em produção mesmo com a rota corretamente registrada.

    Causa raiz: `pending_items.router` nascia com `prefix="/v1/clients"`, então
    a ÚNICA rota registrada já era /api/v1/clients/.../pending-items. Este
    middleware trata QUALQUER caminho iniciado por /api/v1/ como "canônico" e
    o reescreve removendo o "/v1" ANTES de rotear (linha 31-37 de
    api_version_middleware.py) — virava /api/clients/.../pending-items, que
    nunca existiu como rota (o app só tinha a versão com /v1 embutido no
    próprio router). Resultado: 404 mesmo a rota "existindo".

    Este teste fixa o contrato: um router que declara seu prefixo SEM "/v1"
    (deixando o middleware sintetizar o alias canônico, como dossie_cliente.py
    e clients.py já fazem) resolve corretamente em /api/v1/<prefixo>/...
    Se algum router voltar a embutir "/v1" no próprio prefixo, o teste
    equivalente para aquele router replicaria o 404 reproduzido na auditoria.
    """
    from app.routers import pending_items

    app = FastAPI()
    app.add_middleware(APIVersionCompatibilityMiddleware)
    app.include_router(pending_items.router, prefix="/api")

    assert pending_items.router.prefix == "/clients", (
        "pending_items.router não deve embutir '/v1' no próprio prefixo — "
        "isso quebra o alias canônico do compat middleware (ver docstring "
        "deste teste)."
    )

    client = TestClient(app)
    fake_id = "00000000-0000-0000-0000-000000000000"

    # Caminho canônico (o que o frontend chama): NÃO pode ser 404 de rota
    # inexistente. A dependência de auth ainda bloqueia com 401 sem token —
    # o que importa aqui é que o roteamento resolveu (não 404).
    canonical = client.get(f"/api/v1/clients/{fake_id}/pending-items")
    assert canonical.status_code != 404

    # Alias legado também deve continuar funcionando (mesmo handler).
    legacy = client.get(f"/api/clients/{fake_id}/pending-items")
    assert legacy.status_code != 404
