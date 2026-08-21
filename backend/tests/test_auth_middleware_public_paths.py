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


def test_barras_iniciais_duplicadas_nao_escapam_do_gate_de_autenticacao():
    """`//api/...` não pode ser tratado como rota pública.

    `posixpath.normpath` preserva duas barras iniciais por definição POSIX; sem
    colapsá-las o path não casa `startswith("/api/")` e `_is_publica` liberaria
    a requisição sem JWT. Regressão de fail-open (a proteção efetiva não pode
    depender do roteador devolver 404 nem do `merge_slashes` do nginx).
    """
    assert _is_publica("//api/casos") is False
    assert _is_publica("///api/casos") is False
    assert _is_publica("//api/v1/casos") is False
    assert _is_publica("//api/clients") is False
    # Rota pública continua pública mesmo com barras duplicadas.
    assert _is_publica("//api/auth/login") is True
    # Fora de /api segue liberado (assets, SPA) — comportamento preservado.
    assert _is_publica("/static/app.js") is True
