"""Regressão do kill switch temporário de 2FA."""

from app.core.config import Settings
from app.routers import auth


def test_2fa_desativado_por_default():
    cfg = Settings(_env_file=None)
    assert cfg.TWO_FACTOR_AUTH_ENABLED is False
    assert cfg.require_2fa_roles_list == []


def test_papel_nao_exige_2fa_quando_kill_switch_desligado(monkeypatch):
    cfg = Settings(
        _env_file=None,
        TWO_FACTOR_AUTH_ENABLED=False,
        REQUIRE_2FA_ROLES="superadmin,admin,socio",
    )
    monkeypatch.setattr(auth, "settings", cfg)
    assert auth._papel_exige_2fa("superadmin") is False


def test_reativacao_preserva_politica_por_papel(monkeypatch):
    cfg = Settings(
        _env_file=None,
        TWO_FACTOR_AUTH_ENABLED=True,
        REQUIRE_2FA_ROLES="superadmin,socio",
    )
    monkeypatch.setattr(auth, "settings", cfg)
    assert auth._papel_exige_2fa("superadmin") is True
    assert auth._papel_exige_2fa("advogado") is False


def test_middleware_nao_bloqueia_setup_2fa_quando_kill_switch_off(monkeypatch):
    """Com o kill switch OFF, o gate de setup-2FA do middleware não barra rotas
    de negócio, mesmo que o token ainda traga o claim two_factor_setup_required
    (emitido antes do deploy)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core import auth_middleware
    from app.core.auth_middleware import AuthMiddleware
    from app.core.security import create_access_token

    monkeypatch.setattr(auth_middleware.settings, "TWO_FACTOR_AUTH_ENABLED", False)

    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/api/users/me")
    async def me():
        return {"ok": True}

    token = create_access_token(
        "u1", "admin", two_factor_setup_required=True, expires_minutes=15
    )
    client = TestClient(app)
    r = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
