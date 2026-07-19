from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth_middleware import AuthMiddleware
from app.core.security import create_access_token, decode_token


def test_claim_de_configuracao_2fa_tem_prazo_curto():
    token = create_access_token(
        "u1",
        "admin",
        two_factor_setup_required=True,
        expires_minutes=15,
    )
    payload = decode_token(token)
    assert payload is not None
    assert payload["two_factor_setup_required"] is True
    assert payload["exp"] - payload["iat"] <= 901


def test_claim_de_configuracao_2fa_bloqueia_rotas_de_negocio():
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.post("/api/auth/totp/setup")
    async def setup():
        return {"ok": True}

    @app.post("/api/auth/totp/verificar")
    async def verificar():
        return {"ok": True}

    @app.post("/api/auth/logout")
    async def logout():
        return {"ok": True}

    @app.get("/api/users/me")
    async def me():
        return {"ok": True}

    token = create_access_token(
        "u1",
        "admin",
        two_factor_setup_required=True,
        expires_minutes=15,
    )
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(app)

    assert client.post("/api/auth/totp/setup", headers=headers).status_code == 200
    assert client.post("/api/auth/totp/verificar", headers=headers).status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 200

    response = client.get("/api/users/me", headers=headers)
    assert response.status_code == 403
    assert response.json()["precisa_configurar_2fa"] is True
