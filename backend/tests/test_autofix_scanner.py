from types import SimpleNamespace

from app.services.autofix_scanner import (
    EXPECTED_MODULES,
    _coletar_rotas_api,
    _detectar_colisoes,
    _normalizar_api_path,
    _normalizar_module_key,
    _rota_cobre_prefixo,
)


def test_normalizar_module_key():
    assert _normalizar_module_key(" /Clientes/ ") == "clientes"


def test_expected_modules_uses_canonical_registry():
    keys = {module["module_key"] for module in EXPECTED_MODULES}
    assert "documentos" in keys
    assert "clientes" in keys
    assert "casos" in keys
    assert len(keys) == len(EXPECTED_MODULES)


def test_normalizar_api_version_alias():
    assert _normalizar_api_path("/api/v1/cases/") == "/api/cases"
    assert _normalizar_api_path("/api/health/") == "/api/health"


def test_coletar_rotas_api_ignora_rotas_nao_api():
    app = SimpleNamespace(
        routes=[
            SimpleNamespace(path="/", methods={"GET"}, name="home"),
            SimpleNamespace(
                path="/api/health",
                methods={"GET", "HEAD"},
                name="health",
            ),
        ]
    )
    rotas = _coletar_rotas_api(app)
    assert rotas == [
        {
            "path": "/api/health",
            "normalized_path": "/api/health",
            "methods": ["GET"],
            "name": "health",
        }
    ]


def test_catalog_prefix_accepts_parameterized_and_versioned_routes():
    assert _rota_cobre_prefixo(
        "/api/v1/cases/{case_id}/timeline",
        "/api/cases/{case_id}/timeline",
    )
    assert _rota_cobre_prefixo("/api/clients/abc", "/api/clients")
    assert not _rota_cobre_prefixo("/api/clientes", "/api/clients")


def test_detectar_colisoes_by_method_and_normalized_path():
    collisions = _detectar_colisoes(
        [
            {
                "normalized_path": "/api/cases",
                "methods": ["GET"],
                "name": "legacy",
            },
            {
                "normalized_path": "/api/cases",
                "methods": ["GET"],
                "name": "canonical",
            },
            {
                "normalized_path": "/api/cases",
                "methods": ["POST"],
                "name": "create",
            },
        ]
    )
    assert collisions == [
        {
            "method": "GET",
            "path": "/api/cases",
            "handlers": ["legacy", "canonical"],
        }
    ]
