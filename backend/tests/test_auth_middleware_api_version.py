from __future__ import annotations

import pytest

from app.core.auth_middleware import _api_path_interno, _is_publica


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/v1/auth/login", "/api/auth/login"),
        ("/api/v1/health/ready", "/api/health/ready"),
        ("/api/v1/data-rooms/acesso/token", "/api/data-rooms/acesso/token"),
        ("/api/cases", "/api/cases"),
        ("/assets/app.js", "/assets/app.js"),
    ],
)
def test_api_path_interno_normaliza_prefixo_versionado(path: str, expected: str):
    assert _api_path_interno(path) == expected


@pytest.mark.parametrize(
    "path",
    [
        "/api/auth/login",
        "/api/v1/auth/login",
        "/api/health/ready",
        "/api/v1/health/ready",
        "/api/data-rooms/acesso/token-seguro",
        "/api/v1/data-rooms/acesso/token-seguro",
        "/api/rag/knowledge-base/status",
        "/api/v1/rag/knowledge-base/status",
    ],
)
def test_public_paths_are_equivalent_across_api_versions(path: str):
    assert _is_publica(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "/api/cases",
        "/api/v1/cases",
        "/api/auth/login-extra",
        "/api/v1/auth/login-extra",
        "/api/data-rooms/admin",
        "/api/v1/data-rooms/admin",
    ],
)
def test_protected_paths_remain_protected_across_api_versions(path: str):
    assert _is_publica(path) is False


def test_path_traversal_does_not_inherit_public_prefix():
    assert _is_publica("/api/v1/rag/knowledge-base/../cases") is False
