from app.core.auth_middleware import _is_publica, _path_casa_prefixo_publico


def test_rota_sem_barra_final_nao_aceita_prefixo_textual_parcial():
    prefixo = "/api/auth/login"

    assert _path_casa_prefixo_publico("/api/auth/login", prefixo)
    assert _path_casa_prefixo_publico("/api/auth/login/mfa", prefixo)
    assert not _path_casa_prefixo_publico("/api/auth/login-extra", prefixo)


def test_rota_com_barra_final_aceita_apenas_subarvore_deliberada():
    prefixo = "/api/portal/"

    assert _path_casa_prefixo_publico("/api/portal/dashboard", prefixo)
    assert not _path_casa_prefixo_publico("/api/portal-admin/dashboard", prefixo)


def test_is_publica_normaliza_path_e_bloqueia_colisao_textual():
    assert _is_publica("/api/auth/login")
    assert not _is_publica("/api/auth/login-extra")
    assert not _is_publica("/api/rag/knowledge-base/../cases")
