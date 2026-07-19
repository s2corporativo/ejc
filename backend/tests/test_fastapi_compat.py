from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.fastapi_compat import install_fastapi_route_introspection
from app.core.route_registry import build_route_manifest


def _gate() -> None:
    return None


def test_bootstrap_expande_rotas_lazy_sem_quebrar_runtime_ou_openapi() -> None:
    # Idempotência: o bootstrap de app.core já instala o adaptador, e uma chamada
    # repetida não deve substituir estado nem gerar efeitos colaterais.
    install_fastapi_route_introspection()
    install_fastapi_route_introspection()

    app = FastAPI(title="compat-test", version="1")
    router = APIRouter(prefix="/demo")

    @router.get("/{item_id}", dependencies=[Depends(_gate)], tags=["demo"])
    async def detalhe(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    app.include_router(router, prefix="/api")

    effective = next(
        route for route in app.routes if route.path == "/api/demo/{item_id}"
    )
    assert effective.methods == {"GET"}
    assert effective.dependencies
    assert effective.tags == ["demo"]

    response = TestClient(app).get("/api/demo/123")
    assert response.status_code == 200
    assert response.json() == {"item_id": "123"}
    assert "/api/demo/{item_id}" in app.openapi()["paths"]

    manifest = build_route_manifest(app)
    assert any(
        item["method"] == "GET" and item["path"] == "/api/demo/{item_id}"
        for item in manifest["routes"]
    )
