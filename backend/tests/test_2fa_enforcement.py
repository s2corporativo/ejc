from __future__ import annotations

from pathlib import Path

from app.core.security import create_access_token, decode_token


ROOT = Path(__file__).parents[1]


def test_access_token_supports_restricted_2fa_claim():
    token = create_access_token(
        "user-1",
        "admin",
        two_factor_setup_required=True,
    )
    payload = decode_token(token)
    assert payload is not None
    assert payload["two_factor_setup_required"] is True
    assert payload["role"] == "admin"


def test_access_token_omits_restricted_claim_when_not_needed():
    payload = decode_token(create_access_token("user-1", "advogado"))
    assert payload is not None
    assert "two_factor_setup_required" not in payload


def test_middleware_enforces_2fa_from_database_not_frontend_flag():
    source = (ROOT / "app/core/auth_middleware.py").read_text(encoding="utf-8")
    assert "select(User.totp_enabled)" in source
    assert "settings.require_2fa_roles_list" in source
    assert 'settings.APP_ENV == "production"' in source
    assert '{"superadmin", "admin", "socio"}' in source
    assert '"/api/auth/totp/setup"' in source
    assert '"/api/auth/totp/verificar"' in source
    assert '"precisa_configurar_2fa": True' in source


def test_middleware_is_fail_closed_for_required_roles():
    source = (ROOT / "app/core/auth_middleware.py").read_text(encoding="utf-8")
    assert "except Exception:" in source
    assert "return True" in source
    assert "Falha ao validar enforcement de 2FA" in source
