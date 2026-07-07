from app.core.auth_middleware import _is_publica


def test_public_exact_paths_are_allowed():
    assert _is_publica("/api/auth/login") is True
    assert _is_publica("/api/auth/refresh") is True
    assert _is_publica("/api/health") is True
    assert _is_publica("/api/health/ready") is True


def test_public_path_matching_rejects_textual_prefix_smuggling():
    assert _is_publica("/api/auth/login-extra") is False
    assert _is_publica("/api/auth/refresh-token") is False
    assert _is_publica("/api/openapi.json-extra") is False


def test_public_subtree_does_not_allow_path_traversal_to_protected_route():
    assert _is_publica("/api/rag/knowledge-base/documentos") is True
    assert _is_publica("/api/rag/knowledge-base/../users") is False
